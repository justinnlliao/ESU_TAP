#!/usr/bin/env python3
"""
pedal_logger.py

REVIEW NOTE (2026-09-11): this legacy reader expects three fields. Current
firmware publishes [cut, coag, bipolar, source], so this reader misattributes
source. Do not treat its output as validated current-firmware data. This is a
documentation warning, not a schema fix. See docs/SAFETY_AND_VALIDATION.md.

ROS 2 node -- logs ESU activation/deactivation events to CSV for imitation
learning data collection.

Subscribes to the status topic published by the ESU-TAP micro-ROS node:

    /esu/activation_state  (std_msgs/msg/Int32MultiArray)
        data = [cut, coag, source]
          cut    : 0/1 current EFFECTIVE CUT active state
          coag   : 0/1 current EFFECTIVE COAG active state
          source : 0 = surgeon, 1 = computer, 2 = baseline
                   (attributed on the ESP32)

The ESP32 attributes source deterministically: a change in the debounced
sensed line is ground truth for a surgeon action; otherwise the computer drove
it. The logger just records what it receives. This is more reliable than
inferring source on the PC, because the ESP32 sees the command and the sensed
edge with no transport latency between them.

source = 2 (baseline) is the ESP32's boot-time sync message, not a real
activation. Current firmware also publishes it on reconnection, so it does not
by itself prove an ESP32 restart. The legacy warning below needs updating along
with the message schema; do not infer device-reset events solely from baseline.

CSV columns:
  ros_time_ns  -- ROS wall-clock time in nanoseconds (PC receipt time)
  event_type   -- 'press' or 'release'
  channel      -- 'cut' or 'coag'
  source       -- 'surgeon', 'computer', or 'baseline'
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

    # Source codes as published in field 2 of /esu/activation_state.
    # Must stay in sync with SRC_* in firmware/esp32/src/esu_tap_microros.cpp.
    SOURCE_NAMES = {0: 'surgeon', 1: 'computer', 2: 'baseline'}

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
        # Initialised to the known power-on state (both channels inactive)
        # rather than to None.
        #
        # Previously this was None and the first message was consumed purely to
        # seed the edge detector, emitting nothing. That silently swallowed one
        # real activation whenever the logger started after the ESP32 -- e.g.
        # restarting the logger mid-session. Assuming (0, 0) is safe: the
        # firmware drives both relays LOW in setup(), so the board always boots
        # with both channels inactive.
        self._last_cut = 0
        self._last_coag = 0

        self.get_logger().info('Pedal logger ready.')

    # -- Edge emission --
    def _emit_edge(self, channel, edge_action, source, cut, coag):
        ros_now_ns = self.get_clock().now().nanoseconds
        src_str = self.SOURCE_NAMES.get(source, f'unknown({source})')
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

        # A baseline message mid-session means the ESP32 restarted. Warn loudly:
        # any activation that was in progress across the reset is unrecoverable,
        # and the operator needs to know the dataset has a discontinuity here.
        if source == 2 and (self._last_cut or self._last_coag):
            self.get_logger().warn(
                'ESP32 baseline received while a channel was active '
                f'(cut={self._last_cut}, coag={self._last_coag}). The board '
                'restarted -- this is a device reset, not an operator action. '
                'Data has a discontinuity here.'
            )

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
