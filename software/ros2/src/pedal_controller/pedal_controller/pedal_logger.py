#!/usr/bin/env python3
"""
pedal_logger.py

ROS 2 node -- logs ESU activation/deactivation events to CSV for imitation
learning data collection.

VERSION-AGNOSTIC: works with v1, v2, and v3 boards. It detects the channel
count from the length of each /esu/activation_state message and logs whatever
channels are present. The source code is always the LAST element.

    /esu/activation_state  (std_msgs/msg/Int32MultiArray)
        v1: [cut, coag, source]                      (3 elements)
        v2: [cut, coag, bipolar, source]             (4 elements)
        v3: [cut, coag, bipolar, ligasure, source]   (5 elements)
          each channel : 0/1 current EFFECTIVE active state
          source       : 0 = surgeon, 1 = computer, 2 = baseline
                         (attributed on the ESP32)

The ESP32 attributes source deterministically: a change in the debounced
sensed line is ground truth for a surgeon action; otherwise the computer drove
it. The logger records what it receives. This is more reliable than inferring
source on the PC, because the ESP32 sees the command and the sensed edge with
no transport latency between them.

source = 2 (baseline) is the ESP32's boot-time / reconnection sync message, not
a real activation. It does not by itself prove an ESP32 restart, but a baseline
received WHILE a channel was active does indicate a mid-session reset (logged as
a warning, since the dataset has a discontinuity there).

CSV columns (fixed schema across versions; channels not present on a given board
simply never emit rows and stay 0):
  ros_time_ns  -- ROS wall-clock time in nanoseconds (PC receipt time)
  event_type   -- 'press' or 'release'
  channel      -- 'cut', 'coag', 'bipolar', or 'ligasure'
  source       -- 'surgeon', 'computer', or 'baseline'
  cut          -- cut state at time of event (0 or 1)
  coag         -- coag state at time of event (0 or 1)
  bipolar      -- bipolar state (0 or 1; always 0 on v1)
  ligasure     -- ligasure state (0 or 1; always 0 on v1/v2)
"""

import csv
import os
from datetime import datetime

import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32MultiArray


class PedalLogger(Node):

    # Source codes as published in the LAST field of /esu/activation_state.
    # Must stay in sync with SRC_* in the firmware.
    SOURCE_NAMES = {0: 'surgeon', 1: 'computer', 2: 'baseline'}

    # Channel names in array order (excluding the trailing source field).
    # A v1 message carries the first 2, v2 the first 3, v3 all 4.
    CHANNEL_ORDER = ['cut', 'coag', 'bipolar', 'ligasure']

    def __init__(self):
        super().__init__('pedal_logger')

        # -- Parameters --
        self.declare_parameter('log_dir', os.path.expanduser('~/pedal_logs'))
        log_dir = self.get_parameter('log_dir').get_parameter_value().string_value
        os.makedirs(log_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_path = os.path.join(log_dir, f'pedal_log_{timestamp}.csv')

        # -- CSV setup (fixed superset schema, so logs are comparable across boards) --
        self._file = open(log_path, 'w', newline='')
        self._writer = csv.writer(self._file)
        self._writer.writerow([
            'ros_time_ns', 'event_type', 'channel', 'source',
            'cut', 'coag', 'bipolar', 'ligasure'
        ])
        self._file.flush()
        self.get_logger().info(f'Logging to {log_path}')

        # -- Subscription --
        self.create_subscription(
            Int32MultiArray, '/esu/activation_state', self._state_callback, 10)

        # -- State tracking --
        # One last-state slot per possible channel, initialised to the known
        # power-on state (all inactive) rather than None.
        #
        # Assuming all-zero at start is safe: firmware drives every relay LOW in
        # setup(), so the board always boots with all channels inactive. This
        # also means restarting the logger mid-session does not silently swallow
        # a real activation the way seeding from None would.
        self._last = {ch: 0 for ch in self.CHANNEL_ORDER}

        # Detected once from the first message, for a one-time info log.
        self._n_channels = None

        self.get_logger().info('Pedal logger ready (version-agnostic).')

    # -- Edge emission --
    def _emit_edge(self, channel, edge_action, source, states):
        ros_now_ns = self.get_clock().now().nanoseconds
        src_str = self.SOURCE_NAMES.get(source, f'unknown({source})')
        self._writer.writerow([
            ros_now_ns, edge_action, channel, src_str,
            states['cut'], states['coag'], states['bipolar'], states['ligasure']
        ])
        self._file.flush()
        self.get_logger().info(
            f'[{src_str}] {channel} {edge_action} @ {ros_now_ns} ns '
            f'(cut={states["cut"]}, coag={states["coag"]}, '
            f'bipolar={states["bipolar"]}, ligasure={states["ligasure"]})'
        )

    # -- State callback --
    def _state_callback(self, msg: Int32MultiArray):
        data = [int(x) for x in msg.data]

        # Need at least one channel + the trailing source field.
        if len(data) < 2:
            self.get_logger().warn(
                f'Malformed state (need >= 2 fields): {data}')
            return

        n_channels = len(data) - 1          # last element is source
        if n_channels > len(self.CHANNEL_ORDER):
            self.get_logger().warn(
                f'More channels ({n_channels}) than known ({len(self.CHANNEL_ORDER)}); '
                'ignoring the extras. Update CHANNEL_ORDER for newer firmware.')
            n_channels = len(self.CHANNEL_ORDER)

        source = data[-1]

        # One-time note about which board we're talking to.
        if self._n_channels is None:
            self._n_channels = n_channels
            board = {2: 'v1 (mono)', 3: 'v2 (mono+bipolar)',
                     4: 'v3 (mono+bipolar+ligasure)'}.get(n_channels, f'{n_channels}-channel')
            self.get_logger().info(f'Detected {board} firmware ({n_channels} channels).')

        # Build the current full-width state dict (channels not present stay 0).
        states = {ch: 0 for ch in self.CHANNEL_ORDER}
        for i in range(n_channels):
            states[self.CHANNEL_ORDER[i]] = data[i]

        # A baseline mid-session while something was active = the ESP32 reset.
        if source == 2 and any(self._last[ch] for ch in self.CHANNEL_ORDER):
            active = {ch: self._last[ch] for ch in self.CHANNEL_ORDER if self._last[ch]}
            self.get_logger().warn(
                f'ESP32 baseline received while active ({active}). The board '
                'restarted -- device reset, not an operator action. Dataset has '
                'a discontinuity here.')

        # Emit an edge for every channel that changed.
        for ch in self.CHANNEL_ORDER[:n_channels]:
            if states[ch] != self._last[ch]:
                action = 'press' if states[ch] == 1 else 'release'
                self._emit_edge(ch, action, source, states)
                self._last[ch] = states[ch]

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
