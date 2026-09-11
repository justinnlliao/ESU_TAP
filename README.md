# IMERSE — ESU-TAP: Foot Pedal Interface (micro-ROS)

ESU-TAP is a research PCB interposer for reading pedal dry contacts and issuing
computer-commanded contact closures to an electrosurgical generator's footswitch
interface. It does not intentionally carry the RF/patient output.

The design goals are data collection, computer activation, and manual pedal
pass-through on board power loss. These goals are not a verified system-level
fail-safe guarantee.

## Current status

- v1: historical monopolar hardware.
- v2: CUT, COAG, and bipolar hardware; the checked-in firmware targets this map.
- v3: adds a fourth hardware path labeled LigaSure. Reviewed using KiCad 10.
  LigaSure firmware and generator-specific compatibility are not complete.
- The current ROS logger still expects the old two-channel message and is
  incompatible with the firmware's three-channel status payload.

Read [Protection features and validation status](docs/SAFETY_AND_VALIDATION.md)
before use. This prototype is not validated for clinical use. Passing KiCad
checks or obtaining manufacturing files does not establish fault tolerance.
No numerical system reliability claim is supported.

## How it works

During active operation, bypass relays route the pedal contacts to ESP32 sense
inputs. External pull-ups make these active-low. The firmware drives separate
activation relays from the sensed state OR a computer command.

The activation relays close generator-side signal-to-common contacts. They do
not move the physical pedal contacts. Published state is inferred from inputs
and commands, not measured relay-contact closure or confirmed RF delivery.

The unpowered relay topology is intended to reconnect the pedal signals and
their respective generator commons directly. Verify this on the actual assembly.
Manual bypass is not an emergency stop: a pressed pedal may continue activation.

## Implemented protection and known gaps

The board includes input PTC/Schottky/TVS components, sense-line clamps and
series resistors, and watchdog-controlled bypass relays. These are individual
protection features, not evidence that the complete system is safe.

In reviewed v3 wiring, U10 RESET drives Q1 and bypass relays U6–U9 only.
It does not reset the ESP32 or independently disable activation relays U2–U5.
A frozen activation can remain connected across the generator input and its
common. The watchdog produces a temporary RESET pulse, not sustained fallback.

Powered-offline operation is different from unpowered bypass. Current firmware
stops pedal forwarding while waiting for the ROS agent but continues watchdog
petting. An ON command can also remain latched if the controlling application
dies while the agent stays alive.

See [wiring evidence and required tests](docs/SAFETY_AND_VALIDATION.md) and
[remaining work](docs/ROADMAP.md). Earlier blanket fail-safe claims are superseded.

## ROS 2 interface

| Interface | Type | Current firmware behavior |
| --- | --- | --- |
| `/esu/cut` | `std_srvs/srv/SetBool` | Set/clear CUT command |
| `/esu/coag` | `std_srvs/srv/SetBool` | Set/clear COAG command |
| `/esu/bipolar` | `std_srvs/srv/SetBool` | Set/clear bipolar command |
| `/esu/activation_state` | `std_msgs/msg/Int32MultiArray` | Inferred state stream |

Current firmware publishes `[cut, coag, bipolar, source]`.
Source is 0 for a sensed pedal edge, 1 for a computer-derived edge, and 2 for a
boot/reconnection baseline. Baseline does not necessarily mean a device reset.

The current logger reads `[cut, coag, source]` and can misread bipolar as source.
Do not use its current output as validated attribution. LigaSure services and
a coordinated four-channel message/consumer update are pending.

## Repository layout

- [Hardware](hardware/README.md): revision-specific KiCad projects, local libraries,
  and `fabrication/` exports.
- `firmware/esp32/`: PlatformIO project using `micro_ros_platformio`,
  not `micro_ros_arduino`.
- [ROS setup](software/ros2/SETUP.md): build, serial-agent, and development commands.
- [Testing](software/ros2/TESTING.md): legacy mock scope and required physical tests.
- [Connector notes](docs/connector_documentation.md): wiring notes requiring
  per-assembly verification.
- [Changelog](CHANGELOG.md): history and documentation corrections.

## Development quickstart

Use a disconnected low-voltage dummy contact fixture, not an operating generator.
Resolve the firmware/logger mismatch before treating test logs as valid.
The checked-in firmware is not a complete v3 implementation.

Build the ROS 2 Humble workspace on Ubuntu:

```bash
source /opt/ros/humble/setup.bash
cd ~/ESU_TAP/software/ros2
colcon build
source install/setup.bash
```

Build the firmware from its own directory. Upload only to the intended board
with generator connections removed and the correct serial port selected:

```bash
cd ~/ESU_TAP/firmware/esp32
pio run
# Optional bench upload; replace with your actual port:
pio run -t upload --upload-port /dev/ttyUSB0
```

Run the serial agent:

```bash
docker run -it --rm -v /dev:/dev --privileged --net=host \
  microros/micro-ros-agent:humble serial --dev /dev/ttyUSB0 -b 115200
```

See the setup guide for logger/commander commands and their current limitations.
Auto-reconnection is implemented in software; it is not a safety guarantee.
Changing micro-ROS entity limits in `colcon.meta` requires rebuilding its library
with `pio run -t clean_microros`.

## Power and assembly

Use regulated 5 V DC, center-positive barrel power for the relay rail.
USB powers the ESP32/3.3 V logic and carries serial data. In reviewed v3, the
barrel rail does not connect to the ESP32's EXT_5V header. Loss of either supply
must be tested separately. Input protection is not a validated wrong-voltage cutoff.

Use the exact revision's schematic fields, PCB, and assembly BOM for part
references. Hand-installed parts are separate from SMD assembly files.
Review JLCPCB's placement preview and stock before approving an order; these
checks do not resolve the functional limitations above.

## License

See [LICENSE](LICENSE).
