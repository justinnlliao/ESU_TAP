# ESU-TAP: Foot Pedal Interface (micro-ROS)

ESU-TAP is a research PCB interposer between an electrosurgical generator and its
footswitch. It logs pedal presses and lets a computer close the same footswitch
contacts over ROS 2, while the surgeon's pedal keeps working. It does not carry
the RF/patient output.

> **Research prototype. Not validated for clinical use.** Board-power loss is
> intended to fall back to the manual pedal, but this is not a verified fail-safe
> or emergency stop. Read [Safety and validation](docs/SAFETY.md)
> before connecting a generator, and test on a generator-disconnected fixture first.

## What you need

- An assembled ESU-TAP board ([hardware](hardware/README.md): v1, v2 or v3) with an ESP32-DevKitC
- Regulated 5 V DC, center-positive barrel supply for the relay rail; USB for the ESP32
- Ubuntu 22.04 with ROS 2 Humble and Docker (Docker runs only the micro-ROS agent)

## Quick start

```bash
git clone <this repo> && cd ESU_TAP
./esu.sh setup              # once: PlatformIO + ROS package; asks whether to pull the Docker agent
./esu.sh flash v3 pedal     # ESP32 plugged in, generator DISCONNECTED (v1/v2/v3; pedal or nopedal)
./esu.sh run                # agent + logger + commander in one tmux window
```

In the commander type `arm`, then `c`/`g`/`b`/`l` (cut/coag/bipolar/LigaSure),
`x` = all OFF and disarm, `q` = quit. `./esu.sh stop` stops everything.
`./esu.sh run v3 T01` also passes a trial ID to the logger.
`./esu.sh update` pulls, rebuilds and offers to reflash; `./esu.sh help` lists
everything. If `./esu.sh` says permission denied, use `bash esu.sh`.

- **pedal** (normal): boots in manual, with the pedal forwarded and logged.
  `/esu/arm` switches to autonomous (ROS drives the relays). Pressing any pedal
  cancels all computer commands and hands control back; re-arm to resume.
- **nopedal**: only for boards with nothing wired to the pedal inputs.

## Using ESU-TAP from your own ROS 2 nodes

Once flashed, only the micro-ROS agent has to run (`./esu.sh agent`). The board
then appears as ordinary services and a topic on `ROS_DOMAIN_ID` 0; no package
from this repository is needed.

| Interface | Type | Purpose |
| --- | --- | --- |
| `/esu/arm` | `std_srvs/srv/SetBool` | Enable/disable computer control (pedals always work) |
| `/esu/cut`, `/esu/coag`, `/esu/bipolar` | `std_srvs/srv/SetBool` | Set/clear a channel |
| `/esu/ligasure` | `std_srvs/srv/SetBool` | Set/clear LigaSure (v3 only) |
| `/esu/capabilities` | `std_srvs/srv/Trigger` | JSON: board, channels, firmware, armed state |
| `/esu/activation_state` | `std_msgs/msg/Int32` | Packed current state, published on change |

```bash
ros2 service call /esu/arm std_srvs/srv/SetBool "{data: true}"
ros2 service call /esu/cut std_srvs/srv/SetBool "{data: true}"
ros2 topic echo /esu/activation_state
```

A computer ON command expires after 500 ms: re-send ON about every 100 ms while
the channel should stay on. Only one node should send commands at a time.

`activation_state` bits 0-3 are CUT, COAG, bipolar, LigaSure; bits 4-5 are the
source: 0 pedal, 1 computer, 2 boot/reconnect baseline, 3 takeover (a pedal
press ended computer control; sent with the released computer channel, or with
the unchanged state when no computer output had to open).

To record data alongside your node, run `./esu.sh logger v3 <trial-id>`. It
writes `~/pedal_logs/pedal_log_<trial-id>_<time>.csv` plus a `.metadata.jsonl`.

### Package in another workspace

`software/ros2/src/pedal_controller` can be copied alone into another
workspace's `src/` and built with colcon; it depends only on `rclpy`,
`std_msgs` and `std_srvs`. From that workspace,
`bash src/pedal_controller/esu_run.sh v3` starts the agent, logger and commander.
See [setup](docs/SETUP.md#5-package-in-another-ros-2-workspace).

## How it works

Bypass relays route the pedal contacts to ESP32 inputs. The firmware closes
separate activation relays on the generator side when either a pedal is pressed
or an armed computer command is active. With board power off, the relays fall
back to connecting the pedal straight to the generator. Published state is
inferred from inputs and commands, not measured contact closure or RF delivery.

## Documentation

- [Setup guide](docs/SETUP.md): build, flash, run, logs
- [Safety and validation](docs/SAFETY.md): protections, known gaps, test record
- [Hardware](hardware/README.md) and [connectors](docs/CONNECTORS.md)
- [Changelog](CHANGELOG.md)

For contributors: [CONTRIBUTING.md](CONTRIBUTING.md) and
[docs/contributors/](docs/contributors/README.md) (testing, roadmap, firmware
internals, hardware proposals, enclosure).

## License

[Apache 2.0](LICENSE).
