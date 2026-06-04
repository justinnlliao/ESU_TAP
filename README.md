# IMERSE — ASG300 DRE Foot Pedal PCB Interface (ROS 2 + Serial MCU)

This repo implements a **custom PCB interposer** that sits electrically in-line between the **ASG300 DRE electrosurgical generator's foot pedal** and the generator itself. It has two goals:

- **Data Collection**: timestamp and record when a surgeon physically presses/releases CUT or COAG on the foot pedal
- **Artificial Activation**: inject a programmatic CUT/COAG signal from a computer without the surgeon pressing the pedal

The PCB is placed mid-cable between the foot pedal and the ASG300 DRE generator. Its MCU monitors the CUT/COAG lines to detect surgeon presses and drives those lines to inject computer-commanded activations. The embedded side speaks a **simple USB serial ASCII protocol** to a laptop running **ROS 2 Humble**.

## Hardware

### PCB Interposer

The custom PCB (`pedal_pcb/`) is the core of this system. It is wired in series between the foot pedal cable and the ASG300 DRE generator input:

```
Foot Pedal ──[cable]──► [PCB Interposer] ──[cable]──► ASG300 DRE Generator
                              │
                         USB Serial
                              │
                           Computer
                         (ROS 2 node)
```

The MCU on the PCB:
- Reads the physical CUT and COAG lines (detecting surgeon foot presses)
- Drives those same lines to inject artificial activations on command from the computer

### Connectors

The PCB enclosure uses **TE Connectivity** circular connectors. The female panel sockets mount on the PCB enclosure walls; the male inline plugs terminate the cables on both sides.

| Part Number | Type | Location |
|-------------|------|----------|
| TE 206430-1 | Female panel socket (box/wall mount) | PCB enclosure panel (both sides) |
| TE 206429-1 | Male inline plug (cable ends) | Foot pedal cable end and generator cable end |
| 66105-4 | Socket crimp contact | Loaded into TE 206430-1 |
| 66103-4 | Pin crimp contact | Loaded into TE 206429-1 |

See [`docs/connector_documentation.md`](docs/connector_documentation.md) for full pinout and wiring notes.

## Repository layout

- `pedal_pcb/`
  - KiCad schematic and PCB layout for the in-line interposer board
- `ros2_ws/src/pedal_controller/`
  - ROS 2 (ament_python) package with:
    - `esu_serial_bridge.py`: USB serial ↔ ROS 2 bridge
    - `pedal_commander.py`: publishes commands to ROS 2
    - `pedal_logger.py`: logs press/release edges to CSV
    - `launch/esu_serial_bridge.launch.py`: bridge launch file
- `mcu_serial_firmware/`
  - MCU firmware (`.ino`) that reads two physical switches and drives two outputs, speaking the ASCII protocol over USB serial
- `docs/`
  - Connector specs and pinout (`connector_documentation.md`)
  - Early project brainstorming and approach comparison (`da_vinci_foot_pedal_project.md`)
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

- This is intended for **research and data collection** with an ASG300 DRE electrosurgical generator. Any use in a live clinical environment requires signal characterization, galvanic isolation, and a safety/regulatory review.
- The PCB interposer must be transparent to the ASG300: it should not alter signal timing, impedance, or logic levels on the CUT/COAG lines when in passive monitoring mode.
