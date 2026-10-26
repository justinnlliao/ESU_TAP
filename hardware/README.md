# Hardware

One KiCad project per revision, with project-local libraries (`${KIPRJMOD}`
paths in the symbol and footprint tables) and manufacturing exports in
`fabrication/`.

| Revision | Relays | Channels | Notes |
| --- | --- | --- | --- |
| [v1](esu-tap-v1/README.md) | 3 | CUT, COAG | Original design |
| [v2](esu-tap-v2/README.md) | 6 | CUT, COAG, bipolar | Bench-tested 2026-10-22 ([record](../docs/SAFETY.md#recorded-v2-disconnected-fixture-test-2026-10-22)) |
| [v3](esu-tap-v3/README.md) | 8 | CUT, COAG, bipolar, LigaSure | Latest; KiCad 10 |

On v2 and v3 each channel has a bypass relay (pedal path, restored when
unpowered) and an activation relay (closes the generator-side contact). The external
watchdog controls only the bypass relays; see [SAFETY.md](../docs/SAFETY.md).
Connectors and wiring: [CONNECTORS.md](../docs/CONNECTORS.md).

## Ordering boards

Use Gerbers, BOM and CPL generated from the same saved design. Gerbers, drill
files and ZIPs are Git-ignored, so generate them from KiCad. For JLCPCB the CPL
needs `Designator,Mid X,Mid Y,Rotation,Layer` (mm, Top/Bottom); KiCad's native
position file may need conversion. Check every polarized part's orientation and
stock in the assembler's preview. Hand-installed parts are listed separately
from the SMD assembly files.
