"""Protocol-2 discovery used by commander and disconnected-fixture tools."""
from std_srvs.srv import SetBool, Trigger
from .capabilities import parse_capabilities
from .protocol import revision_channels
from .service_calls import call_service
from .command_session import CommandSession


class DeviceClient:
    def __init__(self, node, expected='auto'):
        self.node = node
        self.expected = expected
        self.clients = {}
        self.last_results = {}
        self.cap_client = node.create_client(Trigger, '/esu/capabilities')
        self.arm_client = node.create_client(SetBool, '/esu/arm')
        self.session = None
        self.info = None

    def read_capabilities(self):
        publishers = self.node.get_publishers_info_by_topic('/esu/activation_state')
        if len(publishers) != 1 or publishers[0].topic_type != 'std_msgs/msg/Int32':
            raise RuntimeError('Requires exactly one protocol-2 board/mock in this ROS domain')
        result = call_service(self.cap_client, Trigger.Request(), 2.0)
        if not result.success:
            raise RuntimeError('Capabilities unavailable; refusing computer activation')
        return parse_capabilities(result.message, self.expected)

    def prepare(self):
        if not self.cap_client.wait_for_service(timeout_sec=5.0):
            raise RuntimeError('Shared firmware /esu/capabilities missing; reflash correct profile')
        self.info = self.read_capabilities()
        if not self.arm_client.wait_for_service(timeout_sec=3.0):
            raise RuntimeError('/esu/arm missing')
        self.channels = revision_channels(self.info['board'])
        self.timeout = min(0.2, self.info['lease_ms'] / 2000.0)
        for ch in self.channels:
            client = self.node.create_client(SetBool, '/esu/' + ch)
            if not client.wait_for_service(timeout_sec=3.0):
                raise RuntimeError('Missing channel service: ' + ch)
            self.clients[ch] = client
        self.session = CommandSession(self.channels, self.send, self.set_arm,
                                      self.info['refresh_ms'] / 1000.0)
        if not self.session.all_off():
            raise RuntimeError('Initial disarm/OFF not acknowledged')
        self.session.start()
        mode = ('pedal connected' if self.info['pedal_connected']
                else 'STANDALONE: pedal inputs ignored')
        self.node.get_logger().info(
            f"Firmware {self.info['firmware']}, profile {self.info['board']}, "
            f"channels {self.channels}, {mode}, lease {self.info['lease_ms']} ms; "
            "computer DISARMED")

    def arm(self):
        fresh = self.read_capabilities()
        changed = [key for key in ('board', 'lease_ms', 'refresh_ms', 'firmware',
                                   'pedal_connected') if fresh[key] != self.info[key]]
        if changed:
            self.session.all_off()
            raise RuntimeError(f"Board capabilities changed ({', '.join(changed)}), e.g. "
                               'reflashed between pedal and standalone modes; restart client')
        # Explicit human/fixture request only. A reboot never auto-rearms.
        self.info = fresh
        return self.session.arm()

    def set_arm(self, on):
        req = SetBool.Request(); req.data = bool(on)
        return call_service(self.arm_client, req, self.timeout).success

    def send(self, channel, on):
        req = SetBool.Request(); req.data = bool(on)
        result = call_service(self.clients[channel], req, self.timeout)
        self.last_results[channel] = result
        return result.success

    def close(self):
        return self.session.close() if self.session else True
