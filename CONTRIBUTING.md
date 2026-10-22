# Contributing to ESU-TAP

Thanks for helping. ESU-TAP switches an electrosurgical generator's footswitch
contacts, so a few rules come before everything else.

## Safety rules

- Test on a **generator-disconnected fixture**. Never test changes on a live
  generator or anything connected to a patient.
- Do not describe a change as making the device "safe" or "fail-safe". State what
  was tested and how, in the terms of [docs/SAFETY_AND_VALIDATION.md](docs/SAFETY_AND_VALIDATION.md).
- Changes to relay, pedal, arming or command-expiry logic must say how they were
  physically verified (fixture, scope/DAQ, board revision), or state clearly that
  they were not.

## Running the tests

These are the checks CI runs. None of them needs ROS or hardware.

```bash
# Python package tests
python3 -B -m unittest discover -s software/ros2/src/pedal_controller/test

# Firmware control logic and runtime simulation on the host.
# Repeat for ESU_BOARD_VERSION=1/2/3 and ESU_PEDAL_CONNECTED=1/0.
g++ -std=c++11 -Wall -Wextra -Werror -DESU_BOARD_VERSION=3 -DESU_PEDAL_CONNECTED=1 \
  firmware/test/control_test.cpp -o /tmp/esu-control-test && /tmp/esu-control-test
g++ -std=gnu++17 -pthread -Wall -Wextra -Werror -Wno-unused-parameter \
  -Wno-missing-field-initializers -Ifirmware/test/host_stubs \
  -DESU_BOARD_VERSION=3 -DESU_PEDAL_CONNECTED=1 \
  firmware/test/runtime_sim.cpp -o /tmp/esu-runtime-sim && /tmp/esu-runtime-sim

# Firmware build for a board (does not flash)
python3 software/esu.py setup
python3 software/esu.py build --board v3

# Shell scripts
shellcheck esu.sh software/ros2/src/pedal_controller/esu_run.sh
```

For ROS-level testing without hardware, use the mock board described in
[software/ros2/TESTING.md](software/ros2/TESTING.md).

## Pull requests

- Say which board revisions (v1, v2, v3) the change affects.
- Add a line to [CHANGELOG.md](CHANGELOG.md) under an "Unreleased" heading.
- Update the docs when commands, parameters or the ROS interface change.
- Keep the `/esu/*` service and topic names and the `activation_state` bit
  layout compatible, or call out the breaking change clearly.
- Keep firmware behavior in `firmware/shared/`; revision differences belong in
  the board profile, not in copies of the code.

## Reporting bugs

Please include:

- board revision and firmware version (`ros2 service call /esu/capabilities std_srvs/srv/Trigger`)
- pedal or nopedal mode
- OS and ROS 2 version
- the exact command you ran and its output
- the logger CSV and `.metadata.jsonl`, if relevant

## Where things live

- `hardware/`: KiCad projects and fabrication files per revision
- `firmware/shared/`: firmware used by all revisions; `firmware/test/`: host tests
- `software/ros2/src/pedal_controller/`: ROS 2 logger, commander and test tools
- `software/esu.py`, `esu.sh`: setup, build, flash and run helpers
- `docs/`: safety, roadmap, wiring and design notes
