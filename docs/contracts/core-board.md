# Contract: Core board

**ID prefix:** `CORE` · **Status:** draft v0.1 · **First phase:** P1 · **License:** CERN-OHL-S-2.0

## Purpose

The fixed "brain" shared by every KO keyboard size. Everything difficult lives here, designed once:
radio and MCU, battery and charging, both USB-C ports and the hub, and the four module ports.
Switch boards and modules change; the core board does not.

## Contents

| Block | Implementation (v1) |
|---|---|
| MCU + radio | Pre-certified nRF52840 module with integrated antenna (part: OPEN-01) |
| Battery | One flat LiPo pouch cell, ≤ 3.5 mm thick, under the switch board |
| Power | Charger with power path, fuel gauge, NTC, power switch (off-board, on solder pads), 3.0 V system rail, switched 5 V rail for LEDs and modules (from USB, or boost converter on battery) |
| USB | 2 × USB-C receptacles on the back edge: port A on the core board, port B on the switch board (D-41), both long-body receptacles through the case wall. From rev A: VBUS priority mux (port A first) and a 2:1 data switch, so either port can be the computer port. From rev B: CC role logic per port, 7-port USB 2.0 HS hub, current-limited accessory-port switch |
| Module ports | 4 × module side interfaces (left, right, back, front) per [module-interface.md](module-interface.md) |
| Switch board | Castellated contact row (33 contacts) per [switch-board.md](switch-board.md); the core board is a strip soldered to the switch board's right edge |
| Service | SWD access, test points, reserved footprint for a future body haptic driver |

**Revisions:** rev A (P1) = MCU, power, both USB-C ports as computer ports (port B through the switch board), switch-board contacts;
rev B (P2) adds the hub, the accessory-port role and port-role logic; rev C (P3) adds the module ports. Module contacts sit on small
**edge boards**, one per side, connected to the core board by FFC cables. Details: [docs/design/core-board-rev-a.md](../design/core-board-rev-a.md).

## Interfaces

| Interface | Owned by |
|---|---|
| Core ↔ switch board | [switch-board.md](switch-board.md) |
| Core ↔ modules (mechanical, electrical, bus, power) | [module-interface.md](module-interface.md) |
| Radio links, connection switching | [wireless.md](wireless.md) |
| Host protocol | [host-app.md](host-app.md) |
| Physical placement, RF window, heights | [mechanical.md](mechanical.md) |

**Core board guarantees to the firmware:**
- Every switchable power domain has a GPIO or I2C control; its default state after reset is **off**.
- Battery voltage, charge state, USB attach and port role are readable by firmware.
- The MCU is reachable over SWD at all times, independent of the USB path.

**Invariants:**
- The battery never powers the accessory USB port.
- Two power sources are never connected to each other (USB ↔ USB, USB ↔ power module).
- With the power switch off, no domain except charging and its protection is powered.

## Power budget (targets)

| State | Target | Notes |
|---|---|---|
| Off (power switch) | ≤ 10 µA from battery | charging still works |
| Sleep (on, idle, RGB off, no modules) | ≤ 50 µA average | wake on key, knob, module, USB |
| Active typing, 2.4 GHz or BLE, RGB off | ≤ 3 mA average | basic-mode budget behind SYS-03 |
| RGB on | ≤ 1.5 A on the LED rail | brightness capped by firmware |

Sanity check: 4 weeks × 8 h/day = 224 h active. A 2,500 mAh cell with 20 % reserve allows ~9 mA
average, so the 3 mA target leaves a large margin for modules and ageing.

## Requirements

| ID | Requirement | Phase | Verify |
|---|---|---|---|
| CORE-001 | The core board shall use one LiPo pouch cell ≤ 3.5 mm thick, with over-charge, over-discharge, over-current and short-circuit protection. | P1 | I/T |
| CORE-002 | Charging shall be monitored by an NTC and stop outside 0–45 °C. | P1 | T |
| CORE-003 | The keyboard shall charge from either USB-C port at 5 V; the input current limit shall follow the Type-C current advertisement (default USB, 1.5 A, 3 A). No USB Power Delivery. | P1 | T |
| CORE-004 | A power path shall let the keyboard run from USB while charging and with a dead or missing battery. | P1 | T |
| CORE-005 | Default charge current shall be 1 A (firmware-configurable); full charge ≤ 4 h for the chosen cell. | P1 | M |
| CORE-006 | A fuel gauge shall report state of charge to the firmware with ±5 % accuracy. | P1 | M |
| CORE-007 | A physical power switch shall cut all domains except charging; battery drain when off ≤ 10 µA. The switch may sit off the board, wired to solder pads (D-43). | P1 | M |
| CORE-008 | Sleep current (on, idle, RGB off, no modules) shall be ≤ 50 µA average. | P1 | M |
| CORE-009 | The LED rail, the 5 V module rail and the USB hub shall be switchable and off by default on battery; the hub shall be powered from VBUS only. | P1 | T/I |
| CORE-010 | The 5 V module rail shall come from VBUS when wired and from a boost converter on battery, and shall support power-source modules feeding the keyboard ([module-interface.md](module-interface.md)). | P3 | T |
| CORE-020 | Two USB-C receptacles on the back edge shall be electrically identical. | P2 | I |
| CORE-021 | The first port to see a source (host or charger) shall become the upstream port; the other shall become the accessory port, presenting Rp. | P2 | T |
| CORE-022 | Port roles should be resolved in hardware, without firmware. Fallback, if testing shows this is unreliable: port A defaults to upstream whenever firmware is not running. | P2 | T |
| CORE-023 | The accessory port shall be powered only from upstream VBUS, through a switch limited to 500 mA, and never from the battery. | P2 | T |
| CORE-024 | VBUS paths shall block reverse current; a host or charger shall never be back-fed. | P2 | T |
| CORE-025 | A USB 2.0 High-Speed hub shall provide downstream ports for: the MCU, the accessory port, and one USB lane per module side. | P2 | T |
| CORE-026 | High-Speed USB shall be routed as 90 Ω differential pairs on an impedance-controlled stackup; a USB stick on the accessory port shall read at ≥ 25 MB/s. | P2 | M |
| CORE-027 | Firmware recovery shall always be possible: over USB via the UF2 bootloader, and over SWD pads reachable with the bottom case removed. | P1 | T |
| CORE-030 | All USB lines and module contacts shall have ESD protection (target IEC 61000-4-2 ±8 kV contact). | P1 | I/T |
| CORE-040 | Four module ports shall implement [module-interface.md](module-interface.md): detection before power, per-side current limit, bus transceiver, USB lane. | P3 | T |
| CORE-050 | The core board shall implement the core side of the core ↔ switch board interface ([switch-board.md](switch-board.md)). | P1 | T |
| CORE-060 | PCB: 4 layers, JLCPCB impedance-controlled stackup, passives ≥ 0402, no BGA, all parts JLCPCB-assemblable. | P1 | I |
| CORE-061 | Core board and battery together shall fit under the smallest supported layout (40 %, see [generator.md](generator.md)). Outline: OPEN-11. | P1 | I |
| CORE-062 | The radio module's antenna keep-out shall be respected, and the antenna shall sit at the case's RF path ([mechanical.md](mechanical.md)). | P1 | I |
| CORE-063 | Every rail, USB, I2C and SWD shall have labelled test points the owner can probe. | P1 | I |
| CORE-064 | A footprint/connector for a future body haptic driver (I2C) shall be reserved and left unpopulated (rev A: solder pads, D-43). | P1 | I |
| CORE-066 | Rev A shall accept a computer or charger on either USB-C port: VBUS priority mux (port A first) with reverse-current blocking, D± 2:1 switch selected by the mux status, CC sensing on both ports, and an input overvoltage cut-off below 6 V. | P1 | T |
| CORE-065 | An underglow strip port shall provide the switched LED rail, GND and a 5 V data line buffered from an MCU pin, for an addressable 5 V LED strip (WS2812/SK6812 class), within the LED rail's 1.5 A; the buffer shall be unpowered while the LED rail is off. Rev A: solder pads (D-43). | P1 | I/T |
| CORE-070 | The radio shall be a pre-certified nRF52840 module with integrated antenna. | P1 | I |

## Not in scope

USB Power Delivery, wireless charging (Qi), 8 kHz polling (later core board with nRF54LM20), status LEDs.
