#!/usr/bin/env python3
"""Protocol-2 software mock. Isolate ROS_DOMAIN_ID; no hardware safety model."""
import json
import math
import secrets
import time
import rclpy
from rclpy.node import Node
from std_srvs.srv import SetBool, Trigger
from std_msgs.msg import Int32
from pedal_controller.protocol import BAUD, revision_channels, require_channel


class MockEsuNode(Node):
    def __init__(self):
        super().__init__('mock_esu_node')
        for name, default in (('board_version', 'v3'), ('sim_surgeon', False),
                              ('sim_period_s', 5.0), ('sim_channel', 'cut'),
                              ('pedal_connected', True)):
            self.declare_parameter(name, default)
        self.board = self.get_parameter('board_version').value
        self.pedal_connected = bool(self.get_parameter('pedal_connected').value)
        self.channels = revision_channels(self.board)
        self.sim_channel = require_channel(self.get_parameter('sim_channel').value, self.channels)
        self.period = float(self.get_parameter('sim_period_s').value)
        if not math.isfinite(self.period) or self.period <= 0:
            raise ValueError('sim_period_s must be positive and finite')
        self.commands = dict.fromkeys(self.channels, 0)
        self.renewed = dict.fromkeys(self.channels, 0.0)
        self.sensed = dict.fromkeys(self.channels, 0)
        self.previous_sensed = self.sensed.copy()
        self.effective = self.sensed.copy()
        self.armed = False
        self.boot_id = secrets.randbits(32)
        self._baseline = True
        self.last_sim = time.monotonic()
        self.pub = self.create_publisher(Int32, '/esu/activation_state', 100)
        self._esu_services = [self.create_service(SetBool, '/esu/' + ch, self._callback(ch))
                              for ch in self.channels]
        self._esu_services += [
            self.create_service(SetBool, '/esu/arm', self._arm),
            self.create_service(Trigger, '/esu/capabilities', self._capabilities)]
        self.create_timer(.01, self._tick)
        self.get_logger().warn('SOFTWARE MOCK; isolate ROS_DOMAIN_ID from hardware.')

    def _disarm(self):
        self.armed = False
        self.commands = dict.fromkeys(self.channels, 0)

    def _expire(self):
        if any(self.commands[ch] and time.monotonic() - self.renewed[ch] >= .5
               for ch in self.channels):
            self._disarm()

    def _arm(self, request, response):
        self._expire()
        if not request.data:
            self._disarm()
            response.success = True
        else:
            response.success = not any(self.sensed.values()) and not any(self.commands.values())
            if response.success:
                self.armed = True
        response.message = ''
        return response

    def _callback(self, channel):
        def callback(request, response):
            self._expire()
            response.success = not request.data or self.armed
            if response.success:
                self.commands[channel] = int(request.data)
                self.renewed[channel] = time.monotonic()
            response.message = ''
            return response
        return callback

    def _capabilities(self, request, response):
        response.success = True
        response.message = json.dumps(dict(
            protocol=2, firmware='3.0.0-bench-mock', board=self.board,
            channel_count=len(self.channels), watchdog=self.board != 'v1', baud=BAUD,
            lease_ms=500, refresh_ms=100, offline_pedals=self.pedal_connected,
            requires_arm=True, pedal_connected=self.pedal_connected,
            armed=self.armed, state=sum(self.effective[ch] << i for i, ch in enumerate(self.channels)),
            boot_id=self.boot_id, dropped_events=0))
        return response

    def _publish(self, source):
        msg = Int32()
        msg.data = (source << 4) | sum(self.effective[ch] << i for i, ch in enumerate(self.channels))
        self.pub.publish(msg)

    def _tick(self):
        self._expire()
        if self._baseline:
            self._publish(2)
            self._baseline = False
        if (self.get_parameter('sim_surgeon').value
                and time.monotonic() - self.last_sim >= self.period):
            self.last_sim = time.monotonic()
            self.sensed[self.sim_channel] ^= 1
        if not self.pedal_connected:   # Standalone firmware ignores pedal inputs.
            self.sensed = dict.fromkeys(self.channels, 0)
        for ch in self.channels:
            effective = int(self.commands[ch] or self.sensed[ch])
            if effective != self.effective[ch]:
                self.effective[ch] = effective
                self._publish(0 if self.sensed[ch] != self.previous_sensed[ch] else 1)
        self.previous_sensed = self.sensed.copy()


def main(args=None):
    rclpy.init(args=args)
    node = MockEsuNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
