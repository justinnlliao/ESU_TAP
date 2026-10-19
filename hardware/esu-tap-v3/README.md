# ESU-TAP v3

Latest design: eight-relay, four-channel prototype for CUT, COAG, bipolar, and a path labeled LigaSure.
Open `esu_tap_v3.kicad_pro` using KiCad 10. The current design was checked with
KiCad 10.0.5. Local libraries use `${KIPRJMOD}` in the library tables.

## Current implementation

LigaSure uses GPIO33 control, GPIO25 sense, and GPIO18 through R22 (680 ohm)
to yellow indicator D12. `firmware/esu-tap-v3/` implements this fourth function;
the ROS logger/commander and revision-selectable mock/bench tools support its
shared packed-state/capability protocol. Physical operation, generator compatibility, and fault
recovery still require testing; software changes do not qualify the hardware.

## Protection limitations

U10 RESET drives Q1, which controls bypass relays U6–U9. It does not reset the
ESP32 or independently disable activation relays U2–U5. Watchdog RESET is
temporary and does not guarantee sustained fallback. The shared firmware candidate
adds local offline pedal processing and command expiry but needs physical validation.

The reported external board-power cutoff is distinct from watchdog timeout:
removing all coil power should release functioning activation relays as well as
bypass relays. The resulting manual pedal path can still activate the generator.
Switch wiring, alternate supplies, and restart behavior remain unverified. See
[proposed hardware changes](../../docs/HARDWARE_FAULT_HANDLING.md) for independent
activation inhibition and sustained fault handling; these changes are not installed.

See [Protection features and validation status](../../docs/SAFETY_AND_VALIDATION.md)
for the wiring evidence, power-loss distinction, and required tests. Do not
describe the board as validated fail-safe or clinically qualified.

## Manufacturing files

The `fabrication/` directory contains revision-specific manufacturing exports.
Use the matching Gerber ZIP, assembly BOM, and CPL. The CPL uses:

```text
Designator,Mid X,Mid Y,Rotation,Layer
```

Coordinates are mm, angles are counterclockwise degrees normalized to 0–359,
and layer names are Top/Bottom. The format correction preserves placement
coordinates and equivalent orientations; it does not apply part-specific JLC
rotation corrections. Check every polarized part in JLCPCB's preview.

The 2026-09-11 KiCad review reported no ERC/DRC errors, no unconnected PCB items,
and no schematic/PCB parity issues under the configured checks. Nine footprint
library warnings and five schematic warnings remained. Some rule checks are
disabled in the project. This report is not proof of functional safety,
component stock, or assembler acceptance.
