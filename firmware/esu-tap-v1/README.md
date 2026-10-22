# v1 firmware profile (legacy hardware retained)

v1 remains supported using the shared firmware's explicit **v1** profile.
CUT/COAG sense GPIOs are 34/35; relay GPIOs 26/27; LEDs 18/21. No external WDI
is configured. Do not use a newer PCB profile on this board.

The files here are compatibility entry points to [shared firmware](../README.md),
not an unchanged historical restoration. Current serial baud is 115200 and
telemetry is packed Int32 with protocol-2 capability discovery, explicit computer
arming and command expiry. Physical pedal handling runs independently of ROS.

Use the [unified setup](../../software/ros2/SETUP.md):
`python3 software/esu.py build --board v1` from the repository root
(add `--no-pedal` for standalone use without a pedal; unwired IO34/IO35 float).
The old directory still supports build-only `pio run -e esp32dev`.
Flashing requires the helper's explicit board/port/disconnected-fixture confirmation.

The original restoration remains traceable to commit
`c63bfcf2c6faf4437ad764aeee6c91029624eb55`, which also documents that older
image and its 115200/array interface; it is not the current install procedure.
No physical v1 validation is established by this refactor.
