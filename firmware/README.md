# Shared ESP32 firmware (bench candidate)

Updated 2026-10-19. One implementation in `shared/`, with explicit `v1`, `v2`,
and `v3` build profiles. The chip cannot identify which PCB it is plugged into.
Capability reporting describes the **flashed profile**, not measured hardware.
Keep v1 support for existing two-channel boards; do not flash a v2/v3 pin map.

| Profile | Sense GPIOs | Relay GPIOs | LED GPIOs | External WDI |
| --- | --- | --- | --- | --- |
| v1: CUT, COAG | 34, 35 | 26, 27 | 18, 21 | None |
| v2: adds bipolar | 35, 34, 17 | 26, 27, 19 | 23, 22, 21 | 14 |
| v3: adds LigaSure | 35, 34, 17, 25 | 26, 27, 19, 33 | 23, 22, 21, 18 | 14 |

U1 pad nets were inspected read-only on all three PCB files. v3 still contains
a stale schematic text note, "LigaSure indicator (GPIO32)"; the PCB connection
and firmware use **GPIO18**, not GPIO32. This software update does not edit the
schematic or certify PCB/schematic synchronization.

All profiles use ROS Humble serial at **115200 baud** (`board_profile.hpp`;
the PC side checks the same value and a test keeps them equal). Root `platformio.ini`
selects pins; old revision folders are compatibility entry points, not separate
implementations. They are no longer unchanged historical firmware. The original
v1 source remains in Git at `c63bfcf2c6faf4437ad764aeee6c91029624eb55`.

## Behavior and capabilities

- **Pedal connected (default) vs standalone.** `ESU_PEDAL_CONNECTED=1` reads
  and forwards the pedal. A `--no-pedal` build (`-DESU_PEDAL_CONNECTED=0`)
  ignores the sense inputs, so unwired inputs cannot cause phantom presses or
  block arming. Sense pins other than input-only GPIO34-39 also enable the
  internal pull-up as a backup to the board pull-ups.
- A dedicated FreeRTOS control task samples pedals, debounces (30 ms), writes
  relays/LEDs, and checks command expiry every nominal 10 ms. It never calls ROS.
  Pedal forwarding continues during agent discovery, reconnection, and teardown.
- Computer commands start disarmed. `/esu/arm` (`SetBool`) explicitly arms only
  while connected, pedals released, and commands cleared. Disarm clears computer
  commands, not physical pedal input. A local pedal is never disabled by this API.
- **Manual priority.** Boot is manual (pedal live, disarmed); arming is
  autonomous. A debounced press on any pedal while armed disarms and clears all
  computer commands in the same control cycle; the pedal alone then drives
  relays. Later renewals are refused; re-arm (pedals released) to resume.
- ON commands expire after **500 ms** without renewal. The matching PC client
  renews desired commands every **100 ms**. These are unvalidated bench defaults,
  not medical response-time guarantees. Task scheduling/failure affects actual
  response; the hardware watchdog gap remains.
- Expiry, detected agent loss, and transport processing errors clear/disarm
  computer commands. An expired command cannot be revived by a late renewal;
  deliberate re-arm is required. Healthy local pedal activity still takes effect.
- Only the control task toggles WDI after a completed control cycle. This is
  not an application-health or independent-output-shutdown guarantee.
- `/esu/capabilities` (`Trigger`, JSON in `message`) reports protocol 2, firmware
  identity, board profile, channels, WDI presence, baud, lease/refresh settings,
  offline/arm policy (`offline_pedals` is false in standalone images),
  pedal-connected mode, current inferred state, armed status, boot ID, and
  dropped telemetry count. The boot ID is a counter kept in NVS, so it changes
  on every boot; it is 0 ("unknown") if the counter could not be saved and read
  back, and the logger then warns that reboot tracking is unavailable. The response uses a fixed backing buffer. The logger
  reads it at connection and after gaps, not continuously.
- `/esu/activation_state` uses one packed `Int32` on every profile: bits 0-3 are
  CUT/COAG/bipolar/LigaSure; bits 4-5 are source (0 sensed, 1 computer-derived,
  2 reconnect baseline, 3 pedal takeover: the computer channel it released, or the
  unchanged state when a takeover released no computer output). Unavailable channel bits must be zero. Capabilities,
  not unused bits, identify the channel count. No simultaneous legacy publisher.
- Break-before-make: an opening output opens first; no output closes until
  `interlock_ms` (5 ms) later, i.e. the next 10 ms control cycle, so two
  channels' contacts are never driven closed together (e.g. during a takeover).
- Telemetry is change-only with a reconnect snapshot and a bounded event queue.
  Offline edges are not buffered for replay. A full queue or a publish that is
  not confirmed within 50 ms is counted and followed by a fresh baseline
  snapshot; it does not tear down the session (link health comes from the
  agent ping). Host-side DDS loss is not exhaustively detected. No
  complete-event or physical-contact/RF claim follows from a valid message.

All micro-ROS entity work stays in one task, with initialized-entity tracking
for cleanup. Control/commands are synchronized separately. No text debug output
is mixed with binary serial data. This does not establish OS/MCU fault tolerance.

## Build and install

Use the [unified Ubuntu setup](../software/ros2/SETUP.md) and
`python3 software/esu.py build --board v3` (substitute the actual revision).
Flashing additionally requires an explicit port and `--fixture-confirmed`.
The pre-upload hook refuses missing board/fixture/port confirmation.
No automated script can verify you physically disconnected the generator.

The ESP32 platform and micro-ROS PlatformIO wrapper are pinned in `common.ini`.
Each entry point sets `include_dir` to the shared headers so PlatformIO's
dependency finder follows their includes and selects framework libraries such
as Arduino-ESP32's bundled `Preferences`. These do not need registry entries in
`lib_deps`. If an environment overrides `lib_deps`, include `${env.lib_deps}`
to retain the pinned micro-ROS wrapper.
The wrapper still fetches ROS dependency branches; this is not a complete
dependency lock. Record resolved dependencies and the agent image digest for
validated builds. A Linux CI matrix is provided, but adding CI is not a passing
target-build result. CI builds both the root and legacy entry points for all
three profiles. Native Windows micro-ROS builds are not validated here.

## Validation and remaining gaps

Native C++ control tests, a host runtime simulation (`test/runtime_sim.cpp`:
the real `runtime.hpp` on PC threads with stubbed Arduino/FreeRTOS/micro-ROS)
and offline Python tests exercise logic, not the full ESP32 scheduler, ROS
transport, electrical response, or energized generator.
Full target builds, ROS mock integration, repeated reconnect tests, and physical
disconnected-fixture validation are required before using the candidate on a
generator. No board has been flashed by this update.

Not solved: welded/shorted outputs; independent hardware inhibit; switch/coil
power restoration while the ESP32 stays alive; sense faults; complete telemetry;
RF immunity; and a hung controller/OS. The board cannot detect coil-power removal
in the current interface. SetBool has no per-client ownership or command nonce;
use one commanding application in an isolated ROS domain. A delayed old request
after deliberate re-arm is not ruled out by the lease alone.

See [safety status](../docs/SAFETY_AND_VALIDATION.md) and
[hardware requirements](../docs/HARDWARE_FAULT_HANDLING.md).
