#!/usr/bin/env python3
"""
pedal_logger.py

ROS 2 node -- logs ESU activation/deactivation events to CSV for imitation
learning data collection.

Subscribes to the status topic published by the ESU-TAP micro-ROS node:

    /esu/activation_state  (std_msgs/msg/Int32MultiArray)
        data = [cut, coag, source]
          cut    : 0/1 current CUT active state
          coag   : 0/1 current COAG active state
          source : 0 = surgeon, 1 = computer  (attributed on the ESP32)

The ESP32 already attributes source (surgeon vs computer) using its own
command-window logic, so the logger just records what it receives. This is
more reliable than inferring source on the PC, because the ESP32 sees the
command and the sensed edge with no network latency between them.

CSV columns:
  ros_time_ns  -- ROS wall-clock time in nanoseconds (PC receipt time)
  event_type   -- 'press' or 'release'
  channel      -- 'cut' or 'coag'
  source       -- 'surgeon' or 'computer'
  cut          -- cut state at time of event (0 or 1)
  coag         -- coag state at time of event (0 or 1)
"""

import csv
import os
from datetime import datetime

import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32MultiArray


class PedalLogger(Node):
    def __init__(self):
        super().__init__('pedal_logger')

        # -- Parameters --
        self.declare_parameter('log_dir', os.path.expanduser('~/pedal_logs'))
        log_dir = self.get_parameter('log_dir').get_parameter_value().string_value
        os.makedirs(log_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_path = os.path.join(log_dir, f'pedal_log_{timestamp}.csv')

        # -- CSV setup --
        self._file = open(log_path, 'w', newline='')
        self._writer = csv.writer(self._file)
        self._writer.writerow([
            'ros_time_ns', 'event_type', 'channel', 'source', 'cut', 'coag'
        ])
        self._file.flush()
        self.get_logger().info(f'Logging to {log_path}')

        # -- Subscription --
        self.create_subscription(
            Int32MultiArray, '/esu/activation_state', self._state_callback, 10)

        # -- State tracking --
        self._last_cut = None
        self._last_coag = None

        self.get_logger().info('Pedal logger ready.')

    # -- Edge emission --
    def _emit_edge(self, channel, edge_action, source, cut, coag):
        ros_now_ns = self.get_clock().now().nanoseconds
        src_str = 'computer' if source == 1 else 'surgeon'
        self._writer.writerow([
            ros_now_ns, edge_action, channel, src_str, cut, coag
        ])
        self._file.flush()
        self.get_logger().info(
            f'[{src_str}] {channel} {edge_action} @ {ros_now_ns} ns '
            f'(cut={cut}, coag={coag})'
        )

    # -- State callback --
    def _state_callback(self, msg: Int32MultiArray):
        if len(msg.data) < 3:
            self.get_logger().warn(f'Malformed state (need 3 fields): {list(msg.data)}')
            return
        cut, coag, source = int(msg.data[0]), int(msg.data[1]), int(msg.data[2])

        # Initialise on first message without emitting edges
        if self._last_cut is None or self._last_coag is None:
            self._last_cut = cut
            self._last_coag = coag
            return

        if cut != self._last_cut:
            self._emit_edge('cut', 'press' if cut == 1 else 'release', source, cut, coag)
            self._last_cut = cut
        if coag != self._last_coag:
            self._emit_edge('coag', 'press' if coag == 1 else 'release', source, cut, coag)
            self._last_coag = coag

    def destroy_node(self):
        self._file.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = PedalLogger()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
