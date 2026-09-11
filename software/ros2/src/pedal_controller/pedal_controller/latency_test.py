#!/usr/bin/env python3
"""
latency_test.py

Automated latency benchmark for the ESU-TAP control path.

REVIEW NOTE (2026-09-11): legacy software tool, not current v2/v3 acceptance.
Verify payload compatibility before interpreting results. Use a disconnected
low-voltage dummy contact fixture; see docs/SAFETY_AND_VALIDATION.md.

Measures TWO distinct latencies over many iterations and reports statistics
for each separately:

  1. ROUND-TRIP latency
       service call sent  ->  SetBool response received
     Pure request/response time through: PC rclpy -> serial -> ESP32 rclc
     executor -> service callback -> response -> back. Does NOT include the
     state publish.

  2. COMMAND latency
       service call sent  ->  matching /esu/activation_state observed
     The operationally meaningful number: how long from "robot issues command"
     to "the rest of the system can see the new state".

-----------------------------------------------------------------------------
IMPORTANT -- how to read these numbers
-----------------------------------------------------------------------------
COMMAND latency has a HARD FLOOR set by the firmware, not by transport speed.

The firmware only publishes /esu/activation_state from timer_callback, which
runs every TIMER_PERIOD_MS (10 ms). A command applied just after a tick waits
almost a full period before it is published. So across random command timing:

  - expect command latency to average roughly (round_trip + TIMER_PERIOD_MS/2)
  - expect up to ~TIMER_PERIOD_MS of jitter (the spread between min and max)

That extra ~5 ms mean and ~10 ms spread is STRUCTURAL. It is the polling
period, not a slow board. If you need to reduce it, the fix is in the firmware
(publish directly from the service callback, or shorten the timer period), not
here.

This benchmark also does NOT measure physical relay closure or generator
response -- both timestamps are taken in the ROS graph. Measuring a generator
contact alone does not establish RF delivery timing.

-----------------------------------------------------------------------------
USAGE
-----------------------------------------------------------------------------
Prereqs: micro-ROS agent running, ESP32 flashed + connected.
A pedal_logger may be running or not; it does not affect the measurement.

  ros2 run pedal_controller latency_test
  ros2 run pedal_controller latency_test --ros-args -p iterations:=200
  ros2 run pedal_controller latency_test --ros-args -p channel:=coag -p settle_ms:=80

The benchmark toggles the chosen channel ON then OFF each iteration, so it
requests OFF between measurements; interruption or a failed OFF request can
leave a command active. It uses the ON edge for timing. Keep the generator
disconnected: this issues repeated activation commands, not passive measurements.
"""

import statistics
import sys
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from std_srvs.srv import SetBool
from std_msgs.msg import Int32MultiArray


SRC_COMPUTER = 1

# Must match TIMER period in the firmware. Used only to contextualise results.
TIMER_PERIOD_MS = 10.0


class LatencyTest(Node):
    def __init__(self):
        super().__init__('latency_test')

        self.declare_parameter('iterations', 100)
        self.declare_parameter('channel', 'cut')        # 'cut' or 'coag'
        self.declare_parameter('settle_ms', 60)         # gap between iterations
        self.declare_parameter('warmup', 5)             # discarded initial runs

        self.iterations = int(self.get_parameter('iterations').value)
        self.channel = str(self.get_parameter('channel').value)
        self.settle_s = float(self.get_parameter('settle_ms').value) / 1000.0
        self.warmup = int(self.get_parameter('warmup').value)

        if self.channel not in ('cut', 'coag'):
            raise ValueError(f"channel must be 'cut' or 'coag', got {self.channel!r}")
        self.idx = 0 if self.channel == 'cut' else 1

        cb = ReentrantCallbackGroup()
        self.cli = self.create_client(
            SetBool, f'/esu/{self.channel}', callback_group=cb)

        self._lock = threading.Lock()
        self._last = None
        # Event fires on every new observation, letting the test thread wake
        # the instant a matching state arrives instead of polling.
        self._event = threading.Event()

        self.create_subscription(
            Int32MultiArray, '/esu/activation_state',
            self._on_state, 10, callback_group=cb)

    def _on_state(self, msg):
        if len(msg.data) < 3:
            return
        with self._lock:
            self._last = (int(msg.data[0]), int(msg.data[1]), int(msg.data[2]))
        self._event.set()

    def _snapshot(self):
        with self._lock:
            return self._last

    def _wait_channel_state(self, want_val, timeout=1.0):
        """Wait until the chosen channel reads want_val in an observed message.
        Returns the monotonic time of detection, or None on timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            snap = self._snapshot()
            if snap is not None and snap[self.idx] == want_val:
                return time.monotonic()
            self._event.clear()
            self._event.wait(timeout=max(0.0, deadline - time.monotonic()))
        return None

    def _one_iteration(self):
        """Perform one ON measurement, then turn the channel back OFF.

        Returns (round_trip_s, command_s) or None if the iteration failed.
        Timing note: t0 is captured immediately before call_async and is the
        single reference point for BOTH measurements, so they are directly
        comparable.
        """
        # Ensure we start from OFF so the ON edge is a real transition.
        self._set(False)
        if self._wait_channel_state(0, timeout=1.0) is None:
            return None
        self._event.clear()

        # --- timed ON command ---
        req = SetBool.Request()
        req.data = True
        t0 = time.monotonic()
        future = self.cli.call_async(req)

        # Round-trip: wait for the service response.
        rt_deadline = t0 + 3.0
        while not future.done() and time.monotonic() < rt_deadline:
            time.sleep(0.0005)
        if not future.done() or future.result() is None:
            self._set(False)
            return None
        t_response = time.monotonic()

        # Command: wait for the observed published state to show channel ON.
        t_state = self._wait_channel_state(1, timeout=1.0)
        if t_state is None:
            self._set(False)
            return None

        # Return channel to OFF for the next iteration.
        self._set(False)
        self._wait_channel_state(0, timeout=1.0)

        return (t_response - t0, t_state - t0)

    def _set(self, val):
        req = SetBool.Request()
        req.data = val
        fut = self.cli.call_async(req)
        deadline = time.monotonic() + 2.0
        while not fut.done() and time.monotonic() < deadline:
            time.sleep(0.0005)

    def run(self):
        print('\n' + '#' * 70)
        print('# ESU-TAP LATENCY BENCHMARK')
        print('#' * 70)
        print(f'  channel     : {self.channel}')
        print(f'  iterations  : {self.iterations}  (+{self.warmup} warm-up, discarded)')
        print(f'  settle gap  : {self.settle_s * 1000:.0f} ms')
        print(f'  firmware timer period: {TIMER_PERIOD_MS:.0f} ms '
              '(sets the command-latency floor)')

        if not self.cli.wait_for_service(timeout_sec=10.0):
            print('\033[91mService not available. Agent up? ESP32 connected?\033[0m')
            return False

        print('\nRunning... (generator RF output should be OFF for this)\n')

        round_trips = []
        commands = []
        fails = 0

        total = self.warmup + self.iterations
        for i in range(total):
            result = self._one_iteration()
            time.sleep(self.settle_s)

            if result is None:
                fails += 1
                if i >= self.warmup:
                    print(f'  iter {i - self.warmup + 1:4d}: \033[91mFAILED\033[0m')
                continue
            rt_ms = result[0] * 1000.0
            cmd_ms = result[1] * 1000.0

            if i < self.warmup:
                continue  # discard warm-up

            round_trips.append(rt_ms)
            commands.append(cmd_ms)
            n = i - self.warmup + 1
            if n <= 10 or n % 25 == 0:
                print(f'  iter {n:4d}:  round-trip {rt_ms:6.2f} ms   '
                      f'command {cmd_ms:6.2f} ms')

        # Safety: leave the relay open.
        self._set(False)

        if not commands:
            print('\n\033[91mNo successful iterations. Nothing to report.\033[0m')
            return False

        self._report('ROUND-TRIP  (call -> response)', round_trips)
        self._report('COMMAND     (call -> observed state)', commands)

        # The gap between the two means is, in effect, the publish-path cost:
        # executor scheduling + the timer-period wait.
        gap = statistics.mean(commands) - statistics.mean(round_trips)
        print('\n' + '-' * 70)
        print(f'Mean COMMAND - mean ROUND-TRIP = {gap:.2f} ms')
        print(f'  Expected ~{TIMER_PERIOD_MS / 2:.1f} ms from the 10 ms publish '
              'timer alone. Much larger means executor scheduling overhead;')
        print('  much smaller is suspicious (are commands landing on tick boundaries?).')

        if fails:
            print(f'\n\033[93m{fails} iteration(s) failed and were excluded.\033[0m')
        return True

    @staticmethod
    def _report(name, samples):
        s = sorted(samples)
        n = len(s)

        def pct(p):
            if n == 1:
                return s[0]
            k = (n - 1) * p
            f = int(k)
            c = min(f + 1, n - 1)
            return s[f] + (s[c] - s[f]) * (k - f)

        print('\n' + '=' * 70)
        print(f'{name}   (n={n})')
        print('=' * 70)
        print(f'  min     {min(s):7.2f} ms')
        print(f'  mean    {statistics.mean(s):7.2f} ms')
        print(f'  median  {statistics.median(s):7.2f} ms')
        print(f'  p95     {pct(0.95):7.2f} ms')
        print(f'  p99     {pct(0.99):7.2f} ms')
        print(f'  max     {max(s):7.2f} ms')
        if n > 1:
            print(f'  stdev   {statistics.stdev(s):7.2f} ms')


def main(args=None):
    rclpy.init(args=args)
    node = LatencyTest()

    executor = MultiThreadedExecutor()
    executor.add_node(node)
    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()

    ok = False
    try:
        ok = node.run()
    except KeyboardInterrupt:
        print('\n\nAborted.')
    finally:
        try:
            node._set(False)  # never leave a relay latched
            time.sleep(0.2)
        except Exception:
            pass
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()

    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
