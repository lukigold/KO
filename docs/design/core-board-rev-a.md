# Design note: Core board rev A

**Implements:** [core-board.md](../contracts/core-board.md) (P1 scope) · **Status:** schematic done (generated, ERC and netlist verified), layout next · **Date:** 2026-11-15, schematic 2026-11-18

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
| USB-C receptacle | HRO **TYPE-C-31-M-12** (USB 2.0, 16-pin) | C165948 | 511,683 | — | Most common at JLCPCB and has a KiCad footprint (changed from KH-TYPE-C-16P in the schematic phase) | GCT USB4105 |
| USB ESD | ST **USBLC6-2SC6** | C5261088 | 70,038 | 0.04 | D+, D−, VBUS | — |
| Switch-board connector | Hirose **FH34SRJ-24S-0.5SH** (24-pin, 0.5 mm pitch, 1.0 mm tall, flip lock) | C324726 | 8,019 | 0.28 | Lowest height, robust lock | Molex 505110-2491 (C5902849) |
| 32.768 kHz crystal | ECS **ECS-.327-12.5-34B** (CL 12.5 pF, ESR ≤ 70 kΩ) with 18 pF load capacitors | C387600 | 3,204 | — | Lowest-power BLE timing | Internal RC (higher sleep current) |

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

## 5. MCU pin assignment (rev A, final)

Taken from the schematic (hardware/core/tools/gen_schematic.py). "LF" = BMD-340 pins rated
"standard drive, low frequency I/O only"; they carry only rows, static outputs, interrupts and analog inputs.
Firmware board support must use exactly this map.

| Function | nRF52840 pin (BMD-340 pad) | Notes |
|---|---|---|
| ROW0–ROW3 | P1.01–P1.04 (57–60) LF | Inputs, internal pull-down, wake (SENSE) |
| ROW4–ROW7 | P1.12–P1.15 (61–64) LF | Inputs, internal pull-down, wake (SENSE) |
| COL_CLK, COL_DAT, COL_LAT | P0.13, P0.14, P0.15 (31–33) | SPIM SCK/MOSI + latch GPIO |
| RSV_MISO, RSV_INT | P0.16, P0.17 (34, 35) | Reserved for Hall-effect switch boards |
| I2C_SDA, I2C_SCL | P0.06, P0.08 (22, 24) | TWIM, 4.7 kΩ pull-ups to 3V0 |
| LED_SDB, LED_EN, BOOST_EN | P1.05, P1.06, P1.07 (48–50) LF | Static outputs; LED_EN and BOOST_EN have 100 kΩ pull-downs |
| LED_FAULT, CHG_INT | P1.10, P1.11 (53, 54) LF | Open-drain inputs, 10 kΩ pull-ups |
| FG_ALRT | P0.30 (11) LF | Open-drain input, 10 kΩ pull-up |
| HAPTIC_EN | P0.31 (12) LF | Reserved haptic connector |
| CC1, CC2 | P0.02/AIN0, P0.03/AIN1 (15, 19) LF | SAADC: USB-C current advertisement (default ≈ 0.25–0.61 V, 1.5 A ≈ 0.70–1.16 V, 3 A ≈ 1.31–2.04 V across 5.1 kΩ) |
| 32.768 kHz crystal | P0.00, P0.01 (13, 14) | LFXO |
| USB | USB_D+, USB_D− (68, 67); VBUS (66) | Direct to port A in rev A |
| SWD | SWDIO, SWCLK (44, 43); P0.18/RESET (39); P1.00 SWO (56) | 2×5 1.27 mm header |
| Expansion header | P0.19 TX, P0.20 RX, P0.22 SCK, P0.23 MOSI, P0.24 MISO, P0.21 CS, P0.25/P0.26/P0.27/P1.08 IO1–4, P0.28/P0.29 AIN (LF) | J502, unpopulated by default |
| Spare (test pads) | P0.04/AIN2, P0.05/AIN3 (20, 21) | Full-speed, analog-capable; for rev C prototyping |
| Not connected | P0.07, P0.09, P0.10, P0.11, P0.12, P1.09 | Free for later revisions |

Rev C needs four analog inputs for module signature detection; the map is reassigned in that revision
(board support is per core-board revision, FW-019).

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

- **Outline:** **50 × 32 mm**, 4 layers, JLCPCB impedance-controlled stackup, **1.0 mm** thick. At 45 × 30 mm the parts covered about 60 % of the board, too dense to route well. 50 × 32 mm still fits easily beside the battery under a 40 % layout.
- **Edges:**
  - Top edge = back of the keyboard: USB-C, opening outwards.
  - Right edge: BMD-340, antenna flush with the edge.
  - Bottom edge = towards the switch board: FFC connector, the cable leaves the edge.
  - Left edge: power slide switch and battery connector.
- **Antenna keep-out:**
  - No copper on any layer in a 4.4 mm strip along the right edge, over the module and 5 mm beyond it (19 mm from the top); datasheet section 6.1.
  - The module footprint carries the same keep-out over its antenna section.
- **Layers:**
  - In1 is a solid GND plane, the reference for every signal.
  - Top, bottom and In2 get GND pours after routing.
  - Power nets use 0.5 mm tracks (net class Power), USB uses a 0.2/0.2 mm pair (net class USB).
  - Everything else: 0.15 mm tracks, 0.15 mm clearance, 0.5/0.25 mm vias. All within JLCPCB's standard 4-layer rules.
- **Placement** (`hardware/core/tools/gen_pcb.py`, generated from the schematic netlist, footprints linked to their symbols):
  - Charger top-left beside the USB-C VBUS pins: PMID capacitor directly above the PMID/GND pads, inductor to the right, SYS/BAT capacitors below.
  - USB ESD and CC resistors right below the receptacle.
  - Power rails in the middle band: LDO, boost with inductor and output capacitors, 5 V mux, LED switch.
  - Fuel gauge beside the battery connector.
  - 32.768 kHz crystal directly above BMD-340 pads 13/14; VCC/VBUS decoupling on the module's left side.
  - Bottom side: SWD header, test points, unpopulated expansion and haptic connectors.
- **Status:** placement done; DRC shows no overlaps, clearance or short violations. Routing is not started.

### Custom footprints

`hardware/core/tools/gen_footprints.py` writes `hardware/core/lib/ko.pretty`. Each footprint was loaded through
KiCad's API and drawn with its pad numbers to compare against the source drawing.

| Footprint | Source | How the geometry was taken |
|---|---|---|
| u-blox_BMD-340 | Datasheet R13, fig. 12 (land pads), fig. 2 (pin numbers), sec. 6.1 (keep-out) | Rendered fig. 12 at 600 dpi, calibrated on the 15.00 × 10.20 mm outline (126.3 px/mm), detected all 0.5 mm pad squares. They sit on a 1.10 mm column grid with half-pitch staggered rows. Numbering matched to fig. 2 row by row |
| Texas_RYK_WQFN-HR-18 | BQ25628E datasheet p. 74–75 (RYK0018A) | Measured every pad edge on TI's 20× land pattern and checked against its dimension labels (±0.01 mm). Four L-shaped corner pads as custom pads |
| Hirose_FH34SRJ-24S | Hirose catalogue p. 3–4 | Signal pads 0.3 × 0.8 mm at 0.5 mm pitch, tabs 0.4 × 0.8 mm at ±6.75 mm, 3.3 mm tab offset; contact 1 at +x; cable enters from the tab side |

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

## 11. Schematic (rev A)

**How it is made:**
- **Source of truth:** `hardware/core/tools/gen_schematic.py` describes every part (value, footprint, LCSC number) and every net. It writes the six KiCad sheets plus the project symbol library `lib/ko.kicad_sym`. The KiCad files are outputs; edit the Python, not the GUI.
- **Verification:** `hardware/core/tools/check_schematic.py` runs ERC and fails on any error. It exports KiCad's netlist, compares it pin by pin with the intended nets, and writes the PDF and BOM. Current result: 0 errors, 69 nets, 0 mismatches. The only warnings are the three custom footprints still to be drawn (waived until layout).
- **Part numbers:** `hardware/core/bom/parts.csv` holds the LCSC numbers, resolved by `hardware/tools/jlc_lookup.py` with a lookup date. Re-check stock before ordering; 30.1 kΩ and 133 kΩ showed unknown stock.

**Sheets:** Battery and charger · Power rails · MCU and radio · USB · Switch board connector · Service and expansion.

**Design decisions made while drawing:**

| Item | Value | Why |
|---|---|---|
| Charger input limit (ILIM) | 5.1 kΩ → 490 mA | USB-compliant before firmware runs. Firmware reads CC1/CC2, then disables ILIM (EN_EXTILIM = 0) and sets IINDPM to 1.5 A or 3 A |
| CC sensing | CC1/CC2 to AIN0/AIN1, protected by a second USBLC6-2SC6 | Detects the source's current advertisement without a Type-C controller |
| Battery temperature | RT1 5.23 kΩ, RT2 30.1 kΩ, 10 kΩ NTC (103AT class) on J102 taped to the cell; board NTC RT101 unpopulated as fallback | TI datasheet values for 0–60 °C |
| Charger passives | VBUS 1 µF, PMID 10 µF + 100 nF, BTST 47 nF, REGN 4.7 µF, L 1 µH (WPN252012E1R0MT), SYS 2 × 10 µF, BAT 10 µF | TI application circuit |
| Boost output | 1 MΩ / 133 kΩ → 5.07 V; COUT 2 × 22 µF; L 1 µH | VREF 0.595 V; true output disconnect when off |
| 5 V mux | TPS2116 priority mode, MODE = VBUS, PR1 divider 100 kΩ / 33 kΩ → switches to boost below 4.03 V | Basic-part values |
| LED rail limit | AP22653 with 15 kΩ → 1.735 A | Datasheet table |
| 3.0 V LDO | 1 µF in, 2.2 µF out | ≥ 0.5 µF effective output required |
| Power switch | PCM12 slide switch: SYS ↔ PWR_EN ↔ GND, 1 MΩ pull-down | Off = LDO disabled; charger and fuel gauge stay powered |
| nRF52840 | VCC = VCCH = 3V0 (normal mode), 10 µF + 100 nF on VCC, 4.7 µF on VBUS | BMD-340 datasheet; total VBUS capacitance 6.7 µF (< 10 µF USB limit) |

**Owner review checklist:**
1. **Battery connector polarity:** J101 pin 1 = +. JST PH cells from different vendors swap polarity; check your cell before plugging in.
2. **Power switch position:** it sits on the schematic only. Its physical position is OPEN-07.
3. **Expansion and haptic headers:** both are left unpopulated. Tell me if you want either fitted on the prototypes.

**Still to do in layout:** custom footprints for the BMD-340 (68 pads, datasheet land pattern),
the BQ25628E (RYK WQFN-HR-18) and the FH34SRJ-24S connector; check the SOT-583 footprint pin order against
the TPS2116 datasheet.

## 12. Next steps

1. Custom footprints, then PCB layout: charger and boost loops first, radio keep-out, USB pair.
2. DRC clean, 3D render, 1:1 print for fit check.
3. Owner review, then order rev A at JLCPCB.
