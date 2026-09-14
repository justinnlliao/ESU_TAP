# Software regressions and disconnected-fixture checks

These procedures do not establish functional safety, clinical suitability,
generator compatibility, RF delivery timing, or numerical reliability.
See [pending physical fault tests](../../docs/SAFETY_AND_VALIDATION.md).
Do not attach an operating electrosurgical generator to these tests.

## 1. Offline regression tests (no ROS required)

From the repository root, with Python 3.10 or newer:

```bash
python -B -m unittest discover -s software/ros2/src/pedal_controller/test -v
```

The suite checks all three message schemas, invalid messages, unavailable-channel
rejection, pulse cleanup/deadlines, response failures, fresh-state matching,
receipt timestamps, logger synchronization, fixture gating, and mock behavior.
Node classes use a minimal fake base: this does **not** validate rclpy execution,
DDS, serial transport, firmware compilation, or electrical behavior.

## 2. Actual ROS mock integration (required separately)

Build/source the workspace as described in [SETUP.md](SETUP.md).
In **every** mock-test terminal, use an isolated ROS domain unused by real boards:

```bash
export ROS_DOMAIN_ID=73
source /opt/ros/humble/setup.bash
source ~/ESU_TAP/software/ros2/install/setup.bash
```

Start logger first, then the mock, then a client in separate terminals:

```bash
ros2 run pedal_controller pedal_logger
ros2 run pedal_controller mock_esu_node --ros-args -p board_version:=v3
ros2 run pedal_controller pedal_commander
```

The mock defaults to v3 with simulated pedals OFF. Repeat with `v2` and `v1`.
It models per-channel pedal OR command and timer-driven, change-only publishing.
It does not model debounce electronics, reconnect behavior, watchdogs or relays.

Checks:

1. Correct services exist; commander shows only available channels.
2. Select unavailable LigaSure on a v2 mock: commander must reject, never send CUT ON.
3. Pulse each supported channel; observe ON/OFF requests and logger edges without
   artificial service timeouts. Pulse timing is PC request scheduling only.
4. Ctrl+C during a command: verify best-effort OFF acknowledgement.
5. Restart logger mid-session: first observation is `sync`, not an invented press.
   An idle late subscriber may wait for a change; the firmware has no state query.
6. Start a fresh mock with `-p sim_surgeon:=true -p sim_channel:=ligasure` on v3
   to exercise that channel's simulated pedal edges (default period 5 seconds).
7. Never run two mock/hardware service providers with these names in the same domain.

Automated mock timing check (no real board in this domain):

```bash
ros2 run pedal_controller latency_test --ros-args \
  -p board_version:=v3 -p fixture_confirmed:=true \
  -p channel:=ligasure -p iterations:=20 -p warmup:=2
```

`fixture_confirmed` confirms an isolated software mock OR a physically
disconnected low-voltage dummy fixture, not generator permission.
Repeat each channel on each revision. Missing services/wrong-width telemetry fail.
The benchmark aborts on failed ON/OFF checks, not silently excluding bad trials.

Service-response and state-message timestamps are captured independently in
their completion/receipt handlers using the PC monotonic clock. State can arrive
before the response. The 10-ms firmware timer is a polling interval, not proof
of a fixed RTT-plus-5-ms relationship. No physical/RF latency is measured.

## 3. Actual board on a disconnected dummy fixture

Use the exact revision's firmware and one isolated real board; replace the mock
with the serial agent. Release all pedals and stop other command clients.

```bash
ros2 run pedal_controller system_test --ros-args \
  -p board_version:=v3 -p fixture_confirmed:=true
```

The interactive test walks **all selected-revision channels**, checks fresh
computer and pedal telemetry, and asks for independent contact measurements.
It does not silently substitute CUT or accept an old snapshot. Use independent
continuity measurements: relay clicks, LEDs and acknowledgements are insufficient.
OFF at cleanup is best-effort and does not override a held physical pedal.

Run latency testing separately only after contact behavior has been checked.
Record the exact board/assembly, firmware/software commits, dependency versions,
supplies, domain/serial settings, repetitions, instrumentation, traces and failures.

## Outstanding safety work

Command expiration and powered-offline forwarding remain unimplemented; the
external watchdog does not independently cancel activation or reset the ESP32.
Define timeout, refresh and re-arm requirements before changing those behaviors.
Validate supply loss, agent/transport/process loss, stalls, and stuck-contact/driver
faults on a controlled dummy fixture. This software update does not resolve them.

The 2026-09-14 update was tested offline only. Actual ROS Humble integration,
target firmware builds and physical fault testing remain required.
