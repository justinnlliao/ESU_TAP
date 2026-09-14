"""Offline regressions: no ROS graph, serial connection, or hardware commands.

Node classes are loaded with a minimal fake base; this does NOT test rclpy's
executor or transport. Run the separate ROS mock checks before bench deployment.
"""

import ast
from concurrent.futures import Future
import math
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE))
from pedal_controller.protocol import (CHANNELS, StateHistory, parse_state,
                                       require_channel, revision_channels)
from pedal_controller.service_calls import CallResult, call_service


class FakeNode:
    overrides = {}
    available = CHANNELS

    def __init__(self, name):
        self.params = dict(self.overrides)
        self.log = Mock()
        self.requests = []

    @property
    def clients(self):
        return ()

    @property
    def services(self):
        return ()

    def declare_parameter(self, name, default):
        self.params.setdefault(name, default)

    def get_parameter(self, name):
        value = self.params[name]
        return SimpleNamespace(value=value)

    def get_logger(self):
        return self.log

    def create_client(self, kind, name):
        return SimpleNamespace(wait_for_service=lambda **kw: name.split('/')[-1] in self.available)

    def destroy_client(self, client):
        pass

    def create_subscription(self, *args):
        pass

    def create_service(self, *args):
        return args

    def create_timer(self, *args):
        pass

    def create_publisher(self, *args):
        return SimpleNamespace(publish=lambda msg: self.requests.append(tuple(msg.data)))


def load_class(filename, class_name, **extra):
    tree = ast.parse((PACKAGE / 'pedal_controller' / filename).read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    ns = dict(Node=FakeNode, math=math, time=time, CHANNELS=CHANNELS,
              require_channel=require_channel, revision_channels=revision_channels,
              parse_state=parse_state, StateHistory=StateHistory, call_service=call_service,
              Int32MultiArray=SimpleNamespace, SetBool=SimpleNamespace(Request=SimpleNamespace),
              CHANNEL_KEYS=dict(zip(('c', 'g', 'b', 'l'), CHANNELS)))
    ns.update(extra)
    exec(compile(ast.Module(body=[cls], type_ignores=[]), filename, 'exec'), ns)
    return ns[class_name]


class ProtocolTests(unittest.TestCase):
    def test_all_revisions_source_is_last(self):
        for revision, count in (('v1', 2), ('v2', 3), ('v3', 4)):
            self.assertEqual(len(revision_channels(revision)), count)
            states, source = parse_state([1] + [0] * (count - 1) + [1])
            self.assertEqual(source, 1)
            self.assertEqual(len(states), count)

    def test_reject_malformed(self):
        for data in ([], [0, 1], [0] * 6, [2, 0, 1], [0, 0, 3], [0.5, 0, 1]):
            with self.subTest(data=data), self.assertRaises(ValueError):
                parse_state(data)

    def test_no_channel_substitution(self):
        with self.assertRaises(ValueError):
            require_channel('ligasure', revision_channels('v2'))

    def test_no_stale_observation(self):
        history = StateHistory(4)
        history.record([1, 0, 0, 0, 1])
        self.assertIsNone(history.wait(lambda x: True, history.mark(), timeout=0))

    def test_retains_receipt_time_before_response(self):
        history = StateHistory(4)
        mark = history.mark()
        history.record([1, 0, 0, 0, 1], received_at=10.1)
        item = history.wait(lambda x: x.states[0] == 1, mark, timeout=0, not_before=10.0)
        self.assertEqual(item.received_at, 10.1)
        self.assertIsNone(history.wait(lambda x: True, mark, timeout=0, not_before=10.2))

    def test_wrong_revision_rejected(self):
        with self.assertRaises(ValueError):
            StateHistory(4).record([1, 0, 0, 1])


class ServiceTests(unittest.TestCase):
    def test_ack_and_negative_ack(self):
        for success in (True, False):
            future = Future()
            future.set_result(SimpleNamespace(success=success, message='ack'))
            result = call_service(SimpleNamespace(call_async=lambda _: future), object(), .1)
            self.assertEqual(result.success, success)
            self.assertGreaterEqual(result.received_at, result.sent_at)

    def test_timeout_is_unknown(self):
        future = Future()
        result = call_service(SimpleNamespace(call_async=lambda _: future), object(), .001)
        self.assertFalse(result.success)
        self.assertIn('unknown', result.message)

    def test_transport_exception(self):
        client = SimpleNamespace(call_async=Mock(side_effect=RuntimeError('lost')))
        self.assertFalse(call_service(client, object(), .1).success)


class CommanderTests(unittest.TestCase):
    def setUp(self):
        FakeNode.overrides = {}
        FakeNode.available = CHANNELS
        self.kind = load_class('pedal_commander.py', 'PedalCommander')

    def test_missing_ligasure_rejected(self):
        FakeNode.overrides = {'channel': 'ligasure'}
        FakeNode.available = CHANNELS[:3]
        node = self.kind()
        with self.assertRaises(ValueError):
            node.prepare()
        self.assertEqual(node._channel, 'ligasure')

    def test_invalid_configuration(self):
        for overrides in ({'pulse_ms': 0}, {'wait_timeout_s': float('nan')}, {'channel': 'typo'}):
            FakeNode.overrides = overrides
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.kind().prepare()

    def test_all_off_attempts_every_channel(self):
        node = self.kind()
        node._esu_clients = dict.fromkeys(CHANNELS)
        node._call = Mock(side_effect=[False, True, True, True])
        self.assertFalse(node.all_off())
        self.assertEqual(node._call.call_count, 4)

    def test_pulse_off_after_ack_failure(self):
        node = self.kind()
        node._call = Mock(side_effect=[False, True])
        self.assertFalse(node._pulse_once())
        self.assertEqual(node._call.call_args_list[-1].args, ('cut', False))

    def test_pulse_off_after_interruption(self):
        node = self.kind()
        node._call = Mock(side_effect=[KeyboardInterrupt(), True])
        with self.assertRaises(KeyboardInterrupt):
            node._pulse_once()
        self.assertEqual(node._call.call_args_list[-1].args, ('cut', False))

    def test_pulse_deadline_does_not_add_ack_time(self):
        node = self.kind()
        node._pulse_ms = 300
        node._call = Mock(return_value=True)
        with patch.object(time, 'monotonic', side_effect=[10.0, 10.2]), patch.object(time, 'sleep') as sleep:
            self.assertTrue(node._pulse_once())
            self.assertAlmostEqual(sleep.call_args.args[0], .1)


class LoggerTests(unittest.TestCase):
    def setUp(self):
        kind = load_class('pedal_logger.py', 'PedalLogger')
        self.node = kind.__new__(kind)
        self.node._last = None
        self.node._n_channels = None
        self.node.get_logger = Mock(return_value=Mock())
        self.node._emit_edge = Mock()

    def test_first_message_sync_then_ligasure_edge(self):
        self.node._state_callback(SimpleNamespace(data=[0, 0, 0, 0, 2]))
        self.assertEqual(self.node._emit_edge.call_count, 4)
        self.assertTrue(all(c.args[1] == 'sync' for c in self.node._emit_edge.call_args_list))
        self.node._state_callback(SimpleNamespace(data=[0, 0, 0, 1, 1]))
        self.assertEqual(self.node._emit_edge.call_args.args[:3], ('ligasure', 'press', 1))

    def test_schema_change_rejected(self):
        self.node._state_callback(SimpleNamespace(data=[0, 0, 0, 0, 2]))
        self.node._emit_edge.reset_mock()
        self.node._state_callback(SimpleNamespace(data=[1, 0, 1]))
        self.node._emit_edge.assert_not_called()

    def test_reconnect_is_sync_not_release(self):
        self.node._state_callback(SimpleNamespace(data=[1, 0, 0, 0, 1]))
        self.node._emit_edge.reset_mock()
        self.node._state_callback(SimpleNamespace(data=[0, 0, 0, 0, 2]))
        self.assertTrue(all(c.args[1] == 'sync' for c in self.node._emit_edge.call_args_list))


class BenchTests(unittest.TestCase):
    def setUp(self):
        FakeNode.overrides = {}
        FakeNode.available = CHANNELS
        self.bench = load_class('bench_runtime.py', 'BenchNode')

    def test_fixture_confirmation_required(self):
        node = self.bench('test')
        with self.assertRaises(ValueError):
            node.prepare()
        self.assertEqual(node._esu_clients, {})

    def test_transition_checks_computer_source_on_v3(self):
        node = self.bench('test')
        def send(ch, active):
            node.history.record([1, 0, 0, 0, 1], 10.1)
            return CallResult(True, 10.0, 10.2, 'ack')
        node.set_channel = send
        _, observation = node.transition('cut', True)
        self.assertEqual(observation.source, 1)
        self.assertEqual(observation.received_at, 10.1)

    def test_latency_release_attempted_on_on_failure(self):
        kind = load_class('latency_test.py', 'LatencyTest', BenchNode=self.bench)
        node = kind()
        node.transition = Mock(side_effect=[RuntimeError('lost on'), (None, None)])
        with self.assertRaises(RuntimeError):
            node._one_iteration()
        self.assertEqual(node.transition.call_args_list[-1].args, ('cut', False))

    def test_mock_all_revisions_and_or_behavior(self):
        kind = load_class('mock_esu_node.py', 'MockEsuNode')
        for rev in ('v1', 'v2', 'v3'):
            FakeNode.overrides = {'board_version': rev}
            node = kind()
            node._tick()
            self.assertEqual(len(node.requests[-1]), len(revision_channels(rev)) + 1)
            node._callback('cut')(SimpleNamespace(data=True), SimpleNamespace())
            node._tick()
            self.assertEqual(node.requests[-1][0], 1)
            self.assertEqual(node.requests[-1][-1], 1)
            node.sensed['cut'] = 1
            node._callback('cut')(SimpleNamespace(data=False), SimpleNamespace())
            node._tick()
            self.assertEqual(node.effective['cut'], 1)


if __name__ == '__main__':
    unittest.main()
