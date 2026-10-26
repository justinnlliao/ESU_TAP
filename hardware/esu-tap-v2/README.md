# ESU-TAP v2

Six-relay, three-channel (CUT, COAG, bipolar) design. Open `esu_tap_v2.kicad_pro`.
Build firmware with `--board v2`.

One v2 board passed a disconnected-fixture bench session on 2026-10-22; see the
[test record](../../docs/SAFETY.md#recorded-v2-disconnected-fixture-test-2026-10-22).
U9 RESET drives Q1 (bypass relays only) and ESP32 EN is unconnected, so the
watchdog does not reset the ESP32 or clear activation outputs.

Enclosure dimensions: [contributors/ENCLOSURE_V2.md](../../docs/contributors/ENCLOSURE_V2.md).
The v3 reference designators in
[HARDWARE_FAULT_HANDLING.md](../../docs/contributors/HARDWARE_FAULT_HANDLING.md)
do not apply directly to v2.
