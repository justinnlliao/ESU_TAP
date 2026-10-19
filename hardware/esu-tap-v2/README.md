# ESU-TAP v2

Six-relay, three-channel CUT/COAG/bipolar hardware. Open `esu_tap_v2.kicad_pro`.
Project-local libraries use `${KIPRJMOD}` paths in the symbol/footprint tables.

The shared firmware's v2 profile targets this pin map, with capability discovery,
packed telemetry, local offline pedal handling, and expiring computer commands.
It is an unqualified bench candidate, not a flashed-board test result.
See [current limitations](../../docs/SAFETY_AND_VALIDATION.md).

A targeted PCB inspection on 2026-09-11 confirmed U9 RESET drives Q1 and ESP32 EN
is unconnected; do not describe the external supervisor as resetting the ESP32.
This was not a fresh full v2 electrical or functional qualification.

Removing all coil power should release functioning activation relays and restore
manual pedal bypass, not guarantee all RF stops. Verify any external board-power
cutoff with every supply combination and on power restoration. The reported
phantom-test cutoff has not been qualified here. See
[proposed hardware fault-handling changes](../../docs/HARDWARE_FAULT_HANDLING.md);
its v3 reference designators must not be applied directly to v2.

Exports are in `fabrication/`. Generate and review a matching Gerber/BOM/CPL
set for the exact saved revision. Availability of these files is not a safety
approval; verify placement and stock separately.
