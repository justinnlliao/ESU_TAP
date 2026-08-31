# ESU-TAP v3

Active KiCad 9 hardware project for ESU-TAP.

Open `esu_tap_v3.kicad_pro` from this directory. The `libraries/` directory is
project-local and is registered through `sym-lib-table` and `fp-lib-table` using
`${KIPRJMOD}` paths, so a clean clone opens without user-specific library paths.

This directory contains source design data only. Generate Gerbers, assembly BOMs,
and placement files from a reviewed commit when creating a fabrication release.
