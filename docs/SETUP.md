# Setup guide

Ubuntu 22.04, ROS 2 Humble, and the board's revision (v1, v2 or v3). Keep the
generator disconnected while installing, flashing and testing.

**Short version:** from the repository root run `./esu.sh setup`, then
`./esu.sh flash v3 pedal` (or `nopedal`, `v1`, `v2`), then `./esu.sh run`. After a
`git pull`, run `./esu.sh update`. `esu.sh` finds the ESP32 port, asks you to
confirm the generator is disconnected before flashing, remembers the last
board/mode, and calls the `software/esu.py` commands described below.

## 1. Prerequisites (once)

Install ROS 2 Humble and Docker from their official instructions, plus git,
cmake, build-essential, python3-pip, python3-venv, colcon and rosdep. Your
account needs access to the ESP32 serial device (`dialout` group) and Docker.
Use the system Python, not an active Conda environment.

From the repository root:

```bash
python3 software/esu.py doctor      # checks the tools above
python3 software/esu.py setup       # PlatformIO in ~/.platformio/penv
python3 software/esu.py host-build  # builds the ROS package
```

If ROS dependencies are missing: `source /opt/ros/humble/setup.bash`, run
`rosdep install --from-paths software/ros2/src --ignore-src -r -y`, then
repeat `host-build`.

## 2. Build and flash the firmware

| PCB | Profile | Channels |
| --- | --- | --- |
| v1 | v1 | CUT, COAG |
| v2 (six relays) | v2 | CUT, COAG, bipolar |
| v3 (eight relays) | v3 | CUT, COAG, bipolar, LigaSure |

The ESP32 cannot detect which PCB it is on, so always pass the real revision;
v1 uses different pins.

```bash
python3 software/esu.py build --board v3
python3 software/esu.py flash --board v3 --port /dev/serial/by-id/YOUR_ESP32 --fixture-confirmed
```

The first build downloads dependencies and takes several minutes. Find the port
with `ls -l /dev/serial/by-id/`, and stop any running agent or serial monitor
before flashing. A direct `pio run -t upload` additionally needs
`ESU_FLASH_BOARD=v3`, `ESU_FIXTURE_CONFIRMED=1` and an explicit upload port.

**Pedal (default) or no pedal.** Add `--no-pedal` to `build` and `flash` only for
a board with nothing wired to its pedal inputs. That image ignores the inputs,
so floating pins cannot look like presses. Reflash without it to use a pedal.

## 3. Run

`./esu.sh run v3 T01` starts all three pieces in tmux. To run them yourself,
use one terminal each, from the repository root:

```bash
python3 software/esu.py agent --port /dev/serial/by-id/YOUR_ESP32   # micro-ROS agent (Docker)
python3 software/esu.py logger --board v3 --trial T01               # records to ~/pedal_logs
python3 software/esu.py commander --board v3 --fixture-confirmed    # interactive commands
```

In the commander, release the pedals and type `arm`, then c=cut, g=coag,
b=bipolar, l=LigaSure, x=all OFF and disarm, s=status, q=quit.

- Commands expire 500 ms after the last renewal; the commander renews every
  100 ms and tolerates one missed renewal. Two misses disarm it until you re-arm.
- Pressing any pedal while armed cancels all computer commands (manual always
  wins). Re-arm with pedals released to continue.
- The commander prints `cut on`, `cut off`, `NOT sent (not armed)`, or
  `delivery unconfirmed; output state unknown` if a reply was lost.
- Real boards use ROS domain **0** and **115200 baud**. The agent runs the
  `microros/micro-ros-agent:jazzy` image (`--agent-image` to override) in a
  container named `esu-agent`; `docker stop esu-agent` stops it.
- Only one board (or mock) and one commanding program per ROS domain.
  `ROS_LOCALHOST_ONLY` is taken from your shell (default off).

## 4. Logs

The logger writes `~/pedal_logs/pedal_log_<trial>_<time>.csv` with columns
`ros_time_ns,event_type,channel,source,cut,coag,bipolar,ligasure,monotonic_ns`,
plus a `.metadata.jsonl` with the board's capability snapshots and any gaps.

- `event_type` is `press`, `release`, `sync` (first observation or reconnect
  baseline, not a real press) or `takeover`.
- Timestamps are PC receipt times. Changes while the board was offline are not
  replayed. State is inferred from inputs and commands, not measured contacts.
- Bad messages are warned about and recorded in the metadata; logging continues.

## 5. Package in another ROS 2 workspace

`software/ros2/src/pedal_controller` can be copied alone into another
workspace's `src/` (it needs only `rclpy`, `std_msgs`, `std_srvs`). Flash the
board from this repository first. From that workspace root:

```bash
bash src/pedal_controller/esu_run.sh v3 T01          # agent + logger + commander in tmux
bash src/pedal_controller/esu_run.sh stop
bash src/pedal_controller/esu_run.sh agent           # or one terminal each
bash src/pedal_controller/esu_run.sh logger v3 T01
bash src/pedal_controller/esu_run.sh commander v3
```

It sources ROS and the workspace itself, uses `ROS_DOMAIN_ID` (default 0), and
picks the only `/dev/serial/by-id` device (set `ESU_PORT` if there are several).
It builds the package only if the workspace was never built; after updating the
package run `colcon build --packages-select pedal_controller`.

## 6. Mock board (no hardware)

```bash
./esu.sh mock v3                      # software board on ROS domain 73
ESU_DOMAIN=73 ./esu.sh logger v3      # in another terminal; same for commander
```

See [contributors/TESTING.md](contributors/TESTING.md) for the full test procedures.

## Older firmware

Boards still running pre-protocol-2 firmware can be logged without reflashing,
after sourcing ROS and the workspace:

```bash
ros2 run pedal_controller pedal_logger --ros-args -p wire_format:=legacy_array -p board_version:=v1
ros2 run pedal_controller pedal_logger --ros-args -p wire_format:=legacy_packed -p board_version:=v2
```

The commander refuses old firmware, since it has no command expiry. Reflash to
command the board.
