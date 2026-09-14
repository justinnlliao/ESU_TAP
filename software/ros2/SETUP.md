# Build and run ESU-TAP software

Development target: ROS 2 Humble on Ubuntu 22.04, micro-ROS over USB serial.
Use a disconnected low-voltage dummy contact fixture, not an operating generator.
Read [protection and validation status](../../docs/SAFETY_AND_VALIDATION.md).

## Select the revision

| Board | Firmware project | Channels | State fields |
| --- | --- | --- | --- |
| v1 | No current standalone project | CUT, COAG | cut, coag, source |
| v2 | firmware/esu-tap-v2 | Adds bipolar | cut, coag, bipolar, source |
| v3 | firmware/esu-tap-v3 | Adds LigaSure | cut, coag, bipolar, ligasure, source |

Do not flash a newer pin map onto v1. Commander discovers services; unavailable
requested channels are errors, never replacements. Mock and bench tools require
the selected `board_version` (default `v3`).
The logger reads source from the final field and rejects a width change mid-run.

## Build ROS software

Source the installed ROS environment in each terminal:

```bash
source /opt/ros/humble/setup.bash
cd ~/ESU_TAP/software/ros2
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
```

Build from this workspace, not your home directory. Local `build/`, `install/`,
and `log/` are ignored. No ROS runtime or hardware test was executed as part of
the offline 2026-09-14 code update; use the [testing procedure](TESTING.md).

## Build firmware

Open the intended revision directory as the PlatformIO project root:

```bash
cd ~/ESU_TAP/firmware/esu-tap-v3  # substitute esu-tap-v2 for v2
pio run
# Optional disconnected-fixture upload to the identified board:
pio run -t upload --upload-port /dev/ttyUSB0
```

Configs name the lab symlink `/dev/esp32-esu`; override it when absent.
On Windows use the actual `COM` port for upload, for example
`pio run -t upload --upload-port COM5` only if COM5 is the identified board.
Ubuntu is the documented micro-ROS build/run environment; Windows support for
the entire dependency stack is not verified here.

Stop the serial agent/monitor before flashing: only one process may own the port.
These projects use `micro_ros_platformio`, not `micro_ros_arduino`.
After changing `colcon.meta`, run `pio run -t clean_microros` before rebuilding.
The platform and micro-ROS dependency are currently unpinned; record actual
versions/build hashes when validating a release.

## Run with one board

Only one board or mock, and one commanding application, may use these absolute
`/esu/*` names in a ROS domain. Use an isolated domain for mock tests; do not
run a mock alongside hardware advertising the same services.

Start the logger **before** connecting the board/agent so it can receive the
boot/reconnection baseline. Publication is change-only; late subscribers may
not see an initial state until something changes.

In separate terminals, source ROS and this workspace, then run:

```bash
# Logger:
ros2 run pedal_controller pedal_logger

# Serial agent:
docker run -it --rm -v /dev:/dev --privileged --net=host \
  microros/micro-ros-agent:humble serial --dev /dev/ttyUSB0 -b 115200

# Commander:
ros2 run pedal_controller pedal_commander
```

Keys: `c` CUT, `g` COAG, `b` bipolar, `l` LigaSure (only if available).
`x` requests OFF on every discovered channel; `s` shows last acknowledged
commands, **not physical state**. Initially unknown channels first request OFF
when toggled; a subsequent toggle requests ON. Bare ENTER uses `channel`.

```bash
ros2 run pedal_controller pedal_commander --ros-args \
  -p mode:=pulse -p channel:=ligasure -p pulse_ms:=300
```

Pulse timing schedules OFF relative to the ON request; it is not a guaranteed
relay closure duration. Failed ON acknowledgement still triggers an OFF attempt.
Script mode runs three such pulses separated by one-second waits. Abort on
failed acknowledgement; do not infer safety from a timeout or an exit code.

The executor spins in one background thread; input/service waits run on the
main thread. Ctrl+C preserves the ROS context for best-effort OFF requests.
Repeated interruption, process death, transport failure, or firmware faults can
prevent OFF. The firmware has no command lease and an agent ping does not
establish the command application's health.

## Logger records

Logs are written under `~/pedal_logs/` with unique, non-overwriting filenames.
Columns remain `ros_time_ns,event_type,channel,source,cut,coag,bipolar,ligasure`.
`event_type` now includes `sync` for first observation and reconnection baseline;
exclude these from press/release training labels. A baseline is not proof of
an ESP32 reset. Timestamps are PC ROS-clock receipt times, not physical/RF timing.
Normal runs should use `use_sim_time=false`; simulated time requires its own clock.

Status is inferred effective state (pedal OR command). Pedal changes masked by
an existing computer command are not separate events in this interface.
See [TESTING.md](TESTING.md) for revision-selectable mock and fixture commands.
