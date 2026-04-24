# IMERSE — Da Vinci Foot Pedal Interface (ROS 2 + Serial MCU)

This repo implements a **low-risk v1** interface for a Da Vinci foot pedal / ESU-style “CUT/COAG” activation with two goals:

- **Actuation**: trigger CUT/COAG programmatically from a computer
- **Logging**: timestamp when a human physically presses/releases CUT/COAG

The embedded side uses a **simple USB serial ASCII protocol**. The laptop side runs **ROS 2 Humble** with a serial bridge + commander + logger.

## Repository layout

- `ros2_ws/src/pedal_controller/`
  - ROS 2 (ament_python) package with:
    - `esu_serial_bridge.py`: USB serial ↔ ROS 2 bridge
    - `pedal_commander.py`: publishes commands to ROS 2
    - `pedal_logger.py`: logs press/release edges to CSV
    - `launch/esu_serial_bridge.launch.py`: bridge launch file
- `mcu_serial_firmware/`
  - MCU firmware (`.ino`) that reads two physical switches and drives two outputs, speaking the ASCII protocol over USB serial.
- `docs/`
  - Background + connector notes (`connector_documentation.md`)
  - Early project brainstorming (`da_vinci_foot_pedal_project.md`)
- `Literature Review/`
  - Reference material (papers/notes)

## MCU ↔ PC serial protocol

MCU → PC (state updates, newline-delimited):

- `STATE cut=<0|1> coag=<0|1> ts=<millis>\n`

PC → MCU (commands, newline-delimited; case-insensitive):

- `CUT_ON <ms>`
- `COAG_ON <ms>`
- `CUT_OFF`
- `COAG_OFF`

`<ms>` is optional; if provided the MCU will auto-release after that duration.

## ROS 2 topics (current)

- **Published by bridge**
  - `/esu/activation_state` (`std_msgs/String`)
    - Example: `cut=0 coag=1 ts=123456`
- **Subscribed by bridge**
  - `/esu/command` (`std_msgs/String`)
    - Examples: `CUT_ON 300`, `COAG_OFF`

The logger subscribes to `/esu/activation_state` and emits press/release edges into the CSV log.

## Quickstart (ROS 2 Humble)

If ROS 2 is not installed yet, follow **`ros2_ws/SETUP.md`** (Windows binary install, colcon, pyserial) before the steps below.

### 1) Build the ROS 2 package

From the `ros2_ws` directory:

```bash
colcon build --merge-install --packages-select pedal_controller
```

Linux/macOS: `source install/local_setup.bash`  
Windows **cmd** after `call <ros2 install>\local_setup.bat`: `call install\local_setup.bat`  
Windows **PowerShell**: `.\install\local_setup.ps1` if present, otherwise use **cmd** as above.

### 2) Flash the MCU

Open `mcu_serial_firmware/pedal_firmware.ino` in Arduino IDE and flash it to your board.

### 3) Run the bridge

Windows (default `COM3`):

```bash
ros2 launch pedal_controller esu_serial_bridge.launch.py
```

Linux (default `/dev/ttyUSB0`), or override explicitly:

```bash
ESU_SERIAL_PORT=/dev/ttyUSB0 ros2 launch pedal_controller esu_serial_bridge.launch.py
```

### 4) Start logging

```bash
ros2 run pedal_controller pedal_logger
```

Logs are written to `~/pedal_logs/` by default.

### 5) Send commands

Interactive (toggle ON/OFF with ENTER):

```bash
ros2 run pedal_controller pedal_commander --ros-args -p mode:=interactive -p channel:=cut
```

Pulse:

```bash
ros2 run pedal_controller pedal_commander --ros-args -p mode:=pulse -p pulse_ms:=300 -p channel:=coag
```

## Notes / assumptions

- This is intended for **bench testing and early demos**. Any real integration into medical hardware needs signal characterization, isolation, and a safety plan.
