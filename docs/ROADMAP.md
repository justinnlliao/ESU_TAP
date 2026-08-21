# Roadmap & Known Limitations

Forward-looking items only. Completed work lives in [CHANGELOG.md](../CHANGELOG.md).
This is the honest list of what the current board does **not** do, what is
deferred, and what comes next.

---

## Known limitations (current board, v2)

These are deliberate scoping decisions, not defects. They matter most for anyone
building this board from the published files.

### Power input is not overvoltage-tolerant
The input protection (PTC + reverse-polarity Schottky + SMAJ6.0A TVS) covers
**fault containment** — dead short and reversed polarity. It does **not** protect
against a wrong-voltage adapter. A sustained 9–12 V input can expose the rail to
damaging voltage before the PTC (a current device, not a voltage device) trips,
and the TVS clamp (~10.3 V) is a pulse rating, not continuous.

- **Use a regulated 5 V DC, center-positive supply.** The jack is labeled as
  such on the silkscreen.
- An eFuse footprint is reserved and currently bridged with a 0 Ω jumper. A true
  overvoltage-cutoff eFuse or a wide-input regulator can be dropped in there in a
  future revision without a respin.

### RF filtering on the sense lines is not populated
The ferrite footprints on `CUT_SENSE` / `COAG_SENSE` / `BI_SENSE` are placed but
unpopulated. v1 (monopolar) ran on these same lines with no RF filtering and no
observed issues, so coupled RF from the generator does not appear significant in
this setup. The footprints exist as insurance; populate them only if a bench
measurement shows RF on the lines. The ESD clamp + series resistor **are**
populated (those guard against ESD/fault events, a different risk).

### Not validated for clinical use
This is a research / data-collection interposer. It has standard PCB clearances,
no IEC 60601-1 isolation barrier, and screw-terminal connectors. Any use beyond
the bench requires signal characterization, isolation validation, and a
safety/regulatory review.

### Failsafe timing
On a firmware hang, fallback to pass-through takes up to the watchdog interval
(~1.6 s) plus relay release. On power loss it is just relay release (~ms). The
board fails to **manual pedal control**, not to "off" — it cannot stop a
generator that a human pedal is actively firing; that remains the operator's and
the generator's responsibility.

---

## Open verification items

Things to confirm on the physical board or bench before relying on results.

- **Footswitch line scope measurement.** Scope `CUT_SENSE` / `COAG_SENSE` /
  `BI_SENSE` during a live activation to quantify any coupled RF. Resolves
  whether the RF ferrite is ever needed and closes the isolation assumption.
- **Bench continuity check on arrival.** Verify pedal → generator forwarding in
  both powered (sensed + commanded) and unpowered (bypass) states, per modality,
  before trusting the board in a session.
- **Bipolar footswitch impedance.** Confirm the BV-1254B / bipolar jack idle
  impedance matches the monopolar assumption (~24 Ω) at first bring-up.
- **Watchdog hang test.** Deliberately stall the firmware and confirm the board
  drops to bypass within the expected interval.
- **Shared-common tolerance.** Confirm the generator tolerates its footswitch
  behavior with the split-common bypass topology (mono and bipolar commons no
  longer share GND in bypass).

---

## Next revision (v3)

**Modality roadmap:** v1 monopolar → v2 monopolar + bipolar → **v3 vessel
sealing.** Each generation adds an independent pedal/generator path on the same
interposer architecture, so the connector, bypass-pole, and forwarding work in
v2 is the foundation v3 builds on.

- **Vessel sealing channel.** Another pedal/generator path, cloned from the
  bipolar channel. Requires its own footswitch and a generator with a
  vessel-seal output (confirm the generator supports it before designing — it may
  require different hardware). Same Step-0 characterization as bipolar: obtain
  the footswitch, measure the jack, confirm the connector, then design.
- **Overvoltage eFuse.** Populate the reserved eFuse footprint (currently a 0 Ω
  jumper) for true wrong-adapter protection.
- **Keyed cable connectors.** Swap screw terminals for keyed, latching,
  strain-relieved cable connectors for deployment robustness.
- **RS-232 telemetry.** Read generator-confirmed activation state directly
  (blocked on generator firmware). Would let the logger record what the
  generator *actually fired* rather than inferring from commands — see the
  data-integrity note below.
- **Standalone SD logging.** VSPI pins are kept clear on v2 (CUT LED moved off
  IO18) so an SD card can be added without a re-layout.

---

## Data-integrity note (imitation learning)

The ASG-300 arbitrates simultaneous activations **first-come-first-served** —
whichever channel fired first wins, and later commands are ignored while it is
active. Because the board cannot observe generator-side state, a logged *command*
is not proof of a generator *activation*: if the computer commands a channel
while another is already active, the generator ignores it but the log would
otherwise record it. The logging pipeline must therefore distinguish **command**
from **activation** events and mark suppressed commands, rather than assuming
every command fired. RS-232 telemetry (above) would resolve this directly.
