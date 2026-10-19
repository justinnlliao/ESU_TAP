# Proposed hardware fault-handling changes

Design requirements dated 2026-10-13, **not implemented or qualified**.
See [current protection and validation status](SAFETY_AND_VALIDATION.md).
No PCB, schematic, or fabrication files are changed by this proposal. A subsequent
shared firmware candidate implements some software mitigations, not hardware fixes.

## Existing design and scope

v2 has six relays (three activation and three bypass); v3 has eight (four of
each). v3 is the latest design, not proof of the physical revision under test.
In the inspected v3 PCB, U10 RESET drives Q1 gate, Q1 drain drives `/COIL_GND`,
and U6-U9 are bypass relays. U2-U5 activation coils have separate Q2-Q5 drivers;
U1 EN is unconnected. For example, U5 closes `GEN_LIGA` to `LIGA_GEN_COM`
independently of U9 bypass position. Do not transplant reference designators or
rework instructions onto v2 or an assembled board without checking its nets.

The operator's board-power button is reported, not electrically verified. If it
removes all coil power, functioning activation relays should open while manual
pedal bypass returns. It is not an unconditional RF stop. Power restoration can
re-energize coils if the MCU stayed powered with a command/drive still asserted.

## Required design decisions and changes

1. **Distinguish two functions.** Controller-fault fallback should remove
   computer activation and restore manual pedal control. A stop-all-energy
   function must also override a held pedal. These are different requirements;
   a normally closed manual bypass cannot by itself provide the latter. Define
   a generator-manufacturer-compatible independent stop with the lab's qualified
   reviewer; this document does not prescribe generator mains or RF-path wiring.
2. **Add an independent activation inhibit.** A hardware-controlled enable
   must remove activation-coil drive despite a stuck-HIGH MCU output or shorted
   low-side driver. Review a dedicated switched coil-supply architecture or
   equivalent; merely moving the pedal common or resetting the MCU is insufficient.
   Coordinate bypass release to restore the intended manual path. Verify default
   OFF behavior at startup, missing logic power, undervoltage, and fault assertion.
3. **Latch the fault until deliberate re-arm.** A watchdog timeout must disable
   activation and maintain fallback until an explicit recovery sequence succeeds.
   Define startup inhibition, fault dominance, cleared commands, valid controller
   health, and deliberate re-arm. Neither returning power, resuming heartbeat,
   nor reconnecting ROS should automatically restore a previous computer ON.
   The existing TPS3823A RESET pulse alone is not a sustained fault latch:
   [TI datasheet, section 7.3.4](https://www.ti.com/lit/ds/symlink/tps3823.pdf).
4. **Audit every power and discharge path.** Size the enable switch for the
   actual simultaneous coil load and transients; review flyback paths, release
   delay, decoupling, USB/backfeed, and the physical cutoff's switched rail.
   Verify that no alternate path keeps coils energized. Keep generator-side
   commons separate; do not combine them to simplify an inhibit circuit.
5. **Address stuck contacts separately.** Coil-power removal cannot open a
   welded relay contact. If the fault-tolerance requirement includes this case,
   review independent series interruption of the computer-activation branches,
   suitable feedback, and detection of failed interruption. Maintain each
   channel's isolation/common separation and analyze failures of the added
   inhibit itself. One extra switch does not establish single-fault safety.
6. **Treat MCU reset as recovery, not the shutdown mechanism.** A reviewed
   supervisor-to-EN connection may assist recovery, but its voltage, drive type,
   boot timing, and USB/programming circuitry must be checked. It does not
   substitute for independent activation inhibition or welded-contact coverage.

Exact switch/relay/latch parts, current ratings, response limits, resistor values,
and wire-cut/jumper locations remain unspecified pending schematic design and
review. This is not a drop-in part substitution. Existing-board rework or an
external safety module may be possible, but neither has been designed here.

## Firmware candidate and validation still needed on the existing PCB

- Shared firmware now has a provisional 500 ms command lease and 100 ms client
  renewal, a separate local pedal task, and deliberate computer re-arm after
  expiry/disconnect. Agent ping success alone is not application health.
- WDI is fed after completed local control cycles, not the ROS waiting loop.
  This does not fix the temporary-bypass/independent-activation hardware gap.
- Validate these changes on the exact assembly. Coil-power loss/restoration is
  not sensed by the firmware, and complete MCU hangs still need hardware coverage.

These can be developed without a PCB order but do not make the current hardware
independently fault-tolerant. Bench validation is required before deployment.

## Validation before claiming the gap is closed

On a generator-disconnected low-voltage fixture, record startup, controller
stall, agent/application/transport loss, every supply combination, cutoff and
power restoration, held pedals, and controlled stuck-driver/contact simulations.
Observe multiple watchdog periods and actual contact continuity. Set acceptable
response times and recovery conditions before the tests; do not invent pass
limits after seeing the measurements. Confirm added shutdown components' failure
behavior and retain unsuccessful trials. Energized phantom validation is a
separate qualified, generator-specific procedure, not these fault-injection tests.
