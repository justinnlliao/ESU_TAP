import os

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    default_port = "COM3" if os.name == "nt" else "/dev/ttyUSB0"
    return LaunchDescription(
        [
            Node(
                package="pedal_controller",
                executable="esu_serial_bridge",
                name="esu_serial_bridge",
                output="screen",
                parameters=[
                    {
                        "port": os.environ.get("ESU_SERIAL_PORT", default_port),
                        "baud": 115200,
                        "read_timeout_s": 0.2,
                        "reconnect_s": 1.0,
                    }
                ],
            )
        ]
    )

