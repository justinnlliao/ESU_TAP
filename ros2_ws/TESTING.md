# Testing the ESU-TAP ROS 2 stack (before the board arrives)

This document explains how to test the PC-side ROS 2 stack **without the
physical ESP32 board**, using a software stand-in (`mock_esu_node`).

## What this tests

The mock node impersonates the ESP32 firmware exactly:

- Hosts the two services the real firmware hosts: `/esu/cut`, `/esu/coag`
  (`std_srvs/SetBool`)
- Publishes `/esu/activation_state` (`std_msgs/Int32MultiArray`, `[cut, coag, source]`)
- Fakes a surgeon press every few seconds so source attribution is visible

Running the **real** `pedal_commander` and **real** `pedal_logger` against the
mock exercises the entire ROS 2 interface contract end-to-end. What it does NOT
test is the hardware layer (relay, optocoupler, generator, micro-ROS over real
serial) — those need the board.

## Prerequisites

- ROS 2 Humble (Ubuntu 22.04). See `SETUP.md`.
- Workspace built:

      cd ros2_ws
      colcon build --packages-select pedal_controller
      source install/local_setup.bash

## Run the three-terminal test

Source ROS 2 and the workspace in **each** terminal first:

    source /opt/ros/humble/setup.bash
    source install/local_setup.bash

**Terminal 1 — mock ESP32:**

    ros2 run pedal_controller mock_esu_node

**Terminal 2 — real logger** (writes CSV to `~/pedal_logs/`):

    ros2 run pedal_controller pedal_logger

**Terminal 3 — real commander** (ENTER toggles the channel on/off):

    ros2 run pedal_controller pedal_commander --ros-args -p channel:=cut

## What a passing test looks like

- Every ~5 s the logger prints a `[surgeon]` row (from the mock's simulated press)
- When you press ENTER in the commander, the logger prints a `[computer]` row
- The commander prints the service acknowledgement (`CUT ON -> ok (cut on)`)
- A CSV file appears in `~/pedal_logs/` with correct `source` values

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

Replace the mock with the real thing:

1. Flash `microros_firmware/esu_tap_microros.ino` to the ESP32.
2. Start the micro-ROS agent instead of the mock node:

       ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/ttyUSB0 -b 115200

3. Run the **same** `pedal_logger` and `pedal_commander` unchanged. If they
   worked against the mock, the only new variables are hardware.
