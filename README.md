# IMERSE — ESU-TAP: ASG-300 Foot Pedal Interface (micro-ROS)

A custom PCB interposer (**ESU-TAP**) that sits between a Bovie electrosurgical
foot pedal and the **DRE ASG-300** electrosurgical generator. It has two goals:

- **Data collection** — timestamp and record when the surgeon presses/releases
  CUT, COAG, or bipolar (for imitation learning on a da Vinci surgical robot).
- **Computer activation** — inject a programmatic activation from a computer,
  without the surgeon touching the pedal.

The design goal is that the board is **electrically invisible**: a surgeon
operating the generator should not be able to tell it is inline, and if the
board loses power the pedal keeps working.

```
Foot Pedal ──►[ ESU-TAP board ]──► ASG-300 Generator
                     │
              micro-ROS (serial)
                     │
               PC (ROS 2 Humble)
```

> **Status:** v2 (monopolar + bipolar) is the current revision. See
> [CHANGELOG.md](CHANGELOG.md) for version history and [docs/ROADMAP.md](docs/ROADMAP.md)
> for known limitations and future work.

## How it works: sense-then-forward

The pedal is **not** wired straight through to the generator during normal
operation. Instead:

1. The ESP32 **reads** the pedal's dry contacts directly (active-low, external
   pull-ups — the input-only sense pins have no internal pull-ups).
2. When it sees a press — **or** a computer command — it **drives a relay** that
   closes the corresponding contact on the generator's footswitch jack.
3. It publishes the resulting state so the press can be logged with correct
   attribution (surgeon vs computer).

This is why the board can log a surgeon press *and* a computer activation on the
same channel without interference: sensing and driving are separate nets.

> **Key consequence:** the pedal-side sense nets and the generator-side drive
> nets are **separate**. A computer relay command produces no sensed edge, so the
> firmware tracks commanded state independently and drives the generator from the
> *effective* state (`sensed OR commanded`).

### Failsafe: power-loss and firmware-hang both fall back to the pedal

The board fails to **manual pedal control**, not to "off":

- **Unpowered** → the bypass relays are de-energized (their default state) and
  route the pedal straight through to the generator, commons included. A dead
  board degrades to a plain pedal.
- **Firmware healthy** → a watchdog (TPS3823A) is petted by the ESP32; its RESET
  keeps a MOSFET on that energizes the bypass-relay coils, putting the board in
  active sense-then-forward mode.
- **Firmware hung** → the watchdog stops being petted (~1.6 s), RESET drops, the
  coils de-energize, and the board falls back to pass-through.

Because "coils de-energized" is the default state under power loss, dead
silicon, or a hung MCU, **the safe state is what happens when nothing works** —
no action is required to fail safe.

Mono and bipolar commons are kept isolated: in bypass each modality returns
through its own generator common, not through shared board ground.

## ROS 2 interface

The ESP32 is a first-class ROS 2 node via micro-ROS:

| Interface | Type | Direction | Purpose |
|---|---|---|---|
| `/esu/cut` | `std_srvs/srv/SetBool` | ESP32 hosts, PC calls | activate/deactivate CUT |
| `/esu/coag` | `std_srvs/srv/SetBool` | ESP32 hosts, PC calls | activate/deactivate COAG |
| `/esu/activation_state` | `std_msgs/msg/Int32MultiArray` | ESP32 publishes, PC logs | status stream |

`source`: `0` = surgeon (pedal contacts moved), `1` = computer (relay commanded),
`2` = baseline (boot/reconnect sync — not a real event).

**Attribution is deterministic, not timing-based.** A change in the debounced
*sensed* line is ground truth for a surgeon action and takes precedence;
otherwise the computer drove it.

The PC bridges the ESP32 into the ROS 2 graph with the standard **micro-ROS
agent** — no custom bridge node.

## Repository layout

```
ESU_TAP/
  hardware/
    esu-tap-v2/                  active KiCad 9 design; project-local libraries
    esu-tap-v1/                  archived KiCad revision
  firmware/esp32/
    platformio.ini               PlatformIO micro-ROS firmware project
    src/esu_tap_microros.cpp     ESP32 firmware (flash this)
    colcon.meta                  raises micro-ROS entity limits (see below)
  software/ros2/
    src/pedal_controller/        command, logging, latency, and system-test nodes
    SETUP.md                     full build-and-run instructions
  docs/
    connector_documentation.md   confirmed connector pinout and wiring
    ROADMAP.md                   known limitations and future work
  CHANGELOG.md                   version history (v1 → v2)
```

## Quickstart (ROS 2 Humble on Ubuntu)

See `software/ros2/SETUP.md` for the complete walkthrough. In brief:

**Build the workspace once:**
```bash
source /opt/ros/humble/setup.bash
cd ~/ESU_TAP/software/ros2
colcon build
source install/setup.bash
```

**Flash the firmware** (PlatformIO — not the Arduino IDE, see Firmware notes):
```bash
cd ~/ESU_TAP/firmware/esp32
pio run -t upload
```

**Run, in separate terminals** (each sourced as above):
```bash
# 1) micro-ROS agent (bridges the ESP32 over serial)
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

- **Build system: PlatformIO** with **`micro_ros_platformio`** — not the Arduino
  IDE with `micro_ros_arduino`. The two use different transport-setup calls and
  are not interchangeable.
- **`colcon.meta` raises the micro-ROS entity limits.** The stock defaults cap
  `RMW_UXRCE_MAX_SERVICES=1`; this node hosts multiple services, so the extra
  ones fail to create without the override. After editing `colcon.meta`, rebuild
  the micro-ROS library: `pio run -t clean_microros`.
- **Auto-reconnect state machine.** The firmware pings the agent, builds entities
  when it appears, and tears them down + rebuilds if the agent restarts or drops.
  On a dropped link it forces the relays OFF (fail-safe).
- **Watchdog.** The firmware must pet the watchdog (IO4) within its ~1.6 s
  interval or the board drops to pass-through. See the Failsafe section.

## Power

- **5 V DC, center-positive**, via the barrel jack. Use a regulated supply; the
  board is **not** overvoltage-tolerant (see [ROADMAP](docs/ROADMAP.md)).
- Do **not** power from USB and the barrel jack at the same time. During
  sessions, run from the barrel jack with USB disconnected — this also breaks the
  mains-earth path through the laptop. USB is for flashing (generator
  disconnected).

## Confirmed hardware interface

The pedal connector and cable were measured directly (see
`docs/connector_documentation.md`):

- **Connectors:** AMP CPC Series 1 (TE 206430-1 female panel, 206429-1 male
  inline) confirmed on the monopolar pedal; bipolar connector to be confirmed at
  bipolar bring-up.
- **Footswitch pinout (BV-1253B, monopolar):** Pin 1 = Common, Pin 2 = CUT,
  Pin 3 = COAG, Pin 4 = tied to Pin 1. Dry contacts, no resistor ladder.
- **Bipolar** uses a separate BV-1254B footswitch on its own generator jack.

## Key components (v2)

| Ref | Part | Notes |
|---|---|---|
| U1 | ESP32-DevKitC-32E | integrated USB-serial, 3.3 V GPIO; hand-installed on headers |
| U2–U7 | Omron G6K-2F-Y-5V (LCSC C2982926) | DPDT signal relays: switching + bypass |
| Q1–Q4 | AO3400A (LCSC C20917) | logic-level relay coil drivers + watchdog coil switch |
| U9 | TPS3823A-33DBVR (LCSC C702191) | non-latching watchdog supervisor |
| D1 | SMAJ6.0A (LCSC C364284) | +5 V rail transient clamp |
| D2–D5 | 1N4148W (LCSC C81598) | relay coil flyback diodes |
| — | PESD5V0S1BA | sense-line ESD clamps |
| — | PTC + Schottky | +5 V input fault / reverse-polarity protection |
| J1–J4 | connectors | pedal and generator ports (hand-installed) |
| J5 | barrel jack | 5 V DC center-positive (hand-installed) |

Assembly: SMD parts are JLCPCB PCBA; connectors and the ESP32 module are
hand-installed.

## Notes / assumptions

- Intended for **research and data collection** with the DRE ASG-300. Not
  validated for clinical use (see [ROADMAP](docs/ROADMAP.md)).
- The ASG-300 arbitrates simultaneous activations **first-come-first-served**, so
  a logged command is not proof of a generator activation. The logging pipeline
  distinguishes command from activation events. See the data-integrity note in
  the ROADMAP.
- **Modality roadmap:** v1 monopolar → v2 monopolar + bipolar → v3 vessel
  sealing.

## License

See [LICENSE](LICENSE).
