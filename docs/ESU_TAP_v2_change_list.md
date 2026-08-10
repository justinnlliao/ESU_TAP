# ESU-TAP v2 — Change List

**Status:** draft for review
**Basis:** v1 netlist (`esu_tap_v1.net`, Eeschema 9.0.4, 2026-07-16), Omron G6K datasheet K106-E1-11, ASG-300 published specs, Zettler AZ733 + 2N7002 datasheets.

**Confidence key**
- ✅ Verified against a datasheet or the v1 netlist
- ⚠️ Reasoned, not measured — needs bench confirmation
- ❓ Open decision

---

## 0. Blockers — do these before opening KiCad

v1's architecture was rebuilt mid-project because the schematic got ahead of the measurements. The bipolar path is a fresh unknown. Don't repeat it.

| # | Task | Why it blocks |
|---|---|---|
| 0.1 | ~~Bench-test the v1 bypass~~ ✅ **DONE — CONFIRMED BROKEN on the bench.** Unpowered board leaves the pedal inert; generator does not fire. §1.1 third-pole fix is locked in. | — |
| 0.2 | ~~Buy a BV-1254B bipolar footswitch~~ ✅ **DONE — in hand** | — |
| 0.3 | ~~Characterize the BV-1254B~~ ✅ **DONE** — 2 static ID lines + 1 signal contact (see §2.2) | — |
| 0.4 | **Inspect the generator's bipolar jack** — connector type, is it CPC? | v1 taught you not to assume the connector |
| 0.5 | ~~Measure the bipolar jack's idle impedance~~ ⚠️ **ASSUMED = monopolar (~24 Ω).** Not measured — flagged as an assumption, not a fact. Verify at first bipolar bring-up. | — |
| 0.6 | ~~Mono and bipolar commons the same node?~~ ✅ **RESOLVED** — bipolar common is dedicated/independent. Pole count stays 5 (§3.1). | — |
| 0.7 | ~~Scope the mono footswitch line~~ ⚠️ **NOT scoped — deferred by choice.** Board runs clean at low process load with no observed issues. Protection parts are precautionary (bad plug-in / fault), so they stay **DNP-with-footprint** per §4. Populate only if a fault ever shows up. | — |

---

## 1. v1 bugs to fix

### 1.1 Bypass failsafe has no return path — CRITICAL ⚠️

**Finding.** `/COMMON` and `GND` are separate nets (✅ confirmed in netlist). With the board unpowered:

```
pedal shorts J1-2 → J1-1 (= GND)
J1-2 = /CUT_SENSE → U4 pole A (NC) → /GEN_CUT = J4-2
generator sees J4-2 pulled to GND
generator needs J4-2 shorted to J4-1 (/COMMON)
GND is not connected to /COMMON anywhere
→ /COMMON floats. No return path. Generator does not fire.
```

**Severity:** not a hazard — fails open, nothing activates spuriously. It is a **functional failure**: board dead = surgeon's pedal dead, which is the exact thing the bypass exists to prevent.

**Root cause:** the isolation and the bypass were never traced against each other. Separate commons is *why* there's no return. You can have a real barrier or a 2-pole bypass, not both.

**v1 stopgap:** one wire, GND → `/COMMON`. Bypass works immediately, isolation gone entirely. Acceptable only as a *documented* benchtop compromise.

**v2 fix:** bypass needs a **third pole** to switch GND ↔ `/COMMON`. See §3.

⚠️ Rests on the G6K pinout (coil 1/8, pole A COM=3 NC=2 NO=4, pole B COM=6 NC=7 NO=5). ✅ **Bench-confirmed broken** (0.1) — unpowered board leaves the pedal inert. No longer a prediction.

### 1.2 Connectors still screw terminals ✅

J1/J4 are `TerminalBlock*` in the netlist. Never updated. Replace with TE CPC Series 1 — 206430-1 female panel sockets, 206429-1 male inline plugs, 66105-4 / 66103-4 contacts, 1-206062-4 backshells.

### 1.3 Firmware GPIO map — RESOLVED ✅

Superseded. `microros_firmware/esu_tap_microros.ino` already carries the final map
(IO26/27 relay drive, IO34/35 sense, IO18/21 LEDs, `pinMode INPUT` only on 34/35).
The stale `pedal_firmware.ino` reference was to the retired plain-serial firmware.
Remaining firmware work is §9.

### 1.4 Computer-commanded activations were never published — CRITICAL ✅ FIXED

**Finding.** `CUT_SENSE` / `COAG_SENSE` and `GEN_CUT` / `GEN_COAG` are separate nets
(✅ confirmed in `esu_tap_v1.kicad_sch`). The ESP32 senses the *pedal* dry contacts;
the relays close the *generator* contacts. These do not interact.

`publish_state()` was reachable only from `timer_callback`, gated on a change in the
sensed lines. A relay command does not move the pedal contacts → no sensed edge →
no publish. Consequences:

- `/esu/activation_state` reported **surgeon presses only**; robot activations were invisible
- the `source = 1` branch was unreachable dead code
- every row `pedal_logger` wrote said `surgeon`

For imitation learning this is worse than missing data — it is a systematically
**wrong** label set, the same failure class as §2.3.

**Why testing missed it.** `mock_esu_node.py` publishes directly from its service
callbacks; the firmware did not. The mock validated the ROS 2 stack, not the firmware
publish path, while its docstring claimed it mimicked the firmware exactly.

**Fix (applied to v1 firmware).** Effective state = `sensed OR commanded`. Commanded
state is tracked in `volatile int cmdCut / cmdCoag`, set by the service callbacks and
snapshotted once per timer tick. `timer_callback` remains the single publish path.

**Attribution is now deterministic, not timing-based.** A change in the debounced
*sensed* line is ground truth for a surgeon action and takes precedence; otherwise the
computer drove it. The 750 ms `CMD_WINDOW_MS` heuristic was removed — it was only ever
needed because command and sense were being inferred from one signal.

**One message is now published per changed channel**, so each edge carries its own
source. A single combined message forced one `source` value onto two independent events.

### 1.5 Logger swallowed the first activation ✅ FIXED

`pedal_logger` consumes its first message purely to initialise its edge detector. The
firmware published nothing at boot, so the first *real* activation of every session was
absorbed as the baseline and never written to CSV. The mock node had an initial publish;
the firmware did not. Firmware now publishes a `(0, 0, surgeon)` baseline at the end of
`setup()`.

⚠️ Both fixes are code-reviewed, not bench-confirmed. Verify against hardware before
trusting any collected dataset.

---

## 2. New capability — bipolar

### 2.1 The BV-1253B cannot do bipolar on this generator ✅

The BV-1253B behaves differently per generator. On the Specialist PRO it's mono+bipolar (yellow = mono, blue = bipolar). On the **Surgi-Center PRO / OR PRO 300 it cannot perform bipolar functions** — it acts as dual-monopolar, yellow = cut, blue = coag. The ASG-300 is the OR PRO 300 / IDS-300 lineage.

**Bipolar requires the BV-1254B** — a separate single-pedal bipolar footswitch, listed for the IDS-200/210/300/310/400 and A2250/A3250/A2350/A3350.

**Consequence: v2 is not "add a channel." It's "add a second, independent pedal-and-jack path."**

### 2.2 Additions

**BV-1254B in hand and characterized ✅** — the bipolar pedal presents **2 static identity
lines + 1 signal contact** (simpler than a mono channel, which has 2 switched signals).
The ID lines are *not switched* — they wire straight through to the generator so it always
sees a bipolar pedal is present. Only the single signal contact is sensed/forwarded.

| Item | Detail |
|---|---|
| Connectors | **2 more CPC** — bipolar pedal socket (J5) + bipolar generator plug (J6). Total 4 + power. |
| Switching relay | K_BIP — third G6K (U5). **Only 1 pole used** (single signal), vs 2 for a mono channel. |
| ID lines | **2× static straight-through** pedal→generator. Not relayed, not sensed. ⚠️ must stay connected regardless of board power — route on the always-connected side so an unpowered/hung board doesn't make the generator think the pedal vanished. |
| Driver | AO3400A + 1 kΩ gate series + 10 kΩ gate pulldown + 1N4148W flyback |
| Sense | IO36 (VP), external 10 kΩ pull-up, active-low |
| LED | Blue on IO22 (matches pedal colour convention) |
| Bypass poles | +2 (bipolar signal + bipolar COM) — see §3. Common is dedicated, not shared (✅ confirmed with pedal in hand). |

### 2.3 FCFS corrupts the dataset — highest-value fix in v2 ✅

The ASG-300's FCFS design allows only one output active at a time; while the monopolar foot-controlled output is active, handswitching **and bipolar footswitch capability are both inactive**, and secondary commands will not override the first.

**So: a command is not an activation.** Command bipolar while the surgeon holds CUT → generator silently ignores it → logger records a bipolar event that never happened. For imitation learning that's not a missing label, it's a **wrong** one.

Latent with two mono channels. Live with three and real arbitration.

**Mitigations, in order:**
1. **Firmware enforces FCFS itself** — never command a channel while another is sensed or commanded active. You already read all pedal states; predict the arbitration and refuse rather than fire blind.
2. **Logger emits commands and activations as distinct event types**, plus a `suppressed` reason code. Never let the schema imply an activation it can't confirm.
3. Accept that generator-side state is unobservable — that's what RS-232 telemetry would give, and it's blocked on generator firmware (per Jiawei).

---

## 3. Bypass architecture

### 3.1 Pole count

| Path | Poles |
|---|---|
| Mono CUT | 1 |
| Mono COAG | 1 |
| **Mono COMMON** | **1** ← missing in v1 |
| Bipolar BIP | 1 |
| **Bipolar COMMON** | **1** |
| **Total** | **5** → 3× DPDT, one spare |

❓ If §0.6 shows the generator's mono and bipolar commons are the same node, this drops to 4 poles / 2 relays.

**This is what sizes the board — not relay dielectric.**

### 3.2 Watchdog-held failsafe (promote from deferred)

v1: bypass coil power-tied (U4 pin 1 = +5V, pin 8 = GND ✅). Covers unpowered. **Does not cover powered-but-hung.**

v2: drive the bypass coil from a watchdog IC output that the ESP32 pets.

| State | Bypass coil | Result |
|---|---|---|
| Unpowered | de-energized | pedal → generator direct ✅ |
| Powered, firmware healthy | energized | sense-then-forward |
| **Powered, firmware hung** | **de-energized** | **pedal → generator direct ✅** |

**Part LOCKED: TPS3823A-33DBVR** ✅ (SOT-23-5, 3.3 V supervise, push-pull, ~1.6 s timeout).
Use the **A suffix** — the non-A latches RESET low if WDI keeps toggling during a reset
event, which is exactly wrong for a failsafe; the A version recovers cleanly. LCSC family
is C7719 (plain); confirm A-suffix stock when pulling from SnapMagic.

**Polarity (RESET is active-low, push-pull):** drive the bypass-coil MOSFET gate
*directly* from RESET.
- healthy → petting IO4 → RESET HIGH → coil-FET on → coils energized → active mode
- hung → no pet → RESET LOW → coil-FET off → coils drop → **bypass** ✅
- power off → all low → coils drop → **bypass** ✅
All three land correct with a direct RESET→gate connection. If you need an inverter, the
polarity is flipped somewhere — stop and recheck.

⚠️ **Two datasheet gotchas:**
- A floating WDI makes the chip self-pulse and silently *disable* the watchdog. The IO4
  pet trace must be solidly connected; add a 1 kΩ WDI→GND so a broken pet line is
  detectable rather than fail-disabled.
- **The bypass coils now switch**, so U4/U6/U7 each need a **flyback diode** across the
  coil (cathode → +5V), same as the switching relays. 3× SOD-123. In v1/early-v2 they
  were power-tied and didn't need one; they do now.

**Note:** bypass relays must stay electromechanical. Only a mechanical NC contact passes through when unpowered — no SSR can do this.

---

## 4. Protection

The realistic threat is **coupled RF at 490 kHz, ESD, and faults** — not kilovolt dielectric breakdown. The generator's output is already isolated internally: it's **Defibrillator-proof Type CF with isolated output circuitry** ✅, and the footswitch jack sits on the far side of that certified barrier.

**Populate strategy — reserve space, defer the spend (⚠️ these are speculative until §0.7).**
Every protection part below is defending against a threat that has **not been measured** — the
footswitch line has not been scoped (blocker 0.7). Rather than build a fortress against ghosts
or risk a re-spin, **place all protection footprints on the board but mark the speculative ones
DNP (do-not-populate)** in the BOM. After 0.7:
- line clean → leave DNP, or fit 0 Ω jumpers where a series element sits
- line noisy → populate the exact clamp/bead the measurement calls for

Pads cost nothing; the reserved space is what saves the re-spin. The enable switch is **not**
speculative — it is populated (it addresses stuck-on, a real failure mode).

| Item | Populate | Detail |
|---|---|---|
| **TVS — power rails** | **POPULATE** | 3V3 rail + 5 V barrel. Rails are known voltages; protection is cheap insurance. |
| **TVS — signal lines** | **DNP until 0.7** | senses + GEN lines. Working voltage on GEN side is unknown until scoped. |
| **Series resistors** | footprint + 0 Ω | ~1 kΩ on IO34 / IO35 / IO36. Fit 0 Ω until a reason to add R appears. |
| **RF filtering** | **DNP until 0.7** | ferrite + shunt cap at each connector, targeting 490 kHz. Bead value needs the measurement. |
| **Hardware enable switch** | **POPULATE** | in series with generator-side common. Breaks all channels. Not speculative. |
| Enable switch sense | POPULATE | IO32 (internal pull-up, unlike 34–39) so firmware can log state |

The one non-negotiable: **do §0.7 before finalizing.** Every "is this overkill?" question
collapses the moment there's a scope trace. Until then, DNP is the honest default.

### 4.1 Rejected: AZ733 + 2N7002

Both fail a datasheet check. Recorded so this isn't relitigated.

**2N7002 + AZ733 is broken:**
- AZ733 5 V coil: **47 Ω, ~106 mA** (530 mW) ✅ — that's 92% of the 2N7002's **115 mA** continuous rating ✅
- 2N7002 Vgs(th) max **2.5 V** ✅; Rds(on) specified only at Vgs = 10 V (2.0 Ω) and 5 V (3.0 Ω) ✅. **Nothing at 3.3 V.**
- Worst-case at Vgs = 3.3 V, Rds ≈ 15–30 Ω ⚠️ → coil sees 3.05–3.79 V vs. ~75% pickup → **may not actuate**

**AZ733 independently wrong for this job:**
- It's a **12 A power relay** switching a few-mA dry contact → minimum-load failure. Standard silver contacts develop film at signal levels. (Gold-plated versions exist — mandatory if ever used.)
- **530 mW coil** vs G6K's 100 mW, typ **34 K** temperature rise ✅ → makes the continuous-duty concern *worse*, not better
- Through-hole, breaks the all-SMD JLCPCB PCBA flow, and 3× won't fit

**Why the isolation premise doesn't hold:**
- The buck converter is the *power-regulating* stage (tens–hundreds of volts); the kV comes from the step-up transformer on the RF output. A buck is step-down; it structurally can't make 4 kV.
- For 4 kV to reach the footswitch jack, the generator's certified defib-rated barrier must fail. At that point the device is catastrophically broken and the ESP32 is not the concern.
- **Dielectric ≠ RF immunity.** 5000 Vrms is a 50/60 Hz 1-minute test. At 490 kHz the barrier is a *capacitor*: ~2 pF ≈ 162 kΩ reactance. Rating doesn't describe this path; physical spacing does.
- **A 5 kV relay on a board with ~0.2 mm clearances is a half-measure.** ⚠️ That gap flashes over around 1–2 kV (Paschen estimate). The relay would be the strongest link in a chain of weak ones — connectors, pour, bypass relay all fail first. Real 4 kV design = mm of creepage, milled slots, rated connectors, isolated supply. Different board, not a part swap.
- **The hazard points the wrong way.** A dead ESP32 is $8. The hazards are uncommanded activation and failure to deactivate. 4 kV through a contact **welds it shut** — hazard #2 — which coil-side isolation does nothing about. §3.2 and the enable switch do.

**Borrow the FMEA from Medtronic, not the relay.**

---

## 5. Power

| Item | Detail |
|---|---|
| **5 V barrel jack** | ✅ Necessary: `+5V` is currently fed *only* by U1 pin J2_19 (EXT_5V) = DevKitC 5 V pin = USB VBUS |
| **ORing schottky** | ✅ The barrel jack lands on the same net as VBUS → contention. Schottky, or a hard documented "never both" rule |
| **Adapter** | Double-insulated or medical-grade. A cheap wall wart's Y-caps to mains earth partly reinstate the path you're breaking |
| **USB out during sessions** | micro-ROS over WiFi is already the data path. Flash over USB with the generator disconnected |
| Current budget | Recompute: 3 switching + up to 3 bypass G6K coils @ 21.1 mA ✅ + ESP32 WiFi peaks |

**Why the barrel jack is the real answer to "it'll fry the laptop":** barrel jack in, USB out, WiFi = an **air gap**. No copper to the laptop at all. You can't beat an air gap with a component. The ESP32 isn't the propagation path — the shared USB copper is; a dead chip doesn't push energy anywhere.

❓ If USB serial is genuinely needed during sessions, the correct part is a **USB isolator** (ADuM4160-class, ~$25) — 5 kV on the path actually at risk. Not the relay, which isn't on that path.

---

## 6. Drivers — MMBT3904 → AO3400A

**This is a symbol swap and nothing else.** ✅

- Q1/Q2 are MMBT3904 SOT-23: pin 1 = B, 2 = E, 3 = C ✅
- AO3400A is SOT-23: pin 1 = G, 2 = S, 3 = D → **same pin order**. B→G, E→S, C→D. Footprint and every connection unchanged.
- **R2/R4 already exist as base pulldowns to GND** ✅ → they become gate pulldowns for free. The mandatory boot-state protection is already on your board.
- R1/R3 (1 kΩ, C11702) ✅ become gate series resistors. 1 kΩ is fine; no change needed.
- D1/D2 (1N4148W, C81598) ✅ flybacks unchanged.
- **AO3400A = LCSC C20917**, JLCPCB Basic part, Vgs(th) ≤ 1.0 V, ~28 mΩ @ 4.5 V.

**Honest note:** the electrical gain is small — ~2.6 mA of base current per channel and no β dependence. Do it because it's free, not because it protects anything. **A MOSFET is not an isolation device** (Crss ≈ 5 pF couples drain to gate to your GPIO), and the transistor sits on the *coil* side of the barrier, which has no connection to the generator at all.

---

## 7. Relays

**Default: keep the G6K-2F-Y-5V (C2982926).** ✅ 1500 VAC coil-to-contact, signal-grade bifurcated Au-alloy contacts rated to 10 µA @ 10 mV, 100 mW coil, SMD, existing footprint.

**Continuous-duty concern: resolved.** ✅ Omron's warning is real but narrow — *"ON continuously for long periods (without switching)"* causes coil heat → film on contacts → **contact resistance drift**, not burnout. "Long periods" = weeks-to-months (telecom holding circuits). Hours is nowhere near it. K1/K2/K_BIP cycle constantly and are exempt entirely; only the bypass coils are continuous-duty, and a couple of hours per session is fine. Thermal: ~105 mW in a 0.7 g package, equilibrates in minutes.

❓ **Alternative: MOSFET-output photorelays** (Toshiba TLP3475-class) for the switching channels — if a 2 kV number is needed on paper. 3.75–5 kVrms, optical barrier, no wear, no coil, no heat, no minimum-load problem, SMD, and the transistor question disappears (input LED runs off a GPIO through a resistor). Trade-offs: SPST-NO only, ~µA off-leakage — **needs one bench check against the generator's detection threshold.**

**Not the AZ733.** See §4.1.

---

## 8. GPIO map

| Function | GPIO | v1 | v2 | Notes |
|---|---|---|---|---|
| CUT sense | IO34 | ✅ | keep | input-only, ext 10 kΩ (R5), active-low. **Never `INPUT_PULLUP`** |
| COAG sense | IO35 | ✅ | keep | input-only, ext 10 kΩ (R6), active-low |
| **BIPOLAR sense** | **IO36 (VP)** | free ✅ | **new** | input-only, ext 10 kΩ, same rule |
| CUT relay | IO26 | ✅ | keep | active-HIGH → AO3400A |
| COAG relay | IO27 | ✅ | keep | active-HIGH → AO3400A |
| **BIPOLAR relay** | **IO25** | free ✅ | **new** | active-HIGH → AO3400A |
| CUT LED (red) | IO18 → **IO13** | ✅ | **move** | frees VSPI — see §8.1 |
| COAG LED (yellow) | IO21 | ✅ | keep | |
| **BIPOLAR LED (blue)** | **IO22** | free ✅ | **new** | |
| **Enable switch sense** | **IO32** | free ✅ | **new** | internal pull-up available |
| **Watchdog pet** | **IO4** | free ✅ | **new** | |
| Power LED (white) | — | ✅ | keep | hardwired 3V3 via R9 |

Avoid IO0/2/5/12/15 (strapping), IO1/3 (UART0).

### 8.1 SD card decision — RESOLVED: keep the capability ✅

IO18 is the CUT LED (R8). VSPI wants IO18/19/23/5 — IO19/23/5 are free, IO18 is not.
**Decision: reserve SD.** Move the CUT LED off IO18 (→ IO13) so the full VSPI bus stays
available. Not adding the SD socket now, but the pins are kept clear so it's a drop-in
later with no re-layout. ⚠️ In the current v2 netlist the CUT LED is still on IO18 —
**this move is outstanding.**

---

## 9. Firmware

| # | Change |
|---|---|
| 9.1 | ~~Rewrite to the final GPIO map~~ — done in v1 (§1.3). v2 adds IO25/36/22/32/4 and the IO18→IO13 LED move |
| 9.2 | Sense: `pinMode INPUT` only on IO34/35/36. External pull-ups. Active-low. |
| 9.3 | Relay drive: active-HIGH on IO26/27/25 |
| 9.4 | LEDs on IO13/21/22 |
| 9.5 | **FCFS mutual exclusion** — refuse a command while another channel is sensed or commanded active (§2.3) |
| 9.6 | Watchdog petting on IO4; define the hang criteria |
| 9.7 | Enable switch state on IO32, logged |
| 9.8 | Attribution: extend the deterministic sensed-vs-commanded rule from §1.4 to 3 channels. Effective state = `sensed OR commanded` per channel; publish one message per changed channel. No timing window. |

## 10. ROS2

| # | Change |
|---|---|
| 10.1 | **`pedal_logger.py` schema** — add `bipolar` column; split `event_type` into command vs. activation; add `suppressed` reason code (§2.3) |
| 10.2 | `pedal_commander.py` — bipolar channel in all three modes |
| 10.3 | Source inference — the 0.75 s window is **removed** (§1.4); attribution is deterministic on the ESP32. PC side just records what it receives. Remains FCFS-aware per §2.3. |
| 10.4 | `esu_serial_bridge.py` — unchanged if WiFi/micro-ROS is the session path |

---

## 11. Mechanical

- **4 CPC panel sockets + barrel jack + enable switch** need enclosure wall length. Board grows well past 71 × 57 mm.
- **Sketch the box before the board.** Connector wall space is the real constraint.
- Shielded enclosure, shield bonded to cable shields at the connectors.
- Route pedal cables away from the active electrode.

---

## 12. Deferred to v3

**Modality progression:** v1 monopolar → v2 monopolar + bipolar → **v3 adds vessel sealing.** Each generation adds an output/pedal path on the same interposer architecture, so the connector, bypass-pole, and FCFS work in v2 is the foundation v3 builds on — don't design v2 in a way that boxes out a fourth path.

| Item | Reason |
|---|---|
| **Vessel sealing** | ❓ Advanced bipolar modality (feedback-controlled energy delivery, LigaSure-class). Almost certainly its **own footswitch + generator output path** — same "new pedal path" pattern as bipolar, so it needs the same Step-0 characterization (buy the footswitch, measure the jack, confirm connector) before design. Verify the ASG-300 lineage even *supports* a vessel-sealing output before committing — it may require a different generator. |
| RS-232 telemetry | Blocked on generator firmware changes (per Jiawei). Would solve §2.3 properly. |
| Real IEC 60601-1 isolation barrier | mm creepage, milled slots, rated connectors, isolated DC-DC + digital isolators. Different board. Only if this moves toward patient contact. |
| SD logging | ❓ Decide now — §8.1 keeps the option open for free |

---

## 13. Open decisions

| # | Question | Blocks |
|---|---|---|
| 13.1 | Is the v1 bypass bug confirmed on the bench? | §3 topology |
| 13.2 | Mono and bipolar generator commons — same node? | §3.1 pole count |
| 13.3 | Is the bipolar jack a CPC? | §2.2 BOM |
| 13.4 | ~~SD logging in scope?~~ ✅ **RESOLVED — reserve capability.** Keep VSPI clear (move CUT LED IO18→IO13); no socket now. | §8.1 |
| 13.5 | G6K or photorelays? | §7 — depends on whether a 2 kV number is a formal requirement or a comfort margin |
| 13.6 | ~~WDT IC selection~~ ✅ **RESOLVED — TPS3823A-33DBVR**, direct RESET→coil-FET gate, +1 kΩ WDI→GND, +3× coil flybacks (§3.2) | — |
| 13.7 | Is USB serial needed during sessions? | §5 — USB isolator or not |
| 13.8 | Should `mock_esu_node.py` be rebuilt to mirror the firmware's publish path rather than its own? | It hid §1.4. A mock that cannot reproduce a firmware bug is a false negative. |

---

## 14. Parts & libraries

Library target: append everything to `esu_tap_pcb/esu_tap_v2/libraries/` so the project's
`${KIPRJMOD}`-relative sym/fp-lib-tables pick it up with no path edits. Download tool is
**SnapMagic Search** (formerly SnapEDA) — easyeda2kicad is not working on this machine.

### Confirmed — download now

| Ref | Part | Pkg | LCSC | Source | Populate |
|---|---|---|---|---|---|
| Q1–Q3 driver | AO3400A | SOT-23 | C20917 | snapeda.com/parts/AO3400A/Alpha | POPULATE |
| TVS 3V3 rail | SMAJ5.0A (uni) | SMA/DO-214AC | — | snapeda.com/parts/SMAJ5.0A/Littelfuse | POPULATE |
| TVS 5 V barrel | SMAJ6.0A (uni) | SMA | — | snapeda.com/parts/SMAJ6.0A/Littelfuse | POPULATE |
| TVS sense lines | PESD5V0S1BA (bidi) | SOD-323 | — | snapeda.com/parts/PESD5V0S1BA/DG,115/NXP | **DNP until §0.7** |
| Barrel jack | CUI PJ-102AH (5.5×2.1 mm) | THT horiz | — | fp is **built-in**: `Connector_BarrelJack:BarrelJack_CUI_PJ-102AH_Horizontal`; symbol `Connector:Barrel_Jack` or snapeda.com/parts/PJ-102AH/CUI%20Devices | POPULATE |

A/CA suffix: `A` = unidirectional (rails), `CA`/bidi = signal lines that ring both ways.
Barrel jack is through-hole (conventional — takes plug/unplug force); it's a hand-solder /
non-PCBA line item, which is expected.

### Already in the v1 library — no download

- **G6K-2F-Y-5V** relay (C2982926) — place a 3rd switching instance + the bypass bank
- **1N4148W** flyback (C81598), **1 kΩ** (C11702), 10 kΩ, decoupling caps — v1 lib or KiCad `Device`

### Not yet chosen — real design decisions, do NOT blind-download

| Part | Blocked on |
|---|---|
| Watchdog IC (TPS3823 / MAX6369 class) | timeout + output polarity (§13.6) — must be "asserted only while petted" |
| ORing schottky (SS34 / B5819W class) | trivial at these loads; pick one, then pull |
| Ferrite bead | impedance at 490 kHz — needs the §0.7 measurement |
| TVS on GEN lines | working voltage unknown until §0.7 scoped |
| CPC connectors (TE Series 1) | not on LCSC; pull TE's own KiCad lib. **First settle** whether the PCB land is a CPC footprint at all or just a header the CPC's wires crimp into (§0.4) |

---

## Sequencing

1. Bench-test the v1 bypass (§0.1)
2. Order the BV-1254B (§0.2) — longest lead
3. Characterize BV-1254B + bipolar jack (§0.3–0.6)
4. Scope the mono footswitch line (§0.7) — settles §13.5
5. Resolve open decisions
6. *Then* KiCad

**Flag the bypass bug to Jiawei now**, before confirming. "Our failsafe doesn't fail safe" is worth being early about rather than right about, and it deserves a second reader.
