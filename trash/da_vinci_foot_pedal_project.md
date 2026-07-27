# Da Vinci Surgical Machine Foot Pedal Integration Project

This document outlines the initial brainstorming and technical feasibility for interfacing with the foot pedal of a Da Vinci surgical robot (models Si and Xi). The goals are two-fold:
1. **Actuation:** Be able to trigger the foot pedal functions programmatically from a computer.
2. **Data Recording:** Detect and record when a surgeon (or anyone else) physically presses the pedals.

---

## 1. Mechanical Approach

This approach involves building an external "exoskeleton" or robotic presser that physically interacts with the existing pedals.

### Implementation Ideas
*   **Actuation (Computer Control):** 
    *   **Linear Actuators / Solenoids:** Mount a fast-acting linear actuator or heavy-duty solenoid directly above the target pedals (e.g., the camera clutch or energy pedals). 
    *   **Pneumatics:** If speed is highly critical, small pneumatic cylinders offer very fast actuation times compared to electric linear actuators.
*   **Data Recording (Surgeon Input):**
    *   **Limit Switches:** As you suggested, placing limit switches beneath the pedal or on the mechanical actuator assembly to detect when the pedal reaches the bottom of its travel.
    *   **Load Cells / Force Sensors:** Instead of a binary "pressed/not pressed" switch, placing a thin load cell under the pedal could provide continuous data on *how hard* the surgeon is pressing.
    *   **Optical/Laser Distance Sensors:** Mounting a small Time-of-Flight (ToF) sensor to measure the depression distance of the pedal without physically touching it.

### Pros & Cons
*   **Pros:** 
    *   **Completely Non-Invasive:** You do not alter the electrical circuits of a highly sensitive, expensive, and regulated Class III medical device. No voided warranties or triggered software security faults.
    *   **Fail-Safe:** If the system loses power, it simply stops pressing, allowing the surgeon full normal control.
*   **Cons:** 
    *   **Bulk & Ergonomics:** Da Vinci consoles are ergonomically optimized. Adding mechanical rigs above the pedals might interfere with the surgeon's feet.
    *   **Latency:** Physical motors take time to move, which adds latency between the computer command and the actual pedal actuation.

---

## 2. Electrical Approach ("Man-in-the-Middle")

This approach involves intercepting the electrical signals between the foot pedal assembly and the core console/generator.

### System Architecture Guess (Si vs Xi)
*   **Older systems (Si) / Simple Pedals:** Likely use simple contact closures (for digital state) or potentiometers/Hall-effect sensors (for variable state).
*   **Newer systems (Xi):** Highly likely to use a digital communication bus (like CAN bus, RS485, or EtherCAT) to send a serialized data stream of all pedal states to the main controller, to reduce cable wiring and improve error checking.

### Implementation Ideas
*   **Data Recording (The "Sniffer"):**
    *   Build a **Y-Splitter / Breakout Cable**. You disconnect the pedal cable from the console, plug it into your custom board, and plug your board into the console.
    *   **If Analog:** Use high-impedance Op-Amps to measure the voltage changes on the lines without drawing current (which would drop the voltage and likely trigger a hardware fault on the Da Vinci).
    *   **If Digital:** Tap into the CAN/Serial bus using a microcontroller (e.g., Arduino with a CAN transceiver, or a Raspberry Pi) and sniff the packets to reverse-engineer which byte corresponds to which pedal press.
*   **Actuation (Computer Control):**
    *   **If Analog:** Use Digital Potentiometers (DigiPots) or solid-state relays (SSRs) connected to the microcontroller to inject the correct voltage or close the circuit.
    *   **If Digital:** You would have to actively inject forged packets onto the data bus mimicking the pedal assembly. 

### Pros & Cons
*   **Pros:**
    *   **Invisible & Ergonomic:** Zero physical clutter added to the surgeon's workspace.
    *   **Zero Latency:** Electronic injection is essentially instantaneous.
    *   **High-Fidelity Data:** You get exactly the same data the machine is seeing.
*   **Cons:**
    *   **Extremely High Risk of Faults:** Da Vinci systems have aggressive safety protocols. If the machine detects a tiny unexpected impedance drop, an extra microsecond of latency on the data bus, or a malformed packet, it will trigger a system-wide safety halt (E-Stop). 
    *   **Liability:** Directly interfacing with the electronics of a surgical robot raises massive safety and liability concerns in a clinical setting.

---

## Next Steps & Recommendations

1.  **Investigate the Connector:** The very first step is to locate the cable connecting the foot pedal assembly to the console. Photograph the connector. Count the pins. This will give a huge clue as to whether it's analog (lots of pins, one for each pedal) or digital (4-6 pins for power, ground, and data).
2.  **Multimeter Probing (Safest First Step):** If you can access the pins while the machine is on, use a standard multimeter to check for resting voltages, and see what happens to those voltages when a pedal is pressed.
3.  **Prototype the Mechanical Concept:** Given the safety risks of the electrical route, it might be much faster to 3D print a bracket that holds a standard micro-switch underneath the pedal to solve the "Data Recording" requirement first.

*Note: This document was the initial brainstorming phase; see below for the chosen approach.*

---

## Chosen Approach: Electrical PCB Interposer (ASG300 DRE)

After evaluating both approaches above, the project has adopted the **electrical man-in-the-middle** strategy with a custom PCB. The target device is the **ASG300 DRE electrosurgical generator** (not a Da Vinci robotic system). The foot pedal for this generator uses discrete analog lines (CUT and COAG) that are straightforward to intercept.

### Architecture

A custom KiCad-designed PCB (`pedal_pcb/`) is inserted in-line between the foot pedal cable and the ASG300 DRE generator:

```
Foot Pedal ──► [PCB Interposer] ──► ASG300 DRE Generator
                      │
                 USB Serial to Computer (ROS 2)
```

The PCB MCU:
- **Monitors** the CUT and COAG lines to detect and timestamp surgeon foot presses
- **Drives** those lines to inject artificial activations commanded from the computer

### Connectors

The enclosure uses TE Connectivity circular connectors:

| Part | Description |
|------|-------------|
| TE 206430-1 | Female panel socket (box/wall mount) — on PCB enclosure |
| TE 206429-1 | Male inline plug (cable ends) — on foot pedal and generator cables |
| 66105-4 | Socket crimp contact (for 206430-1) |
| 66103-4 | Pin crimp contact (for 206429-1) |

Full connector details are in [`connector_documentation.md`](connector_documentation.md).
