#!/usr/bin/env python3
"""
mock_esu_node.py

Software stand-in for the ESU-TAP ESP32 firmware, for testing the ROS 2 stack
BEFORE the physical board arrives.

It implements the legacy two-channel interface, not the current firmware's
four-field CUT/COAG/bipolar/source contract:

  SERVICES (hosted here, called by pedal_commander):
    /esu/cut    (std_srvs/SetBool)  data=true -> CUT on,  false -> CUT off
    /esu/coag   (std_srvs/SetBool)  data=true -> COAG on, false -> COAG off

  TOPIC (published here, logged by pedal_logger):
    /esu/activation_state  (std_msgs/Int32MultiArray)  [cut, coag, source]
      source: 0 = surgeon, 1 = computer

Mock behavior (not an exact firmware model):
  - When a service is called, it drives the internal cut/coag state and
    publishes a new activation_state with source=1 (computer).
  - It also SIMULATES surgeon presses on a timer (source=0) so you can see the
    logger attribute both sources correctly. Toggle with the 'sim_surgeon'
    parameter.

This is NOT flight code. It exists only so the real commander and real logger
can be exercised end-to-end without hardware.

KNOWN LIMITATION -- read before trusting a green test run:
  This node publishes directly from its service callbacks. The firmware does
  NOT; it has a single publish path in its timer callback. That difference
  concealed a firmware bug (see docs/archive/ESU_TAP_v2_change_list.md 1.4)
  in which computer-commanded activations were never published at all, because
  the sense pins read the pedal contacts and a relay command does not move
  them. This mock passed cleanly the whole time.

  Treat a passing run here as evidence about the ROS 2 stack only -- the
  topic/service contract, the commander, and the logger. It says nothing about
  whether the firmware actually emits the events it should.

Run:
  ros2 run pedal_controller mock_esu_node
  ros2 run pedal_controller mock_esu_node --ros-args -p sim_surgeon:=false
"""

import rclpy
from rclpy.node import Node
from std_srvs.srv import SetBool
from std_msgs.msg import Int32MultiArray


class MockEsuNode(Node):
    def __init__(self):
        super().__init__('mock_esu_node')

        # -- Parameters --
        self.declare_parameter('sim_surgeon', True)      # periodically fake surgeon presses
        self.declare_parameter('sim_period_s', 5.0)      # how often to fake one
        self._sim_surgeon = self.get_parameter('sim_surgeon').get_parameter_value().bool_value
        self._sim_period  = float(self.get_parameter('sim_period_s').get_parameter_value().double_value)

        # -- Internal "hardware" state --
        self._cut = 0
        self._coag = 0

        # -- Publisher: activation status --
        self._pub = self.create_publisher(Int32MultiArray, '/esu/activation_state', 10)

        # -- Service servers (mimic the ESP32) --
        self.create_service(SetBool, '/esu/cut',  self._on_cut)
        self.create_service(SetBool, '/esu/coag', self._on_coag)

        # -- Optional simulated surgeon presses --
        if self._sim_surgeon:
            self._sim_state = False
            self.create_timer(self._sim_period, self._sim_surgeon_press)

        # Publish an initial state so subscribers have a baseline
        self._publish(source=0)

        self.get_logger().info(
            'Mock ESU node up. Services: /esu/cut, /esu/coag. '
            'Publishing /esu/activation_state. '
            f'Surgeon simulation: {"ON" if self._sim_surgeon else "OFF"}.'
        )

    # -- Publish helper --
    def _publish(self, source: int):
        msg = Int32MultiArray()
        msg.data = [self._cut, self._coag, source]
        self._pub.publish(msg)

    # -- Service callbacks (source = computer = 1) --
    def _on_cut(self, request, response):
        self._cut = 1 if request.data else 0
        self._publish(source=1)
        response.success = True
        response.message = 'cut on' if request.data else 'cut off'
        self.get_logger().info(f'[service] {response.message}')
        return response

    def _on_coag(self, request, response):
        self._coag = 1 if request.data else 0
        self._publish(source=1)
        response.success = True
        response.message = 'coag on' if request.data else 'coag off'
        self.get_logger().info(f'[service] {response.message}')
        return response

    # -- Simulated surgeon press (source = surgeon = 0) --
    def _sim_surgeon_press(self):
        self._sim_state = not self._sim_state
        self._cut = 1 if self._sim_state else 0
        self._publish(source=0)
        self.get_logger().info(
            f'[sim surgeon] cut {"press" if self._sim_state else "release"}'
        )


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
