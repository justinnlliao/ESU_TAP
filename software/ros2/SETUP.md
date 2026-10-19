# Unified firmware and software setup

Bench candidate updated 2026-10-13. Use Ubuntu 22.04, ROS 2 Humble and the
physical board's explicit v1/v2/v3 profile. The same PC package supports all three.
No clinical qualification or full ESP32/ROS integration pass is implied.
Keep the generator disconnected for installation, flashing and fixture tests.

## Prerequisites (one time on the Ubuntu computer)

Install ROS 2 Humble and Docker using their official instructions. With your
administrator's approval, install git, cmake, build-essential, python3-pip,
python3-venv, colcon and rosdep. Ensure your account can access the ESP32 serial
device and Docker; this helper does not change groups or install system packages.
Use the system Python/ROS environment rather than an active Conda environment.

Open a terminal **in your clone's root**; clone paths differ between accounts.
The helper resolves the repository from its own file, not from your home folder.

```bash
python3 software/esu.py doctor
python3 software/esu.py setup
python3 software/esu.py host-build
```

If ROS dependencies are missing, source `/opt/ros/humble/setup.bash` and run
`rosdep install --from-paths software/ros2/src --ignore-src -r -y` from the
repository root, then repeat host-build. The helper always builds from the ROS
workspace with `--base-paths src`, so it does not scan home/Anaconda packages.

Setup creates/reuses `~/.platformio/penv` (or `PLATFORMIO_CORE_DIR/penv`) so the
micro-ROS builder's activation script exists. It never reflashes a board.
See [firmware profiles and dependency limits](../../firmware/README.md).

## Select and build the physical board

| PCB | Build profile | Channels | External watchdog |
| --- | --- | --- | --- |
| v1, legacy | v1 | CUT, COAG | No |
| v2, six relays | v2 | CUT, COAG, bipolar | Yes, bypass only |
| v3, eight relays | v3 | CUT, COAG, bipolar, LigaSure | Yes, bypass only |

```bash
python3 software/esu.py build --board v3
```

Replace v3 with the actual revision. First build downloads/compiles dependencies
and may take several minutes. No hardware auto-detection is possible: all use
an ESP32, but v1 sense/LED pins differ. Firmware capabilities report what was
flashed, not what board is physically attached.

**Pedal connected (default) vs standalone.** Add `--no-pedal` to `build` and
`flash` for a board used without a pedal (autonomous runs). That image ignores
the sense inputs entirely, so unwired inputs cannot read as phantom presses or
block arming; only ROS commands drive the relays. Reflash without the flag to
record surgeon pedal data again. The logger prints which mode the board reports.

Find the ESP32 using `ls -l /dev/serial/by-id/`, not a guessed ttyUSB number.
Stop the existing serial agent and serial monitor before flashing. Substitute
the **actual** device path below; the example path is deliberately a placeholder.

```bash
python3 software/esu.py flash --board v3 --port /dev/serial/by-id/YOUR_ESP32 --fixture-confirmed
```

The helper supplies board/fixture confirmation to a pre-upload guard. A direct
PlatformIO upload also needs `ESU_FLASH_BOARD=v3`,
`ESU_FIXTURE_CONFIRMED=1`, and an explicit upload port. Build-only commands need
none of those confirmations. Do not set them for a generator-connected assembly.

## Start the runtime: one pane per command

Run each command from the repository root. Substitute the correct board and port.
The helper sources ROS/overlay and sets the domain. `ROS_LOCALHOST_ONLY` is
taken from your shell (default off) for both the nodes and the agent container,
so the ESU nodes can share a graph with the lab's other ROS nodes.
Real ESP32 images currently use domain **0**; changing an agent
environment variable does not change the firmware domain. Use a separate domain
(default 73) for software mocks, with matching logger/commander `--domain 73`.
Every shared profile uses **115200 baud**. The helper's agent uses the
`microros/micro-ros-agent:jazzy` image (the humble image crashed on the lab
host); override with `--agent-image`. Older images (the 2026-10-13 candidate at
57600, or historical array firmware) are not compatible: reflash.

Pane 1, exactly one named agent:

```bash
python3 software/esu.py agent --port /dev/serial/by-id/YOUR_ESP32
```

Pane 2, read-only logger:

```bash
python3 software/esu.py logger --board v3
```

Pane 3, computer commands on the disconnected fixture only:

```bash
python3 software/esu.py commander --board v3 --fixture-confirmed
```

Release pedals and type `arm` explicitly before requesting computer ON.
Keys: c=cut, g=coag, b=bipolar, l=Ligasure, x=OFF+disarm, s=command status, q=quit.
Only supported channels are offered; no substitutions. OFF does not override a
held pedal. Initial OFF/disarm requests must be acknowledged.

Commands expire after 500 ms without renewal; the matching client renews desired
ON commands every 100 ms. One missed renewal is tolerated (the next still lands
inside the lease); two in a row disarm the client, with no automatic re-arm.
The commander prints plain text: `cut on`, `cut off`, `NOT sent (not armed)`, or
`delivery unconfirmed; output state unknown` when a command went out but its
reply was lost (check the fixture). Re-arming is refused, with a restart
required, if the board was reflashed between pedal and standalone modes. These are provisional bench values, not validated deadlines.
Physical pedals continue locally when ROS is absent. A stalled MCU, stuck
contact, or restored coil power with a live MCU remains a hardware/system gap.

The helper uses `--name esu-agent` so duplicate helper agents cannot start.
It does not stop unrelated lab containers. Use `docker ps` to inspect, and
`docker stop esu-agent` to stop this agent. Never run a monitor on the same port.
Only one board/mock and one commanding application may use a ROS domain.

## Capability discovery and logs

`/esu/capabilities` is a read-only Trigger service. Commander refuses old or
inconsistent capability contracts. The logger reads it once when the board
connects (channel count, pedal/standalone mode, startup snapshot, boot ID,
telemetry-loss count) and again only after a link gap or a mid-session
baseline, so no text is polled over the serial link during a session.

The logger terminal shows one line when the board connects and then plain
events, e.g. `cut on   (computer)`, `coag off   (surgeon)`. If the firmware
loses a telemetry message it publishes a fresh baseline; the logger records
that as a resync (`sync` rows) and keeps logging. Bad capability replies, extra
publishers and malformed messages are warned about and marked in the metadata
file; logging is not stopped.

Telemetry is packed Int32: channel bits 0-3 and source bits 4-5. Logs keep the
fixed CSV columns
`ros_time_ns,event_type,channel,source,cut,coag,bipolar,ligasure`.
A companion `.metadata.jsonl` records capability snapshots and discontinuities.
First/reconnect snapshots are `sync`, not training press/release labels.
Timestamps are PC receipt times. Offline edges and host-side message losses are
not fully recoverable. Inferred state is not physical contact/RF feedback.

## Existing flashed firmware (read-only compatibility)

You do not have to erase an old image just to read its telemetry. After sourcing
ROS and the overlay manually, select the known wire format and board:

```bash
ros2 run pedal_controller pedal_logger --ros-args -p wire_format:=legacy_array -p board_version:=v1
ros2 run pedal_controller pedal_logger --ros-args -p wire_format:=legacy_packed -p board_version:=v2
```

Use only the command matching the actual flashed image. Historical array firmware
uses Int32MultiArray; the later v2 packed firmware uses Int32. The old agent baud
must match that image. Legacy command clients have no lease; the new commander
intentionally refuses legacy firmware rather than silently dropping protection.

## Mock and validation

Use `python3 software/esu.py mock --board v3 --domain 73`, with logger/commander
also on domain 73 and no real board in that domain. Repeat all three profiles.
See [testing](TESTING.md). Native/offline tests do not replace actual ROS integration,
a complete target build, or the recorded disconnected-fixture fault tests.
