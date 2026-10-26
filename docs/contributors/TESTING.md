# Testing

None of these tests establish safety, clinical suitability, generator
compatibility or RF timing (see [SAFETY.md](../SAFETY.md)). Never attach an
operating generator. `fixture_confirmed` means an isolated software mock or a
disconnected low-voltage dummy fixture, nothing else.

## 1. Offline Python tests (no ROS needed)

```bash
python3 -B -m unittest discover -s software/ros2/src/pedal_controller/test -v
```

Covers message schemas, invalid messages, unavailable-channel rejection,
command renewal and cleanup, logger synchronization, fixture gating, mock
behavior, and the install/flash guards (skipped when the package is copied
without this repository). Nodes run against a fake base class, so this does not
test rclpy, DDS, serial transport or hardware.

## 2. Firmware logic on the PC (Linux, no board)

For every revision in both pedal and no-pedal builds, as CI does:

```bash
for revision in 1 2 3; do for pedal in 1 0; do
  g++ -std=c++11 -Wall -Wextra -Werror -DESU_BOARD_VERSION=$revision -DESU_PEDAL_CONNECTED=$pedal \
    firmware/test/control_test.cpp -o /tmp/esu-control-test && /tmp/esu-control-test || break 2
  g++ -std=gnu++17 -pthread -Wall -Wextra -Werror -Wno-unused-parameter \
    -Wno-missing-field-initializers -Ifirmware/test/host_stubs \
    -DESU_BOARD_VERSION=$revision -DESU_PEDAL_CONNECTED=$pedal \
    firmware/test/runtime_sim.cpp -o /tmp/esu-runtime-sim && /tmp/esu-runtime-sim || break 2
done; done
```

`control_test` checks the pure control logic. `runtime_sim` runs the real
`runtime.hpp` on PC threads with stubbed Arduino/FreeRTOS/micro-ROS: pedal
forwarding, arming, lease expiry, telemetry resync, agent loss and reconnection,
watchdog petting, break-before-make, and floating inputs in no-pedal builds.
Neither covers the ESP32 scheduler, serial transport or electrical behavior.

## 3. ROS integration with the mock board

Use an isolated domain (73) in every terminal, with no real board on it:

```bash
./esu.sh mock v3
ESU_DOMAIN=73 ./esu.sh logger v3
ESU_DOMAIN=73 ./esu.sh commander v3
```

Repeat for v2 and v1. The mock models pedal OR command per channel, change-only
publishing and break-before-make; it does not model debounce, reconnects,
watchdogs or relays. Check:

1. Only the revision's channels are offered; LigaSure on a v2 mock is rejected
   and never turns into CUT.
2. After `arm`, each channel turns on and off with matching logger rows.
3. Ctrl+C during a command sends a best-effort OFF.
4. A logger restarted mid-session starts with `sync`, not an invented press.
5. A mock started with `ROS_DOMAIN_ID=73 ros2 run pedal_controller mock_esu_node
   --ros-args -p board_version:=v3 -p sim_surgeon:=true -p sim_channel:=ligasure`
   produces simulated pedal edges every 5 s.

Timing on the mock (PC-side only, no physical latency):

```bash
ros2 run pedal_controller latency_test --ros-args \
  -p board_version:=v3 -p fixture_confirmed:=true \
  -p channel:=ligasure -p iterations:=20 -p warmup:=2 -p trial_id:=MOCK1
```

ON and OFF are timed separately and every sample is saved to
`~/pedal_logs/latency_<trial_id>_<channel>_<time>.csv`. The test aborts on a
failed ON/OFF check rather than dropping the trial.

## 4. Real board on a disconnected dummy fixture

Flash the exact revision, run the agent instead of the mock, release all pedals
and stop other command clients. Measure contacts independently: relay clicks,
LEDs and acknowledgements are not enough.

```bash
ros2 run pedal_controller system_test --ros-args -p board_version:=v3 -p fixture_confirmed:=true
```

`system_test` walks every channel with computer and pedal and asks you to
confirm each contact. Then, per channel and revision:

- **Takeover:** arm, command one channel, press a different pedal, both ways.
  The commanded relay must open before the pressed one closes (one 10 ms cycle);
  check with both outputs on a scope/DAQ. Re-arm must be refused while the pedal
  is held, and the logger must show `takeover` then a `surgeon` press. With the
  pedal on the commanded channel itself, the output stays closed, `armed:false`,
  and a `takeover` row is written.
- **Lease expiry:** `kill -9` the commander (a normal exit sends OFF) with the
  agent alive. The output must open about 500 ms after the last renewal, and ON
  must be refused until re-arm.
- **Agent loss and reconnect** with a pedal held: the pedal keeps working and
  commands do not come back.

Run latency tests only after contact behavior is confirmed. Record the board and
assembly, commits, dependency versions, supplies, settings, repetitions,
instruments, traces and failures. The v2 results from 2026-10-22 are in
[SAFETY.md](../SAFETY.md#recorded-v2-disconnected-fixture-test-2026-10-22); the
remaining required physical tests are listed there.
