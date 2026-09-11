# ESU-TAP v2

Three-channel CUT/COAG/bipolar hardware. Open `esu_tap_v2.kicad_pro`.
Project-local libraries use `${KIPRJMOD}` paths in the symbol/footprint tables.

The checked-in firmware targets the v2 pin map, but the ROS logger's message
schema remains incompatible. Powered-offline forwarding is not dependable in
the present firmware. See [current limitations](../../docs/SAFETY_AND_VALIDATION.md).

A targeted PCB inspection on 2026-09-11 confirmed U9 RESET drives Q1 and ESP32 EN
is unconnected; do not describe the external supervisor as resetting the ESP32.
This was not a fresh full v2 electrical or functional qualification.

Exports are in `fabrication/`. Generate and review a matching Gerber/BOM/CPL
set for the exact saved revision. Availability of these files is not a safety
approval; verify placement and stock separately.
