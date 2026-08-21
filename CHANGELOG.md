# Changelog

All notable changes to ESU-TAP are recorded here. Newest first.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/).
Hardware revisions are versioned by board (v1, v2, ...); firmware and software
track alongside the board they target.

---

## [v2] — Monopolar + Bipolar (current)

v2 is a functional and safety redesign of v1. It adds a bipolar channel, fixes
the v1 bypass failsafe, and adds a firmware watchdog and input/signal
protection. Targets KiCad 9 and JLCPCB PCBA.

### Added
- **Bipolar channel.** Second independent pedal/generator path (BV-1254B
  bipolar footswitch). One switching relay, one sense line, one bypass path.
  Mono and bipolar are fully separate signal chains.
- **Watchdog-held failsafe.** TPS3823A-33DBVR (non-latching variant) supervises
  the firmware. The ESP32 pets it on IO4; RESET drives a low-side MOSFET (Q4)
  that grounds the bypass-relay coil rail (`/COIL_GND`). Healthy firmware keeps
  the coils energized (active mode); a firmware hang **or** power loss drops the
  coils and the board falls back to pass-through. Watchdog interval ~1.6 s.
- **Third bypass pole for the commons.** The v1 bypass only rerouted the hot
  lines; v2 adds pole(s) so the generator commons are bridged to the pedal
  commons in the unpowered state, completing the return path (fixes the v1 bug
  below).
- **Split / isolated commons.** Mono and bipolar each have separate
  pedal-common and generator-common nets (`/MONO_PED_COM`, `/MONO_GEN_COM`,
  `/BI_PED_COM`, `/BI_GEN_COM`). In bypass, each modality returns through its
  own generator common; neither touches board GND or the other modality. In the
  powered state the pedal commons switch to GND so sensing works. (Per review
  from R. Prakash.)
- **5 V barrel-jack power input** with an ORing/reverse-polarity Schottky, so
  the board runs from a dedicated supply with USB disconnected during sessions
  (breaks the mains path through the laptop).
- **Input rail protection:** SMAJ6.0A TVS across +5 V (transient clamp), and a
  resettable PTC in series with the +5 V input for fault containment
  (short / reverse).
- **eFuse footprint (0 Ω jumper populated).** A footprint for a future overvoltage
  eFuse is reserved and bridged with a 0 Ω link, so the protection can be added
  in a later revision without a respin. See ROADMAP.
- **Sense-line protection.** Each of `CUT_SENSE` / `COAG_SENSE` / `BI_SENSE`
  routes `connector → PESD5V0S1BA ESD clamp → ~1 kΩ series resistor → ESP32`,
  so no GPIO sits directly on an externally reachable net.
- **RF ferrite footprint (unpopulated).** Placed but not populated; v1 ran clean
  without RF filtering, so it is insurance pending a bench measurement rather
  than a committed part. See ROADMAP.

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
- **Watchdog part correction.** Selected the non-latching TPS3823**A** variant;
  the plain part latches RESET low if WDI toggles during a reset event, which is
  wrong for a failsafe.
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
- Auto-connect / auto-reconnect state machine with fail-safe relay-off on link
  loss.
- ROS 2 `pedal_controller` package: logger, commander, latency test, system
  test, mock node.
- Confirmed the footswitch connector (AMP CPC Series 1) and BV-1253B pinout by
  direct measurement.

### Known issues (carried into v2)
- Bypass pass-through did not complete when unpowered (see v2 → Fixed).
- Screw-terminal footprints not yet swapped to keyed cable connectors.
