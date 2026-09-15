# v1 recovery and setup on a new account on blue

Updated 2026-09-15. Use this guide for the physical v1 board whose ESP32 was
subsequently flashed with v2 firmware. Commands below run in Bash on blue,
not Windows PowerShell. Substitute your clone path if it is not ~/ESU_TAP.

Keep the electrosurgical generator physically disconnected throughout flashing
and initial checks. Use a disconnected low-voltage contact fixture.
An old successful test is evidence for that configuration, not a new safety approval.

## What was restored

The following files were restored from commit
`c63bfcf2c6faf4437ad764aeee6c91029624eb55` (2026-07-29, commit message
"Working system + docs cleanup: reconnect fix, forwarding, README/SETUP/TESTING rewrite"):

- `microros_firmware/src/esu_tap_microros.cpp` -> `firmware/esu-tap-v1/src/esu_tap_microros.cpp`
- `microros_firmware/platformio.ini` -> `firmware/esu-tap-v1/platformio.ini`
- `microros_firmware/colcon.meta` -> `firmware/esu-tap-v1/colcon.meta`

Contents are unchanged apart from any checkout line-ending normalization.
This is the historical source, not a recovered binary/readback from your ESP32.
The old configuration has unpinned dependencies; rebuilding today is not proof
of a byte-identical July firmware image. Preserve any original build logs/binaries
you still have. No v2/v3 code or PCB was changed by this restoration.

| Function | Restored v1 GPIO | v2 GPIO (do not flash on v1) |
| --- | --- | --- |
| CUT sense | 34 | 35 |
| COAG sense | 35 | 34 |
| CUT relay | 26 | 26 |
| COAG relay | 27 | 27 |
| CUT indicator | 18 | 23 |
| COAG indicator | 21 | 22 |

This map agrees with the current saved v1 PCB. Verify the manufactured board and
any hand wiring match it. Source comments describing guaranteed safe states,
baseline as proof of reset, or unpowered bypass are historical claims, not current
qualification; the [validation document](SAFETY_AND_VALIDATION.md) supersedes them.

## 1. Get these files onto blue

The restoration starts as local changes on the Windows checkout. A pull on blue
will not receive uncommitted/unpushed files. First commit/push the restoration and
guide from that checkout, or transfer those changed files explicitly. Do not
roll the whole repository back to c63bfcf or restore the obsolete ROS tools.

Under the new account on blue:

```bash
whoami
cd ~/ESU_TAP
git status --short
git pull --ff-only
test -f firmware/esu-tap-v1/platformio.ini
git log -1 --oneline
```

If the pull reports conflicting local work, stop and preserve it; do not reset
the checkout. If the test command fails, these changes have not arrived yet.
The new account should own its own clone. Do not copy another account's
`build/`, `install/`, `log/` or `.pio/` caches: they may encode old paths.

## 2. Check machine software; install only what is missing

ROS installed under /opt is shared across accounts; shell setup, Python virtual
environments, device permissions and workspace builds are account-specific.

```bash
lsb_release -ds
test -f /opt/ros/humble/setup.bash
source /opt/ros/humble/setup.bash
command -v ros2 colcon rosdep git cmake docker
python3 --version
```

This pipeline targets Ubuntu 22.04 with ROS 2 Humble and Python 3.10.
If Humble is absent or blue uses a different OS/distro, stop and have the lab
administrator check the machine rather than installing a second ROS stack blindly.

If needed, an administrator can install the supporting tools:

```bash
sudo apt update
sudo apt install git cmake build-essential python3-pip python3-venv \
  python3-colcon-common-extensions python3-rosdep
```

PlatformIO can be installed for this account using the VS Code PlatformIO
extension or its [official isolated installer](https://docs.platformio.org/en/latest/core/installation/methods/installer-script.html).
For the installer route, download `get-platformio.py` using that official page,
inspect it, then run it with `python3 get-platformio.py` (without sudo).
The commands below use its normal per-account executable:

```bash
~/.platformio/penv/bin/pio --version
```

If the extension reports a different Core path, substitute it below. Do not
activate PlatformIO's Python environment in the terminals used to build/run ROS.
micro-ROS requires Core >=6.1 plus git/cmake/pip; see
[upstream build requirements](https://github.com/micro-ROS/micro_ros_platformio#requirements).

Docker is normally already installed machine-wide. If `docker info` is denied,
ask the administrator for the lab-approved access method. Do not casually add
accounts to the Docker group: it grants root-level privileges. Approved sudo
Docker use is an alternative; [Docker's permission guidance](https://docs.docker.com/engine/install/linux-postinstall/)
explains the tradeoff.

## 3. Identify the ESP32 and grant this account serial access

Stop the old agent and serial monitors via their owning terminal/account.
Do not kill unknown lab processes.

Connect the same ESP32 using a USB DATA cable, with the generator disconnected:

```bash
~/.platformio/penv/bin/pio device list
ls -l /dev/serial/by-id/
```

Unplug/replug only this ESP32 to identify the matching device if multiple devices
are listed. Prefer its stable by-id path. In each terminal that needs it, set:

```bash
export ESU_PORT='/dev/ttyUSB0'
ls -l "$ESU_PORT"
readlink -f "$ESU_PORT"
id -nG
```

Replace /dev/ttyUSB0 with the device you actually identified; do not assume the
Haply or another USB device is the ESP32. A verified /dev/serial/by-id/... path
is preferable. The restored ini names /dev/esp32-esu, but every upload below
overrides that potentially missing lab symlink.

If the device is owned by group `dialout` and this account is not a member:

```bash
sudo usermod -aG dialout "$(id -un)"
```

Log completely out and back in, then recheck `id -nG` and redefine ESU_PORT.
For a different device group, ask the administrator rather than granting broad
permissions. See [PlatformIO's serial-permission guidance](https://docs.platformio.org/en/latest/core/installation/udev-rules.html).

For a busy port, diagnose only:

```bash
fuser -v "$ESU_PORT"
```

Have the owner stop the identified agent/monitor/service gracefully. Do not
disable machine-wide services or change USB rules without the lab's approval.

## 4. Build and flash ONLY the restored v1 project

Keep the generator disconnected. Preserve the previously verified v1 supply
arrangement; do not adopt v2/v3 dual-supply instructions. The saved v1 PCB ties
the ESP32 EXT_5V pad to +5V. Do not add an independent supply in parallel with
USB without checking the actual board/module power arrangement.

```bash
cd ~/ESU_TAP/firmware/esu-tap-v1
~/.platformio/penv/bin/pio run -e esp32dev
```

The first build downloads/builds dependencies and may take several minutes.
Only after a successful build, with all port consumers stopped:

```bash
~/.platformio/penv/bin/pio run -e esp32dev -t upload --upload-port "$ESU_PORT"
```

This overwrites the ESP32 application with v1. An erase-flash step is not
normally needed and is not part of this procedure. The upload target rebuilds
as needed. Do not select esu-tap-v2 or esu-tap-v3 in PlatformIO.

If upload stalls at "Connecting...", follow the ESP32 board's BOOT/EN upload
procedure. Do not immediately erase memory or switch firmware revisions.
If there are compile/dependency errors, save the FIRST error and build log;
the restored dependency versions are not pinned, so compatibility may need work.

After success, close any serial monitor. A slowly blinking COAG indicator is
consistent with this firmware waiting for its agent, not proof that mapping or
contact behavior has passed. Build/upload success is not functional validation.

## 5. Build the current PC software under the new account

Use a fresh terminal, not one with an activated PlatformIO/Conda environment:

```bash
source /opt/ros/humble/setup.bash
cd ~/ESU_TAP/software/ros2
rosdep update
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install --packages-select pedal_controller
source install/setup.bash
ros2 pkg prefix pedal_controller
```

The printed prefix should be in THIS clone's install directory, not the other
account's old ros2_ws. If rosdep says it is uninitialized, ask an administrator
to run `sudo rosdep init` once machine-wide, then rerun `rosdep update` as
your account. Do not run colcon with sudo.

Optional offline regressions from the repo root:

```bash
cd ~/ESU_TAP
python3 -B -m unittest discover -s software/ros2/src/pedal_controller/test -v
```

These do not connect to a ROS graph or validate hardware.

## 6. Start three terminals, in this order

In **every** ROS terminal:

```bash
source /opt/ros/humble/setup.bash
source ~/ESU_TAP/software/ros2/install/setup.bash
export ROS_DOMAIN_ID=0
```

Restored v1 initializes the default ROS domain (0). An arbitrary different
domain on the PC will not necessarily match it. Coordinate with the lab so
there are no other real boards, mocks or command applications using /esu/*
in domain 0. A different Linux account does not isolate ROS service names.
If domain 0 cannot be used alone, stop and arrange a coordinated domain
configuration rather than sending commands to potentially ambiguous services.

**Terminal A: logger first**

```bash
ros2 run pedal_controller pedal_logger
```

Start it before the agent so the initial three-field baseline can synchronize
logging. Logs go to this account's ~/pedal_logs/. First/reconnection observations
are `sync`, not press/release training labels.

**Terminal B: serial agent**

Set ESU_PORT to the same verified serial device from step 3:

```bash
export ESU_PORT='/dev/ttyUSB0'
docker run --rm -it --net=host --privileged \
  -v /dev:/dev -v /dev/shm:/dev/shm -e ROS_DOMAIN_ID=0 \
  microros/micro-ros-agent:humble serial --dev "$ESU_PORT" -b 115200
```

Replace the example device. If Docker needs approved sudo, prepend sudo to the
docker command. This upstream serial-container pattern uses privileged host
device access; use only on the approved lab host. If that is not allowed, have
the administrator provide the native Humble agent instead. See
[upstream agent instructions](https://github.com/micro-ROS/micro_ros_platformio#using-the-micro-ros-agent).
No port monitor can run concurrently.

**Terminal C: read-only checks first**

```bash
ros2 node list
ros2 service list -t
ros2 topic echo /esu/activation_state
```

Expected board node: /esu_tap_node. Expected activation services: /esu/cut and
/esu/coag, both std_srvs/srv/SetBool. Other standard ROS parameter services are
normal. Unexpected /esu/bipolar or /esu/ligasure means wrong firmware or another
node; stop before commanding.

With the generator still disconnected, press/release the pedal:
CUT should change the first field; COAG the second. Each message has THREE
integers `[cut, coag, source]`. Pedal-derived edges use source 0, computer-derived
edges 1, baseline 2. No messages during unchanged idle is normal.
If CUT changes COAG, stop and check the flashed project and physical wiring.

Stop topic echo with Ctrl+C. On the disconnected fixture:

```bash
ros2 run pedal_controller pedal_commander
```

Only CUT/COAG should be available. `c` + ENTER and `g` + ENTER toggle their
channels. The first toggle of an unknown channel requests OFF; the next requests
ON. `x` requests both OFF. Check the intended contact actually closes/releases,
not merely LED color, relay clicks or service acknowledgements.
Do not leave an ON command unattended. Keep a physical means to remove fixture
power; application/transport failure can prevent software OFF.

## 7. Run the guided v1 checks

Stop commander first; no other application may command the fixture.

```bash
ros2 run pedal_controller system_test --ros-args \
  -p board_version:=v1 -p fixture_confirmed:=true
```

This prompts for both computer-commanded channels and pedal-driven channels,
checks fresh telemetry, and asks for independent continuity measurements.
No bipolar/LigaSure test belongs on v1. If any check fails, stop and preserve
the results; do not proceed to generator testing.

After basic operation passes, optional software timing on the same fixture:

```bash
ros2 run pedal_controller latency_test --ros-args \
  -p board_version:=v1 -p fixture_confirmed:=true \
  -p channel:=cut -p iterations:=20 -p warmup:=2
```

Repeat for coag. Timing is software response/state receipt, not contact or RF
delivery. Turning off a computer command does not override a held physical pedal.

## 8. Shutdown and record the result

Release pedals, request all commands OFF, and independently verify open contacts.
Stop commander/test, then agent and logger; remove fixture power as appropriate.
Record board identity, this restoration commit, actual firmware dependency/build
versions, port, power/wiring arrangement and observed CUT/COAG mapping.

Restoration does not fix unpowered bypass wiring, powered-offline forwarding,
or the absence of command expiration. If the commander dies while the agent
lives, a command can remain ON. v1 does not gain v2/v3 watchdog hardware by
flashing. Do not treat this procedure as permission for clinical use or proof of
generator compatibility. See [required physical validation](SAFETY_AND_VALIDATION.md).

## Next sessions (no reflash unless firmware changes)

Connect the verified fixture/power and USB, source ROS plus this account's
workspace, set the matching domain, start logger, start agent, then commander.
A new login alone does not require reflashing, reinstalling ROS, or rebuilding.
