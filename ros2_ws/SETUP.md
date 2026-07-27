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

The firmware lives in `microros_firmware/`, built with **PlatformIO** (VS Code
extension). Open the `microros_firmware/` folder as the PlatformIO project root --
not the repo root, or PlatformIO will not find `platformio.ini`.

    microros_firmware/
      platformio.ini
      src/esu_tap_microros.cpp

Build and upload from the PlatformIO toolbar, or:

    cd ~/ESU_TAP/microros_firmware
    pio run -t upload

**The first build is slow** (several minutes) -- `micro_ros_platformio` compiles
the micro-ROS stack from source. Later builds are incremental.

**Library note:** this project uses `micro_ros_platformio`, NOT
`micro_ros_arduino`. They expose different transport setup calls
(`set_microros_serial_transports(Serial)` vs `set_microros_transports()`).
Switching to the Arduino IDE means changing that call and the include.

**Close the PlatformIO Serial Monitor before starting the agent** -- both want
exclusive access to `/dev/ttyUSB0`, and the agent will sit silent if the monitor
holds it.

## Notes

- Requirements met: (1) service servers for cut/coag activation and
  deactivation, (2) a topic that logs activation/deactivation status.
- Source attribution (surgeon vs computer) is done on the ESP32 and reported
  in the third field of `/esu/activation_state`.
- The workspace targets Ubuntu 22.04. Windows is possible but the agent and
  serial ports differ; Ubuntu is the supported path.
