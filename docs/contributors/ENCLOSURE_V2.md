# v2 enclosure mechanical reference

Measured 2026-10-14 from `hardware/esu-tap-v2/esu_tap_v2.kicad_pcb`.
PCB SHA-256: `459DB44D46728959837379C0496E131309EA1193361F5AD0619B864708C544B5`.
This is a mechanical reference, not a finished enclosure or medical/electrical
safety qualification. No PCB, schematic, or fabrication files were changed.

Confirmed assembly: TE 206430-1 monopolar panel sockets, Bulgin PX0412/03S
bipolar panel sockets, ESP32 on female headers. Panel sockets are wired to
J1-J4; their enclosure positions are NOT fixed by PCB coordinates.

## 1. Coordinate system and PCB

All dimensions are millimeters. View from the component side, with J3 on the
left/top, J1 left/bottom and J5 toward the bottom. Origin is the upper-left
corner of the board's bounding rectangle; +X right, +Y down. The actual corner
is rounded. For ordinary CAD with +Y upward, negate Y (do not mirror the board).

KiCad absolute origin for these tables: X=86.800, Y=63.400.
Z=0 is the TOP of the main PCB; the board occupies Z=-1.6 to 0.

| Feature | Dimension |
| --- | --- |
| Board width X | 88.000 |
| Board height Y | 62.000 |
| Nominal PCB thickness in project | 1.600; verify actual ordered thickness |
| Four outline corner radii | R2.000 |
| Board mounting holes | Four non-plated diameter 3.200 holes |

| Hole | X from left | Y from top |
| --- | ---: | ---: |
| H1 | 7.3000 | 4.9000 |
| H2 | 9.2075 | 56.7000 |
| H3 | 83.8700 | 17.7000 |
| H4 | 83.8700 | 43.9500 |

**Not a rectangular mounting pattern.** Do not copy one corner offset to all
four bosses. The footprint name includes M3/DIN965, but the board data describes
ordinary through holes, not a machined countersink. Check screw-head, washer and
boss clearance against nearby copper/components. The hole footprint courtyard
is diameter 6.1 mm, not authorization for an arbitrarily large boss or washer.

The saved fabrication ZIP (Gerber timestamp 2026-09-08) has the same outline and
these mounting locations within drill rounding: H2 is X=96.007 absolute in the
drill rather than 96.0075 in the PCB. J1-J5/U1 drilled locations also match.
This does not prove that this is the exact ZIP used for your physical order.

## 2. Board-mounted parts and access

The following rectangles are **F.Fab nominal body envelopes in the PCB**, not
manufacturing tolerances or finished enclosure openings. Allow clearance.

| Ref / role | Body X range | Body Y range | Facing / access |
| --- | --- | --- | --- |
| J3, MON GEN, 4-way terminal | 4.485 to 14.285 | 9.440 to 29.760 | Wire entry left; screws above |
| J1, MON PED, 4-way terminal | 4.535 to 14.335 | 31.840 to 52.160 | Wire entry left; screws above |
| J4, BI GEN, 3-way terminal | 71.180 to 86.420 | 3.325 to 13.125 | Wire entry toward top; screws above |
| J2, BI PED, 3-way terminal | 71.170 to 86.410 | 48.495 to 58.295 | Wire entry toward bottom; screws above |
| J5, PJ-102AH jack | 27.450 to 36.450 | 44.250 to 58.650 | Plug enters from bottom |
| U1, DevKit main PCB envelope | 40.955 to 68.895 | 9.550 to 57.810 | USB at bottom; antenna toward top |

### Terminal blocks

The footprint family is Phoenix MKDS 1,5, horizontal wire entry, 5.08 mm pitch:

- J1/J3: **1715747**, 4 positions, nominal body 20.32 long x 9.8 deep x
  **13.8 above PCB**, solder pins 3.5 long.
- J2/J4: **1715734**, 3 positions, nominal body 15.24 long x 9.8 deep x
  **13.8 above PCB**, solder pins 3.5 long.
- These are inside the box when the TE/Bulgin sockets are used. Reserve wire
  entry/bend space and screwdriver access; the PCB body envelope alone omits both.
- Verify purchased parts: an earlier shopping link used **1715035**, which is
  not the listed 1715734. Do not assume substitutions have identical bodies.

Source: [Phoenix manufacturer catalog, printed page 27](https://www.phoenixcontact.com/assets/2018/interactive_ed/101_977104/epaper/CAT_8_2024_EN_LoRes.pdf).
[1715747 product/drawings](https://www.phoenixcontact.com/en-ca/products/printed-circuit-board-terminal-mkds-15-4-508-1715747).

### Barrel jack J5: PJ-102AH

[Same Sky/CUI datasheet, mechanical drawing page 2](https://www.sameskydevices.com/product/resource/pj-102ah.pdf).

- Nominal body: **9.00 wide x 14.40 deep x 11.00 high**.
- Plug axis X=**31.950**, nominal Z=**6.50 above PCB top** (drawing +/-0.10).
- Front face Y=**58.650**; thus **3.350 recessed** from the bottom board edge.
- Face opening diameter **6.50**; this is NOT automatically the enclosure hole.
- Jack center pin diameter **2.00** in the manufacturer's drawing; mating barrel
  OD 5.5 and insertion depth 9.5. Earlier conversation used the common 5.5x2.1
  plug description; verify the actual purchased plug's mating fit.
- Terminals extend nominal 3.50 below the seating plane before trimming.
- Current drawing general tolerances: X +/-0.50, X.X +/-0.30, X.XX +/-0.20,
  PCB +/-0.05 unless an individual dimension specifies otherwise.

If a wall sits outside the board, the plug must reach through the wall plus
board-to-wall gap plus the 3.35 recess. A small round hole can stop the molded
plug grip before full insertion. Size a recess/access opening around the actual
plug overmold or use a separately selected panel extension. Do not treat J5 as
a threaded panel jack or use its mating-pin diameter as the wall cutout.

### ESP32 / USB / female headers

[Official Espressif dimension drawing](https://dl.espressif.com/dl/schematics/esp32_devkitc_v4_dimensions.pdf)
and [DevKitC documentation](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html).

- Official DevKitC main PCB: **27.94 wide x 48.26 long**, with antenna extension
  shown as **18.00 wide x 6.04 long**.
- Two **1x19** header rows, **2.54 pitch**, **25.40 row spacing**.
- Your PCB header centerlines: X=**42.225** and **67.625**.
- First pads: Y=**10.845**; last pads Y=**56.565**; 18 intervals span 45.720.
- USB centerline: X=**54.925**. The footprint's USB protrusion ends at Y=58.810,
  giving approximately 3.190 recess to the board edge. Treat this as a footprint
  estimate, not a verified USB receptacle drawing or plug-clearance specification.
- Footprint antenna extends to Y=2.810; its extension differs from the official
  drawing. Use the actual module/drawing for antenna clearance and do not assume
  the supplied 3D model is an exact assembled mechanical reference.
- **USB Z position and overall assembled height are not known until the exact
  female headers and mating insertion depth are known.** Measure with the module
  seated. The current KiCad model offset does not establish that stack height.
- Provide USB plug/overmold and bend clearance, plus EN/BOOT button access if
  wanted. Do not put a metal fastener or tightly bundled wiring against the antenna.

### Indicator centers for optional lid windows/light pipes

| Ref | Label | X | Y |
| --- | --- | ---: | ---: |
| D8 | CUT, blue | 34.800 | 2.600 |
| D9 | COAG, red | 34.800 | 6.000 |
| D10 | BI, yellow | 34.800 | 9.350 |
| D6 | Power, blue | 39.450 | 56.450 |

These are footprint origins. Verify optical centers and light-pipe seating
against the fitted LED and lid thickness; do not load the LED mechanically.

## 3. Panel connectors: separate from PCB terminals

### Monopolar: TE 206430-1, shell size 11-4, reverse-gender socket receptacle

[TE part page with STEP/DXF downloads](https://www.te.com/en/product-206430-1.html).
[TE catalog, printed pages 10 and 25](https://www.te.com/commerce/DocumentDelivery/DDEController?Action=srchrtrv&DocFormat=pdf&DocLang=English&DocNm=82021_CPC_sections1-5&DocType=Catalog+Section&PartCntxt=206430-1).

The shell-size-11 reverse-gender catalog row gives:

| Feature | Reference dimension |
| --- | --- |
| Square flange | 28.58 square (G; +/-0.64 shown) |
| Four mounting-hole center spacing | 21.44 x 21.44 (F; +/-0.25) |
| Mounting-hole diameter | 3.18, +0.18/-0 (H) |
| Main panel cutout diameter | 21.34 (J) |
| Maximum panel thickness | 3.18 |
| Overall receptacle axial envelope | 27.18 maximum (A, reverse gender) |
| Flange thickness | 2.39 +/-0.25 (C) |

For a connector centered at local panel (0,0), mounting-hole centers are
(+/-10.72, +/-10.72). This is **flange-mounted**, not a press-fit installation.
The rear body, inserted contacts, wires and any rear accessory need interior
clearance. The catalog is a reference drawing: confirm the current part-specific
CAD and an actual connector before committing a precision final cutout.

Mating cable plug **206429-1** is not another panel socket. Catalog maximum bare
plug envelope: 34.67 axial length and 24.77 coupling OD; cable clamp/backshell
adds length. Leave finger access to turn the coupling. Do not recess the flange
so far that the plug cannot fully engage.

The historical connector notes say 'bolts or press-fits'; use the documented
flange mounting holes, not that historical press-fit suggestion.

### Bipolar: Bulgin PX0412/03S front-panel socket

[Bulgin product page](https://www.bulgin.com/us/products/front-panel-mount-connector-body-px0412-series-3-contact-socket.html).
[Manufacturer 400 Series drawing, PDF page 3 / printed page 42](https://www.bulgin.com/products/pub/media/bulgin/data/400_power.pdf).

| Feature | Drawing dimension |
| --- | --- |
| Panel cutout | Diameter 16.10 with anti-rotation flat |
| Flat location | 7.10 from center toward the flat |
| Maximum panel thickness | 3.20 |
| Front-view body envelope callout | 22.0 |
| Overall axial length | 19.9 |
| Projection from front panel surface | 12.3 |
| Rear fixing thread | M16 x 1.5 |

Construct the nominal D-cutout as a diameter-16.10 circle clipped by a flat
7.10 from its center. Radius=8.05, so the flat removes a cap 0.95 deep; flat-to-
opposite-round distance is 15.15. Rotate the entire profile as required for
connector key orientation. **Do not substitute the PX0413 cutout**: that is a
different rear-panel family.

Keep room behind the wall for the fixing nut, contact insert, wire tails and
assembly tool access. The 19.9 body length does not include bent wires. The
22.0 front-view callout is not the panel hole. Validate hex corner/nut envelope
with the manufacturer's CAD or actual connector.

Mating **PX0410/03P/5560** cable connector: the /5560 gland accepts cable OD
5.5-6.0, not arbitrary cable. See the same catalog for the mating-body drawing;
reserve coupling/finger access and cable bend radius outside the box.

## 4. Box sizing: dimensions that still depend on your assembly

Do not finalize overall height from the flat PCB or zero-offset ESP32 model.

Let S = interior floor to PCB underside (standoff height), H = highest assembled
item above PCB top, and C = chosen lid clearance. Then the minimum interior
height for the board alone is **S + 1.6 + H + C**. Also check any panel connector,
rear nut, internal cable, lid ribs, screw bosses and light pipes in 3D.

For a first fit prototype, 0.5-1.0 lateral clearance per PCB side, 6 mm underside
standoffs and 2 mm lid clearance are possible starting allowances, NOT measured
requirements or qualified insulation distances. Check actual solder tails and
printed tolerances. A 90 x 64 board pocket is not a complete box size: panel
connector tails and terminal wiring can require a substantially larger cavity.

Use a locally thin, flat mounting land within **3.18 mm** at TE sockets and
**3.20 mm** at Bulgin sockets; thick reinforced walls elsewhere can step back.
Print a small connector-cutout coupon before the whole box. Printed hole
compensation should come from that printer/material, not an invented universal
oversize. Account for removal of supports and nut/driver access during assembly.

Still measure/select before final CAD:

1. Exact female-header part and fully seated ESP32 height; USB aperture Z.
2. Actual USB and DC plug overmolds, cable OD and minimum bend radius.
3. Panel socket quantity/orientation/spacing, nuts/fasteners and any TE backshells.
4. Actual terminal part numbers and installed solder-tail lengths.
5. Power/stop-button model and its cutout, if installed on this box; no exact
   switch part number is established by the current PCB files.
6. Enclosure fastening method, print material, wall/lid thickness, service access,
   strain relief, and independent fit checks against the physical board.

Maintain the intended separate commons in wiring and keep fasteners/wire tails
from bridging conductors. A printed box or connector's standalone IP rating does
not establish insulation, ingress protection, or suitability of the completed
surgical interface.

## 5. Local CAD/reference outputs

Ignored working outputs are in `outputs/enclosure-v2/` (not fabrication outputs):

- `esu_tap_v2_board_only.step`: KiCad-exported bare board with drilled holes,
  origin requested at KiCad (86.8,63.4). No components, headers, panel connectors
  or box. Check imported STEP axes/Z datum before using the table above.
- `pj-102ah.pdf`: downloaded Same Sky drawing (2024-09-12 revision).
- `bulgin-400.pdf`: downloaded Bulgin catalog with PX0412 fixing detail.
- `esp32-dimensions.pdf`: official Espressif module dimension drawing.
- `te-cpc.pdf`: TE-authored catalog page 10 from a distributor mirror; identifies
  206430-1 and the dimension callout diagram but does not include page 25's table.

Use the linked TE catalog for its dimension table and part page for STEP/DXF.
Source-server access to a full local TE catalog download was not reliable.
