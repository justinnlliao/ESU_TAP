# Build and run `pedal_controller` (ESU-TAP)

This is the PC-side ROS 2 package for the ESU-TAP foot pedal interposer.
It talks to the ESP32, which runs micro-ROS firmware (`microros_firmware/`)
and connects over a **wired USB serial** link via the micro-ROS agent.

Workspace layout:

    ros2_ws/src/pedal_controller/

## Architecture

    ESP32 (esu_tap_node, micro-ROS)              PC (ROS 2 Humble)
    ---------------------------------            --------------------------------
    service server  /esu/cut   (SetBool) <-----  pedal_commander (service client)
    service server  /esu/coag  (SetBool) <-----
    publisher /esu/activation_state       ----->  pedal_logger (subscriber)
       (Int32MultiArray [cut, coag, source])

The micro-ROS **agent** on the PC bridges the ESP32's USB serial to the ROS 2
graph. It replaces the old custom serial bridge node.

## 1. Install ROS 2 Humble

Target distro is **ROS 2 Humble** (Ubuntu 22.04). On the lab Ubuntu machine it
is already installed at `/opt/ros/humble`. Source it in every shell:

    source /opt/ros/humble/setup.bash

Confirm:

    ros2 --version

## 2. Install the micro-ROS agent

The agent is what connects the ESP32 to ROS 2. Easiest is the Docker image:

    docker run -it --rm -v /dev:/dev --privileged --net=host \
      microros/micro-ros-agent:humble serial --dev /dev/ttyUSB0 -b 115200

Or build the agent from source (one-time) into a separate workspace:

    mkdir -p ~/uros_ws/src && cd ~/uros_ws
    git clone -b humble https://github.com/micro-ROS/micro_ros_setup.git src/micro_ros_setup
    rosdep install --from-paths src --ignore-src -y
    colcon build
    source install/local_setup.bash
    ros2 run micro_ros_setup create_agent_ws.sh
    ros2 run micro_ros_setup build_agent.sh
    source install/local_setup.bash

Then run it with:

    ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyUSB0 -b 115200

Find the ESP32 port with `ls /dev/ttyUSB* /dev/ttyACM*`. If you get a permission
error, add yourself to the dialout group once: `sudo usermod -aG dialout $USER`
(then log out and back in).

## 3. Build this workspace

From the `ros2_ws` folder (the parent of `src`):

    rosdep install --from-paths src --ignore-src -r -y
    colcon build --packages-select pedal_controller
    source install/local_setup.bash

## 4. Run the system

Open three terminals (source ROS 2 + this workspace in each).

**Terminal 1 - micro-ROS agent** (bridges the ESP32):

    ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyUSB0 -b 115200

**Terminal 2 - logger** (records activations to CSV in `~/pedal_logs/`):

    ros2 run pedal_controller pedal_logger

**Terminal 3 - commander** (sends activation commands):

    # interactive: ENTER toggles the channel on/off
    ros2 run pedal_controller pedal_commander

    # single timed pulse on cut for 500 ms:
    ros2 run pedal_controller pedal_commander --ros-args -p mode:=pulse -p pulse_ms:=500 -p channel:=cut

    # command the coag channel instead:
    ros2 run pedal_controller pedal_commander --ros-args -p channel:=coag

You can also call the services directly without the commander node:

    ros2 service call /esu/cut  std_srvs/srv/SetBool "{data: true}"
    ros2 service call /esu/cut  std_srvs/srv/SetBool "{data: false}"

And watch the status stream:

    ros2 topic echo /esu/activation_state

## 5. Flashing the ESP32 firmware

The firmware lives in `microros_firmware/esu_tap_microros.ino`. Flash it with the
Arduino IDE using the **micro_ros_arduino** library (Humble branch) installed.
The board target is your ESP32 dev board (e.g. ESP32-DEVKITC-32E).

## Notes

- Requirements met: (1) service servers for cut/coag activation and
  deactivation, (2) a topic that logs activation/deactivation status.
- Source attribution (surgeon vs computer) is done on the ESP32 and reported
  in the third field of `/esu/activation_state`.
- The workspace targets Ubuntu 22.04. Windows is possible but the agent and
  serial ports differ; Ubuntu is the supported path.
