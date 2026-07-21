# IMERSE — ESU-TAP: ASG-300 DRE Foot Pedal Interface (micro-ROS)

This repo implements a **custom PCB interposer** (the ESU-TAP) that sits
electrically in-line between the **Bovie foot pedal** and the **DRE ASG-300
electrosurgical generator**. It has two goals:

- **Data collection**: timestamp and record when a surgeon physically
  presses/releases CUT or COAG on the foot pedal (for imitation learning)
- **Artificial activation**: inject a programmatic CUT/COAG signal from a
  computer without the surgeon pressing the pedal

The board reads the pedal's dry contacts to detect surgeon presses, and drives
a relay to inject computer-commanded activations. The ESP32 on the board runs
**micro-ROS** and connects to a PC running **ROS 2 Humble** over a wired USB
serial link.

```
Foot Pedal ──[cable]──► [ESU-TAP board] ──[cable]──► ASG-300 Generator
                              │
                       USB serial (micro-ROS)
                              │
                        PC (ROS 2 Humble)
```

## Architecture

The ESP32 is a first-class ROS 2 node (`esu_tap_node`) via micro-ROS:

| Interface | Type | Direction | Purpose |
|---|---|---|---|
| `/esu/cut` | `std_srvs/srv/SetBool` | ESP32 hosts, PC calls | activate/deactivate CUT (`data=true/false`) |
| `/esu/coag` | `std_srvs/srv/SetBool` | ESP32 hosts, PC calls | activate/deactivate COAG |
| `/esu/activation_state` | `std_msgs/msg/Int32MultiArray` | ESP32 publishes, PC logs | status stream `[cut, coag, source]` |

`source` is `0` for a surgeon press and `1` for a computer-commanded press,
attributed on the ESP32 using a command-time window.

This satisfies the project requirement: **service servers** for cut/coag
activation and deactivation, plus a **topic** that logs activation status.

The PC bridges the ESP32 into the ROS 2 graph with the **micro-ROS agent**
(a standard tool, run as one command — no custom bridge node).

## Repository layout

- `esu_tap_pcb/esu_tap_v1/` — KiCad schematic and PCB layout for the interposer
- `microros_firmware/esu_tap_microros.ino` — ESP32 micro-ROS firmware (flash this)
- `ros2_ws/src/pedal_controller/` — ROS 2 (ament_python) package:
  - `pedal_commander.py` — service **client**; commands cut/coag on/off
  - `pedal_logger.py` — subscribes to `/esu/activation_state`, logs edges to CSV
- `docs/`
  - `connector_documentation.md` — confirmed connector pinout and wiring
  - `da_vinci_foot_pedal_project.md` — early project brainstorming
- `ros2_ws/SETUP.md` — full build-and-run instructions

## Quickstart (ROS 2 Humble on Ubuntu)

See `ros2_ws/SETUP.md` for the complete walkthrough, including installing the
micro-ROS agent. In brief, in three sourced terminals:

```bash
# 1) micro-ROS agent (bridges the ESP32 over USB serial)
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyUSB0 -b 115200

# 2) logger  (writes CSV to ~/pedal_logs/)
ros2 run pedal_controller pedal_logger

# 3) commander  (interactive: ENTER toggles the channel)
ros2 run pedal_controller pedal_commander --ros-args -p channel:=cut
```

You can also drive the services directly:

```bash
ros2 service call /esu/cut std_srvs/srv/SetBool "{data: true}"
ros2 topic echo /esu/activation_state
```

Flash `microros_firmware/esu_tap_microros.ino` to the ESP32 with the Arduino
IDE and the `micro_ros_arduino` (Humble) library installed.

## Confirmed hardware interface

The pedal connector and cable were measured directly (see
`docs/connector_documentation.md`):

- **Connector:** Bulgin 400 Series Buccaneer, 3-pole
- **Cable:** Alpha Wire M9600010, 20 AWG, 1 triad, UL PLTW
- **Pinout:** Pin 1 = switched output; Pins 2 & 3 = common (internally bridged).
  Pressing the pedal shorts pin 1 to pins 2/3. Effectively an SPST dry contact.

To activate: relay shorts pin 1 to pin 2. To sense: optocoupler monitors pin 1
↔ pin 2.

## Design notes (PCB — schematic is a work in progress)

> The KiCad schematic is still being brought up to date with the current
> hardware decisions. The authoritative record of component choices lives in
> the design docs / lab notes; the notes below capture the direction but may
> lag the schematic. Verify against the board files before ordering.

- **MCU — ESP32-DevKitC-32E:** chosen for prototyping velocity (integrated
  USB-serial, 3.3 V regulator, decoupling, antenna, boot circuitry). 3.3 V GPIO
  aligns with the sense pull-up rail. Input-only pins IO34/IO35 are used for
  sensing and require **external** pull-ups (no internal pull-ups on those pins).
- **Relay — Omron G6K-2F-Y (non-latching SMD DPDT):** small SMD footprint,
  driven active-HIGH via a low-side MOSFET/transistor from a GPIO.
- **Sense path:** optocoupler-isolated reading of the pedal dry contacts,
  active-low into the MCU. Isolation matters in an electrosurgical environment.

## Notes / assumptions

- Intended for **research and data collection** with the DRE ASG-300. Any use
  in a live clinical environment requires signal characterization, galvanic
  isolation validation, and a safety/regulatory review.
- The interposer must be transparent to the ASG-300 when passive: it should not
  alter timing, impedance, or logic levels on the CUT/COAG lines.
- The ASG-300 uses first-come-first-served arbitration between channels; a
  commanded-but-suppressed activation can produce a mislabeled event, which is a
  data-integrity concern for imitation learning worth designing around.
