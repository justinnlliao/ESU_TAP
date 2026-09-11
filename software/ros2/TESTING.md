# Testing the ESU-TAP ROS 2 stack (before the board arrives)

This document explains how to test the PC-side ROS 2 stack **without the
physical ESP32 board**, using a software stand-in (`mock_esu_node`).

The mock uses the legacy two-channel contract. It is not an exact model of
current firmware, which publishes `[cut, coag, bipolar, source]`. The real logger
still expects three fields. See [current limitations](../../docs/SAFETY_AND_VALIDATION.md).
No passing result here establishes electrical safety, offline operation, or
watchdog recovery. LigaSure software and fault-response tests remain incomplete.

## What this tests

The mock implements the legacy two-channel interface:

- Hosts two legacy services: `/esu/cut`, `/esu/coag`
  (`std_srvs/SetBool`)
- Publishes `/esu/activation_state` (`std_msgs/Int32MultiArray`, `[cut, coag, source]`)
- Fakes a surgeon press every few seconds so source attribution is visible

Running the **real** `pedal_commander` and **real** `pedal_logger` against the
mock exercises that legacy interface contract. What it does NOT
test is the hardware layer (relays, pedal sensing, generator, micro-ROS over
real serial) — those need the board.

## Prerequisites

- ROS 2 Humble (Ubuntu 22.04). See `SETUP.md`.
- Workspace built:

      source /opt/ros/humble/setup.bash
      cd ~/ESU_TAP/software/ros2
      colcon build
      source install/setup.bash

## Run the three-terminal test

Source ROS 2 and the workspace in **each** terminal first:

    source /opt/ros/humble/setup.bash
    source ~/ESU_TAP/software/ros2/install/setup.bash

**Terminal 1 — mock ESP32:**

    ros2 run pedal_controller mock_esu_node

**Terminal 2 — real logger** (writes CSV to `~/pedal_logs/`):

    ros2 run pedal_controller pedal_logger

**Terminal 3 — real commander** (interactive: c=CUT, g=COAG, x=all off):

    ros2 run pedal_controller pedal_commander

## What a passing test looks like

- Every ~5 s the logger prints a `[surgeon]` row (from the mock's simulated press)
- When you toggle a channel in the commander, the logger prints a `[computer]` row
- The commander prints the service acknowledgement (`CUT ON -> ok (cut on)`)
- A CSV file appears in `~/pedal_logs/` with correct `source` values

> NOTE: the mock publishes directly from its service callbacks; the real
> firmware publishes from its timer. That difference once concealed a real
> firmware bug (computer activations were never published). A green run here
> validates the ROS 2 stack — the topic/service contract, commander, logger —
> NOT the firmware's publish path. Always confirm on hardware too.

## Quick checks without the commander

    # call the service directly
    ros2 service call /esu/cut std_srvs/srv/SetBool "{data: true}"

    # watch the status stream
    ros2 topic echo /esu/activation_state

    # confirm the interfaces exist
    ros2 service list | grep esu
    ros2 topic list | grep esu

## Mock parameters

    # turn off the simulated surgeon presses
    ros2 run pedal_controller mock_esu_node --ros-args -p sim_surgeon:=false

    # change how often a fake surgeon press happens (seconds)
    ros2 run pedal_controller mock_esu_node --ros-args -p sim_period_s:=2.0

## When the board arrives

Do not directly substitute current firmware and assume the old tests apply.
First fix the schema mismatch and extend the tools for the target hardware.
Keep the generator disconnected and use a low-voltage dummy contact fixture:

1. Flash `firmware/esp32/src/esu_tap_microros.cpp` to the ESP32 with
   PlatformIO (see `SETUP.md` §5).
2. Start the micro-ROS agent instead of the mock node:

       docker run -it --rm -v /dev:/dev --privileged --net=host \
         microros/micro-ros-agent:humble serial --dev /dev/ttyUSB0 -b 115200

3. Run revision-compatible logger, commander, and tests only after they have
   been updated. Compare inferred messages against independently measured
   contact closures, not just relay clicks or service acknowledgements.

## Physical fault testing still required

The detailed pending procedure is in
[Protection features and validation status](../../docs/SAFETY_AND_VALIDATION.md).
Record results for total and individual supply losses, agent/transport loss,
commanding-process death with the agent alive, sense faults, and controller
stalls with every activation ON and OFF. Observe several watchdog cycles and
measure actual contact release and manual-path continuity.

Define acceptable timing and recovery/re-arm criteria before testing. Do not
mark a test passed just because a watchdog pulse or temporary bypass occurred.
No physical fault-test results or numerical reliability rating are established
by this document.
