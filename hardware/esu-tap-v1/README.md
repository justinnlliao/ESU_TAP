# ESU-TAP v1 (historical)

Historical monopolar KiCad revision retained for comparison and traceability.
New four-channel work is in [v3](../esu-tap-v3/README.md).

The [v1 firmware profile](../../firmware/esu-tap-v1/README.md) now uses the shared
bench candidate. Original firmware remains in Git at c63bfcf. Use the
[unified setup](../../software/ros2/SETUP.md) with `--board v1`.
Do not flash v2/v3: v1 uses CUT/COAG sense GPIO34/35 and LED GPIO18/21.

Earlier design notes contain claims about v1 bypass failures. They are historical
records, not a fresh verification of the user's manufactured board or its
fabrication snapshot. Do not infer that a working physical board changed because
a newer KiCad version was installed.

See [protection and validation status](../../docs/SAFETY_AND_VALIDATION.md).
v3 analysis does not validate or invalidate a particular v1 assembly. Record its
exact source revision, firmware, wiring, and physical tests before making claims.
