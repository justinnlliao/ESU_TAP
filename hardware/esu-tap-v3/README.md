# ESU-TAP v3

Latest design: eight relays, four channels (CUT, COAG, bipolar, and a path
labeled LigaSure). Open `esu_tap_v3.kicad_pro` in KiCad 10 (checked with 10.0.5).
Build firmware with `--board v3`.

LigaSure uses GPIO33 control, GPIO25 sense, and GPIO18 through R22 (680 ohm) to
yellow indicator D12. The schematic note "GPIO32" is stale. No physical test of
a v3 board is recorded yet, and LigaSure compatibility with a specific
vessel-sealing generator is not established.

U10 RESET drives Q1, which controls bypass relays U6-U9 only. It does not reset
the ESP32 or disable activation relays U2-U5; see [SAFETY.md](../../docs/SAFETY.md)
and the proposed fixes in
[HARDWARE_FAULT_HANDLING.md](../../docs/contributors/HARDWARE_FAULT_HANDLING.md).

## Manufacturing files

`fabrication/` holds the BOM, CPL and job file. The CPL uses
`Designator,Mid X,Mid Y,Rotation,Layer`: mm, counterclockwise degrees 0-359,
Top/Bottom. Part-specific JLC rotation corrections are not applied; check every
polarized part in JLCPCB's preview.

The 2026-09-11 KiCad review reported no ERC/DRC errors, no unconnected items and
no schematic/PCB parity issues under the configured checks, with nine footprint
library and five schematic warnings remaining. Some rule checks are disabled.
