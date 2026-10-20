# ESU-TAP: Foot Pedal Interface (micro-ROS)

ESU-TAP is a research PCB interposer for reading pedal dry contacts and issuing
computer-commanded contact closures to an electrosurgical generator's footswitch
interface. It does not intentionally carry the RF/patient output.

The design goals are data collection, computer activation, and manual pedal
pass-through on board power loss. These goals are not a verified system-level
fail-safe guarantee.

## Quick start on a new computer (Ubuntu 22.04 + ROS 2 Humble)

```bash
git clone <this repo> && cd ESU_TAP
./esu.sh setup              # once: PlatformIO + ROS package; asks whether to pull the Docker agent
./esu.sh flash v1 pedal     # plug in the ESP32, generator DISCONNECTED (or: nopedal, v2, v3)
./esu.sh run                # agent + logger + commander in one tmux window
```

After a `git pull` elsewhere, `./esu.sh update` pulls, rebuilds, and offers to
reflash the board/mode last flashed from this computer. The ESP32 port is found
automatically under `/dev/serial/by-id` (you pick if there are several).
`./esu.sh status` shows what is installed; `./esu.sh help` lists everything.
The script only wraps `software/esu.py`; see the [setup guide](software/ros2/SETUP.md)
for what each step does. If `./esu.sh` says permission denied, use `bash esu.sh`.

- **pedal**: a foot pedal is wired in; surgeon presses are forwarded and logged.
- **nopedal**: standalone/autonomous; pedal inputs are ignored, only ROS drives relays.
- **Docker**: only the micro-ROS agent uses it. `./esu.sh docker` pulls the image
  ahead of time (optional; the first `run` pulls it otherwise).

## Current status

- v1: legacy two-channel hardware remains supported by the shared v1 profile.
- v2: six-relay CUT, COAG, and bipolar hardware and a dedicated firmware project.
- v3: latest design, eight relays; adds a fourth hardware path labeled LigaSure. Reviewed using KiCad 10.
  The shared v3 firmware profile implements LigaSure; generator-specific compatibility
  and physical fault-response validation remain incomplete.
- ROS commander/logger support all three revision interfaces. Mock and bench
  tools select a revision explicitly. See the testing guide for scope and limits.

Read [Protection features and validation status](docs/SAFETY_AND_VALIDATION.md)
before use. This prototype is not validated for clinical use. Passing KiCad
checks or obtaining manufacturing files does not establish fault tolerance.
No numerical system reliability claim is supported.

The 2026-10-13 [shared firmware](firmware/README.md) is a **bench candidate**:
one implementation, explicit revision profiles, protocol-2 capability discovery,
local pedal processing independent of ROS, and expiring/re-armed computer commands.
It has not been flashed or physically qualified by this update. Use the
[unified installation guide](software/ros2/SETUP.md), not historical baud/array examples.

The 2026-10-19 update keeps that design and changes: 115200 baud on every
profile; a pedal-connected (default) vs standalone/autonomous build option;
lost telemetry is resynced with a fresh snapshot instead of dropping the link;
the client tolerates one missed command renewal; plain operator text in the
logger ("cut on", "coag off"); and the jazzy micro-ROS agent image. See the
[changelog](CHANGELOG.md).

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

## Reported phantom-test setup (2026-10-13)

The operator reports supervised phantom testing with the generator connected
and a button that cuts interface-board power, not generator power. The exact
assembled revision, switch wiring, and cutoff/restart measurements are not
recorded here. This statement is not test approval or evidence of RF shutdown.

If the button removes all relay-coil power, functioning activation relays should
open while bypass relays restore the manual pedal path. A held pedal can still
activate the generator; a welded contact may remain closed. Describe this as
an intended **computer-control cutoff with manual pedal fallback**, not a
verified stop-all-RF emergency stop. Verify USB/other supply paths and behavior
on power restoration on a generator-disconnected fixture first.

See [cutoff limitations and test records](docs/SAFETY_AND_VALIDATION.md#reported-board-power-cutoff-and-phantom-testing)
and [proposed hardware changes](docs/HARDWARE_FAULT_HANDLING.md).

## Implemented protection and known gaps

The board includes input PTC/Schottky/TVS components, sense-line clamps and
series resistors, and watchdog-controlled bypass relays. These are individual
protection features, not evidence that the complete system is safe.

In reviewed v3 wiring, U10 RESET drives Q1 and bypass relays U6–U9 only.
It does not reset the ESP32 or independently disable activation relays U2–U5.
A frozen activation can remain connected across the generator input and its
common. The watchdog produces a temporary RESET pulse, not sustained fallback.

Powered-offline operation is different from unpowered bypass. The shared bench
candidate processes local pedals in a dedicated task and expires computer ON
commands after 500 ms without renewal. Expiry/disconnect disarms computer control;
the client renews every 100 ms, tolerates one missed renewal, and requires
deliberate re-arm after two misses or any other fault.
These source-level changes need full target/runtime and physical validation.
Already-flashed historical firmware may still stop forwarding offline and latch ON.

See [wiring evidence and required tests](docs/SAFETY_AND_VALIDATION.md) and
[remaining work](docs/ROADMAP.md). Earlier blanket fail-safe claims are superseded.

## ROS 2 interface

| Interface | Type | Current firmware behavior |
| --- | --- | --- |
| `/esu/cut` | `std_srvs/srv/SetBool` | Set/clear CUT command |
| `/esu/coag` | `std_srvs/srv/SetBool` | Set/clear COAG command |
| `/esu/bipolar` | `std_srvs/srv/SetBool` | Set/clear bipolar command |
| `/esu/ligasure` | `std_srvs/srv/SetBool` | Set/clear LigaSure command (v3 only) |
| `/esu/arm` | `std_srvs/srv/SetBool` | Explicit computer arm/disarm; does not disable pedals |
| `/esu/capabilities` | `std_srvs/srv/Trigger` | Read-only JSON profile, features, snapshot and diagnostics |
| `/esu/activation_state` | `std_msgs/msg/Int32` | Packed inferred state stream, all profiles |

All shared profiles encode CUT/COAG/bipolar/LigaSure in bits 0-3 and source in
bits 4-5. Unavailable bits stay zero; capabilities identify the channel count.
Source is 0 for a sensed pedal edge, 1 for a computer-derived edge, and 2 for a
boot/reconnection baseline. Baseline does not necessarily mean a device reset.

The logger validates capabilities and the packed schema. Explicit read-only
legacy modes also support historical array and packed images.
First observations and reconnection baselines are logged as `sync`, not invented
press/release events. Messages are change-only; capability discovery supplies a
late logger's initial snapshot. Offline transitions are not replayed, and
telemetry does not provide exhaustive loss detection.
Inferred effective-state edges do not capture every overlapping pedal/command action.

## Repository layout

- [Hardware](hardware/README.md): revision-specific KiCad projects, local libraries,
  and `fabrication/` exports.
- [Shared firmware](firmware/README.md): common control/runtime with v1/v2/v3
  profiles. Old revision directories are thin compatibility entry points.
- `software/esu.py`: path-independent setup/build/flash/agent/logger helper.
- [ROS setup](software/ros2/SETUP.md): build, serial-agent, and development commands.
- [Testing](software/ros2/TESTING.md): offline regressions, revision-selectable
  mock and dummy-fixture checks, and required physical tests.
- [Connector notes](docs/connector_documentation.md): wiring notes requiring
  per-assembly verification.
- [Changelog](CHANGELOG.md): history and documentation corrections.

## Development quickstart

Use Ubuntu 22.04 / ROS Humble and a generator-disconnected fixture. From the
repository root, with the prerequisites in [setup](software/ros2/SETUP.md):

```bash
./esu.sh setup                       # or: python3 software/esu.py setup && ... host-build
python3 software/esu.py build --board v3
```

Substitute the actual board revision; v1 is explicitly supported. The setup guide
gives one command per runtime pane and guarded flashing with an explicit port.
All profiles use 115200 baud. Command expiry is a software mitigation, not
independent hardware shutdown. No device is flashed by building the source.

Firmware assumes a pedal is connected. For standalone/autonomous use with no
pedal, build/flash with `--no-pedal`: the sense inputs are then ignored, so
unwired inputs cannot read as phantom presses. The logger reports which mode
the board is in. In the default mode an unplugged pedal relies on the board's
pull-ups; inputs without them float and can activate relays.

## Quick run: standalone (no pedal)

Generator disconnected. Replace `v2` with the actual board and `PORT` with the
ESP32's device (`ls -l /dev/serial/by-id/`; on the lab PC, the CP2102N entry).
Each new terminal starts with `cd ~/ESU_TAP` (or wherever your clone lives).

Terminal 1, flash once (skip if already flashed with `--no-pedal`), then the agent:

```bash
docker stop esu-agent 2>/dev/null
python3 software/esu.py flash --board v2 --port PORT --fixture-confirmed --no-pedal
python3 software/esu.py agent --port PORT
```

Terminal 2, logger (writes `~/pedal_logs/pedal_log_<time>.csv` and `.metadata.jsonl`):

```bash
python3 software/esu.py logger --board v2
```

Terminal 3, commander: type `arm`, then c/g/b (cut/coag/bipolar), x=OFF+disarm, q=quit.

```bash
python3 software/esu.py commander --board v2 --fixture-confirmed
```

Optional latency test, in terminal 3 after quitting the commander (only one
commanding client at a time). Repeat with `channel:=coag` / `bipolar`:

```bash
source /opt/ros/humble/setup.bash && source software/ros2/install/setup.bash
export ROS_DOMAIN_ID=0
ros2 run pedal_controller latency_test --ros-args \
  -p board_version:=v2 -p fixture_confirmed:=true -p channel:=cut -p iterations:=100
```

This measures PC-side command/telemetry receipt times only, not contact or RF
timing. To return to pedal mode, reflash without `--no-pedal` and restart the commander.

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
