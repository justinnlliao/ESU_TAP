# Contributing to ESU-TAP

Thanks for helping. ESU-TAP switches an electrosurgical generator's footswitch
contacts, so a few rules come before everything else.

## Safety rules

- Test on a **generator-disconnected fixture**. Never test changes on a live
  generator or anything connected to a patient.
- Do not describe a change as making the device "safe" or "fail-safe". State what
  was tested and how, in the terms of [docs/SAFETY.md](docs/SAFETY.md).
- Changes to relay, pedal, arming or command-expiry logic must say how they were
  physically verified (fixture, scope/DAQ, board revision), or state clearly that
  they were not.

## Running the tests

CI runs these on every push; none needs ROS or hardware:

```bash
python3 -B -m unittest discover -s software/ros2/src/pedal_controller/test   # Python
shellcheck esu.sh software/ros2/src/pedal_controller/esu_run.sh              # shell scripts
python3 software/esu.py setup && python3 software/esu.py build --board v3    # firmware build, no flash
```

plus the firmware logic tests for every revision. The full commands, the mock
board and the hardware test procedures are in
[docs/contributors/TESTING.md](docs/contributors/TESTING.md).

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
