"""Shared runtime for explicit, disconnected-fixture tests, not acceptance."""

import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.executors import SingleThreadedExecutor
from rclpy.signals import SignalHandlerOptions
from std_msgs.msg import Int32MultiArray
from std_srvs.srv import SetBool

from pedal_controller.protocol import StateHistory, revision_channels
from pedal_controller.service_calls import call_service


class BenchNode(Node):
    def __init__(self, name):
        super().__init__(name)
        self.declare_parameter('board_version', 'v3')
        self.declare_parameter('fixture_confirmed', False)
        self.channels = revision_channels(self.get_parameter('board_version').value)
        self.history = StateHistory(len(self.channels))
        self._esu_clients = {}
        self.create_subscription(Int32MultiArray, '/esu/activation_state', self._on_state, 100)

    def _on_state(self, msg):
        received_at = time.monotonic()
        try:
            self.history.record(msg.data, received_at)
        except ValueError as exc:
            self.get_logger().error(str(exc))

    def prepare(self):
        if self.get_parameter('fixture_confirmed').value is not True:
            raise ValueError('Requires fixture_confirmed:=true and a disconnected dummy fixture '
                             '(or an isolated software mock); no requests sent')
        for ch in self.channels:
            cli = self.create_client(SetBool, f'/esu/{ch}')
            if not cli.wait_for_service(timeout_sec=3.0):
                raise RuntimeError(f'Missing /esu/{ch}; check board_version and firmware')
            self._esu_clients[ch] = cli
        if not self.all_off():
            raise RuntimeError('Initial OFF requests not acknowledged; aborting')

    def set_channel(self, channel, on):
        req = SetBool.Request()
        req.data = on
        return call_service(self._esu_clients[channel], req, 2.0)

    def all_off(self):
        results = [self.set_channel(ch, False).success for ch in self._esu_clients]
        return all(results)

    def transition(self, channel, on, source=1):
        """Require a fresh, correct-width, all-channel telemetry observation."""
        mark = self.history.mark()
        result = self.set_channel(channel, on)
        expected = tuple(int(on and ch == channel) for ch in self.channels)
        observation = self.history.wait(
            lambda item: item.states == expected and item.source == source,
            mark, not_before=result.sent_at) if result.success else None
        if not result.success or observation is None:
            raise RuntimeError(f'{channel} {on}: ACK/telemetry missing or wrong; {result.message}')
        return result, observation


def run_bench(node_type, args=None):
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    node = None
    executor = None
    worker = None
    ok = False
    try:
        node = node_type()
        executor = SingleThreadedExecutor()
        executor.add_node(node)
        worker = threading.Thread(target=executor.spin, daemon=True)
        worker.start()
        node.prepare()
        ok = node.run()
    except (KeyboardInterrupt, EOFError):
        print('Aborted. OFF requests are best-effort; verify fixture contacts.')
    except Exception as exc:
        print(f'Test failed: {exc}')
    finally:
        try:
            if node is not None and not node.all_off():
                print('OFF NOT ACKNOWLEDGED. Physical state unknown.')
                ok = False
        finally:
            if executor is not None:
                executor.shutdown()
            if worker is not None:
                worker.join(timeout=2.0)
            if node is not None:
                node.destroy_node()
            rclpy.shutdown()
    raise SystemExit(0 if ok else 1)
