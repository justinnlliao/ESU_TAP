#!/usr/bin/env python3
"""Read-only logger; records inferred state, never proof of contact/RF output.

Default is shared protocol-2 firmware: the board is identified once through
/esu/capabilities, then again only after a link gap or a mid-session baseline
(not polled continuously, to keep text off the serial link). Legacy array/packed
subscriptions require explicit wire_format and board_version.

The terminal shows plain operator text ("cut on", "coag off"); the CSV keeps
the full per-channel record. Problems (bad capability reply, extra publishers,
malformed messages) are warned about and marked as discontinuities in the
metadata file; logging continues rather than stopping for the session.
"""
import csv
import json
import os
import re
import time
from datetime import datetime
import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32, Int32MultiArray
from std_srvs.srv import Trigger
from pedal_controller.protocol import CHANNELS, parse_state, revision_channels
from pedal_controller.capabilities import parse_capabilities

CAPABILITY_RETRY_S = 5.0


class PedalLogger(Node):
    SOURCE_NAMES = {0: 'surgeon', 1: 'computer', 2: 'baseline', 3: 'takeover'}
    CHANNEL_ORDER = list(CHANNELS)

    def __init__(self):
        super().__init__('pedal_logger')
        for key, value in (('log_dir', os.path.expanduser('~/pedal_logs')),
                           ('board_version', 'auto'), ('wire_format', 'standard'),
                           ('trial_id', '')):
            self.declare_parameter(key, value)
        self.expected = self.get_parameter('board_version').value
        self.wire_format = self.get_parameter('wire_format').value
        if self.wire_format not in ('standard', 'legacy_array', 'legacy_packed'):
            raise ValueError('wire_format must be standard, legacy_array, or legacy_packed')
        # Shared with video/robot recorders for the same trial; goes in the file name.
        self.trial_id = self.get_parameter('trial_id').value
        if not re.fullmatch(r'[A-Za-z0-9_-]{0,64}', self.trial_id):
            raise ValueError('trial_id: letters, digits, _ and - only (max 64)')
        self._n_channels = None
        if self.wire_format != 'standard':
            self._n_channels = len(revision_channels(self.expected))
        self._last = None
        self._info = None
        self._future = None
        self._requested_at = 0.0
        self._retry_at = 0.0
        self._want_caps = False
        self._link_missing = False
        self._publisher_problem = False
        self._info_boot_known = True
        self._subscription = None
        directory = self.get_parameter('log_dir').value
        os.makedirs(directory, exist_ok=True)
        prefix = 'pedal_log_' + (self.trial_id + '_' if self.trial_id else '')
        stem = os.path.join(directory, prefix + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        self._metadata_path = stem + '.metadata.jsonl'
        self._metadata = open(self._metadata_path, 'x')
        self._file = open(stem + '.csv', 'x', newline='')
        self._writer = csv.writer(self._file)
        # monotonic_ns (last column, so existing column positions are unchanged):
        # this PC's monotonic clock. It never jumps, but only compares within one
        # machine; ros_time_ns (wall clock) is what aligns with other recorders.
        self._writer.writerow(['ros_time_ns', 'event_type', 'channel', 'source', *CHANNELS,
                               'monotonic_ns'])
        self._file.flush()
        self._record_metadata({'event': 'logger_start', 'wire_format': self.wire_format,
                               'selected_board': self.expected, 'trial_id': self.trial_id})
        self._cap_client = self.create_client(Trigger, '/esu/capabilities')
        self.create_timer(1.0, self._poll)
        if self.wire_format != 'standard':
            kind = Int32MultiArray if self.wire_format == 'legacy_array' else Int32
            self._subscription = self.create_subscription(kind, '/esu/activation_state',
                                                          self._state_callback, 100)
        self.get_logger().info('Logging to ' + stem + '.csv')
        self.get_logger().info('Waiting for the board...')

    # -- Link and capability tracking (graph checks are local; no serial traffic) --
    def _poll(self):
        info = self.get_publishers_info_by_topic('/esu/activation_state')
        expected_type = ('std_msgs/msg/Int32MultiArray' if self.wire_format == 'legacy_array'
                         else 'std_msgs/msg/Int32')
        problem = len(info) > 1 or any(p.topic_type != expected_type for p in info)
        if problem != self._publisher_problem:
            self._publisher_problem = problem
            if problem:
                self._last = None
                self._record_metadata({'event': 'invalid_publishers',
                                       'publishers': [p.topic_type for p in info]})
                self.get_logger().error(
                    'More than one publisher (or a wrong type) on /esu/activation_state: '
                    'events may be mixed until it is removed. Marked in metadata.')
            else:
                self._record_metadata({'event': 'publishers_ok'})
                self.get_logger().info('Single board publisher again.')
        if self.wire_format != 'standard':
            return
        now = time.monotonic()
        if self._future is not None:
            if now - self._requested_at > 2.0:
                self._future.cancel()
                self._future = None
                self._last = None
                self._link_missing = True
                self._retry_at = now + CAPABILITY_RETRY_S
                self.get_logger().warn('Board not answering: recording a discontinuity.')
                self._record_metadata({'event': 'capability_timeout'})
            return
        if not self._cap_client.service_is_ready() or len(info) != 1:
            if self._info is not None:
                self._last = None
                if not self._link_missing:
                    self._record_metadata({'event': 'capability_or_publisher_missing'})
                    self.get_logger().warn('Board disconnected: recording a discontinuity.')
                    self._link_missing = True
            return
        if (self._info is None or self._link_missing or self._want_caps) and now >= self._retry_at:
            self._want_caps = False
            self._future = self._cap_client.call_async(Trigger.Request())
            self._requested_at = now
            self._future.add_done_callback(self._on_capabilities)

    def _record_metadata(self, data):
        self._metadata.write(json.dumps({'receipt_time_ns': self.get_clock().now().nanoseconds,
                                         'monotonic_ns': time.monotonic_ns(), **data}) + '\n')
        self._metadata.flush()

    def _on_capabilities(self, future):
        if future is not self._future:
            return
        self._future = None
        if future.cancelled():
            return
        try:
            response = future.result()
            if response is None or not response.success:
                raise ValueError('Capability request failed')
            info = parse_capabilities(response.message, self.expected)
        except Exception as exc:
            # Transient on a marginal link, or wrong firmware: warn and retry.
            self._retry_at = time.monotonic() + CAPABILITY_RETRY_S
            self._record_metadata({'event': 'invalid_capabilities', 'reason': str(exc)})
            self.get_logger().error(f'Board info rejected ({exc}); retrying in '
                                    f'{CAPABILITY_RETRY_S:.0f} s.')
            return
        changed_board = self._info is not None and info['board'] != self._info['board']
        discontinuity = changed_board or self._link_missing or (self._info is not None and (
            info['boot_id'] != self._info['boot_id']
            or info['dropped_events'] != self._info['dropped_events']))
        self._link_missing = False
        if changed_board:
            self.get_logger().warn(f"Board changed from {self._info['board']} to {info['board']}.")
        if discontinuity:
            self._last = None
            self.get_logger().warn('Link gap, reboot or lost messages: dataset discontinuity.')
        first = self._info is None
        self._info = info
        self._n_channels = info['channel_count']
        self._record_metadata(info)
        if first:
            mode = 'pedal connected' if info['pedal_connected'] else \
                'STANDALONE (pedal inputs ignored)'
            self.get_logger().info(
                f"Board {info['board']}: {', '.join(CHANNELS[:self._n_channels])}; {mode}.")
        if info['boot_id'] == 0 and (first or self._info_boot_known):
            # The board could not save its boot counter: reboots cannot be told
            # apart by ID. Link gaps and baselines are still marked.
            self.get_logger().warn('Board reports no boot ID: reboot tracking unavailable.')
            self._record_metadata({'event': 'boot_id_unavailable'})
        self._info_boot_known = info['boot_id'] != 0
        if self._subscription is None:
            # First snapshot is explicitly a sync, not an activation edge.
            self._state_callback(type('Snapshot', (), {'data': info['state'] | 32})())
            self._subscription = self.create_subscription(Int32, '/esu/activation_state',
                                                          self._state_callback, 100)
        elif discontinuity:
            self._state_callback(type('Snapshot', (), {'data': info['state'] | 32})())

    # -- Output --
    def _emit_edge(self, channel, action, source, states, quiet=False):
        self._writer.writerow([self.get_clock().now().nanoseconds, action, channel,
                               self.SOURCE_NAMES[source], *(states[ch] for ch in CHANNELS),
                               time.monotonic_ns()])
        self._file.flush()
        if quiet:
            return
        if action == 'takeover':
            where = f'{channel}: ' if channel else ''
            self.get_logger().info(f'{where}surgeon took over (computer control ended)')
        else:
            verb = 'on' if action == 'press' else 'off'
            self.get_logger().info(f'{channel} {verb}   ({self.SOURCE_NAMES[source]})')

    def _active_text(self, states):
        active = [ch for ch in CHANNELS[:self._n_channels] if states[ch]]
        return ', '.join(active) if active else 'none'

    def _state_callback(self, msg):
        if self._n_channels is None:
            return
        try:
            values, source = parse_state(msg.data, self._n_channels)
        except (ValueError, TypeError) as exc:
            self.get_logger().error(f'Ignored malformed state: {exc}')
            self._record_metadata({'event': 'malformed_state', 'reason': str(exc)})
            self._last = None
            return
        states = dict.fromkeys(CHANNELS, 0)
        states.update(zip(CHANNELS, values))
        if self._last is None or source == 2:
            reconnect = self._last is not None
            if reconnect and self.wire_format == 'standard':
                self._want_caps = True   # Check boot ID / drop count once.
            for ch in CHANNELS[:self._n_channels]:
                self._emit_edge(ch, 'sync', source, states, quiet=True)
            label = 'board resynced' if reconnect else 'board connected'
            self.get_logger().info(f'>>> {label}   active: {self._active_text(states)}')
        else:
            changed = [ch for ch in CHANNELS[:self._n_channels] if states[ch] != self._last[ch]]
            for ch in changed:
                self._emit_edge(ch, 'press' if states[ch] else 'release', source, states)
            if not changed and source == 3:
                # Takeover on a channel the computer already held: the output did
                # not change, so record the hand-over itself on each active channel.
                for ch in [c for c in CHANNELS[:self._n_channels] if states[c]] or ['']:
                    self._emit_edge(ch, 'takeover', source, states)
        self._last = states

    def destroy_node(self):
        self._file.close()
        self._metadata.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = PedalLogger()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
