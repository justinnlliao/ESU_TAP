# ESU-TAP v1 firmware (historical restoration)

For the physical two-channel v1 PCB only. Do not select the v2/v3 PlatformIO
projects for this board: the sense/LED pin maps differ.

The source, platformio.ini and colcon.meta were restored unchanged (allowing
checkout newline normalization) from commit
`c63bfcf2c6faf4437ad764aeee6c91029624eb55`, under `microros_firmware/`.
That commit recorded a working system; this restoration is not a fresh bench
test or a recovered binary. Unpinned dependencies can change today's build.

| Signal | GPIO |
| --- | --- |
| CUT / COAG sense | 34 / 35 |
| CUT / COAG relay drive | 26 / 27 |
| CUT / COAG LED | 18 / 21 |

USB serial: 115200 baud. ROS 2 Humble; default domain 0. Services are
`/esu/cut` and `/esu/coag`; state is `[cut, coag, source]`.
Source 2 is a boot/reconnection baseline, not proof of an MCU reset.

Follow the [full new-account recovery guide](../../docs/V1_BLUE_SETUP.md).
Build with `pio run -e esp32dev` in THIS folder; upload only after identifying
the correct board/port, with the generator disconnected. The historical ini's
`/dev/esp32-esu` port can be overridden with `--upload-port`.

Historical source comments are preserved for traceability. Claims of safe OFF,
guaranteed bypass, or reliable restart are not current qualification. There is
no command lease, dependable powered-offline forwarding, or added hardware
watchdog. See [limitations](../../docs/SAFETY_AND_VALIDATION.md).
