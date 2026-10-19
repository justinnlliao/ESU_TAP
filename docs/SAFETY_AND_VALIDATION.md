# Protection features and validation status

Hardware reviewed 2026-09-11; software status updated 2026-09-14.
Cutoff/test-scope clarification added 2026-10-13; no new physical validation.
Shared firmware source updated later on 2026-10-13 as a bench candidate. The
software mitigations below are not evidence of a flashed or qualified assembly.
This page supersedes earlier claims that watchdog timeout
guarantees sustained manual bypass or cancels computer activation. This is a
documentation of limitations, not evidence of a hardware or firmware safety fix.

## Scope and permitted claims

ESU-TAP is a research prototype. Protection components, normal-operation trials,
and passing KiCad checks do not establish system-level fault tolerance, clinical
suitability, or a numerical reliability rating.

The detailed wiring findings below apply to the saved v3 design reviewed on
2026-09-11. Separate firmware projects target v2 and v3. Do not transfer v3 findings or
historical v1 test claims to another revision or an already-built board without
checking its exact board, firmware, and assembly configuration.

An accurate project description is:

> The prototype incorporates input-protection components and a normally
> de-energized relay bypass intended to preserve manual pedal operation during
> board power loss. An external watchdog controls the bypass relays. Sustained
> fault recovery and independent removal of computer-commanded activation remain
> incomplete. Shared candidate firmware adds local offline pedal handling and
> expiring computer commands; physical behavior and system-level fault tolerance
> have not been validated.

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

## Reported board-power cutoff and phantom testing

On 2026-10-13 the operator described supervised phantom testing with the
generator connected and a stop button that removes interface-board power.
It does not remove generator power. Switch wiring, the assembled board revision,
remaining USB/other supplies, and measured contact/RF response have not been
verified here. No physical test result or institutional approval is implied.

Removing **all relay-coil power** should release functioning activation relays
even when the MCU output remains HIGH. It also releases the bypass relays,
restoring the intended physical-pedal-to-generator path. Thus:

- Computer-commanded closure is intended to clear, assuming no alternate coil
  supply, welded contact, or other conductive fault.
- A held pedal can continue activation through the restored bypass path.
- This is an intended computer-control cutoff with manual pedal fallback,
  not a verified stop-all-RF emergency stop.
- Removing only logic power is not equivalent to removing coil power. Verify
  the actual assembly with USB and every other supply combination present.
- Reapplying coil power while the MCU remains powered could restore a still-HIGH
  drive or latched command. Do not assume a board-power button resets firmware.
- Manual coil-power removal is different from watchdog timeout: the present
  watchdog only controls bypass coils, not the separate activation coils.

Phantom testing avoids patient exposure, but supervision does not establish
fault probability, prevent unintended energy delivery, or replace a reviewed
method of stopping the generator independently of this interface. Energized
tests need a lab-approved procedure, manufacturer instructions, operator/material
protection, and a defined response if activation persists. Repository mock and
fault-injection procedures remain restricted to disconnected fixtures.

Before crediting the button as a safeguard, record a generator-disconnected
continuity test for every channel: computer ON with pedals released; pedal
held; cutoff maintained; and power restored. Repeat with each supply combination.
Measure contact transitions and supply states, not just LEDs or relay clicks.
Define release-time and re-arm acceptance criteria before testing; none are
approved in this document. Do not use an ordinary continuity meter on a live
generator connection. RF cessation is a separate measurement under a qualified
generator-specific procedure, not inferred from these continuity tests.

For each trial record: board revision/assembly ID and source commit, firmware
build, switch wiring, supply configuration, generator/pedal identity, test type
(disconnected or energized phantom), supervisor/procedure reference, stimulus,
independent measurements, response time, result, and trace/log location.
Mark unperformed tests **not tested**, not passed. Retain failed/interrupted
trials and mark reconnect gaps; missing telemetry is not evidence of inactivity.
Normal-operation data supports only the conditions actually tested, not a
clinical-use or system reliability claim.

See [hardware fault-handling requirements](HARDWARE_FAULT_HANDLING.md) for
proposed changes. They are not installed fixes or approved rework instructions.

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
| Barrel supply removed, USB retained | Verify loss of all coil power on the actual assembly; bypass and telemetry can behave differently |
| USB/logic supply lost, barrel retained | Separate power fault; verify coil states and recovery |
| ESP32 powered, ROS agent absent/disconnected | Shared candidate continues local pedal handling in a separate task and clears/disarms computer commands on detected link loss; historical firmware may stop forwarding |
| Commanding application stops, agent remains alive | Shared candidate expires unrenewed ON commands after 500 ms nominally and disarms computer control; historical firmware can latch ON indefinitely |
| Firmware hangs with an output HIGH | External watchdog does not independently clear activation |

Firmware attempts to clear activation outputs on detected agent loss. This is a
software action, not an independent shutdown guarantee. An agent ping does not
prove the commanding application is healthy. A shorted driver or welded relay
contact cannot be repaired by an MCU reset; a shorted sense input can resemble
a held pedal. These examples are not an exhaustive fault analysis.

The shared candidate's 500 ms expiry and 100 ms PC renewal interval are provisional
bench settings, not qualified reaction-time limits. Pedals remain effective on
expiry/disarm. Only completed local control cycles pet WDI; ROS work runs separately.
Expiry cannot cover a stalled control task/MCU or a welded contact. The firmware
cannot detect the external coil-power cutoff; a live MCU and renewed command can
still re-energize coils when power returns. Independent hardware inhibition remains
required for that fault coverage. No physical board was flashed by this update.

## Software and data limitations

- `firmware/shared/` now implements all three profiles, retaining the v1 pin map
  and its lack of external WDI. v3 adds LigaSure using GPIO33 control, GPIO25
  sense, and GPIO18 through R22 (680 ohm) to D12 for its indicator.
- All shared profiles publish packed Int32 at 115200 baud; `/esu/capabilities`
  identifies the flashed profile and reports lease/arm policy and diagnostics.
  This is not automatic physical PCB identification. The logger validates the
  supported-channel mask; historical telemetry requires an explicit legacy mode.
  Initial/reconnection snapshots are `sync` records, not actual activation edges
  or proof of a reset. Capability discovery supplies an initial state snapshot;
  offline transitions and host-side message loss are not exhaustively recoverable.
  Separate raw pedal/command streams are not implemented.
- Commander refuses unavailable channels. One executor thread processes replies;
  the calling thread waits without nested spinning. Pulse duration schedules an
  OFF request from the ON-send deadline, not from acknowledgement. This does not
  guarantee contact timing, successful OFF, or independent shutdown. On timeout,
  local future cancellation does not retract a command already sent to firmware.
- The matching commander starts disarmed, requires explicit arming, and renews
  desired ON commands. One missed renewal is tolerated; two consecutive misses
  clear its intentions and require re-arm;
  there is no automatic compatibility fallback to unleased legacy commands.
- Mock and bench tools select v1/v2/v3. Bench checks require explicit fixture
  confirmation. Isolate the ROS domain, with no other command clients. Software
  mock/unit results are not physical acceptance or safety qualification.
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
7. Board-power cutoff with a latched command, pedals released/held, every supply
   combination, and power restoration with the MCU still running. Confirm whether
   old commands/drive levels return; record the actual switch-controlled rail.

After addressing gaps, generator compatibility, connector pinouts, signal
levels, isolation, EMC, and applicable safety requirements need separate
qualified review and controlled validation. Generated manufacturing files,
stock availability, placement acceptance, and passing ERC/DRC are not functional
or clinical-use approval.
