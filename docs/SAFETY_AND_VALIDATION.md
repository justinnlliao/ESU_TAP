# Protection features and validation status

Reviewed 2026-09-11. This page supersedes earlier claims that watchdog timeout
guarantees sustained manual bypass or cancels computer activation. This is a
documentation correction, not a hardware or firmware fix.

## Scope and permitted claims

ESU-TAP is a research prototype. Protection components, normal-operation trials,
and passing KiCad checks do not establish system-level fault tolerance, clinical
suitability, or a numerical reliability rating.

The detailed wiring findings below apply to the saved v3 design reviewed on
2026-09-11. The checked-in firmware targets v2. Do not transfer v3 findings or
historical v1 test claims to another revision or an already-built board without
checking its exact board, firmware, and assembly configuration.

An accurate project description is:

> The prototype incorporates input-protection components and a normally
> de-energized relay bypass intended to preserve manual pedal operation during
> board power loss. An external watchdog controls the bypass relays. Sustained
> fault recovery and independent removal of computer-commanded activation remain
> incomplete. Powered operation without the ROS connection and system-level fault
> tolerance have not been validated.

Use “demonstrated power-loss pass-through” only with a recorded physical test of
the stated revision. No measured “99% reliable” claim is established. Deferring
software safety work is a limitation, not evidence that hardware compensates.

## Implemented features and limits

- PTC, series Schottky, and TVS components are intended for input fault
  containment, reverse-polarity protection, and transient suppression. They do
  not establish safe operation with a sustained wrong-voltage adapter. Use a
  regulated 5 V center-positive supply; fault limits and thermal behavior need testing.
- Sense-line ESD clamps and series resistors are implemented. They do not prove
  protection for every transient, RF immunity, or medical isolation.
- Relay bypass switches pedal signals and commons. Its de-energized state is
  intended to restore direct pedal-to-generator paths, assuming correctly wired,
  functioning relays and connectors. Verify on the actual assembly.
- Power-loss bypass is not an emergency stop: a pressed physical pedal may
  intentionally continue activating the generator.

## What the v3 external watchdog controls

| Connection | Function |
| --- | --- |
| U1 GPIO14 to U10 WDI | Firmware watchdog input |
| U10 RESET to Q1 gate | Controls bypass-coil return |
| Q1 drain, `/COIL_GND`, to U6–U9 coil returns | Releases bypass relays when Q1 turns off |
| U2–U5 coil returns to Q2–Q5 | Separate ESP32-controlled activation drivers |
| U1 EN | Not connected to U10 RESET |

The TPS3823A watchdog timeout is specified as 0.9–2.5 s (1.6 s typical).
RESET asserts for 120–300 ms (200 ms typical), then the watchdog timer restarts.
It is not a latched “controller healthy” output. See the
[TI datasheet, §6.8 and §7.3.4](https://www.ti.com/lit/ds/symlink/tps3823.pdf).

Timeout can briefly release the bypass relays but does not reset the ESP32,
remove the separate activation drive, or guarantee continuous bypass until
recovery. Bypass relays can re-energize while the controller remains faulty.

For example, U5 connects `GEN_LIGA` (pin 4) directly to `LIGA_GEN_COM` (pin 3)
when energized. U9 switches the pedal path; it is not in series with that
activation contact. Switching pedal common away from board GND cannot break
a stuck-closed U5 connection. Other activation channels have the same independent
contact arrangement. This is circuit analysis, not a measured failure-rate claim.

ESP32 internal watchdogs and panic recovery may reset the MCU for some faults.
Coverage and timing depend on the built firmware configuration and monitored
tasks. Those settings and recovery behavior have not been validated here. See
[Espressif watchdog documentation](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/system/wdts.html).

## Unpowered versus powered-offline

| Condition | Current status |
| --- | --- |
| All board power removed | Direct manual bypass intended; physical continuity testing required |
| Barrel supply removed, USB retained | Relay supply lost; verify bypass and telemetry separately |
| USB/logic supply lost, barrel retained | Separate power fault; verify coil states and recovery |
| ESP32 powered, ROS agent absent/disconnected | Current firmware stops pedal polling/forwarding but continues watchdog petting; dependable offline operation is not implemented |
| Commanding application stops, agent remains alive | ON command can remain latched; no command lease/expiration is implemented |
| Firmware hangs with an output HIGH | External watchdog does not independently clear activation |

Firmware attempts to clear activation outputs on detected agent loss. This is a
software action, not an independent shutdown guarantee. An agent ping does not
prove the commanding application is healthy. A shorted driver or welded relay
contact cannot be repaired by an MCU reset; a shorted sense input can resemble
a held pedal. These examples are not an exhaustive fault analysis.

## Software and data limitations

- `firmware/esp32/src/esu_tap_microros.cpp` implements CUT, COAG, and bipolar,
  not LigaSure. v3 uses GPIO33 for LigaSure control, GPIO25 for sense, and GPIO18
  through R22 (680 ohm) to D12 for its indicator.
- Firmware publishes `[cut, coag, bipolar, source]`. The current logger reads
  `[cut, coag, source]`, misreading bipolar as source. The legacy mock does not
  validate the current firmware contract. Passing mock tests do not validate v2/v3.
- Published state is inferred from sense inputs and commands, not measured
  relay-contact state or confirmed generator RF output. Source labels do not
  prove the generator actually delivered energy.

## Verification still required

Use a disconnected low-voltage dummy contact fixture for initial tests, not an
operating electrosurgical generator. Define acceptable response times and
recovery/re-arm behavior before testing; no approved timing threshold is recorded.

Record hardware revision/commit, firmware build and watchdog settings, supplies,
wiring, instrumentation, repetitions, contact-state traces, and results. Test:

1. Each pedal/command channel and release, startup, and reconnection.
2. Total power loss and each supply lost independently.
3. Controller stall with outputs OFF and each activation ON; observe multiple
   watchdog periods, not just the initial bypass pulse.
4. Agent loss, transport loss with logic power retained, and commanding-process
   loss while the agent stays alive.
5. Sense open/short faults and controlled stuck-driver/contact simulations on
   the dummy fixture.
6. Firmware/logger agreement against independent contact-state measurements.

After addressing gaps, generator compatibility, connector pinouts, signal
levels, isolation, EMC, and applicable safety requirements need separate
qualified review and controlled validation. Generated manufacturing files,
stock availability, placement acceptance, and passing ERC/DRC are not functional
or clinical-use approval.
