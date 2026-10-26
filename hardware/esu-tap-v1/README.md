# ESU-TAP v1

Original two-channel (CUT, COAG) design, kept for existing boards. Open
`esu_tap_v1.kicad_pro`. New work is in [v3](../esu-tap-v3/README.md).

Build firmware with `--board v1`: v1 uses sense GPIO34/35 and LED GPIO18/21, so a
v2/v3 profile must not be flashed onto it. v1 has no external watchdog. No
physical test of a v1 board with the current firmware is recorded.
