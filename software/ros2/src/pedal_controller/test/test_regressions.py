"""Offline regressions: no ROS graph, serial connection, or hardware commands.

Node classes are loaded with a minimal fake base; this does NOT test rclpy's
executor or transport. Run the separate ROS mock checks before bench deployment.
"""

import ast
from concurrent.futures import Future
import math
import json
import secrets
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE))
from pedal_controller.protocol import (BAUD, CHANNELS, StateHistory, parse_state,
                                       require_channel, revision_channels)
from pedal_controller.service_calls import CallResult, call_service
from pedal_controller.command_session import CommandSession
from pedal_controller.capabilities import parse_capabilities


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
        return SimpleNamespace(publish=lambda msg: self.requests.append(msg.data))


class FakeDevice:
    def __init__(self, node, expected='auto'):
        self.node = node
        self.channels = FakeNode.available
        self.clients = dict.fromkeys(self.channels)
        self.session = None

    def prepare(self):
        self.session = CommandSession(self.channels, lambda *a: True, lambda *a: True, .1)

    def arm(self):
        return self.session.arm()


def load_class(filename, class_name, **extra):
    tree = ast.parse((PACKAGE / 'pedal_controller' / filename).read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    ns = dict(Node=FakeNode, math=math, time=time, CHANNELS=CHANNELS,
              require_channel=require_channel, revision_channels=revision_channels,
              parse_state=parse_state, StateHistory=StateHistory, call_service=call_service,
              Int32MultiArray=SimpleNamespace, Int32=SimpleNamespace,
              Trigger=SimpleNamespace(Request=SimpleNamespace),
              DeviceClient=FakeDevice, json=json, secrets=secrets,
              parse_capabilities=parse_capabilities, CallResult=CallResult,
              SetBool=SimpleNamespace(Request=SimpleNamespace), BAUD=BAUD,
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
        FakeNode.overrides = {'fixture_confirmed': True}
        FakeNode.available = CHANNELS
        self.kind = load_class('pedal_commander.py', 'PedalCommander')

    def test_missing_ligasure_rejected(self):
        FakeNode.overrides = {'channel': 'ligasure', 'fixture_confirmed': True}
        FakeNode.available = CHANNELS[:3]
        node = self.kind()
        with self.assertRaises(ValueError):
            node.prepare()
        self.assertEqual(node._channel, 'ligasure')

    def test_invalid_configuration(self):
        for overrides in ({'pulse_ms': 0}, {'pulse_ms': float('nan')}, {'channel': 'typo'}):
            FakeNode.overrides = {'fixture_confirmed': True, **overrides}
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.kind().prepare()

    def test_all_off_attempts_every_channel(self):
        send = Mock(side_effect=[False, True, True, True])
        session = CommandSession(CHANNELS, send, lambda _: True, .1)
        self.assertFalse(session.all_off())
        self.assertEqual(send.call_count, 4)

    def test_lost_ack_is_reported_as_unknown_not_unsent(self):
        node = self.kind()
        node.device.prepare()
        node.device.session = CommandSession(CHANNELS, lambda *a: False, lambda *a: True, .1)
        self.assertFalse(node._call('cut', True))                 # not armed yet
        self.assertIn('NOT sent', node.get_logger().error.call_args.args[0])
        node.device.session.armed = True
        self.assertFalse(node._call('cut', True))                 # sent, reply lost
        message = node.get_logger().error.call_args.args[0]
        self.assertIn('delivery unconfirmed; output state unknown', message)
        self.assertNotIn('NOT sent', message)

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
        self.node._n_channels = 4
        self.node.wire_format = 'standard'
        self.node._want_caps = False
        self.node.get_logger = Mock(return_value=Mock())
        self.node._record_metadata = Mock()
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
        self.assertTrue(self.node._want_caps)   # re-check boot ID once, no polling

    def test_sync_is_one_terminal_line(self):
        self.node._state_callback(SimpleNamespace(data=32))
        self.assertTrue(all(c.kwargs.get('quiet') for c in self.node._emit_edge.call_args_list))
        lines = [c.args[0] for c in self.node.get_logger().info.call_args_list]
        self.assertEqual(lines, ['>>> board connected   active: none'])

    def test_malformed_does_not_stop_logging(self):
        self.node._state_callback(SimpleNamespace(data=32))
        self.node._state_callback(SimpleNamespace(data=0x7F))      # corrupt
        self.node._emit_edge.reset_mock()
        self.node._state_callback(SimpleNamespace(data=0x11))
        self.assertEqual(self.node._emit_edge.call_count, 4)        # resynced, still logging


class LoggerTextTests(unittest.TestCase):
    def test_operator_text(self):
        kind = load_class('pedal_logger.py', 'PedalLogger')
        node = kind.__new__(kind)
        node._file = Mock()
        node._writer = Mock()
        node.get_logger = Mock(return_value=Mock())
        node.get_clock = Mock()
        states = dict.fromkeys(CHANNELS, 0)
        node._emit_edge('cut', 'press', 1, states)
        node._emit_edge('coag', 'release', 0, states)
        lines = [c.args[0] for c in node.get_logger().info.call_args_list]
        self.assertEqual(lines, ['cut on   (computer)', 'coag off   (surgeon)'])


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
            self.assertEqual(node.requests[-1], 32)
            self.assertFalse(node._callback('cut')(SimpleNamespace(data=True), SimpleNamespace()).success)
            self.assertTrue(node._arm(SimpleNamespace(data=True), SimpleNamespace()).success)
            node._callback('cut')(SimpleNamespace(data=True), SimpleNamespace())
            node._tick()
            states, source = parse_state(node.requests[-1], len(revision_channels(rev)))
            self.assertEqual(states[0], 1)
            self.assertEqual(source, 1)
            node.sensed['cut'] = 1
            node._callback('cut')(SimpleNamespace(data=False), SimpleNamespace())
            node._tick()
            self.assertEqual(node.effective['cut'], 1)


class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.send = Mock(return_value=True)
        self.arm = Mock(return_value=True)
        self.session = CommandSession(CHANNELS[:2], self.send, self.arm, .1)

    def test_on_requires_explicit_arm(self):
        self.assertFalse(self.session.command('cut', True))
        self.send.assert_not_called()
        self.assertTrue(self.session.arm())
        self.assertTrue(self.session.command('cut', True))

    def test_only_desired_channels_renewed(self):
        self.session.arm()
        self.session.command('cut', True)
        self.send.reset_mock()
        self.session.renew_once()
        self.send.assert_called_once_with('cut', True)
        self.session.command('cut', False)
        self.send.reset_mock()
        self.session.renew_once()
        self.send.assert_not_called()

    def test_one_missed_renewal_is_tolerated(self):
        self.session.arm()
        self.session.command('cut', True)
        self.send.return_value = False
        self.assertFalse(self.session.renew_once())
        self.assertTrue(self.session.armed)
        self.send.return_value = True
        self.assertTrue(self.session.renew_once())
        self.send.return_value = False
        self.assertFalse(self.session.renew_once())   # counter was reset by the success
        self.assertTrue(self.session.armed)

    def test_failed_renewal_disarms_and_never_rearms(self):
        self.session.arm()
        self.session.command('cut', True)
        self.send.return_value = False
        self.assertFalse(self.session.renew_once())
        self.assertFalse(self.session.renew_once())
        self.assertFalse(self.session.armed)
        self.assertFalse(self.session.desired)
        self.arm.assert_called_with(False)
        self.send.return_value = True
        self.assertFalse(self.session.command('cut', True))

    def test_unknown_channel_never_sent(self):
        with self.assertRaises(ValueError):
            self.session.command('ligasure', True)
        self.send.assert_not_called()

    def test_mock_expiry_preserves_pedal_and_rejects_late_renewal(self):
        FakeNode.overrides = {'board_version': 'v2'}
        node = load_class('mock_esu_node.py', 'MockEsuNode')()
        with patch.object(time, 'monotonic', return_value=10.0):
            node._arm(SimpleNamespace(data=True), SimpleNamespace())
            node._callback('cut')(SimpleNamespace(data=True), SimpleNamespace())
        node.sensed['cut'] = 1
        with patch.object(time, 'monotonic', return_value=10.5):
            self.assertFalse(node._callback('cut')(SimpleNamespace(data=True), SimpleNamespace()).success)
            node._tick()
        self.assertFalse(node.armed)
        self.assertEqual(node.effective['cut'], 1)


class DeviceClientTests(unittest.TestCase):
    def setUp(self):
        FakeNode.overrides = {'board_version': 'v1'}
        mock = load_class('mock_esu_node.py', 'MockEsuNode')()
        self.info = json.loads(mock._capabilities(None, SimpleNamespace()).message)
        self.call = Mock(return_value=CallResult(True, 1.0, 1.1, json.dumps(self.info)))
        kind = load_class('device_client.py', 'DeviceClient',
                          call_service=self.call, CommandSession=CommandSession)
        self.node = Mock()
        self.node.get_publishers_info_by_topic.return_value = [
            SimpleNamespace(topic_type='std_msgs/msg/Int32')]
        self.device = kind(self.node, 'v1')

    def test_duplicate_or_wrong_type_blocks_discovery(self):
        for types in ([], ['std_msgs/msg/Int32'] * 2, ['std_msgs/msg/Int32MultiArray']):
            self.node.get_publishers_info_by_topic.return_value = [
                SimpleNamespace(topic_type=t) for t in types]
            with self.assertRaises(RuntimeError):
                self.device.read_capabilities()
        self.call.assert_not_called()

    def test_failed_capabilities_never_fall_back(self):
        self.call.return_value = CallResult(False, 1.0, None, 'timeout')
        with self.assertRaises(RuntimeError):
            self.device.read_capabilities()
        self.assertIsNone(self.device.session)

    def test_prepare_only_disarms_and_sends_off(self):
        with patch.object(CommandSession, 'start') as start:
            self.device.prepare()
        start.assert_called_once()
        self.assertFalse(self.device.session.armed)
        self.assertEqual(self.device.channels, ('cut', 'coag'))
        self.assertTrue(all(call.args[1].data is False for call in self.call.call_args_list[1:]))

    def test_changed_pedal_mode_blocks_rearm(self):
        self.device.info = self.info
        self.device.session = Mock()
        standalone = {**self.info, 'pedal_connected': False, 'offline_pedals': False}
        self.call.return_value = CallResult(True, 1.0, 1.1, json.dumps(standalone))
        with self.assertRaisesRegex(RuntimeError, 'pedal_connected'):
            self.device.arm()
        self.device.session.all_off.assert_called_once()
        self.device.session.arm.assert_not_called()

    def test_changed_refresh_blocks_rearm(self):
        self.device.info = self.info
        self.device.session = Mock()
        self.call.return_value = CallResult(True, 1.0, 1.1,
                                            json.dumps({**self.info, 'refresh_ms': 50}))
        with self.assertRaises(RuntimeError):
            self.device.arm()
        self.device.session.all_off.assert_called_once()
        self.device.session.arm.assert_not_called()


class CapabilityTests(unittest.TestCase):
    def test_mock_contract_all_revisions(self):
        for rev in ('v1', 'v2', 'v3'):
            FakeNode.overrides = {'board_version': rev}
            node = load_class('mock_esu_node.py', 'MockEsuNode')()
            text = node._capabilities(None, SimpleNamespace()).message
            self.assertEqual(parse_capabilities(text, rev)['board'], rev)
            with self.assertRaises(ValueError):
                parse_capabilities(text, 'v2' if rev == 'v1' else 'v1')
            data = json.loads(text)
            for key, value in (('protocol', 1), ('channel_count', 99), ('refresh_ms', 600),
                               ('requires_arm', False), ('lease_ms', True), ('state', 16),
                               ('baud', 57600), ('pedal_connected', None)):
                with self.subTest(rev=rev, key=key), self.assertRaises(ValueError):
                    parse_capabilities(json.dumps({**data, key: value}))

    def test_offline_pedals_must_match_pedal_mode(self):
        for pedal in (True, False):
            FakeNode.overrides = {'board_version': 'v2', 'pedal_connected': pedal}
            node = load_class('mock_esu_node.py', 'MockEsuNode')()
            data = json.loads(node._capabilities(None, SimpleNamespace()).message)
            self.assertIs(parse_capabilities(json.dumps(data))['offline_pedals'], pedal)
            with self.subTest(pedal=pedal), self.assertRaises(ValueError):
                parse_capabilities(json.dumps({**data, 'offline_pedals': not pedal}))
        FakeNode.overrides = {}

    def test_logger_warns_when_boot_id_unknown(self):
        FakeNode.overrides = {'board_version': 'v1'}
        info = json.loads(load_class('mock_esu_node.py', 'MockEsuNode')()
                          ._capabilities(None, SimpleNamespace()).message)
        FakeNode.overrides = {}
        kind = load_class('pedal_logger.py', 'PedalLogger')
        node = kind.__new__(kind)
        for name, value in (('_info', None), ('_link_missing', False), ('_subscription', 'sub'),
                            ('expected', 'auto'), ('_info_boot_known', True)):
            setattr(node, name, value)
        node._record_metadata = Mock()
        node._state_callback = Mock()
        node.get_logger = Mock(return_value=Mock())
        future = Future()
        future.set_result(SimpleNamespace(success=True,
                                          message=json.dumps({**info, 'boot_id': 0})))
        node._future = future
        node._on_capabilities(future)
        self.assertIn('reboot tracking unavailable', node.get_logger().warn.call_args.args[0])

    def test_packed_channels_checked(self):
        for count in (2, 3, 4):
            states, source = parse_state(0x11, count)
            self.assertEqual(len(states), count)
            self.assertEqual(source, 1)
        with self.assertRaises(ValueError):
            parse_state(8, 3)
        for value in ([1.2], ['1'], [-1], [64], [48]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_state(value)


if __name__ == '__main__':
    unittest.main()
