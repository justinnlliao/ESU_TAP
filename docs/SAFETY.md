# Safety and validation status

ESU-TAP is a research prototype. It is **not validated for clinical use**, and
no system-level fault tolerance or numerical reliability is claimed. Passing
KiCad checks, software tests or normal-operation trials does not change that.
Findings below apply to the revision stated; do not transfer them to another
revision or an assembled board without checking it.

A description supported by the current evidence:

> The prototype incorporates input-protection components and a normally
> de-energized relay bypass intended to preserve manual pedal operation during
> board power loss. An external watchdog controls the bypass relays. Firmware
> handles pedals locally without ROS and expires computer commands. Independent
> hardware removal of computer activation and sustained fault recovery are not
> implemented, and system-level fault tolerance has not been validated.

## What the board does and does not protect against

- **Input protection.** PTC, series Schottky and TVS parts on the supply, ESD
  clamps and series resistors on the sense lines. They are not a validated
  wrong-voltage cutoff, RF-immunity or isolation measure. Use regulated 5 V
  center-positive power.
- **Power-loss bypass.** With relay-coil power off, the relays are intended to
  connect each pedal straight to the generator. This is manual fallback, **not
  an emergency stop**: a held pedal keeps activating the generator.
- **Firmware mitigations.** Pedals are handled in a local task independent of
  ROS. Computer commands start disarmed, expire 500 ms after the last renewal,
  and are cleared on agent loss or a pedal press. These are software actions
  with provisional timing, not independent shutdown.
- **Published state** is inferred from inputs and commands, not measured relay
  contacts or confirmed RF output.

| Condition | Behavior |
| --- | --- |
| All board power removed | Manual bypass intended; verify continuity on the assembly |
| Barrel removed, USB kept / USB removed, barrel kept | Separate faults; verify coil states and recovery for each |
| ESP32 powered, ROS agent lost | Local pedals continue; computer commands cleared and disarmed |
| Commanding program stops, agent alive | Unrenewed commands expire after 500 ms and disarm |
| Firmware hangs with an output on | **Not covered.** The watchdog does not clear activation outputs |
| Welded relay contact or shorted driver | **Not covered.** No reset can open it; a shorted sense input looks like a held pedal |

Firmware built before the 2026-10-13 shared firmware has no command expiry and
may stop forwarding pedals offline. Reflash it.

## Board-power cutoff and energized testing

The lab uses a button that removes interface-board power (not generator power)
during supervised phantom testing. Removing **all relay-coil power** should open
the activation relays and restore the manual pedal path, so:

- computer-commanded activation is intended to stop, unless a contact is welded
  or another supply keeps coils energized;
- a held pedal can continue activating through the restored bypass;
- removing only USB/logic power is not the same as removing coil power;
- restoring coil power while the ESP32 stayed powered could re-apply a command;
  the button does not reset the firmware.

Call this a **computer-control cutoff with manual pedal fallback**, not a
stop-all-RF emergency stop. Energized tests need a lab-approved procedure, the
generator manufacturer's instructions, and an independent way to stop the
generator. Never use a continuity meter on a live generator connection; RF
cessation is a separate, generator-specific measurement.

## v3 external watchdog wiring

| Connection | Function |
| --- | --- |
| U1 GPIO14 to U10 WDI | Firmware watchdog input |
| U10 RESET to Q1 gate | Controls bypass-coil return |
| Q1 drain (`/COIL_GND`) to U6-U9 coil returns | Releases bypass relays when Q1 turns off |
| U2-U5 coil returns to Q2-Q5 | Separate ESP32-driven activation relays |
| U1 EN | Not connected to U10 RESET |

The TPS3823A times out after 0.9-2.5 s and pulses RESET for 120-300 ms, then
restarts ([TI datasheet](https://www.ti.com/lit/ds/symlink/tps3823.pdf) §6.8,
§7.3.4). A timeout briefly releases the bypass relays but does not reset the
ESP32, remove activation drive, or hold the bypass until recovery. For example,
U5 connects `GEN_LIGA` to `LIGA_GEN_COM` independently of U9, so moving the
pedal path cannot break a stuck U5. v2 has the same arrangement (U9 RESET drives
Q1; ESP32 EN unconnected). ESP32 internal watchdog coverage is not validated.
Proposed fixes: [contributors/HARDWARE_FAULT_HANDLING.md](contributors/HARDWARE_FAULT_HANDLING.md).

## Recorded v2 disconnected-fixture test (2026-10-22)

Operator-reported results for one v2 board, generator unplugged, with
independent contact measurement on the generator-side outputs. Firmware
`3.2.0-bench` (confirmed by `/esu/capabilities`, boot IDs 13-14), source commit
`dd7bd6f` plus the uncommitted `esu.sh` commander-prompt removal, pedal build,
jazzy micro-ROS agent image, ROS domain 0. Assembly ID, supply part numbers and
meter/scope model were not recorded. Logger file:
`~/pedal_logs/pedal_log_T01_20261022_204146_653592.csv` (210 rows, 0 dropped
events) on the test PC.

| # | Test | Result |
| --- | --- | --- |
| 1 | `system_test`: every v2 channel, computer and pedal, fresh telemetry | Pass |
| 2 | Pedal takeover both directions, same-channel takeover, re-arm refused with pedal held | Pass (7 takeover rows logged) |
| 3 | Commander `kill -9` with agent alive: output opens on lease expiry; ON refused until re-arm | Pass |
| 4 | Agent stopped: output opens, pedals still work, no command revival on reconnect | Pass |
| 5 | Barrel removed, USB removed, both removed, stop button; each with computer ON and pedal held; power restored | Pass, with observation below |
| 6 | Controller stall / firmware hang | **Not tested** |
| 7 | Logger against measured contact behavior | Pass for the events logged; offline periods have no telemetry |

**Observation (test 5, USB reconnected):** with a pedal held, plugging USB back
in causes a short, noticeable interruption of that pedal's output before it
recovers. The likely cause is the boot handover: the bypass relays move the
pedal path to the board shortly after power returns, before the firmware
control task is forwarding pedals. This interrupts activation (it opens, not
closes) but would interrupt a held cut. Duration was not measured; use a scope
if it matters. Avoid plugging or unplugging USB while a pedal is in use.

Not covered by this record: test 6, sense open/short and stuck-driver faults
(items 3 and 5 below), v1/v3 boards, the `nopedal` build, RF cessation on an
energized generator, release-time acceptance criteria, and repetitions. This is
one bench session on one board, not system-level validation.

## Verification still required

On a disconnected low-voltage dummy fixture, with response-time and re-arm
acceptance criteria defined **before** testing:

1. Each pedal/command channel and release, startup, and reconnection.
2. Total power loss and each supply lost independently.
3. Controller stall with outputs off and each activation on, over several
   watchdog periods.
4. Agent loss, transport loss with logic power kept, and commanding-process
   loss with the agent alive.
5. Sense open/short faults and simulated stuck drivers/contacts.
6. Logger agreement with independent contact measurements.
7. Board-power cutoff with a latched command, pedals released and held, every
   supply combination, and power restored with the ESP32 still running.

For each trial record: board revision and assembly ID, source commit, firmware
build, supply and switch wiring, generator/pedal identity, test type
(disconnected or energized phantom), procedure reference, stimulus, independent
measurements, response time, result, and log/trace location. Mark unperformed
tests **not tested**, keep failed trials, and note reconnect gaps; missing
telemetry is not evidence of inactivity.

Beyond these, generator compatibility, connector pinouts, signal levels,
isolation, EMC and applicable safety standards need separate qualified review.
