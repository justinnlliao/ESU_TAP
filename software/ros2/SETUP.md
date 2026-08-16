# Build and run `pedal_controller` (ESU-TAP)

This is the PC-side ROS 2 package for the ESU-TAP foot pedal interposer.
It talks to the ESP32, which runs micro-ROS firmware (`firmware/esp32/`)
and connects over a **wired USB serial** link via the micro-ROS agent.

Workspace layout:

    software/ros2/src/pedal_controller/

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

From the `software/ros2` folder (the parent of `src`):

    source /opt/ros/humble/setup.bash
    cd ~/ESU_TAP/software/ros2
    colcon build
    source install/setup.bash

> Build from `~/ESU_TAP/software/ros2`, NOT from your home directory. Running
> `colcon build` in `~` dumps `build/ install/ log/` into your home folder
> (colcon searches recursively and finds the package anyway). If that happens,
> `rm -rf ~/build ~/install ~/log` and rebuild from the right place.

## 4. Run the system — the exact terminals

The firmware **auto-connects and auto-reconnects**, so you do NOT need to press
EN, and boot order no longer matters. Start these in any order.

In every terminal below, first source both:

    source /opt/ros/humble/setup.bash
    source ~/ESU_TAP/software/ros2/install/setup.bash

**Terminal 1 — micro-ROS agent** (bridges the ESP32 over USB serial). Docker is
the supported path on `blue`:

    docker run -it --rm -v /dev:/dev --privileged --net=host \
      microros/micro-ros-agent:humble serial --dev /dev/ttyUSB0 -b 115200

Within a second or two you should see `session established` and entities being
created, WITHOUT pressing EN. If you restart the agent, the board reconnects on
its own. (If the port is busy: `sudo fuser -k /dev/ttyUSB0`, then rerun.)

**Terminal 2 — logger** (records activations to CSV in `~/pedal_logs/`):

    ros2 run pedal_controller pedal_logger

**Terminal 3 — commander** (interactive keyboard console):

    ros2 run pedal_controller pedal_commander

    #   c  ENTER  -> toggle CUT
    #   g  ENTER  -> toggle COAG
    #   x  ENTER  -> all OFF (panic)
    #   s  ENTER  -> show state
    #   h  ENTER  -> help

Or drive the services directly, no commander needed:

    ros2 service call /esu/cut  std_srvs/srv/SetBool "{data: true}"
    ros2 service call /esu/cut  std_srvs/srv/SetBool "{data: false}"
    ros2 topic echo /esu/activation_state

### Optional test / benchmark nodes (Terminal 3, in place of the commander)

**Interactive full-system acceptance test** — walks CUT/COAG for both computer
and surgeon paths, cross-checks published telemetry, prints pass/fail:

    ros2 run pedal_controller system_test

**Automated latency benchmark** — toggles a channel N times, reports round-trip
and command latency stats. Run with the generator RF output OFF:

    ros2 run pedal_controller latency_test
    ros2 run pedal_controller latency_test --ros-args -p iterations:=200 -p channel:=coag

### Pre-hardware testing (no board)

To exercise the ROS 2 stack without the ESP32, replace Terminal 1's agent with
the mock node. See `TESTING.md`.

    ros2 run pedal_controller mock_esu_node

## 5. Flashing the ESP32 firmware

The firmware lives in `firmware/esp32/`, built with **PlatformIO** (VS Code
extension). Open the `firmware/esp32/` folder as the PlatformIO project root --
not the repo root, or PlatformIO will not find `platformio.ini`.

    firmware/esp32/
      platformio.ini
      src/esu_tap_microros.cpp

Build and upload from the PlatformIO toolbar, or:

    cd ~/ESU_TAP/firmware/esp32
    pio run -t upload --upload-port /dev/ttyUSB0

> `pio` is the VS Code extension's Core 6.x at `~/.platformio/penv/bin/pio`
> (on PATH via `.bashrc`). `platformio.ini` names `/dev/esp32-esu`, but that
> udev symlink is not resolving yet, so pass `--upload-port /dev/ttyUSB0`
> explicitly for now.

**Stop the agent before flashing** — `sudo fuser -k /dev/ttyUSB0` if you get
"could not open port" or "multiple access on port". Only one thing (agent,
flasher, or serial monitor) can own the port at a time; this is the cause of
nearly every serial error.

**If upload fails with "no serial data received":** hold BOOT, tap EN, release
EN, keep holding BOOT until "Connecting..." becomes "Chip is ESP32...", release.

**The first build is slow** (several minutes) -- `micro_ros_platformio` compiles
the micro-ROS stack from source. Later builds are incremental. After editing
`colcon.meta`, force a rebuild of the micro-ROS library: `pio run -t clean_microros`.

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
