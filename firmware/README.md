# Firmware

One ESP32 implementation in `shared/` with a build profile per PCB revision.
The chip cannot detect which PCB it is on: always build the real revision, and
never flash a v2/v3 profile onto a v1 board. Build and flash with the
[setup guide](../docs/SETUP.md) (`python3 software/esu.py build --board v3`).

| Profile | Sense GPIOs | Relay GPIOs | LED GPIOs | External WDI |
| --- | --- | --- | --- | --- |
| v1: CUT, COAG | 34, 35 | 26, 27 | 18, 21 | None |
| v2: adds bipolar | 35, 34, 17 | 26, 27, 19 | 23, 22, 21 | 14 |
| v3: adds LigaSure | 35, 34, 17, 25 | 26, 27, 19, 33 | 23, 22, 21, 18 | 14 |

The v3 schematic still has a stale note "LigaSure indicator (GPIO32)"; the PCB
and firmware use **GPIO18**.

## Layout

- `shared/board_profile.hpp`: pins and constants per revision (115200 baud everywhere)
- `shared/control.hpp`: pure control logic (debounce, arming, lease, break-before-make)
- `shared/runtime.hpp`: control task and micro-ROS task
- `src/main.cpp` and `platformio.ini`: the build used by `esu.py`
- `esu-tap-v1/`, `-v2/`, `-v3/`: thin compatibility entry points to the same code
  (`pio run -e esp32dev` in each); CI builds them too
- `test/`: host tests ([contributors/TESTING.md](../docs/contributors/TESTING.md))
- `check_upload.py`: pre-upload guard that requires board, port and fixture confirmation

## Behavior

- **Control task.** A FreeRTOS task samples pedals, debounces them (30 ms),
  writes relays and LEDs, and checks command expiry every 10 ms. It never calls
  ROS, so pedals keep working during agent loss and reconnection. Only this task
  pets the external watchdog, after each completed cycle.
- **Manual priority.** The board boots manual (pedal live, computer disarmed).
  `/esu/arm` arms only while connected, with pedals released and commands
  cleared. A debounced press on any pedal while armed disarms and clears all
  computer commands in the same cycle; later renewals are refused until re-arm.
- **Command lease.** ON commands expire 500 ms after the last renewal (the PC
  client renews every 100 ms). Expiry, agent loss and transport errors clear and
  disarm; a late renewal cannot revive an expired command.
- **Break-before-make.** An opening output opens first; nothing closes until
  `interlock_ms` (5 ms) later, i.e. the next cycle, so two channels are never
  driven closed together.
- **No-pedal builds** (`ESU_PEDAL_CONNECTED=0`, `--no-pedal`) ignore the sense
  inputs. Sense pins outside GPIO34-39 also enable internal pull-ups as backup.
- **Telemetry.** `/esu/activation_state` is a packed `Int32` published on
  change: bits 0-3 CUT/COAG/bipolar/LigaSure, bits 4-5 source (0 pedal,
  1 computer, 2 baseline, 3 takeover). Unavailable channel bits are zero. A full
  event queue or a publish not confirmed within 50 ms is counted and followed by
  a fresh baseline; offline changes are not replayed.
- **Capabilities.** `/esu/capabilities` (`Trigger`, JSON) reports protocol 2,
  firmware version, profile, channels, watchdog, baud, lease/refresh times,
  pedal mode, current state, armed status, boot ID (an NVS counter; 0 if it
  could not be stored) and dropped-telemetry count.

All micro-ROS work stays in one task, and no text is printed on the serial link.

## Dependencies

The ESP32 platform and micro-ROS PlatformIO wrapper are pinned in `common.ini`.
Each entry point sets `include_dir` to `shared/` so PlatformIO finds framework
libraries such as `Preferences`; an environment that overrides `lib_deps` must
include `${env.lib_deps}`. The wrapper still fetches ROS branches, so record
resolved dependencies and the agent image digest for any validated build.
Native Windows micro-ROS builds are not supported.

## Known gaps

Not handled in firmware: welded or shorted outputs, independent hardware
inhibit, coil power returning while the ESP32 stays powered (it cannot sense
coil power), sense faults, and a hung controller. `SetBool` has no per-client
ownership, so use one commanding program per ROS domain. See [SAFETY.md](../docs/SAFETY.md).
The original v1 firmware is in Git at `c63bfcf2c6faf4437ad764aeee6c91029624eb55`.
