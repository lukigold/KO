# Design note: Core board rev A

**Implements:** [core-board.md](../contracts/core-board.md) (P1 scope) · **Status:** architecture and part selection done, schematic next · **Date:** 2026-11-15

Design notes explain *how* a contract is implemented. They never override a contract; if they disagree,
fix one of them in the same change.

## 1. Revision plan

The core board is built in three revisions. Each one adds one risky subsystem, so a fault never blocks everything.

| Rev | Phase | Adds | Contract scope |
|---|---|---|---|
| **A** | P1 | MCU + radio, battery charging and power path, fuel gauge, 3.0 V and 5 V rails, one USB-C port (direct to MCU), switch-board connector, LED rail, SWD, expansion header | CORE-001…009, 027, 030, 050, 060…064, 070 |
| B | P2 | 7-port USB hub, second identical USB-C port, port-role logic, accessory port | CORE-020…026 |
| C | P3 | Four module ports via edge boards, module bus | CORE-010, CORE-040 |

Rev A is deliberately simple. Its job is a daily-usable wireless keyboard and proving the power budget (SYS-03).

## 2. Block diagram (rev A)

```
                 ┌──────────────────────────── Core board rev A ────────────────────────────┐
 USB-C (port A) ─┤ ESD ─ VBUS ─┬─ BQ25628E charger ─ SYS ─┬─ TPS7A02 3.0 V ─► 3V0 rail      │
  Rd 5.1 kΩ      │             │   │ I²C, INT             └─ TPS61023 boost ─┐              │
                 │             │   └─ BAT ── LiPo 1S (protected) + NTC     │              │
                 │             └──────────── TPS2116 IN1 ◄── IN2 ◄─────────┘              │
                 │                              └ V5 ─ AP22653 (≈1.7 A) ─► LED_5V ───────┼─► FFC 24-pin ─► switch board
                 │ D+/D− ─────────────────────► BMD-340 (nRF52840) ◄─ I²C ─ MAX17048      │     (rows, column chain,
                 │                               │  32.768 kHz XTAL                       │      I²C, LED_SDB)
                 │  power switch ─► LDO EN        ├─ SWD header (2×5, 1.27 mm)             │
                 │                               ├─ expansion header (UART, SPI, I²C, GPIO)│
                 │                               └─ reserved: haptic driver (DNP)         │
                 └──────────────────────────────────────────────────────────────────────────┘
```

## 3. Power tree

| Rail | Source | Range | Max load | Consumers |
|---|---|---|---|---|
| VBUS | USB-C port A | 5 V | 3 A (Type-C advertisement; charger input limit follows it) | charger, V5 mux |
| SYS | BQ25628E power path | ≈ VBAT on battery; ≥ 3.5 V (VSYSMIN) on USB | ≈ 2 A | 3.0 V LDO, boost |
| BAT | 1-cell LiPo, protected | 3.0–4.2 V | — | charger, fuel gauge |
| 3V0 | TPS7A02 LDO, enabled by the power switch | 3.0 V | 200 mA | nRF52840, I²C devices, switch-board logic (shift registers, EEPROM, LED driver logic) |
| V5 | TPS2116: VBUS (priority) or TPS61023 boost from SYS | 5 V | 2.5 A on USB, ≈ 1 A on battery | LED rail; module rails from rev C |
| LED_5V | AP22653 from V5, enabled by MCU | 5 V | ≈ 1.5 A (limit ≈ 1.7 A) | per-key RGB on the switch board |

**Why 3.0 V instead of 3.3 V:**
- Every chip on the always-on rail works at 3.0 V.
- The LDO's 25 nA quiescent current suits the 50 µA sleep budget.
- A linear regulator draws the same battery current a buck would at these loads, and it's quieter for the radio.
- It drops out only below a ≈ 3.2 V cell, where less than 5 % of the capacity remains.

**Power switch:** a slide switch drives the LDO and boost enable pins.
- **Off:** the MCU and everything behind it are unpowered. Only the charger (1.5 µA) and the fuel gauge (hibernate, a few µA) stay on.
- That meets CORE-007 (≤ 10 µA when off), and charging still works.

## 4. Part selection (rev A)

Stock and prices from JLCPCB/LCSC on 2026-11-15 (unit price at quantity 1, USD).

| Function | Part | LCSC | Stock | ≈ USD | Why | Alternative |
|---|---|---|---|---|---|---|
| MCU + radio | u-blox **BMD-340-A-R** (nRF52840, integrated antenna, pre-certified, 10 × 15 × 1.9 mm, LGA-60) | C5456944 | 349 | 8.74 | Small, thin, certified, Zephyr/Embassy board support exists; -10 revision is in production | Ebyte E73-2G4M08S1CX (C2764963, 974, 6.79): castellated and hand-solderable but 18 × 13 mm; not footprint-compatible |
| Charger + power path | TI **BQ25628E** (2 A, I²C, NVDC power path, NTC/JEITA, ADC, 1.5 µA battery-only, 0.15 µA ship mode) | C18221178 | 3,208 | 2.74 | Lowest quiescent current in its class, power path for dead-battery operation | BQ25628 (C6055599) |
| Fuel gauge | Analog Devices **MAX17048G+T10** | C2682616 | 26,611 | 2.18 | Accurate state of charge without calibration cycles; auto-hibernate | Charger ADC (voltage-based, misses ±5 %) |
| 3.0 V rail | TI **TPS7A0230PDBVR** (200 mA, 25 nA Iq) | C3747031 | 27,347 | 0.51 | See §3 | TPS7A0233 (3.3 V) |
| 5 V boost | TI **TPS61023DRLR** (≈ 1 A at 5 V from a 3.3 V cell) | C919459 | 3,839 | 0.27 | Tiny, enough for battery-mode LEDs and later modules | TPS61022 (stock 302) |
| 5 V source mux | TI **TPS2116DRLR** (2.5 A, priority mode, reverse blocking) | C3235557 | 64,213 | 0.46 | Seamless switch between USB and boost | TPS2121 |
| LED rail switch | Diodes **AP22653W6-7** (adjustable limit up to 2.1 A, reverse blocking when off) | C2158037 | 7,048 | 0.25 | Current limit + hard off = 0 µA LED leakage | — |
| USB-C receptacle | Kinghelm **KH-TYPE-C-16P** (USB 2.0) | C709357 | 147,898 | 0.08 | Cheap, common; mid-mount variant considered for height in layout | GCT USB4105 |
| USB ESD | ST **USBLC6-2SC6** | C5261088 | 70,038 | 0.04 | D+, D−, VBUS | — |
| Switch-board connector | Hirose **FH34SRJ-24S-0.5SH** (24-pin, 0.5 mm pitch, 1.0 mm tall, flip lock) | C324726 | 8,019 | 0.28 | Lowest height, robust lock | Molex 505110-2491 (C5902849) |
| 32.768 kHz crystal | JLCPCB basic part, chosen in schematic | — | — | — | Lowest-power BLE timing | Internal RC (higher sleep current) |

Switch-board parts, for the matching interface ([switch-board.md](../contracts/switch-board.md)):

| Function | Part | LCSC | Stock | ≈ USD |
|---|---|---|---|---|
| Column shift registers | TI SN74HC595PWR (TSSOP-16) | C273642 | 145,649 | 0.24 |
| Descriptor EEPROM | 24C32 class (4 KB; 2 Kbit is too small for a full-size map) | chosen in SWB design | — | — |
| RGB LED driver | Lumissil IS31FL3741A (39 × 9 matrix = 117 RGB LEDs) | C2940604 | 443 | 3.67 |

**Preview of later revisions** (checked now, so nothing blocks later):

| Function | Part | LCSC | Stock |
|---|---|---|---|
| 7-port USB 2.0 hub (rev B) | Microchip USB2517I-JZX | C478081 | 3,551 |
| Type-C port controller ×2 (rev B) | TI TUSB320 (LI variant) | C2836598 | 5,228 |
| USB 2.0 data mux ×2 (rev B) | TI TS3USB221A | C128396 | 99,897 |
| VBUS input mux (rev B) | TI TPS2121 (4.5 A) | C485916 | 35,597 |
| Knob motor driver | ADI/Trinamic TMC6300 | C5274455 | **59** (OPEN-19) |
| Knob angle sensor | MagnTek MT6701 | C3202694 | 3,901 |

## 5. MCU pin budget (rev A)

The BMD-340 exposes 48 GPIOs. Rev A uses about 20. The rest goes to the expansion header and test pads,
so module-bus experiments can start on rev A in P2/P3.

| Function | Pins | Notes |
|---|---|---|
| Matrix rows ROW0–7 | 8 | Wake-capable inputs (GPIO SENSE) |
| Column chain COL_DAT, COL_CLK, COL_LAT | 3 | SPIM; ≤ 10 MHz at 3.0 V |
| I²C (charger, fuel gauge, switch-board EEPROM + LED driver) | 2 | One bus at 400 kHz |
| LED_SDB, LED_5V_EN, BOOST_EN | 3 | |
| Charger INT, fuel-gauge ALRT | 2 | |
| Reserved switch-board lines RSV_MISO, RSV_INT | 2 | Hall-effect variant later |
| USB D+/D− | dedicated | VBUS sensing is built into the nRF52840 |
| SWD | dedicated | |
| 32.768 kHz crystal | 2 | P0.00/P0.01 |
| Expansion header | ~10 | UART, SPI, 4 GPIO, 2 analog inputs |

Pin assignment rules for the schematic:
- High-speed signals (SPIM, UART) must avoid pins the nRF52840 product spec marks "low frequency I/O only".
- Analog-capable pins (AIN0–7) are kept free for module-port sensing (rev C).
- The radio module's recommended layout is followed exactly.

## 6. Port-role logic (rev B preview, confirmed from datasheets)

Recorded now because it decides parts and connectors.

- **Without firmware, either port can be the computer port.** An unpowered TUSB320 presents Rd (5.1 kΩ) on
  both CC pins ("dead battery" mode). A computer therefore supplies VBUS on whichever port it is
  plugged into, and that VBUS powers the USB domain (hub, TUSB320s, mux).
- **The TUSB320s run only from VBUS, never from the battery.** Each draws ≈ 100 µA when unattached, twice
  the whole sleep budget.
- **Signals:**
  - `ID_x` low means port *x* is attached as a source. That makes it the accessory port.
  - `VBUS_x` present with `ID_x` high means port *x* is the upstream port.
  - If both ports have a source, port A has priority.
- **VBUS input:** a TPS2121 joins both ports. Driving its `OVx` pin above 1.06 V disables that input, so the
  accessory port's own output can never be taken for an input. PR1 gives port A priority.
- **Data:** two TS3USB221 muxes connect hub upstream and the accessory downstream port to A or B.
  Their select signal comes from the logic above, built from a few gates in the USB domain.
- **Accessory power:** an AP22653 per port, limited to ≈ 600 mA, enabled by `ID_x`, blocking reverse current when off.
- **Firmware is needed only for the accessory port.** After dead-battery mode, the TUSB320 needs a short I²C
  sequence before it presents Rp on both CC pins. Recovery and the computer connection never depend on firmware.
- **Back-powering:** TUSB320 GPIO and I²C pins are not fail-safe. Their I²C bus is therefore separated from the
  MCU's by a PCA9306-class translator that disconnects when the USB domain is off.

This satisfies CORE-022 for the computer connection and recovery. The D-11 fallback only matters for the accessory port.

## 7. Module ports (rev C preview)

- **Edge boards:** the module contacts sit on small **edge boards**, one per side, carrying contacts, magnets and ESD. They connect to the core board through thin FFC cables. That keeps the switch-board interface size-independent (D-31).
- **Per-side power:** an AP22653 per side with a **two-step current limit**: a switched ILIM resistor gives about 150 mA while the module identifies itself, and about 1.5 A once it is granted (MOD §4).
- **Signature detection:** a weak probe current on `VMOD`, measured by an analog input before power is enabled.
- **Power from modules:** the input path for power-source modules gets a footprint in rev C but stays unpopulated until MOD-009.
- **Module bus:** still open (OPEN-03). The nRF52840 has only two UARTs, at up to 1 Mbit/s. Four sides with up to 4 modules each, and 1 ms latency, are tight on polling. Options to evaluate on rev A's expansion header:
  - (a) CAN FD with an SPI controller: multi-master, no polling
  - (b) RS-485-style links with a small helper MCU that aggregates the four sides and does signature detection
  - (c) A faster shared half-duplex link

## 8. Power budget (estimate, rev A)

| State | Main contributors | Estimate | Target |
|---|---|---|---|
| Off (switch) | charger 1.5 µA, fuel gauge hibernate 3–4 µA, leakage | ≈ 6 µA | ≤ 10 µA |
| Sleep | charger 1.5 µA, fuel gauge ≈ 4 µA, LDO 0.03 µA, nRF52840 System ON + RTC ≈ 2 µA, radio keep-alive 10–30 µA, logic leakage ≈ 2 µA | ≈ 20–40 µA | ≤ 50 µA |
| Active typing, RGB off | nRF52840 radio events + 1 kHz scanning | ≈ 1–3 mA | ≤ 3 mA |

PPK2 measurements on rev A replace these estimates (CORE-008, SYS-03).

## 9. PCB

- **Stackup:** 4 layers, JLCPCB impedance-controlled stackup, **1.0 mm thick** (height budget; the core sits under the back of the switch board).
- **Placement:**
  - Back-edge centre of the case, USB-C on the back edge.
  - FFC toward the switch board.
  - Radio module's antenna at the board edge facing the RF path (OPEN-06), with the datasheet keep-out.
- **Bottom side:** SWD header and test points, reachable with the bottom case removed.
- **Size target:** about 45 × 30 mm, confirmed during layout (OPEN-11). It must leave room for the battery under a 40 % layout.

## 10. Rev A verification plan

| Check | Requirement | Method |
|---|---|---|
| Rails come up in order, no current spikes | CORE-004 | Bench supply + scope/PPK2 |
| Charging at 1 A, stops on NTC out of range | CORE-002, 005 | Current-limited bench test, heat gun on NTC |
| Runs from USB with no battery | CORE-004 | Remove battery |
| Fuel gauge within ±5 % over a discharge | CORE-006 | Compare with coulomb count from PPK2 |
| Off ≤ 10 µA, sleep ≤ 50 µA, typing ≤ 3 mA | CORE-007, 008 | PPK2 |
| USB enumeration, UF2 bootloader, SWD recovery | CORE-027 | Flash and recover |
| Switch board: descriptor read, 1 kHz scan, wake on key, LED rail 0 µA when off | CORE-050, SWB-005, FW-007 | Firmware tests + PPK2 |
| Bluetooth range inside the printed case | RF-040 | RSSI at 2 m |

## 11. Next steps

1. Schematic in KiCad, hierarchical sheets: power, MCU/radio, USB, switch-board connector, expansion and service.
2. ERC clean, then BOM with LCSC numbers.
3. Layout with the radio and charger reference layouts.
4. DRC clean, renders, 1:1 print for fit check.
5. Owner review, then order.
