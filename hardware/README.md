# Hardware

KiCad source for ESU-TAP lives here. Each revision is self-contained: open the
`.kicad_pro` file in its revision directory and KiCad resolves the project-local
symbols, footprints, and 3D models through `${KIPRJMOD}`.

- [`esu-tap-v2/`](esu-tap-v2/) is the active KiCad 9 revision.
- [`esu-tap-v1/`](esu-tap-v1/) is retained as a historical reference.

Fabrication exports are generated only for a reviewed release and should be
attached to that release or stored under a revision-specific `production/`
directory. Local Gerbers, BOMs, placement files, caches, and lock files are
ignored by Git.
