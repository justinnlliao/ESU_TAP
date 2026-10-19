# Changelog

All notable changes to ESU-TAP are recorded here. Newest first.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/).
Hardware revisions are versioned by board (v1, v2, ...); firmware and software
track alongside the board they target.

---

## Unreleased: bench-candidate fixes (2026-10-19)

- Serial baud is 115200 on every profile (was 57600), defined once in
  `board_profile.hpp` and checked against `protocol.BAUD` and `esu.py` by a test.
- Pedal-connected (default) vs standalone build: `--no-pedal`
  (`-DESU_PEDAL_CONNECTED=0`) ignores the sense inputs so unwired inputs cannot
  cause phantom activations or block arming. Reported in capabilities as
  `pedal_connected`. Non-input-only sense pins (IO17, IO25) again enable the
  internal pull-up as a backup.
- A failed or queue-dropped telemetry publish no longer tears down the micro-ROS
  session (which disarmed computer control on every lost message). It is
  counted and followed by a fresh baseline snapshot. Publish confirmation window
  raised from 10 ms to 50 ms. Link loss is still detected by agent pings.
- Boot ID is an NVS boot counter (was `esp_random()` before RF start-up).
- Logger: plain operator text (`cut on`, `coag off`), one terminal line on
  connect/resync, capabilities read only at connection and after gaps (no
  per-second text over serial), and warnings plus metadata instead of stopping
  for the session on bad capability replies, extra publishers, or malformed data.
- Command client tolerates one missed lease renewal; two consecutive misses
  disarm. Commander prints `cut on` / `cut off` or why a command failed.
- `esu.py`: jazzy agent image by default (`--agent-image` to override);
  `ROS_LOCALHOST_ONLY` inherited instead of forced on; `--no-pedal` for
  build/flash/mock.
- Added a host runtime simulation (`firmware/test/runtime_sim.cpp`) to CI and
  standalone variants of the native control tests. Removed lab and personal
  identifiers from README/SETUP.
- Review fixes: a lost ON acknowledgement is reported as "delivery unconfirmed;
  output state unknown" instead of "NOT sent"; re-arm refuses (restart
  required) if the board switched between pedal and standalone firmware;
  standalone images report `offline_pedals: false`; the boot ID is 0
  ("unknown", logger warns) unless the NVS counter write is confirmed.
- Offline testing only. No board flashed and no ESP32 target build run here;
  boards running the 2026-10-13 image (57600) must be reflashed.

## Unreleased: shared bench firmware and host contract (2026-10-13)

- Retain v1/v2/v3 as explicit pin/capability profiles over one shared runtime;
  replace divergent per-version implementations with compatibility entry points.
- Add independent local control task, explicit computer arming, 500 ms command
  leases, 100 ms client renewal, and disarming on detected disconnect/expiry.
  Preserve physical pedal control without ROS. These are provisional bench
  settings, not validated shutdown limits or independent hardware protection.
- Standardize new images on 57600 baud, packed Int32 telemetry, capability
  discovery, supported-channel checks, and boot/drop metadata. Legacy firmware
  requires an explicit read-only logger mode; command clients refuse it.
- Add Ubuntu/Humble setup/build/runtime helper, guarded profile-specific upload,
  native control tests, expanded Python regressions, and build-only CI matrix.
- Pin the outer ESP32 platform/micro-ROS wrapper versions; upstream transitive
  ROS dependencies are not fully locked. Update installation and validation docs.
- No board flashed, PCB edited, or physical generator test performed by this
  change. Full target builds, ROS integration, and disconnected-fixture tests
  remain required before deployment; existing hardware safety gaps remain.

## Documentation: board-power cutoff and phantom-test scope (2026-10-13)

- Recorded the operator-reported board-power button and supervised phantom
  context without claiming verified wiring, RF cessation, or test approval.
- Distinguished computer-control cutoff/manual bypass from stop-all-energy;
  added supply, held-pedal, stale-command, and power-restoration checks.
- Added proposed hardware fault-handling requirements and separate firmware
  gaps. Clarified six-relay v2 versus eight-relay v3 design identity.
- No schematic, PCB, firmware, fabrication output, or physical test changed
  as part of this documentation update.

## [Unreleased] — Restore v1 firmware (2026-09-15)

- Restored v1 source, PlatformIO configuration and micro-ROS metadata from
  c63bfcf into a dedicated `firmware/esu-tap-v1/` project; historical contents
  preserved rather than adapting v2/v3 firmware.
- Added [new-account recovery/setup on blue](docs/V1_BLUE_SETUP.md), including
  USB permissions, correct v1 pin map, firmware upload, ROS build, agent/logger
  startup, and disconnected-fixture checks.
- No PCB, v2/v3 firmware, or physical board was changed. A fresh target build
  and physical tests remain required; historical dependencies are unpinned.

## Software review corrections (2026-09-14)

- Refuse unavailable command channels instead of substituting CUT. Use one
  executor thread; remove nested/concurrent spinning and bound the ON response
  wait by the pulse's OFF-request deadline. Cleanup remains best-effort.
- Add shared schema/response/observation helpers and offline regression tests.
- Make mock and dummy-fixture tools revision-selectable, including LigaSure;
  require explicit fixture confirmation for activating test procedures.
- Timestamp state observations independently of response arrival, reject stale
  matches, and abort benchmarks on failed acknowledgements or state transitions.
- Log first/reconnection observations as sync records, reject malformed/changing
  schemas, and avoid overwriting logs. Sync records are not training edge labels.
- Update firmware paths, software contracts and limitation documentation;
  align ROS package metadata at 2.0.0.
- Firmware edits are comments only. No PCB, fabrication files, command lease,
  offline policy, flashed board, or hardware safety behavior changed.
- Offline checks do not replace actual ROS Humble integration or physical tests.

## Documentation and v3 CPL correction (2026-09-11)

- Corrected unsupported claims of guaranteed watchdog shutdown, sustained
  bypass, and powered-offline operation. See
  [current protection and validation status](docs/SAFETY_AND_VALIDATION.md).
- Documented the current v3 watchdog wiring, incomplete LigaSure firmware,
  firmware/logger schema mismatch, and outstanding physical fault tests.
- Converted v3 CPL headers to JLCPCB's five-column schema, preserving positions
  and equivalent orientations. Assembler upload/placement approval remains separate.
- No hardware or executable firmware behavior was changed by these corrections.

Historical entries below describe earlier design intentions and reported findings,
not a fresh qualification of manufactured v1/v2 boards. Prior blanket safety
claims are superseded by the validation document.

## [v3] — Four-channel hardware prototype

Adds a fourth pedal/generator path labeled LigaSure. Current hardware uses
GPIO33 control, GPIO25 sense, and GPIO18 through R22 to D12 for its indicator.
Firmware and generator-specific compatibility validation remain incomplete.

## [v2] — Monopolar + Bipolar

v2 adds a bipolar channel, common-routing changes, an external watchdog, and
input/signal protection. These changes were intended to improve failure handling;
they do not establish a verified fail-safe system. Originally targeted KiCad 9
and JLCPCB PCBA.

### Added
- **Bipolar channel.** Second independent pedal/generator path (BV-1254B
  bipolar footswitch). One switching relay, one sense line, one bypass path.
  Mono and bipolar are fully separate signal chains.
- **Watchdog-controlled bypass.** The current v2 PCB uses GPIO14 to U9 WDI;
  U9 RESET drives Q1 and `/COIL_GND`. ESP32 EN is unconnected. This is not
  independent activation shutdown or guaranteed sustained fallback; the earlier
  “watchdog-held failsafe” description was incorrect.
- **Third bypass pole for the commons.** The v1 bypass only rerouted the hot
  lines; v2 adds pole(s) so the generator commons are bridged to the pedal
  commons in the unpowered state, completing the return path (fixes the v1 bug
  below).
- **Split / isolated commons.** Mono and bipolar each have separate
  pedal-common and generator-common nets (`/MONO_PED_COM`, `/MONO_GEN_COM`,
  `/BI_PED_COM`, `/BI_GEN_COM`). In bypass, each modality returns through its
  own generator common; neither touches board GND or the other modality. In the
  powered state the pedal commons switch to GND so sensing works.
- **5 V barrel-jack input** for the relay rail, with a series reverse-polarity
  Schottky. The present serial architecture retains USB for ESP32 logic power
  and communication; the previous USB-disconnected operating claim is superseded.
- **Input rail protection:** SMAJ6.0A TVS across +5 V (transient clamp), and a
  resettable PTC in series with the +5 V input for fault containment
  (short / reverse).
- **Overvoltage cutoff proposal.** Earlier notes proposed an eFuse/0-ohm
  reservation. Do not treat that proposal as an implemented or drop-in feature;
  inspect the current design and see ROADMAP.
- **Sense-line protection.** Each of `CUT_SENSE` / `COAG_SENSE` / `BI_SENSE`
  routes `connector → PESD5V0S1BA ESD clamp → ~1 kΩ series resistor → ESP32`,
  so no GPIO sits directly on an externally reachable net.
- **RF filtering proposal.** Earlier notes discussed optional ferrites. Current
  population must follow the exact schematic and BOM, not historical DNP notes.
  Lack of observed interference in earlier trials is not RF-immunity validation.

### Changed
- **Relay coil drivers: MMBT3904 → AO3400A** (LCSC C20917). Logic-level N-MOSFET,
  drop-in for the SOT-23 footprint (Base→Gate, Emitter→Source, Collector→Drain).
  The former base pulldowns become gate pulldowns, which also provides boot-state
  protection.
- **Connectors** carried over as documented; screw-terminal footprints used on
  this revision for bench flexibility.
- **Modality naming** unified so each generator common connects end-to-end from
  the connector through the switching and bypass relays (fixed a net-naming
  split that had left the switching relays forwarding to a floating internal
  common — see Fixed).

### Fixed
- **v1 bypass failsafe had no return path (CONFIRMED, critical).** With the board
  unpowered, the pedal common (GND) and generator common were separate nets with
  nothing bridging them, so an unpowered board left the pedal inert — a dead
  board meant the surgeon lost the pedal. v2 adds the common-bridge bypass pole.
- **Switching relays forwarded to a disconnected internal common.** The generator
  common at the connector and the internal common net used by the switching /
  bypass relays were separate nets, so a computer command closed a relay to a net
  that never reached the generator. Unified in v2; forwarding now completes.
- **Watchdog selection.** TPS3823A-33DBVR was selected. Earlier A/non-A
  suffix reasoning was not a system-level safety analysis. The selected part's
  temporary RESET behavior must be considered in the actual circuit.
- **C3 realizable footprint.** 22 µF changed from an unrealistic 0402 to 0805.
- **D1 topology.** SMAJ6.0A is a shunt TVS from +5 V to GND (obsolete `5V_JACK`
  net removed).

### Removed
- **SMAJ5.0A across the 3.3 V rail.** A 5 V-standoff TVS clamps around 9 V, which
  is far too high to protect a 3.3 V rail — it would never conduct in time.
  Removed from the design.

---

## [v1] — Monopolar (archived)

Initial working interposer. Monopolar only (CUT / COAG). Established the
sense-then-forward architecture and the micro-ROS interface.

### Added
- Sense-then-forward architecture: ESP32 reads pedal dry contacts (IO34/IO35),
  drives G6K relays to close the generator footswitch contacts.
- micro-ROS interface (`/esu/cut`, `/esu/coag` services;
  `/esu/activation_state` telemetry) with deterministic surgeon-vs-computer
  attribution.
- Auto-connect / auto-reconnect state machine with software-requested relay-off
  on detected link loss; this is not independently guaranteed fault handling.
- ROS 2 `pedal_controller` package: logger, commander, latency test, system
  test, mock node.
- Confirmed the footswitch connector (AMP CPC Series 1) and BV-1253B pinout by
  direct measurement.

### Known issues (carried into v2)
- Bypass pass-through did not complete when unpowered (see v2 → Fixed).
- Screw-terminal footprints not yet swapped to keyed cable connectors.
