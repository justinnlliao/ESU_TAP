#!/usr/bin/env python3
"""Bench command client. Acknowledgement is not physical contact feedback.

An ON can persist if this process dies while the agent remains alive. OFF on
exit is best-effort, not an emergency stop. Use a disconnected dummy fixture.
"""

import math
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.executors import SingleThreadedExecutor
from rclpy.signals import SignalHandlerOptions
from std_srvs.srv import SetBool

from pedal_controller.protocol import CHANNELS, require_channel
from pedal_controller.service_calls import call_service

CHANNEL_KEYS = dict(zip(('c', 'g', 'b', 'l'), CHANNELS))


class PedalCommander(Node):
    def __init__(self):
        super().__init__('pedal_commander')
        for name, default in (('mode', 'interactive'), ('pulse_ms', 300),
                              ('channel', 'cut'), ('wait_timeout_s', 2.0),
                              ('discover_timeout_s', 3.0)):
            self.declare_parameter(name, default)
        self._mode = self.get_parameter('mode').value
        self._pulse_ms = self.get_parameter('pulse_ms').value
        self._channel = self.get_parameter('channel').value.strip().lower()
        self._timeout = float(self.get_parameter('wait_timeout_s').value)
        self._discover = float(self.get_parameter('discover_timeout_s').value)
        self._esu_clients = {}

    def prepare(self):
        """Validate everything before any activation request is sent."""
        if self._mode not in ('interactive', 'pulse', 'script'):
            raise ValueError('mode must be interactive, pulse, or script')
        if any(not math.isfinite(v) or v <= 0
               for v in (self._timeout, self._discover, self._pulse_ms)):
            raise ValueError('Pulse and timeout settings must be finite and positive')
        require_channel(self._channel, CHANNELS)
        for channel in CHANNELS:
            client = self.create_client(SetBool, f'/esu/{channel}')
            if client.wait_for_service(timeout_sec=self._discover):
                self._esu_clients[channel] = client
            else:
                self.destroy_client(client)
        require_channel(self._channel, self._esu_clients)
        for required in ('cut', 'coag'):
            require_channel(required, self._esu_clients)
        self.get_logger().info(f'Available channels: {list(self._esu_clients)}')

    def _call(self, channel, activate, timeout=None):
        require_channel(channel, self._esu_clients)
        request = SetBool.Request()
        request.data = activate
        result = call_service(self._esu_clients[channel], request,
                              self._timeout if timeout is None else timeout)
        message = f'{channel.upper()} {"ON" if activate else "OFF"}: {result.message}'
        if result.success:
            self.get_logger().info(message)
        else:
            self.get_logger().error(message)
        return result.success

    def all_off(self):
        # Do not short-circuit: attempt every channel even if one fails.
        results = [self._call(ch, False) for ch in self._esu_clients]
        return all(results)

    def _pulse_once(self):
        # Deadline starts before ON; waiting for ACK must not add a full service
        # timeout to the requested pulse. This is PC request timing, not a
        # guaranteed contact-closure duration or independent watchdog.
        duration = self._pulse_ms / 1000.0
        deadline = time.monotonic() + duration
        on_ok = False
        off_ok = False
        try:
            on_ok = self._call(self._channel, True, min(self._timeout, duration))
            if on_ok:
                time.sleep(max(0.0, deadline - time.monotonic()))
        finally:
            off_ok = self._call(self._channel, False)
        return on_ok and off_ok

    def _interactive_loop(self):
        # Unknown until acknowledged; never present a local guess as feedback.
        state = dict.fromkeys(self._esu_clients)
        keys = {k: ch for k, ch in CHANNEL_KEYS.items() if ch in state}
        print(f'Keys: {keys}; x=OFF requests; s=last acknowledged commands; Ctrl+C=quit')
        print('Unknown state: first toggle requests OFF. This is not contact feedback.')
        while True:
            raw = input('> ').strip().lower()
            if raw in ('x', 'off', 'stop'):
                for ch in state:
                    state[ch] = False if self._call(ch, False) else None
            elif raw in ('s', 'state'):
                print(state)
            else:
                ch = self._channel if not raw else keys.get(raw, raw)
                if ch not in state:
                    print('Unknown/unavailable channel; no request sent.')
                    continue
                target = state[ch] is False
                if self._call(ch, target):
                    state[ch] = target
                else:
                    state[ch] = None
                    if target:
                        # A failed ON acknowledgement does not prove ON failed.
                        self._call(ch, False)

    def run(self):
        if self._mode == 'interactive':
            self._interactive_loop()
            return True
        if self._mode == 'pulse':
            return self._pulse_once()
        for _ in range(3):
            time.sleep(1.0)
            if not self._pulse_once():
                return False
        return True


def main(args=None):
    # Keep the ROS context alive on Ctrl+C long enough to attempt OFF responses.
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
        print('Stopping; requesting OFF on discovered channels.')
    except Exception as exc:
        node.get_logger().error(str(exc))
    finally:
        try:
            if not node.all_off():
                ok = False
                node.get_logger().error('OFF not confirmed. Verify fixture contacts independently.')
        finally:
            executor.shutdown()
            worker.join(timeout=2.0)
            node.destroy_node()
            rclpy.shutdown()
    raise SystemExit(0 if ok else 1)


if __name__ == '__main__':
    main()
