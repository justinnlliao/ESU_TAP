#!/usr/bin/env python3
"""
pedal_logger.py
ROS2 node — subscribes to /esu/activation_state and logs press/release
timestamps (ROS clock) to a timestamped CSV file.

Topics subscribed:
  /esu/activation_state (std_msgs/String)  "cut=0 coag=1 ts=123456"
  /esu/command          (std_msgs/String)  "CUT_ON <ms>", "COAG_OFF", ...

CSV columns:
  ros_time_ns, event_type, channel, esp_millis, source, cut, coag
    source = "computer" if it closely follows a command on /esu/command
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import csv
import os
from datetime import datetime
import re
import time


class PedalLogger(Node):
    def __init__(self):
        super().__init__('pedal_logger')

        # ── Parameters ──────────────────────────────────────────
        self.declare_parameter('log_dir', os.path.expanduser('~/pedal_logs'))
        self.declare_parameter('computer_cmd_window_s', 0.75)
        log_dir = self.get_parameter('log_dir').get_parameter_value().string_value
        os.makedirs(log_dir, exist_ok=True)
        self._cmd_window_s = float(
            self.get_parameter('computer_cmd_window_s').get_parameter_value().double_value
        )

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_path = os.path.join(log_dir, f'pedal_log_{timestamp}.csv')

        # ── CSV setup ────────────────────────────────────────────
        self._file = open(log_path, 'w', newline='')
        self._writer = csv.writer(self._file)
        self._writer.writerow(['ros_time_ns', 'event_type', 'channel', 'esp_millis', 'source', 'cut', 'coag'])
        self._file.flush()
        self.get_logger().info(f'Logging to {log_path}')

        # ── Track commands to infer source on edge ───────────────
        self._last_cmd_time_by_channel = {'cut': 0.0, 'coag': 0.0}
        self._last_cmd_action_by_channel = {'cut': None, 'coag': None}  # 'on' | 'off' | None

        # ── Subscriptions ────────────────────────────────────────
        self.create_subscription(
            String, '/esu/activation_state', self._state_callback, 10)

        self.create_subscription(
            String, '/esu/command', self._cmd_callback, 10)

        # ── State tracking ───────────────────────────────────────
        self._last_cut = None
        self._last_coag = None

        self.get_logger().info('Pedal logger ready.')

    def _cmd_callback(self, msg: String):
        cmd = (msg.data or '').strip().upper()
        if not cmd:
            return
        now = time.time()

        # Expected: CUT_ON <ms>, CUT_OFF, COAG_ON <ms>, COAG_OFF
        m = re.match(r'^(CUT|COAG)_(ON|OFF)\b', cmd)
        if not m:
            return
        ch = m.group(1).lower()
        act = m.group(2).lower()  # on/off
        self._last_cmd_time_by_channel[ch] = now
        self._last_cmd_action_by_channel[ch] = act

    def _parse_state(self, s: str):
        # Expected: "cut=0 coag=1 ts=123456"
        kv = {}
        for part in (s or '').strip().split():
            if '=' not in part:
                continue
            k, v = part.split('=', 1)
            kv[k.strip().lower()] = v.strip()
        if 'cut' not in kv and 'coag' not in kv:
            return None
        try:
            cut = int(kv.get('cut', -1))
            coag = int(kv.get('coag', -1))
            ts = int(kv.get('ts', -1))
        except Exception:
            return None
        return cut, coag, ts

    def _infer_source(self, channel: str, edge_action: str) -> str:
        """
        edge_action: 'press' | 'release'
        We call it 'computer' if a matching recent command occurred.
        """
        now = time.time()
        dt = now - float(self._last_cmd_time_by_channel.get(channel, 0.0))
        if dt <= self._cmd_window_s:
            last_act = self._last_cmd_action_by_channel.get(channel)
            if (edge_action == 'press' and last_act == 'on') or (edge_action == 'release' and last_act == 'off'):
                return 'computer'
            # Even if it doesn't match perfectly, keep it conservative:
            # a recent command suggests computer involvement.
            return 'computer'
        return 'surgeon'

    def _emit_edge(self, channel: str, edge_action: str, esp_millis: int, cut: int, coag: int):
        ros_now_ns = self.get_clock().now().nanoseconds
        source = self._infer_source(channel, edge_action)
        event_type = edge_action

        self._writer.writerow([ros_now_ns, event_type, channel, esp_millis, source, cut, coag])
        self._file.flush()
        self.get_logger().info(
            f'[{source}] {channel} {event_type} @ {ros_now_ns} ns (esp:{esp_millis} ms, cut={cut}, coag={coag})'
        )

    def _state_callback(self, msg: String):
        parsed = self._parse_state(msg.data)
        if parsed is None:
            self.get_logger().warn(f'Malformed state: {msg.data}')
            return
        cut, coag, ts = parsed

        # Initialize on first message without emitting edges.
        if self._last_cut is None or self._last_coag is None:
            self._last_cut = cut
            self._last_coag = coag
            return

        # Emit edges per channel
        if cut != self._last_cut:
            self._emit_edge('cut', 'press' if cut == 1 else 'release', ts, cut, coag)
            self._last_cut = cut
        if coag != self._last_coag:
            self._emit_edge('coag', 'press' if coag == 1 else 'release', ts, cut, coag)
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
