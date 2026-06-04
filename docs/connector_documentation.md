# Connector Documentation — ASG300 DRE Foot Pedal PCB

This document covers the connectors used on the PCB interposer and its cables.

## System Overview

The PCB enclosure sits mid-cable between the ASG300 DRE foot pedal and the generator. Two connectors are needed on the enclosure panel (one facing the foot pedal, one facing the generator). The existing cables each terminate in a mating inline plug.

```
Foot Pedal ──[TE 206429-1 plug]──► [TE 206430-1 socket | PCB | TE 206430-1 socket] ◄──[TE 206429-1 plug]──► ASG300 DRE
```

## TE Connectivity Part Numbers

### TE 206430-1 — Female Panel Socket (Box/Wall Mount)

- **Type**: Circular connector, female, panel/chassis mount
- **Mounting**: Bolts or press-fits into the enclosure wall
- **Mating plug**: TE 206429-1
- **Crimp contact loaded**: 66105-4 (socket contact, wire-side)
- **Quantity on PCB enclosure**: 2 (one per side)

### TE 206429-1 — Male Inline Plug (Cable Ends)

- **Type**: Circular connector, male, free-hanging inline plug
- **Mounting**: Terminates the end of a cable; mates into TE 206430-1
- **Crimp contact loaded**: 66103-4 (pin contact, wire-side)
- **Quantity**: 2 (one on foot pedal cable end, one on generator cable end)

## Crimp Contacts

| Part | Type | Loaded Into |
|------|------|-------------|
| 66105-4 | Socket (female contact) | TE 206430-1 (panel socket) |
| 66103-4 | Pin (male contact) | TE 206429-1 (inline plug) |

Use the appropriate TE crimp tool for 66-series contacts. Strip wire to the specified length in the contact datasheet and verify crimp pull-force before assembly.

## Pinout

Document the per-pin signal assignments here as they are finalized during schematic/PCB design. At minimum, record:

| Pin | Signal | Direction (relative to PCB) | Notes |
|-----|--------|----------------------------|-------|
| — | CUT | Input (from pedal) / Output (to generator) | Monitored and driven by MCU |
| — | COAG | Input (from pedal) / Output (to generator) | Monitored and driven by MCU |
| — | GND | — | Common ground reference |
| — | (additional) | — | Fill in from schematic |

## Assembly Notes

- Verify connector gender and contact type before crimping — swapping socket/pin contacts is a common assembly error.
- The panel socket (206430-1) requires a cutout in the enclosure wall; confirm the cutout diameter against the datasheet before machining.
- After crimping, perform a continuity check through the full cable-to-PCB path before closing the enclosure.
- The PCB must not alter the electrical characteristics of the CUT/COAG lines when in passive monitoring mode. Verify input impedance and leakage current are within ASG300 DRE specifications.
