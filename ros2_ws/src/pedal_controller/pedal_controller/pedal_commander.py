#!/usr/bin/env python3
"""
pedal_commander.py
ROS2 node — publishes ESU commands to /esu/command (std_msgs/String).

Modes:
  interactive  : keyboard-driven (press ENTER to press, again to release)
  pulse        : press for a fixed duration then auto-release
  script       : run a list of timed (delay, action) commands

Run:
  ros2 run pedal_controller pedal_commander
  ros2 run pedal_controller pedal_commander --ros-args -p mode:=pulse -p pulse_ms:=500 -p channel:=cut
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import threading
import time


class PedalCommander(Node):
    def __init__(self):
        super().__init__('pedal_commander')

        # ── Parameters ──────────────────────────────────────────
        self.declare_parameter('mode', 'interactive')   # interactive | pulse | script
        self.declare_parameter('pulse_ms', 300)         # press duration for pulse mode
        self.declare_parameter('channel', 'cut')        # cut | coag

        self._mode     = self.get_parameter('mode').get_parameter_value().string_value
        self._pulse_ms = self.get_parameter('pulse_ms').get_parameter_value().integer_value
        self._channel  = self.get_parameter('channel').get_parameter_value().string_value.strip().lower()
        if self._channel not in ('cut', 'coag'):
            self.get_logger().warn(f'Unknown channel [{self._channel}], defaulting to [cut].')
            self._channel = 'cut'

        # ── Publisher ────────────────────────────────────────────
        self._pub = self.create_publisher(String, '/esu/command', 10)
        self.get_logger().info(
            f'Pedal commander started in [{self._mode}] mode (channel={self._channel}).'
        )

        # ── Launch mode ──────────────────────────────────────────
        if self._mode == 'interactive':
            self._interactive_thread = threading.Thread(
                target=self._interactive_loop, daemon=True)
            self._interactive_thread.start()

        elif self._mode == 'pulse':
            # Single pulse after 1s warmup
            self.create_timer(1.0, self._pulse_once)

        elif self._mode == 'script':
            # Example script: 3 presses with varying delays
            # Replace this list with your own sequence
            self._script = [
                (1.0,  'press'),
                (0.5,  'release'),
                (2.0,  'press'),
                (0.5,  'release'),
                (1.5,  'press'),
                (0.5,  'release'),
            ]
            self._script_thread = threading.Thread(
                target=self._run_script, daemon=True)
            self._script_thread.start()
        else:
            self.get_logger().error(f'Unknown mode: {self._mode}')
            raise SystemExit(2)

    # ── Command helpers ──────────────────────────────────────────
    def press(self):
        on = f'{self._channel.upper()}_ON'
        msg = String()
        msg.data = on
        self._pub.publish(msg)
        self.get_logger().info(f'CMD: {msg.data}')

    def release(self):
        off = f'{self._channel.upper()}_OFF'
        msg = String()
        msg.data = off
        self._pub.publish(msg)
        self.get_logger().info(f'CMD: {msg.data}')

    def pulse(self, ms: int):
        on = f'{self._channel.upper()}_ON {int(ms)}'
        msg = String()
        msg.data = on
        self._pub.publish(msg)
        self.get_logger().info(f'CMD: {msg.data}')

    # ── Interactive mode ─────────────────────────────────────────
    def _interactive_loop(self):
        print('\n=== Pedal Commander (interactive) ===')
        print(f'  Channel: {self._channel}')
        print('  ENTER       → press (sends <CHANNEL>_ON)')
        print('  ENTER again → release (sends <CHANNEL>_OFF)')
        print('  Ctrl+C      → quit\n')
        pressed = False
        while True:
            input()  # wait for enter
            if not pressed:
                self.press()
                pressed = True
            else:
                self.release()
                pressed = False

    # ── Pulse mode ───────────────────────────────────────────────
    def _pulse_once(self):
        self.pulse(self._pulse_ms)
        # Optionally send OFF after the duration; firmware also supports auto-off timers.
        time.sleep(self._pulse_ms / 1000.0)
        self.release()
        self.get_logger().info(f'Pulse complete ({self._pulse_ms} ms) on {self._channel}')
        # Only fire once
        raise SystemExit

    # ── Script mode ──────────────────────────────────────────────
    def _run_script(self):
        self.get_logger().info(f'Running script ({len(self._script)} steps)...')
        for delay_s, action in self._script:
            time.sleep(delay_s)
            if action == 'press':
                self.press()
            elif action == 'release':
                self.release()
        self.get_logger().info('Script complete.')


def main(args=None):
    rclpy.init(args=args)
    node = PedalCommander()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        try:
            node.release()   # safety: always release on exit
        except Exception:
            pass
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
