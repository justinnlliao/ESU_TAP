#!/usr/bin/env python3
"""
system_test.py

Interactive full-system acceptance test for the ESU-TAP interposer.

This drives the REAL /esu/cut and /esu/coag services and verifies the entire
control + telemetry chain end to end:

    command  ->  ESP32 service callback  ->  relay closes generator contact
             ->  timer publishes /esu/activation_state  ->  this node observes it

It also subscribes to /esu/activation_state itself, so it can independently
confirm that each command produced the expected published state with the
expected source attribution -- rather than trusting that the relay clicked.

It is INTERACTIVE by design: it pauses before every step so the operator
(you) can watch the board, listen for the relay, and confirm the generator's
behaviour before proceeding. Nothing is automated that could energise the
generator without a human in the loop.

-----------------------------------------------------------------------------
SAFETY / SCOPE
-----------------------------------------------------------------------------
This test was written for the following configuration:
  - DRE ASG-300 connected
  - Active circuit OPEN (no electrode, no load)
  - Operator triggering each step

Recommended: run the FIRST full pass with generator RF output OFF (or disabled
/ at minimum). The purpose of this test is to validate control and logging, not
to deliver energy. Energise only after the plumbing is proven.

With output enabled and an open circuit, the ASG-300 is expected to ALARM on
activation (no return path). That alarm confirms the relay closed the
generator-side contact -- it is a datapoint, not a fault.

This script never enables generator output. It only opens/closes the
interposer relays, exactly as the robot would.

-----------------------------------------------------------------------------
USAGE
-----------------------------------------------------------------------------
Prereqs, in separate terminals:
  1. micro-ROS agent running, ESP32 flashed and connected (LEDs off = ready)
  2. (optional but recommended) pedal_logger running, to capture the CSV
  3. this node:  ros2 run pedal_controller system_test

The logger and this node both subscribe to /esu/activation_state, so you can
cross-check the live console here against the CSV afterwards.
"""

import sys
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from std_srvs.srv import SetBool
from std_msgs.msg import Int32MultiArray


# Source codes, mirroring SRC_* in the firmware.
SRC_SURGEON = 0
SRC_COMPUTER = 1
SRC_BASELINE = 2
SRC_NAME = {SRC_SURGEON: 'surgeon', SRC_COMPUTER: 'computer', SRC_BASELINE: 'baseline'}

# How long to wait for a published state to reflect a command before failing.
# The firmware timer runs every 10 ms; 1.0 s is generous and covers transport.
STATE_TIMEOUT_S = 1.0


class SystemTest(Node):
    def __init__(self):
        super().__init__('system_test')
        cb = ReentrantCallbackGroup()

        self.cut_cli = self.create_client(SetBool, '/esu/cut', callback_group=cb)
        self.coag_cli = self.create_client(SetBool, '/esu/coag', callback_group=cb)

        # Latest observed [cut, coag, source], guarded by a lock because the
        # subscription runs in a different executor thread than the test flow.
        self._lock = threading.Lock()
        self._last = None            # (cut, coag, source) or None
        self._event = threading.Event()   # set whenever a new message arrives

        self.create_subscription(
            Int32MultiArray, '/esu/activation_state',
            self._on_state, 10, callback_group=cb)

        # Running tally.
        self.passed = 0
        self.failed = 0
        self.failures = []           # list of human-readable failure strings

    # ------------------------------------------------------------------ obs
    def _on_state(self, msg: Int32MultiArray):
        if len(msg.data) < 3:
            return
        with self._lock:
            self._last = (int(msg.data[0]), int(msg.data[1]), int(msg.data[2]))
        self._event.set()

    def _snapshot(self):
        with self._lock:
            return self._last

    def _wait_for_state(self, want_cut, want_coag, want_source, timeout=STATE_TIMEOUT_S):
        """Block until an observed message matches, or timeout. Returns the
        matching (cut, coag, source) tuple, or None on timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            snap = self._snapshot()
            if snap is not None:
                c, g, s = snap
                if c == want_cut and g == want_coag and s == want_source:
                    return snap
            self._event.clear()
            self._event.wait(timeout=deadline - time.monotonic())
        return None

    # --------------------------------------------------------------- checks
    def _call(self, client, channel, data):
        """Call a SetBool service, return the response or None on failure."""
        req = SetBool.Request()
        req.data = data
        future = client.call_async(req)
        # Spun by the MultiThreadedExecutor in the background thread.
        deadline = time.monotonic() + 3.0
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.01)
        if not future.done():
            return None
        return future.result()

    def _record(self, ok, label, detail=''):
        if ok:
            self.passed += 1
            print(f'   \033[92mPASS\033[0m  {label}')
        else:
            self.failed += 1
            msg = f'{label}' + (f'  ({detail})' if detail else '')
            self.failures.append(msg)
            print(f'   \033[91mFAIL\033[0m  {label}' + (f'  -- {detail}' if detail else ''))

    def _pause(self, prompt='Press ENTER to continue, or Ctrl+C to abort...'):
        try:
            input(f'\n>>> {prompt} ')
        except EOFError:
            raise KeyboardInterrupt

    # ---------------------------------------------------------- step: command
    def command_step(self, title, client, channel, data,
                     want_cut, want_coag, want_source, watch_for):
        """One command + verification step.

        watch_for : short string telling the operator what to physically look
                    for (LED, relay click, generator behaviour).
        """
        print('\n' + '=' * 70)
        print(f'STEP: {title}')
        print('=' * 70)
        print(f'  Command  : /esu/{channel}  data={data}')
        print(f'  Expect   : state -> [cut={want_cut}, coag={want_coag}, '
              f'source={SRC_NAME[want_source]}]')
        print(f'  Watch for: {watch_for}')
        self._pause('Ready? ENTER to send the command...')

        # Clear stale observations so we only accept a message caused by THIS
        # command.
        self._event.clear()
        resp = self._call(client, channel, data)

        # 1. Service responded.
        if resp is None:
            self._record(False, 'service call returned', 'no response within timeout')
            return
        self._record(resp.success is True, 'service returned success=True',
                     f'success={getattr(resp, "success", None)}, '
                     f'message={getattr(resp, "message", None)!r}')

        # 2. Published state reflected the command with correct attribution.
        matched = self._wait_for_state(want_cut, want_coag, want_source)
        if matched is None:
            snap = self._snapshot()
            self._record(
                False, 'observed published state matched command',
                f'wanted [cut={want_cut}, coag={want_coag}, '
                f'source={SRC_NAME[want_source]}], last saw {snap}')
        else:
            self._record(True, 'observed published state matched command')

        # 3. Operator confirmation of physical behaviour.
        ans = input('   Did the hardware do what "Watch for" describes? [y/N] ').strip().lower()
        self._record(ans == 'y', 'operator confirmed physical behaviour',
                     'operator said no' if ans != 'y' else '')

    # ------------------------------------------------------------ step: pedal
    def pedal_step(self, title, channel, watch_for):
        """Operator presses/releases the physical pedal; we verify a surgeon
        edge appears. Purely observational -- no command sent."""
        print('\n' + '=' * 70)
        print(f'STEP: {title}')
        print('=' * 70)
        print(f'  Action   : YOU press the pedal ({channel.upper()} side), then release')
        print(f'  Expect   : source=surgeon edges on {channel}')
        print(f'  Watch for: {watch_for}')

        want = 1 if channel == 'cut' else None
        idx = 0 if channel == 'cut' else 1

        self._pause('Press and HOLD the pedal, then ENTER...')
        held = self._snapshot()
        ok_press = held is not None and held[idx] == 1 and held[2] == SRC_SURGEON
        self._record(ok_press, f'{channel} press observed as surgeon',
                     f'saw {held}')

        self._pause('Now RELEASE the pedal, then ENTER...')
        time.sleep(0.2)
        rel = self._snapshot()
        ok_rel = rel is not None and rel[idx] == 0 and rel[2] == SRC_SURGEON
        self._record(ok_rel, f'{channel} release observed as surgeon',
                     f'saw {rel}')

    # ------------------------------------------------------------------- run
    def run(self):
        print('\n' + '#' * 70)
        print('# ESU-TAP FULL SYSTEM TEST')
        print('#' * 70)
        print('\nConfiguration assumed: ASG-300 connected, active circuit OPEN,')
        print('operator in the loop. Recommended: generator RF output OFF for')
        print('this pass. This script only opens/closes the interposer relays.')

        # Wait for services.
        print('\nWaiting for /esu/cut and /esu/coag ...')
        if not self.cut_cli.wait_for_service(timeout_sec=10.0) or \
           not self.coag_cli.wait_for_service(timeout_sec=10.0):
            print('\033[91mServices not available. Is the agent up and the ESP32 '
                  'flashed + connected (LEDs off)?\033[0m')
            return False

        # Confirm the telemetry path works by ACTIVELY probing it, rather than
        # passively waiting for a message.
        #
        # /esu/activation_state is event-driven: the firmware only publishes on
        # a state CHANGE. An idle board (no pedal, no command) publishes
        # nothing, so a passive "wait for any message" wrongly reports the topic
        # as dead. Instead, send a cut-OFF command -- always safe, opens the
        # relay if it happens to be closed -- and confirm a message comes back.
        # That exercises the full command -> publish -> observe loop before any
        # scored step runs.
        print('Probing telemetry path (sending a safe cut-off command)...')
        self._event.clear()
        probe_resp = self._call(self.cut_cli, 'cut', False)
        if probe_resp is None:
            print('\033[91mProbe command got no service response. The ESP32 '
                  'node is registered but not answering.\033[0m')
            return False
        # The probe may not change state (cut was likely already 0), so accept
        # EITHER a fresh message OR an already-known snapshot as proof of life.
        deadline = time.monotonic() + 3.0
        while self._snapshot() is None and time.monotonic() < deadline:
            self._event.wait(timeout=0.1)
        if self._snapshot() is None:
            print('\033[91mProbe succeeded at the service layer but produced NO '
                  'telemetry. Publishing is broken -- the service callback runs '
                  'but /esu/activation_state never updates.\033[0m')
            print('Next step: instrument rcl_publish return code in the firmware '
                  '(currently swallowed by RCSOFTCHECK).')
            return False
        print(f'Telemetry path verified. Current state: {self._snapshot()}')

        self._pause('Review the safety notes above. ENTER to begin the sequence...')

        # --- Computer-commanded CUT ---
        self.command_step(
            'Computer CUT on', self.cut_cli, 'cut', True,
            want_cut=1, want_coag=0, want_source=SRC_COMPUTER,
            watch_for='RED D4 lights, CUT relay clicks. '
                      'If gen output is ON: expect an open-circuit alarm.')
        self.command_step(
            'Computer CUT off', self.cut_cli, 'cut', False,
            want_cut=0, want_coag=0, want_source=SRC_COMPUTER,
            watch_for='RED D4 off, CUT relay releases, any alarm clears.')

        # --- Computer-commanded COAG ---
        self.command_step(
            'Computer COAG on', self.coag_cli, 'coag', True,
            want_cut=0, want_coag=1, want_source=SRC_COMPUTER,
            watch_for='YELLOW D5 lights, COAG relay clicks.')
        self.command_step(
            'Computer COAG off', self.coag_cli, 'coag', False,
            want_cut=0, want_coag=0, want_source=SRC_COMPUTER,
            watch_for='YELLOW D5 off, COAG relay releases.')

        # --- Surgeon pedal path ---
        print('\n' + '-' * 70)
        print('SURGEON PATH -- these verify the sense side, source=surgeon.')
        print('-' * 70)
        self.pedal_step('Surgeon CUT', 'cut',
                        watch_for='logger prints [surgeon] cut press/release. '
                                  'D4 does NOT light (LED is relay-driven).')
        self.pedal_step('Surgeon COAG', 'coag',
                        watch_for='logger prints [surgeon] coag press/release.')

        # --- Summary ---
        print('\n' + '#' * 70)
        print(f'# RESULT: {self.passed} passed, {self.failed} failed')
        print('#' * 70)
        if self.failures:
            print('\nFailures:')
            for f in self.failures:
                print(f'  - {f}')
            print('\nDo NOT trust collected data until these are resolved.')
        else:
            print('\nAll checks passed. Control + telemetry chain verified.')
        return self.failed == 0


def main(args=None):
    rclpy.init(args=args)
    node = SystemTest()

    # Run the ROS executor in a background thread so input() can block the
    # main thread without freezing subscriptions or service futures.
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()

    ok = False
    try:
        ok = node.run()
    except KeyboardInterrupt:
        print('\n\nAborted by operator.')
    finally:
        # Safety: make sure both relays are commanded OPEN on the way out, so a
        # half-finished test never leaves a relay latched closed.
        try:
            for cli, name in ((node.cut_cli, 'cut'), (node.coag_cli, 'coag')):
                if cli.service_is_ready():
                    req = SetBool.Request()
                    req.data = False
                    cli.call_async(req)
            time.sleep(0.3)
        except Exception:
            pass
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()

    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
