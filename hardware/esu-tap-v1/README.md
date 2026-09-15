# ESU-TAP v1 (historical)

Historical monopolar KiCad revision retained for comparison and traceability.
New four-channel work is in [v3](../esu-tap-v3/README.md).

Original two-channel firmware is restored in
[firmware/esu-tap-v1](../../firmware/esu-tap-v1/README.md) from commit c63bfcf.
Use the [new-account setup and reflash guide](../../docs/V1_BLUE_SETUP.md).
Do not flash v2/v3: v1 uses CUT/COAG sense GPIO34/35 and LED GPIO18/21.

Earlier design notes contain claims about v1 bypass failures. They are historical
records, not a fresh verification of the user's manufactured board or its
fabrication snapshot. Do not infer that a working physical board changed because
a newer KiCad version was installed.

See [protection and validation status](../../docs/SAFETY_AND_VALIDATION.md).
v3 analysis does not validate or invalidate a particular v1 assembly. Record its
exact source revision, firmware, wiring, and physical tests before making claims.
