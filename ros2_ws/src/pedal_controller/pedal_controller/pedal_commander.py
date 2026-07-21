#!/usr/bin/env python3
"""
pedal_commander.py

ROS 2 service CLIENT for the ESU-TAP micro-ROS node.

The ESP32 (esu_tap_node) hosts two std_srvs/SetBool services:
    /esu/cut    data=True -> CUT on,   data=False -> CUT off
    /esu/coag   data=True -> COAG on,  data=False -> COAG off

This node calls those services. It replaces the old topic-publishing
commander: activation is now a confirmed request/response, so we know the
ESP32 acknowledged each command.

Modes:
  interactive : keyboard-driven (ENTER toggles on/off)
  pulse       : call ON, wait pulse_ms, call OFF (single shot)
  script      : run a list of timed (delay, action) calls

Run:
  ros2 run pedal_controller pedal_commander
  ros2 run pedal_controller pedal_commander --ros-args -p mode:=pulse -p pulse_ms:=500 -p channel:=cut
"""

import threading
import time

import rclpy
from rclpy.node import Node
from std_srvs.srv import SetBool


class PedalCommander(Node):
    def __init__(self):
        super().__init__('pedal_commander')

        # -- Parameters --
        self.declare_parameter('mode', 'interactive')   # interactive | pulse | script
        self.declare_parameter('pulse_ms', 300)
        self.declare_parameter('channel', 'cut')         # cut | coag
        self.declare_parameter('wait_timeout_s', 2.0)    # service-call timeout

        self._mode     = self.get_parameter('mode').get_parameter_value().string_value
        self._pulse_ms = self.get_parameter('pulse_ms').get_parameter_value().integer_value
        self._channel  = self.get_parameter('channel').get_parameter_value().string_value.strip().lower()
        self._timeout  = float(self.get_parameter('wait_timeout_s').get_parameter_value().double_value)

        if self._channel not in ('cut', 'coag'):
            self.get_logger().warn(f'Unknown channel [{self._channel}], defaulting to [cut].')
            self._channel = 'cut'

        # -- Service clients --
        self._cli_cut  = self.create_client(SetBool, '/esu/cut')
        self._cli_coag = self.create_client(SetBool, '/esu/coag')

        self.get_logger().info('Waiting for ESU-TAP services...')
        self._cli_cut.wait_for_service()
        self._cli_coag.wait_for_service()
        self.get_logger().info(
            f'Connected. Commander started in [{self._mode}] mode (channel={self._channel}).'
        )

        # -- Launch mode --
        if self._mode == 'interactive':
            threading.Thread(target=self._interactive_loop, daemon=True).start()
        elif self._mode == 'pulse':
            self.create_timer(1.0, self._pulse_once)
        elif self._mode == 'script':
            self._script = [
                (1.0, 'press'), (0.5, 'release'),
                (2.0, 'press'), (0.5, 'release'),
                (1.5, 'press'), (0.5, 'release'),
            ]
            threading.Thread(target=self._run_script, daemon=True).start()
        else:
            self.get_logger().error(f'Unknown mode: {self._mode}')
            raise SystemExit(2)

    # -- Service call helper --
    def _client_for(self, channel):
        return self._cli_cut if channel == 'cut' else self._cli_coag

    def _call(self, channel: str, activate: bool):
        """Call the SetBool service for a channel and log the acknowledgement."""
        client = self._client_for(channel)
        req = SetBool.Request()
        req.data = activate

        future = client.call_async(req)
        # Spin this node until the response arrives or we time out.
        rclpy.spin_until_future_complete(self, future, timeout_sec=self._timeout)

        if future.done() and future.result() is not None:
            res = future.result()
            state = 'ON' if activate else 'OFF'
            ack = 'ok' if res.success else 'FAILED'
            self.get_logger().info(f'{channel.upper()} {state} -> {ack} ({res.message})')
            return res.success
        else:
            self.get_logger().error(
                f'{channel.upper()} {"ON" if activate else "OFF"} -> no response (timeout)'
            )
            return False

    def press(self):
        self._call(self._channel, True)

    def release(self):
        self._call(self._channel, False)

    # -- Interactive mode --
    def _interactive_loop(self):
        print('\n=== Pedal Commander (interactive, service client) ===')
        print(f'  Channel: {self._channel}')
        print('  ENTER       -> activate   (calls /esu/%s data=true)' % self._channel)
        print('  ENTER again -> deactivate (calls /esu/%s data=false)' % self._channel)
        print('  Ctrl+C      -> quit\n')
        pressed = False
        while True:
            input()
            if not pressed:
                self.press()
                pressed = True
            else:
                self.release()
                pressed = False

    # -- Pulse mode --
    def _pulse_once(self):
        self.press()
        time.sleep(self._pulse_ms / 1000.0)
        self.release()
        self.get_logger().info(f'Pulse complete ({self._pulse_ms} ms) on {self._channel}')
        raise SystemExit

    # -- Script mode --
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
            node.release()  # safety: always deactivate on exit
        except Exception:
            pass
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
