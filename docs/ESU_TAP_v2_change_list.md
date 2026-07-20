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
| 0.1 | **Bench-test the v1 bypass.** Power board down, plug in, press pedal. | Confirms or kills the §1.1 bug. Changes the bypass topology. |
| 0.2 | **Buy a BV-1254B bipolar footswitch** (~$230) | Long lead. Blocks all bipolar design. |
| 0.3 | **Characterize the BV-1254B** — pin count, pinout, R across every pin pair idle/pressed, ID scheme | You cannot design to a datasheet that doesn't exist publicly |
| 0.4 | **Inspect the generator's bipolar jack** — connector type, is it CPC? | v1 taught you not to assume the connector |
| 0.5 | **Measure the bipolar jack's idle impedance** to its common | The ~24 Ω finding is what broke v1's topology |
| 0.6 | **Are the mono and bipolar generator commons the same node internally?** | If shared, saves a bypass pole (§3) |
| 0.7 | **Scope the mono footswitch line during an activation** | Settles the isolation argument with real numbers |

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

⚠️ Rests on the G6K pinout (coil 1/8, pole A COM=3 NC=2 NO=4, pole B COM=6 NC=7 NO=5). Netlist is consistent with it. **Confirm on the bench before trusting this.**

### 1.2 Connectors still screw terminals ✅

J1/J4 are `TerminalBlock*` in the netlist. Never updated. Replace with TE CPC Series 1 — 206430-1 female panel sockets, 206429-1 male inline plugs, 66105-4 / 66103-4 contacts, 1-206062-4 backshells.

### 1.3 Firmware never updated ✅

`pedal_firmware.ino` still uses generic Arduino pin numbers, not the final GPIO map. Outstanding since v1. See §9.

---

## 2. New capability — bipolar

### 2.1 The BV-1253B cannot do bipolar on this generator ✅

The BV-1253B behaves differently per generator. On the Specialist PRO it's mono+bipolar (yellow = mono, blue = bipolar). On the **Surgi-Center PRO / OR PRO 300 it cannot perform bipolar functions** — it acts as dual-monopolar, yellow = cut, blue = coag. The ASG-300 is the OR PRO 300 / IDS-300 lineage.

**Bipolar requires the BV-1254B** — a separate single-pedal bipolar footswitch, listed for the IDS-200/210/300/310/400 and A2250/A3250/A2350/A3350.

**Consequence: v2 is not "add a channel." It's "add a second, independent pedal-and-jack path."**

### 2.2 Additions

| Item | Detail |
|---|---|
| Connectors | **2 more CPC** — bipolar pedal socket (J5) + bipolar generator plug (J6). Total 4 + power. |
| Switching relay | K_BIP — third G6K (U5) |
| Driver | AO3400A + 1 kΩ gate series + 10 kΩ gate pulldown + 1N4148W flyback |
| Sense | IO36 (VP), external 10 kΩ pull-up, active-low |
| LED | Blue on IO22 (matches pedal colour convention) |
| Bypass poles | +2 (BIP + bipolar COM) — see §3 |

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

❓ Pick a WDT IC (TPS3823 / MAX6369 class). Pet from IO4.

**Note:** bypass relays must stay electromechanical. Only a mechanical NC contact passes through when unpowered — no SSR can do this.

---

## 4. Protection

The realistic threat is **coupled RF at 490 kHz, ESD, and faults** — not kilovolt dielectric breakdown. The generator's output is already isolated internally: it's **Defibrillator-proof Type CF with isolated output circuitry** ✅, and the footswitch jack sits on the far side of that certified barrier.

| Item | Detail |
|---|---|
| **TVS diodes** | Every conductor at J1, J4, J5, J6 |
| **Series resistors** | ~1 kΩ on IO34 / IO35 / IO36 — limits current into the ESP32's ESD clamps |
| **RF filtering** | Ferrite bead + shunt cap at each connector. **490 kHz** is the frequency to target ✅ |
| **Hardware enable switch** | In series with generator-side common. Breaks all channels. Addresses stuck-on contact — the hazard no relay fixes. |
| Enable switch sense | IO32 (has internal pull-up, unlike 34–39) so firmware can log state |

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

### 8.1 SD card decision ❓

IO18 is currently the CUT LED (R8). VSPI wants IO18/19/23/5 — IO19/23/5 are free ✅, IO18 is not.

**Recommendation: move the CUT LED to IO13 regardless.** Costs nothing now, preserves the SD option, painful to change after layout.

---

## 9. Firmware

| # | Change |
|---|---|
| 9.1 | **Rewrite to the final GPIO map** — outstanding since v1 |
| 9.2 | Sense: `pinMode INPUT` only on IO34/35/36. External pull-ups. Active-low. |
| 9.3 | Relay drive: active-HIGH on IO26/27/25 |
| 9.4 | LEDs on IO13/21/22 |
| 9.5 | **FCFS mutual exclusion** — refuse a command while another channel is sensed or commanded active (§2.3) |
| 9.6 | Watchdog petting on IO4; define the hang criteria |
| 9.7 | Enable switch state on IO32, logged |
| 9.8 | Attribution: pedal-GPIO edge with no matching relay command = surgeon; commanded relay = computer. Extend to 3 channels. |

## 10. ROS2

| # | Change |
|---|---|
| 10.1 | **`pedal_logger.py` schema** — add `bipolar` column; split `event_type` into command vs. activation; add `suppressed` reason code (§2.3) |
| 10.2 | `pedal_commander.py` — bipolar channel in all three modes |
| 10.3 | Source inference — 0.75 s window logic extended to 3 channels, FCFS-aware |
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
| 13.4 | SD logging in scope? | §8.1 (mitigated — move the LED anyway) |
| 13.5 | G6K or photorelays? | §7 — depends on whether a 2 kV number is a formal requirement or a comfort margin |
| 13.6 | WDT IC selection | §3.2 |
| 13.7 | Is USB serial needed during sessions? | §5 — USB isolator or not |

---

## Sequencing

1. Bench-test the v1 bypass (§0.1)
2. Order the BV-1254B (§0.2) — longest lead
3. Characterize BV-1254B + bipolar jack (§0.3–0.6)
4. Scope the mono footswitch line (§0.7) — settles §13.5
5. Resolve open decisions
6. *Then* KiCad

**Flag the bypass bug to Jiawei now**, before confirming. "Our failsafe doesn't fail safe" is worth being early about rather than right about, and it deserves a second reader.
