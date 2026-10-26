# Roadmap and known limitations

The current status is [Protection features and validation](../SAFETY.md).
These items include known implementation gaps, not merely optional upgrades.
Archived proposals are not current assembly or safety specifications.

## Fault handling

The [hardware fault-handling proposal](HARDWARE_FAULT_HANDLING.md) separates
manual-pedal fallback from stop-all-energy behavior and outlines independent
activation inhibition, fault latching, re-arm, and stuck-contact coverage.
It is not an implemented redesign or an approved existing-board modification.
The reported board-power cutoff still needs supply/cutoff/restart measurements.

- Design and review an independent means of removing computer activation during
  controller failure while preserving manual pedal control.
- Define sustained bypass and deliberate recovery/re-arm behavior. The current
  temporary watchdog RESET pulse does not provide this by itself.
- Command expiry, deliberate re-arm and the local pedal task passed the v2 bench
  session; repeat on other revisions and with repetitions.
- Audit the built ESP32 firmware's internal watchdog and reset settings.
- Record dummy-fixture fault tests before making fault-tolerance claims.
  Include stuck drivers/contacts; an MCU reset cannot repair these failures.

## Software compatibility

Shared v1/v2/v3 firmware profiles, capability-aware commander/logger support, and
explicit revision selection in the mock/bench tests are implemented. v3 LigaSure uses
GPIO33 control, GPIO25 sense, and GPIO18 LED through R22/D12.

- v2 has run under ROS 2 Humble on a disconnected fixture (2026-10-22). Repeat
  on v1 and v3, and for the `nopedal` build.
- Record the remaining physical fault tests (controller stall, sense and
  stuck-driver faults); offline tests do not cover them.
- Measure and, if needed, fix the short pedal dropout when USB is reconnected
  with a pedal held (boot handover; see the v2 test record).
- Validate the provisional 500 ms lease / 100 ms renewal (one missed renewal
  tolerated) and re-arm behavior. No physical response-time acceptance
  threshold is approved.
- Measure telemetry publish-confirmation time on the real serial link and count
  resync baselines per session; the 50 ms confirmation window is unmeasured.
- Capability snapshots/boot ID/drop count are implemented; add complete event
  sequence tracking if exhaustive message-loss detection is required.
- Verify pinned platform/wrapper target builds and capture transitive ROS
  dependencies and agent image digest; the dependency lock is not yet complete.
- Retain revision selection; never flash a v3 pin map onto older boards.

## Power, signals, and interfaces

- Use regulated 5 V center-positive power. PTC/Schottky/TVS components do not
  provide a validated sustained-overvoltage cutoff. An eFuse is future design
  work; do not assume an existing compatible footprint or drop-in installation.
- Verify current footprints and BOM population instead of archived ferrite/DNP
  proposals. Leaving a series element unpopulated can open a signal path.
  RF immunity and sense-clamp performance require measurement.
- Validate every pedal/generator pinout, signal level, common, and identity
  connection. A relay path labeled LigaSure does not establish compatibility
  with a particular vessel-sealing generator.
- Evaluate enclosure, strain relief, isolation, EMC, and applicable safety
  requirements before use beyond the disconnected bench fixture.
- Optional future work includes appropriate overvoltage cutoff, keyed connectors,
  generator feedback, and local logging. Do not assume standard VSPI pins are
  free; several are already used, including GPIO18 on v3.

## Data integrity and reporting

Published status is inferred sense/command state, not measured contacts or RF
delivery. Generator arbitration may suppress a command; verify it per generator.
Separate command, pedal, contact, and generator-feedback records would support
stronger claims but are not all implemented.

Report test conditions, repetitions, failures, and response times. No system
failure probability or clinical-use approval is established. Passing ERC/DRC or
a software mock test cannot substitute for this evidence.
