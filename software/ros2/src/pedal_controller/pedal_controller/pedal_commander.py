#!/usr/bin/env python3
"""
pedal_commander.py

ROS 2 service CLIENT for the ESU-TAP micro-ROS node.

VERSION-AGNOSTIC: works with v1, v2, and v3 boards. On startup it discovers
which activation services the board actually advertises and only enables those
channels:

    /esu/cut       (all versions)
    /esu/coag      (all versions)
    /esu/bipolar   (v2, v3)
    /esu/ligasure  (v3)

Each is a std_srvs/SetBool: data=True -> channel ON, data=False -> channel OFF.
Activation is a confirmed request/response, so we know the ESP32 acknowledged
each command.

SAFETY: an acknowledgement does not confirm contact closure or RF delivery.
This client does not implement an independent emergency stop. If it dies after
an ON while the agent stays alive, the firmware command can persist. Use a
disconnected dummy-contact fixture for testing; see
docs/SAFETY_AND_VALIDATION.md.

Modes:
  interactive : keyboard-driven (a key toggles a channel on/off)
  pulse       : call ON, wait pulse_ms, call OFF (single shot)
  script      : run a list of timed (delay, action) calls

Run:
  ros2 run pedal_controller pedal_commander
  ros2 run pedal_controller pedal_commander --ros-args -p mode:=pulse -p pulse_ms:=500 -p channel:=bipolar
"""

import threading
import time

import rclpy
from rclpy.node import Node
from std_srvs.srv import SetBool


# All channels this commander knows how to drive, and their service names.
ALL_CHANNELS = {
    'cut':      '/esu/cut',
    'coag':     '/esu/coag',
    'bipolar':  '/esu/bipolar',
    'ligasure': '/esu/ligasure',
}

# Single-key shortcuts for interactive mode. 'c' is cut; coag uses 'g' since
# 'c' is taken; bipolar 'b'; ligasure 'l'.
CHANNEL_KEYS = {'c': 'cut', 'g': 'coag', 'b': 'bipolar', 'l': 'ligasure'}


class PedalCommander(Node):
    def __init__(self):
        super().__init__('pedal_commander')

        # -- Parameters --
        self.declare_parameter('mode', 'interactive')   # interactive | pulse | script
        self.declare_parameter('pulse_ms', 300)
        self.declare_parameter('channel', 'cut')         # default channel
        self.declare_parameter('wait_timeout_s', 2.0)    # service-call timeout
        # How long to wait for each service to appear before deciding the board
        # doesn't have that channel.
        self.declare_parameter('discover_timeout_s', 3.0)

        self._mode     = self.get_parameter('mode').get_parameter_value().string_value
        self._pulse_ms = self.get_parameter('pulse_ms').get_parameter_value().integer_value
        self._channel  = self.get_parameter('channel').get_parameter_value().string_value.strip().lower()
        self._timeout  = float(self.get_parameter('wait_timeout_s').get_parameter_value().double_value)
        self._discover = float(self.get_parameter('discover_timeout_s').get_parameter_value().double_value)

        # -- Discover which channels this board actually offers --
        # cut and coag are required (present on every version). The others are
        # optional; a board that doesn't advertise them is simply an older rev.
        self._clients = {}
        self.get_logger().info('Discovering ESU-TAP services...')
        for ch, srv in ALL_CHANNELS.items():
            cli = self.create_client(SetBool, srv)
            if cli.wait_for_service(timeout_sec=self._discover):
                self._clients[ch] = cli
                self.get_logger().info(f'  found {srv}')
            else:
                # Not on this board. Required channels missing is an error.
                if ch in ('cut', 'coag'):
                    self.get_logger().error(
                        f'Required service {srv} not found. Is the agent running '
                        'and the board flashed?')
                    raise SystemExit(2)
                self.get_logger().info(f'  {srv} not present (older board rev)')

        board = {2: 'v1', 3: 'v2', 4: 'v3'}.get(len(self._clients), f'{len(self._clients)}-channel')
        self.get_logger().info(
            f'Connected to {board} board. Channels: {sorted(self._clients)}')

        # Fall back the default channel if the requested one isn't available.
        if self._channel not in self._clients:
            self.get_logger().warn(
                f'Channel [{self._channel}] not available on this board; '
                'defaulting to [cut].')
            self._channel = 'cut'

        # -- Launch mode --
        if self._mode == 'interactive':
            threading.Thread(target=self._interactive_loop, daemon=True).start()
        elif self._mode == 'pulse':
            self.create_timer(1.0, self._pulse_once)
        elif self._mode == 'script':
            self._script = [
                (1.0, 'press'), (0.5, 'release'),
                (2.0, 'press'), (0.5, 'release'),
                (1.5, 'press'), (0.5, 'release'),
            ]
            threading.Thread(target=self._run_script, daemon=True).start()
        else:
            self.get_logger().error(f'Unknown mode: {self._mode}')
            raise SystemExit(2)

    # -- Service call helper --
    def _call(self, channel: str, activate: bool):
        """Call the SetBool service for a channel and log the acknowledgement."""
        client = self._clients.get(channel)
        if client is None:
            self.get_logger().warn(f'{channel} not available on this board.')
            return False

        req = SetBool.Request()
        req.data = activate

        future = client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=self._timeout)

        if future.done() and future.result() is not None:
            res = future.result()
            state = 'ON' if activate else 'OFF'
            ack = 'ok' if res.success else 'FAILED'
            self.get_logger().info(f'{channel.upper()} {state} -> {ack} ({res.message})')
            return res.success
        else:
            self.get_logger().error(
                f'{channel.upper()} {"ON" if activate else "OFF"} -> no response (timeout)')
            return False

    def press(self):
        self._call(self._channel, True)

    def release(self):
        self._call(self._channel, False)

    # -- Interactive mode --
    def _interactive_loop(self):
        # Independent on/off state per available channel.
        state = {ch: False for ch in self._clients}

        # Only show keys for channels this board has.
        active_keys = {k: ch for k, ch in CHANNEL_KEYS.items() if ch in self._clients}

        def show_help():
            print('\n=== Pedal Commander (interactive, service client) ===')
            for k, ch in active_keys.items():
                print(f'  {k}  ENTER  -> toggle {ch.upper()}')
            print('  x  ENTER  -> all OFF (safety)')
            print('  s  ENTER  -> show current state')
            print('  h  ENTER  -> help')
            print('  Ctrl+C    -> quit (deactivates everything)\n')
            print(f'  Tip: bare ENTER toggles the default channel ({self._channel}).\n')

        def toggle(channel):
            new = not state[channel]
            if self._call(channel, new):
                state[channel] = new

        def report():
            print('   state: ' + '  '.join(
                f'{ch.upper()}={"ON" if state[ch] else "off"}' for ch in self._clients))

        show_help()
        while True:
            raw = input('> ').strip().lower()

            if raw in active_keys:
                toggle(active_keys[raw])
            elif raw in self._clients:            # full channel name typed
                toggle(raw)
            elif raw in ('x', 'off', 'stop'):
                for ch in self._clients:
                    self._call(ch, False)
                    state[ch] = False
            elif raw in ('s', 'state'):
                report()
            elif raw in ('h', 'help', '?'):
                show_help()
            elif raw == '':
                toggle(self._channel)
            else:
                print(f'   unknown: {raw!r}  (h for help)')

    # -- Pulse mode --
    def _pulse_once(self):
        self.press()
        time.sleep(self._pulse_ms / 1000.0)
        self.release()
        self.get_logger().info(f'Pulse complete ({self._pulse_ms} ms) on {self._channel}')
        raise SystemExit

    # -- Script mode --
    def _run_script(self):
        self.get_logger().info(f'Running script ({len(self._script)} steps)...')
        for delay_s, action in self._script:
            time.sleep(delay_s)
            if action == 'press':
                self.press()
            elif action == 'release':
                self.release()
        self.get_logger().info('Script complete.')


def main(args=None):
    rclpy.init(args=args)
    node = PedalCommander()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        try:
            # Safety: deactivate every channel this board has on exit.
            for ch in node._clients:
                node._call(ch, False)
        except Exception:
            pass
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
