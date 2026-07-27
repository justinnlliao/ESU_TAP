# IMERSE — ESU-TAP: ASG-300 Foot Pedal Interface (micro-ROS)

A custom PCB interposer (**ESU-TAP**) that sits between the **Bovie BV-1253B
foot pedal** and the **DRE ASG-300 electrosurgical generator**. It has two
goals:

- **Data collection** — timestamp and record when the surgeon presses/releases
  CUT or COAG (for imitation learning on a da Vinci surgical robot).
- **Computer activation** — inject a programmatic CUT/COAG activation from a
  computer, without the surgeon touching the pedal.

```
Foot Pedal ──[CPC]──► [ESU-TAP board] ──[CPC]──► ASG-300 Generator
                            │
                     USB serial (micro-ROS)
                            │
                      PC (ROS 2 Humble)
```

## How it works: sense-then-forward

The pedal is **not** wired straight through to the generator. Instead:

1. The ESP32 **reads** the pedal's dry contacts directly on IO34/IO35
   (active-low, external pull-ups R5/R6 — IO34/35 have no internal pull-ups).
2. When it sees a press — **or** a computer command — it **drives a relay**
   that closes the corresponding contact on the generator's footswitch jack.
3. It publishes the resulting state so the press can be logged with correct
   attribution (surgeon vs computer).

This is why the board can log a surgeon press *and* a robot activation on the
same channel without them interfering: sensing and driving are separate nets.

> **Key consequence:** `CUT_SENSE`/`COAG_SENSE` (pedal side) and
> `GEN_CUT`/`GEN_COAG` (generator side) are **separate nets**. A computer relay
> command produces no sensed edge, so the firmware tracks commanded state
> independently and drives the generator from the *effective* state
> (`sensed OR commanded`). A surgeon press is forwarded to the generator by the
> firmware — if the firmware doesn't run, the pedal does not reach the generator
> through this path (see Failsafe below).

### Failsafe (and a known v1 limitation)

A power-tied bypass relay (U4/K3) is meant to pass the pedal straight through to
the generator when the board is **unpowered**, so a dead ESP32 degrades to a
plain pedal rather than no pedal.

> ⚠️ **CONFIRMED v1 BUG:** bench testing shows the unpowered pass-through does
> **not** complete — `COMMON` is a separate net and is not routed through when
> the board is unpowered, so an unpowered board leaves the pedal inert. This is
> a genuine safety gap (dead board = surgeon loses the pedal) and is fixed in v2
> by adding a third bypass pole to route the commons. See
> `docs/ESU_TAP_v2_change_list.md` §0.1 / §1.1.

## ROS 2 interface

The ESP32 is a first-class ROS 2 node (`esu_tap_node`) via micro-ROS:

| Interface | Type | Direction | Purpose |
|---|---|---|---|
| `/esu/cut` | `std_srvs/srv/SetBool` | ESP32 hosts, PC calls | activate/deactivate CUT (`data=true`/`false`) |
| `/esu/coag` | `std_srvs/srv/SetBool` | ESP32 hosts, PC calls | activate/deactivate COAG |
| `/esu/activation_state` | `std_msgs/msg/Int32MultiArray` | ESP32 publishes, PC logs | status stream `[cut, coag, source]` |

`source`: `0` = surgeon (pedal contacts moved), `1` = computer (relay commanded
via service), `2` = baseline (boot/reconnect sync message — not a real event).

**Attribution is deterministic, not timing-based.** A change in the debounced
*sensed* line is ground truth for a surgeon action and takes precedence;
otherwise the computer drove it. One message is published per changed channel,
so each edge carries its own source.

The PC bridges the ESP32 into the ROS 2 graph with the **micro-ROS agent**
(a standard tool run as one command — no custom bridge node).

## Repository layout

```
ESU_TAP/
  microros_firmware/
    platformio.ini              PlatformIO project (micro_ros_platformio)
    src/esu_tap_microros.cpp     ESP32 firmware (flash this)
    colcon.meta                  raises micro-ROS entity limits (see below)
  ros2_ws/src/pedal_controller/  ROS 2 (ament_python) package
    pedal_controller/
      pedal_commander.py         service CLIENT — command cut/coag (interactive/pulse/script)
      pedal_logger.py            subscribes /esu/activation_state, logs edges to CSV
      system_test.py             interactive full-system acceptance test
      latency_test.py            automated round-trip + command latency benchmark
      mock_esu_node.py           software stand-in for the ESP32 (pre-hardware testing)
  esu_tap_pcb/esu_tap_v1/        KiCad schematic + PCB layout
  docs/
    ESU_TAP_v2_change_list.md    next-revision hardware/firmware changes
    connector_documentation.md   confirmed connector pinout and wiring
  ros2_ws/SETUP.md               full build-and-run instructions
```

## Quickstart (ROS 2 Humble on Ubuntu)

See `ros2_ws/SETUP.md` for the complete walkthrough. In brief:

**Build the workspace once:**
```bash
source /opt/ros/humble/setup.bash
cd ~/ESU_TAP/ros2_ws
colcon build
source install/setup.bash
```

**Flash the firmware** (PlatformIO — NOT the Arduino IDE, see Firmware notes):
```bash
cd ~/ESU_TAP/microros_firmware
pio run -t upload
```

**Run, in separate terminals** (each sourced as above):
```bash
# 1) micro-ROS agent (bridges the ESP32 over USB serial)
docker run -it --rm -v /dev:/dev --privileged --net=host \
  microros/micro-ros-agent:humble serial --dev /dev/ttyUSB0 -b 115200

# 2) logger  (writes CSV to ~/pedal_logs/)
ros2 run pedal_controller pedal_logger

# 3) commander (interactive: c=CUT, g=COAG, x=all off, h=help)
ros2 run pedal_controller pedal_commander
```

The board **auto-connects and auto-reconnects** — no need to press EN after
starting or restarting the agent. Drive the services directly if you prefer:
```bash
ros2 service call /esu/cut std_srvs/srv/SetBool "{data: true}"
ros2 topic echo /esu/activation_state
```

## Firmware notes

- **Build system: PlatformIO** with the **`micro_ros_platformio`** library —
  **not** the Arduino IDE with `micro_ros_arduino`. The two use different
  transport-setup calls (`set_microros_serial_transports(Serial)` vs
  `set_microros_transports()`) and are not interchangeable.
- **`colcon.meta` raises the micro-ROS entity limits.** The stock defaults cap
  `RMW_UXRCE_MAX_SERVICES=1`; this node hosts two services, so the second one
  (`/esu/coag`) fails to create without the override. After editing
  `colcon.meta`, rebuild the micro-ROS library: `pio run -t clean_microros`.
- **Auto-reconnect state machine.** The firmware pings the agent, builds
  entities when it appears, and tears them down + rebuilds if the agent
  restarts or drops. On a dropped link it forces the relays OFF (fail-safe).
- **LED status:** white D3 = power (hardwired 3V3), red D4 = CUT active (IO18),
  yellow D5 = COAG active (IO21). Slow yellow blink = waiting for the agent;
  fast blink on both = fatal init error (details printed over serial).

## Confirmed hardware interface

The pedal connector and cable were measured directly (see
`docs/connector_documentation.md`):

- **Panel/inline connectors:** AMP CPC Series 1 (TE Connectivity 206430-1 female
  panel socket, 206429-1 male inline plug).
- **Footswitch pinout (BV-1253B):** Pin 1 = Common, Pin 2 = CUT, Pin 3 = COAG,
  Pin 4 = tied to Pin 1. Simple dry contacts, no resistor ladder.
- **Board ports:** one CPC connector to the pedal, one to the generator. The two
  are **not** a parallel pass-through — the pedal side is read by the MCU and
  the generator side is driven by the relays (sense-then-forward).

## Key components (v1)

| Ref | Part | Notes |
|---|---|---|
| U1 | ESP32-DevKitC-32E | integrated USB-serial, 3.3 V GPIO |
| K1/K2 | Omron G6K-2F-Y (LCSC C2982926) | non-latching SMD DPDT, active-HIGH drive |
| Q1/Q2 | MMBT3904 (LCSC C20526) | low-side relay coil driver |
| — | 1N4148 | flyback diodes across coils |
| R5/R6 | 10 kΩ | external pull-ups for IO34/IO35 sense |
| U4/K3 | bypass relay | power-tied pass-through (see Failsafe) |

## Notes / assumptions

- Intended for **research and data collection** with the DRE ASG-300. Any use
  in a live clinical environment requires signal characterization, isolation
  validation, and a safety/regulatory review.
- The ASG-300 arbitrates simultaneous CUT+COAG by **first-come-first-served**
  (whichever channel activated first wins). If both contacts close at once, the
  generator fires only the first — so raw contact state can differ from what the
  generator actually did. This is a data-integrity consideration for imitation
  learning and is tracked for the logging pipeline.
- **Modality roadmap:** v1 monopolar → v2 monopolar + bipolar (requires a
  separate BV-1254B footswitch) → v3 vessel sealing.
