# Roadmap and known limitations

The current status is [Protection features and validation](SAFETY_AND_VALIDATION.md).
These items include known implementation gaps, not merely optional upgrades.
Archived proposals are not current assembly or safety specifications.

## Fault handling

- Design and review an independent means of removing computer activation during
  controller failure while preserving manual pedal control.
- Define sustained bypass and deliberate recovery/re-arm behavior. The current
  temporary watchdog RESET pulse does not provide this by itself.
- Implement command expiration/controller-liveness handling and dependable
  powered-offline pedal behavior. Agent connectivity alone is insufficient.
- Audit the built ESP32 firmware's internal watchdog and reset settings.
- Record dummy-fixture fault tests before making fault-tolerance claims.
  Include stuck drivers/contacts; an MCU reset cannot repair these failures.

## Software compatibility

v3 hardware adds LigaSure, but checked-in firmware supports CUT/COAG/bipolar only.
Coordinate the fourth service, message schema, logger, commander, mock, and tests.
Use explicit hardware-revision selection rather than silently flashing a v3
pin map onto older boards.

Current firmware publishes `[cut, coag, bipolar, source]`; the logger expects
`[cut, coag, source]`. Correct and test this mismatch before relying on data.
v3 LigaSure uses GPIO33 control, GPIO25 sense, and GPIO18 LED through R22/D12.

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
a legacy mock test cannot substitute for this evidence.
