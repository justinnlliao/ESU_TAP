#!/usr/bin/env python3
"""Revision-selectable ROS-only mock, NOT a hardware or watchdog model.

Run on an isolated ROS_DOMAIN_ID; never alongside a real board in that domain.
Commands and simulated pedal states are ORed, with change-only timer publishing.
"""

import math
import time

import rclpy
from rclpy.node import Node
from std_srvs.srv import SetBool
from std_msgs.msg import Int32

from pedal_controller.protocol import revision_channels, require_channel


class MockEsuNode(Node):
    def __init__(self):
        super().__init__('mock_esu_node')
        for name, default in (('board_version', 'v3'), ('sim_surgeon', False),
                              ('sim_period_s', 5.0), ('sim_channel', 'cut')):
            self.declare_parameter(name, default)
        self.channels = revision_channels(self.get_parameter('board_version').value)
        self.sim_channel = require_channel(self.get_parameter('sim_channel').value, self.channels)
        self.period = float(self.get_parameter('sim_period_s').value)
        if not math.isfinite(self.period) or self.period <= 0:
            raise ValueError('sim_period_s must be positive and finite')
        self.commands = dict.fromkeys(self.channels, 0)
        self.sensed = dict.fromkeys(self.channels, 0)
        self.previous_sensed = self.sensed.copy()
        self.effective = self.sensed.copy()
        self._baseline = True
        self.last_sim = time.monotonic()
        self.pub = self.create_publisher(Int32, '/esu/activation_state', 10)
        self._esu_services = [self.create_service(SetBool, f'/esu/{ch}', self._callback(ch))
                         for ch in self.channels]
        self.create_timer(0.01, self._tick)
        self.get_logger().warn('SOFTWARE MOCK: isolate ROS_DOMAIN_ID from all real boards.')

    def _callback(self, channel):
        def callback(request, response):
            self.commands[channel] = int(request.data)
            response.success = True
            response.message = f'{channel} command accepted (mock)'
            return response
        return callback

    def _publish(self, source):
        # Pack channels into bits 0..3 and source into bits 4-5, matching the
        # firmware wire format and protocol.parse_state's decoder.
        packed = source << 4
        for i, ch in enumerate(self.channels):
            if self.effective[ch]:
                packed |= (1 << i)
        msg = Int32()
        msg.data = packed
        self.pub.publish(msg)

    def _tick(self):
        if self._baseline:
            self._publish(2)
            self._baseline = False
        if (self.get_parameter('sim_surgeon').value
                and time.monotonic() - self.last_sim >= self.period):
            self.last_sim = time.monotonic()
            self.sensed[self.sim_channel] ^= 1
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
