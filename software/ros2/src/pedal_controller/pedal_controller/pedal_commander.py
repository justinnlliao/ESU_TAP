#!/usr/bin/env python3
"""Explicitly armed, leased commands for a disconnected bench fixture."""
import math
import threading
import time
import rclpy
from rclpy.node import Node
from rclpy.executors import SingleThreadedExecutor
from rclpy.signals import SignalHandlerOptions
from pedal_controller.device_client import DeviceClient
from pedal_controller.protocol import CHANNELS, require_channel

CHANNEL_KEYS = dict(zip(('c', 'g', 'b', 'l'), CHANNELS))


class PedalCommander(Node):
    def __init__(self):
        super().__init__('pedal_commander')
        for name, default in (('board_version', 'auto'), ('fixture_confirmed', False),
                              ('mode', 'interactive'), ('pulse_ms', 300), ('channel', 'cut')):
            self.declare_parameter(name, default)
        self._mode = self.get_parameter('mode').value
        self._pulse_ms = self.get_parameter('pulse_ms').value
        self._channel = self.get_parameter('channel').value.strip().lower()
        self.device = DeviceClient(self, self.get_parameter('board_version').value)

    def prepare(self):
        if self.get_parameter('fixture_confirmed').value is not True:
            raise ValueError('Computer-control tool requires fixture_confirmed:=true '
                             'for a disconnected fixture or isolated mock')
        if self._mode not in ('interactive', 'pulse', 'script'):
            raise ValueError('mode must be interactive, pulse, or script')
        if not math.isfinite(self._pulse_ms) or self._pulse_ms <= 0:
            raise ValueError('pulse_ms must be positive and finite')
        require_channel(self._channel, CHANNELS)
        self.device.prepare()
        require_channel(self._channel, self.device.channels)

    def _call(self, channel, on):
        # Read the arm state BEFORE the call: a lost acknowledgement disarms the
        # session, so checking afterwards would misreport a sent ON as unsent.
        was_armed = self.device.session.armed
        ok = self.device.session.command(channel, on)
        label = f'{channel} {"on" if on else "off"}'   # e.g. "cut on"
        if ok:
            self.get_logger().info(label)
        elif on and not was_armed:
            self.get_logger().error(f'{label}: NOT sent (not armed; type arm)')
        else:
            self.get_logger().error(f'{label}: delivery unconfirmed; output state unknown '
                                    '(computer disarmed; verify the fixture)')
        return ok

    def _pulse_once(self):
        deadline = time.monotonic() + self._pulse_ms / 1000.0
        on_ok = off_ok = False
        try:
            on_ok = self._call(self._channel, True)
            if on_ok:
                time.sleep(max(0.0, deadline - time.monotonic()))
        finally:
            off_ok = self._call(self._channel, False)
        return on_ok and off_ok

    def run(self):
        if self._mode != 'interactive':
            if not self.device.arm():
                raise RuntimeError('Arm rejected: release pedals and inspect connection')
            for _ in range(3 if self._mode == 'script' else 1):
                if not self._pulse_once():
                    return False
                if self._mode == 'script':
                    time.sleep(1)
            return True
        print('Computer DISARMED. Release pedals; type arm deliberately before ON.')
        print('c=cut, g=coag, b=bipolar, l=ligasure; x=OFF+disarm; s=status; q=quit.')
        while True:
            raw = input('> ').strip().lower()
            if not raw:
                continue  # A blank Enter must never activate a channel.
            session = self.device.session
            if raw in ('q', 'quit'):
                return True
            if raw == 'arm':
                print('ARMED' if self.device.arm() else 'Arm rejected; no ON sent.')
            elif raw in ('x', 'off', 'stop'):
                print('OFF/disarm acknowledged' if session.all_off() else 'OFF NOT confirmed')
            elif raw in ('s', 'state'):
                with session.lock:
                    print(dict(armed=session.armed, commanded=sorted(session.desired),
                               fault=session.fault))
                print('These are command acknowledgements, not physical contact/RF feedback.')
            else:
                ch = CHANNEL_KEYS.get(raw, raw)
                if ch not in self.device.channels:
                    print('Unavailable channel; no command sent.')
                    continue
                with session.lock:
                    target = ch not in session.desired
                self._call(ch, target)


def main(args=None):
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    node = PedalCommander()
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    worker = threading.Thread(target=executor.spin, daemon=True)
    worker.start()
    ok = False
    try:
        node.prepare()
        ok = node.run()
    except (KeyboardInterrupt, EOFError):
        print('Stopping; best-effort OFF/disarm.')
    except Exception as exc:
        node.get_logger().error(str(exc))
    finally:
        try:
            if not node.device.close():
                ok = False
                node.get_logger().error('OFF not confirmed; verify fixture independently.')
        finally:
            executor.shutdown()
            worker.join(timeout=2)
            node.destroy_node()
            rclpy.shutdown()
    raise SystemExit(0 if ok else 1)
