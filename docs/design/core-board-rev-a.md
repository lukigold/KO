# Design note: Core board rev A

**Implements:** [core-board.md](../contracts/core-board.md) (P1 scope) · **Status:** layout done: placed and routed by script, DRC clean (0 violations, 0 unconnected, schematic parity clean), JLCPCB files generated; owner review next · **Date:** 2026-11-15, schematic 2026-11-18, layout 2026-11-20

Design notes explain *how* a contract is implemented. They never override a contract; if they disagree,
fix one of them in the same change.

## 1. Revision plan

The core board is built in three revisions. Each one adds one risky subsystem, so a fault never blocks everything.

| Rev | Phase | Adds | Contract scope |
|---|---|---|---|
| **A** | P1 | MCU + radio, battery charging and power path, fuel gauge, 3.0 V and 5 V rails, two USB-C ports as computer ports (A on the core, B on the switch board) through a VBUS mux and a 2:1 data switch, castellated switch-board contacts, LED rail, underglow port, SWD; power switch, NTC, underglow, haptic and SWD on solder pads for wires (D-43; the expansion header of the first layout was dropped, D-42) | CORE-001…009, 027, 030, 050, 060…066, 070 |
| B | P2 | 7-port USB hub, hub port, port-role logic, accessory port | CORE-020…026 |
| C | P3 | Four module ports via edge boards, module bus | CORE-010, CORE-040 |

Rev A is deliberately simple. Its job is a daily-usable wireless keyboard and proving the power budget (SYS-03).

## 2. Block diagram (rev A)

```
                 ┌──────────────────────── Core board rev A (strip 16 × 80 mm, D-43) ────────────────┐
 USB-C port A ───┤ ESD ─ VBUS_A ─┐                                                                 │
  (core, back)   │  Rd, CC→MCU   ├─ TPS2121 ─ VBUS ─┬─ BQ25628E charger ─ SYS ─┬─ TPS7A02 3.0 V ─► 3V0
 USB-C port B ═══╪═ VBUS_B ──────┘  (A first)  │    │   │ I²C, INT             └─ TPS61023 boost ─┐ │
  (switch board, │  CC1_B/CC2_B → Rd, MCU      │ ST │   └─ BAT ── LiPo 1S + NTC                 │ │
   back-left)    │                             ▼    └────────────── TPS2116 IN1 ◄── IN2 ◄───────┘ │
                 │ D± A ─┬─ TS3USB221A ─► BMD-340 (nRF52840) ◄─ I²C ─ MAX17048      └ V5 ─ AP22653 ─► LED_5V
 D± B (contacts) ╪═══════┘   (S = ST)          │  32.768 kHz XTAL                               │
                 │  switch pads ─► LDO EN       ├─ SWD pads, test points                        │
                 │  underglow pads ◄─ buffer ◄──┤  (P0.26)                                      │
                 │                              └─ haptic pads                                  │
                 └──────────┬────────────────────────────────────────────────────────────────────┘
                            ╘═ 33 castellated contacts ═► switch board: rows, column chain, I²C,
                                                          LED_SDB, LED_5V, 3V0, port B (VBUS, D±, CC)
```

## 3. Power tree

| Rail | Source | Range | Max load | Consumers |
|---|---|---|---|---|
| VBUS | TPS2121: USB-C port A (priority above ≈ 4.0 V) or port B | 5 V (cut-off above ≈ 5.9 V) | 3 A (Type-C advertisement; TPS2121 limit ≈ 3.5 A; charger input limit follows it) | charger, V5 mux |
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
| USB-C receptacle (port A, and port B on the switch board) | HX **TYPE-C 16P L10.0** (USB 2.0, 16-pin, 10 mm long body) | C41427495 | 16,435 (2026-11-22) | — | The mouth stands 3.9 mm proud of the board edge and reaches through the case wall (D-41); replaced the HRO TYPE-C-31-M-12 | — |
| VBUS input mux | TI **TPS2121RUXR** (4.5 A, priority, OVP, reverse blocking) | C485916 | 31,255 (2026-11-22) | — | Either port can power the board, port A first (CORE-066) | TPS2120 |
| USB 2.0 data switch | TI **TS3USB221ARSER** (2:1, 6 Ω, UQFN-10) | C128396 | 99,897 (2026-11-15; not reported 2026-11-22) | 0.27 | Follows the TPS2121 status pin, so the data comes from the port that powers the board | FSUSB42 class |
| USB ESD | ST **USBLC6-2SC6** | C5261088 | 70,038 | 0.04 | D+, D−, VBUS | — |
| Switch-board connection | 33 castellated contacts (bare-board copper, no part) | — | — | — | Soldered edge to edge by the owner (D-41); replaced the FH34SRJ-24S FFC connector | — |
| 32.768 kHz crystal | ECS **ECS-.327-12.5-34B** (CL 12.5 pF, ESR ≤ 70 kΩ) with 18 pF load capacitors | C387600 | 3,204 | — | Lowest-power BLE timing | Internal RC (higher sleep current) |

Switch-board parts, for the matching interface ([switch-board.md](../contracts/switch-board.md)):

| Function | Part | LCSC | Stock | ≈ USD |
|---|---|---|---|---|
| Column shift registers | TI SN74HC595PWR (TSSOP-16) | C273642 | 145,649 | 0.24 |
| Descriptor EEPROM | 24C32 class (4 KB; 2 Kbit is too small for a full-size map) | chosen in SWB design | — | — |
| RGB LED driver | Lumissil IS31FL3741A (39 × 9 matrix = 117 RGB LEDs) | C2940604 | 443 | 3.67 |
| Per-key RGB LED | EKINGLUX **E6CC1205RGBC3UDA** (reverse mount, 3.2 × 1.25 × 1.1 mm, **common anode**: pin 2 +, R/G/B on 1/3/4). Recommended footprint: four 0.75 × 0.7 mm pads, 3.6 mm across, light hole 2.0 mm wide (≈ 3.9 mm long, read from the drawing) | C2802677 | 9,234 (2026-11-22) | 0.03–0.05 |
| Per-key LED, second source | A-SP1513R6GHB1C-A01-2A (reverse mount, common anode, 3.2 × 1.3 mm per LCSC; datasheet still to check) | C5355463 | 14,550 | 0.07–0.13 |

The IS31FL3741A drives common-anode RGB LEDs: each SW line feeds the anodes, the CS lines sink the red, green and
blue cathodes through series resistors (datasheet RGB example at 5 V: 51 Ω red, 20 Ω green and blue; final values in
the switch-board design). The per-key LED sits 4.9 mm south of the switch centre, between the Choc (4.7 mm) and MX
(5.08 mm) light windows. Underglow candidate (not chosen): XINGLIGHT XL-1615RGBC-RF, top-mount common-anode RGB,
1.6 × 1.5 mm, C965840, mounted on the underside so it shines on the desk; datasheet still to check.

**Preview of later revisions** (checked now, so nothing blocks later):

| Function | Part | LCSC | Stock |
|---|---|---|---|
| 7-port USB 2.0 hub (rev B) | Microchip USB2517I-JZX | C478081 | 3,551 |
| Type-C port controller ×2 (rev B) | TI TUSB320 (LI variant) | C2836598 | 5,228 |
| USB 2.0 data mux (rev B adds a second one) | TI TS3USB221A | C128396 | see above |
| VBUS input mux | TI TPS2121 (4.5 A) | C485916 | fitted in rev A |
| Knob motor driver | ADI/Trinamic TMC6300 | C5274455 | **59** (OPEN-19) |
| Knob angle sensor | MagnTek MT6701 | C3202694 | 3,901 |

## 5. MCU pin assignment (rev A, final)

Taken from the schematic (hardware/core/tools/gen_schematic.py). "LF" = BMD-340 pins rated
"standard drive, low frequency I/O only"; they carry only rows, static outputs, interrupts and analog inputs.
Firmware board support must use exactly this map.

| Function | nRF52840 pin (BMD-340 pad) | Notes |
|---|---|---|
| ROW0–ROW3 | P1.01–P1.04 (57–60) LF | Inputs, internal pull-down, wake (SENSE) |
| ROW7, ROW6, ROW5, ROW4 | P0.13, P0.14, P0.15, P0.16 (31–34) | Inputs, internal pull-down, wake (SENSE). Left end of the front pad row: the front row runs left to right in the order of contacts 19–33, so the lines to the castellated edge do not cross (D-43) |
| RSV_MISO, COL_LAT, COL_DAT, COL_CLK | P0.17, P0.21, P0.20, P0.22 (35, 36, 38, 40) | COL_CLK/COL_DAT = SPIM SCK/MOSI, COL_LAT = latch GPIO, RSV_MISO reserved (Hall-effect boards); full-speed pins |
| RSV_INT | P0.24 (42) | Reserved for Hall-effect switch boards |
| I2C_SDA, I2C_SCL | P0.12, P0.19 (28, 37) | TWIM, 4.7 kΩ pull-ups to 3V0. SDA moved from P0.06 (D-35); SCL moved from P0.08 (pad 24, walled in by unused pads) to the outer front row on the strip |
| LED_SDB, LED_EN, BOOST_EN | P1.05, P1.06, P1.07 (48–50) LF | Static outputs; LED_EN and BOOST_EN have 100 kΩ pull-downs |
| LED_FAULT, CHG_INT | P0.28 (9), P1.08 (51) | Open-drain inputs, 10 kΩ pull-ups. Moved from P1.10/P1.11 for routing (D-35) |
| FG_ALRT | P1.00 (56) | Open-drain input, 10 kΩ pull-up; inner front row, towards the fuel gauge (D-43). SWO is not used |
| HAPTIC_EN | P0.23 (41) | Haptic pads J503 (CORE-064) |
| CC1_B, CC2_B | P0.29/AIN5, P0.30/AIN6 (10, 11) LF | SAADC: port B current advertisement, as CC1/CC2. Back pad row, then under the module to contacts 21/23 (D-43) |
| CC1, CC2 | P0.02/AIN0, P0.31/AIN7 (15, 12) LF | SAADC: USB-C current advertisement (default ≈ 0.25–0.61 V, 1.5 A ≈ 0.70–1.16 V, 3 A ≈ 1.31–2.04 V across 5.1 kΩ) |
| 32.768 kHz crystal | P0.00, P0.01 (13, 14) | LFXO |
| USB | USB_D+, USB_D− (68, 67); VBUS (66) | Direct to port A in rev A |
| SWD | SWDIO, SWCLK (44, 43); P0.18/RESET (39) | Solder pads J501 (3V0, SWDIO, SWCLK, RESET, GND) on the bottom, D-43; SWO not connected: probe-rs and defmt use RTT over SWD (D-35) |
| (unused) | P0.25, P0.27, P1.09 | Former expansion-header lines, unconnected since D-42 |
| Underglow strip data | P0.26 (EXP_IO2) | Through U501 (74AHCT1G125, 5 V) and R501 330 Ω to pad DAT of J504; WS2812 timing from the nRF52840 PWM or I2S peripheral (D-40) |
| Spare | P0.03/AIN1, P0.04/AIN2, P0.05/AIN3, P0.08 (19, 20, 21, 24); P1.12–P1.15 (61–64) | Unconnected on the 16 mm strip: the left pad columns sit at the castellated edge |
| Not connected | P0.06, P0.07, P0.09, P0.10, P0.11, P1.10, P1.11 | Free for later revisions |

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
- **Module bus:** still open (OPEN-03). The nRF52840 has only two UARTs, at up to 1 Mbit/s. Four sides with up to 4 modules each, and 1 ms latency, are tight on polling. Options to evaluate on an nRF52840 development kit (rev A has no expansion header, D-42):
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

The first rev A layout (50 × 32 mm board under the keys, 24-pin FFC to the switch board, D-34/D-35) was
routed and DRC clean on 2026-11-22. The owner then moved the core board beside the keys (D-41, 22 × 80 mm,
DRC clean on 2026-11-23) and asked for it narrower and simpler (D-43). This section describes the 16 × 80 mm
strip that replaced both.

- **Outline:** **16 × 80 mm strip**, 4 layers, JLCPCB impedance-controlled stackup, **1.0 mm** thick. It sits
  right of the key area, its back end level with the switch board's back edge.
- **Edges:**
  - Left edge: **33 castellated contacts** (0.8 mm plated half holes on the edge, 2.0 mm pitch, copper
    1.4 × 2.4 mm reaching 1.8 mm into the board on both sides) in two groups: contacts 1–17 at y = 1…33 mm,
    contacts 18–33 at y = 48…78 mm. Between them the radio module spans the full width. Pinout and positions:
    switch-board contract.
  - Back edge: USB-C port A, a long-body receptacle (HX TYPE-C 16P L10.0) whose mouth stands 3.9 mm proud of
    the board edge, so it reaches through an aluminium or printed back wall.
  - Right edge (case wall): BMD-340 with its antenna 0.2 mm beyond the edge (the module may overhang; it leaves
    room for three tracks beside its left pad column). Nothing else reaches the wall: the power switch is off the
    board (pads J103).
  - Front edge: the battery connector (JST PH, opening to the front), so the cable drops under the switch
    board where the battery sits (MECH-003).
- **Antenna keep-out:** no copper on any layer within 4.4 mm of the antenna edge, i.e. a 4.2 mm strip along the
  board's right edge, beside the module and about 4.1 mm beyond it on both sides (y = 32.0…51.0 mm; datasheet
  section 6.1). The module footprint carries the same keep-out over its antenna section.
- **Layers:**
  - In1 is a solid GND plane, the reference for every signal.
  - Top, bottom and In2 get GND pours after routing.
  - Power nets: the current paths are drawn in code at 0.5–1.0 mm (1.0 mm on the VBUS and SYS trunks);
    branches the router draws are 0.3 mm. 3V0: 0.25 mm. USB: 0.2 mm (full speed, no impedance control
    needed at these lengths). Low-current branches may fall back to 0.15 mm (listed under Result).
  - Everything else: 0.15 mm tracks, 0.15 mm clearance, 0.5/0.25 mm vias (power vias 0.6/0.3, the TPS2121
    output and the SYS trunk 0.8/0.4). All within JLCPCB's standard 4-layer rules.
- **Placement** (`hardware/core/tools/gen_pcb.py`, generated from the schematic netlist, footprints linked to
  their symbols), from the back:
  - y 0–14 mm: USB-C port A at the right; the TPS2121 left of it next to contacts 1–3 (port B's VBUS) with its
    three dividers below; the USB and CC ESD arrays right below the receptacle's pads; the TS3USB221A data
    switch next to contacts 5/6; port A's CC Rd resistors below the CC array.
  - y 15–32 mm: boost, 5 V mux and LED rail switch, the block of the first layout turned by 90° with its hand
    routes (mux towards the USB-C, boost towards the charger's SYS, LED switch output towards the right);
    the underglow buffer beside it at the right wall.
  - y 32–36 mm: 32.768 kHz crystal next to module pads 13/14, VCC decoupling (100 nF 3 mm from VCC pad 17,
    10 µF), LED_5V capacitor.
  - y 36–47 mm: BMD-340 across the full width, antenna 0.2 mm beyond the right edge. Its left pad column sits
    1.85 mm inside the castellated edge, so it keeps only its fixed-function pads (VCC, VBUS, USB D±); the rows
    moved to the front pad row, in the order of contacts 19–33, and port B's CC lines to analog pins on the back
    row (§5).
  - y 47–62 mm: C203 (VBUS 4.7 µF) 5 mm from the module's VBUS pad; port B's CC Rd resistors at contacts 21/23;
    the charger, moved as one block from the first layout with its hand-routed switching loop.
  - y 62–69 mm: 3.0 V LDO, fuel gauge, I²C pull-ups.
  - y 70–80 mm: battery connector.
  - Bottom side, copper only: solder pads for wires, each labelled on the silkscreen: J501 SWD and J503 haptic
    driver as 3 × 2 grids under the module, next to the module pins they serve (eight lines fewer through the
    busy front zone); J102 NTC and J103 power switch under the battery connector; J504 underglow under its
    buffer. Test points on VBUS, VBUS_A, VBAT, VBOOST, CHG_QON and the module's USB D±. Nets with a
    wire pad are probed there; port B's VBUS and CC lines at their castellated contacts. No part is assembled
    on the bottom.
- **Contact order:** unchanged from D-41; only the positions moved (D-43). Port B power and data, 3V0, I²C
  and LED_5V (contacts 1–17) sit behind the module next to the USB and 5 V parts; the matrix, its control lines
  and port B's CC lines (18–33) in front of it.
- **Routing** (`hardware/core/tools/route_pcb.py`, D-35), in this order:
  1. **Drawn in code and locked:** the charger's switching node, PMID and bootstrap loop (moved with its
     parts) and the boost, 5 V mux and LED switch copper (turned with its parts). VBUS_B: contacts 1–3 joined
     on top into the TPS2121's IN2 and its capacitor. VBUS_A: both receptacle VBUS pads; the right one reaches
     the left one on the bottom layer under the ESD arrays, where the data and CC lines cross above it on In2;
     the left one runs on top round the dividers to IN1 (0.5 mm). VBUS: the TPS2121's two OUT pads joined
     under the package, one 0.8/0.4 via, then a 1 mm bottom trunk along the castellated edge to the 5 V mux and
     on under the module to the charger (0.8 mm for 9 mm past the dividers' GND vias). USB port A: both D−
     pads joined on top and straight into the ESD array, both D+ pads through vias and across on In2; CC1
     straight down, CC2 across on In2 to the CC array. SYS: from the charger's SYS capacitors on a 1 mm bottom
     trunk under the module to the boost input (0.8/0.4 vias), good for the ≈ 1.7 A the boost draws on battery
     with the LEDs on. VBAT: 0.8 mm on top from the charger's BAT capacitor past the fuel gauge to the battery
     connector. LED_5V: from the LED switch on a 1 mm In2 track to contacts 14–16 (the castellated pads are on
     every layer) and on a 0.6 mm bottom track to the underglow pads.
  2. **GND fan-out:** every SMD GND pad gets its own short stub and via to the In1 plane where there is room;
     the few boxed-in pads connect through the top pour.
  3. **Grid maze router** (`hardware/tools/maze.py`) for every remaining connection: negotiated congestion
     (crossings priced out over iterations), then legalisation with exact clearances and targeted rip-up.
     Results are stored in `hardware/core/route/ko-core-maze.json`. A **repair mode** (`route_pcb.py --repair`)
     then closes what is left: each open connection may rip up the stored routes in its way, all-or-nothing,
     and the pass is kept only if the board gets better. Routes it does not move are written back unchanged,
     each segment at its stored width. A **polish mode** (`--polish`) removes router leftovers KiCad reports as
     dangling, together with the rest of each dead branch up to the next junction, via or pad.
  4. **Clean-up:** vias that join only one layer are removed. Where two tracks of one net leave the same point
     less than 25° apart, a short bridge 0.5 mm from the fork closes the thin V between them, which KiCad
     would otherwise report as a copper sliver.
  5. **Stitching vias** on a 2.5 mm grid where all layers are free, then all pours are filled.
- **Underglow strip port (D-40, D-43):** solder pads J504 on the bottom: LED (LED_5V on the 0.6 mm bottom
  track), DAT, GND. The data comes from P0.26 (EXP_IO2). U501 74AHCT1G125 runs from LED_5V, so its TTL inputs
  take the 3.0 V signal and it is unpowered whenever the rail is off; C501 100 nF; R501 330 Ω at the strip
  input. The strip shares the LED rail's 1.5 A limit with the switch board. Inside the case, so no ESD array.
- **Power switch (CORE-007, D-43):** pads J103 (SYS, EN) for an off-board SPST switch that drives the 3.0 V
  LDO's enable; R107 (1 MΩ) holds it off while the switch is open. Bridge the pads with solder for a board
  that is always on. The switch can sit anywhere in the case (MECH-040, OPEN-07).
- **Result:** RESULT-PENDING

### Ordering at JLCPCB

`hardware/core/tools/fab_outputs.py` writes `hardware/core/fab/`. It refuses to run unless DRC is clean.

| File | Use |
|---|---|
| `ko-core-rev-a-gerbers.zip` | PCB order: 4 layers, 1.0 mm FR-4, 16 × 80 mm, 1 oz outer copper, standard rules (0.15/0.15 mm, 0.25 mm drill), **"Castellated Holes: Yes"** (left edge) |
| `ko-core-rev-a-bom.csv`, `ko-core-rev-a-cpl.csv` | Assembly (PCBA), top side only: BOM-LINES BOM lines, CPL-PARTS placed parts. The DNP fallback NTC (RT101), the wire pads, test points and the castellated edge J401 (bare-board copper) are left out |
| `ko-core-rev-a-fit-1to1.pdf` | Print at 100 % (no "fit to page"): page 1 top, page 2 bottom (mirrored, as seen from below). Check the strip against the case: USB-C mouth through the back wall, antenna end at the right wall, battery connector at the front, castellated edge against the switch board's edge; plan the wires to the bottom pads (power switch, NTC, underglow, haptic) |
| `ko-core-rev-a-top.png`, `-bottom.png`, `-iso.png` | Renders |

Before ordering:
- **Select "Castellated Holes"** in JLCPCB's PCB options. Without it the half holes on the left edge are not
  plated through the cut and the board cannot be soldered to the switch board.
- **Check part rotation in JLCPCB's placement preview.** JLCPCB's library sometimes defines a part's zero rotation
  differently from KiCad. Pin 1 marks on the BMD-340, the BQ25628E, the TPS2121, the TS3USB221A, the other ICs
  and the connectors must match the silkscreen dots; JLCPCB corrects any offset on request.
- **Nothing is assembled on the bottom side** (D-43): single-sided assembly. For the first flash (a new BMD-340
  has no bootloader) solder five thin wires from the SWD pads (3V0, DIO, CLK, RST, GND) to the debug probe, or
  hold pogo pins on them.
- **Wires the owner solders after assembly:** power switch (pads SYS/EN; or a solder bridge for always on), the
  pack NTC (NTC/GND), the underglow strip (LED/DAT/GND), later a haptic driver (V5/3V0/GND/SDA/SCL/EN).
- **TS3USB221A (C128396):** stock was not listed by the parts search; check it in the BOM step and pick the
  second source named in §4 if it is out.
- **Joining the boards:** the owner solders the 33 castellated contacts to the switch board's matching edge row
  (both boards flat on the bench, edges butted, back edges level). Solder all three VBUS_B and LED_5V contacts.

### Custom footprints

`hardware/core/tools/gen_footprints.py` writes `hardware/core/lib/ko.pretty`. Each footprint was loaded through
KiCad's API and drawn with its pad numbers to compare against the source drawing.

| Footprint | Source | How the geometry was taken |
|---|---|---|
| u-blox_BMD-340 | Datasheet R13, fig. 12 (land pads), fig. 2 (pin numbers), sec. 6.1 (keep-out) | Rendered fig. 12 at 600 dpi, calibrated on the 15.00 × 10.20 mm outline (126.3 px/mm), detected all 0.5 mm pad squares. They sit on a 1.10 mm column grid with half-pitch staggered rows. Numbering matched to fig. 2 row by row |
| Texas_RYK_WQFN-HR-18 | BQ25628E datasheet p. 74–75 (RYK0018A) | Measured every pad edge on TI's 20× land pattern and checked against its dimension labels (±0.01 mm). Four L-shaped corner pads as custom pads |
| Hirose_FH34SRJ-24S | Hirose catalogue p. 3–4 | First rev A layout only (FFC to the switch board, replaced by the castellated edge, D-41) |
| USB_C_Receptacle_HX_TYPE-C-16P_L10.0 | HX TYPE-C 16P L10.0 drawing (LCSC C41427495) | 16 SMD pads at the drawing's pitch, two NPTH pegs Ø0.65 mm at ±2.89 mm, four shell slots (0.6 × 1.7 and 0.6 × 1.4 mm); board edge line 5.0 mm from the pegs, so the mouth stands 3.9 mm proud of the edge |
| Texas_RUX_VQFN-HR-12_2x2.5mm | TPS2121 datasheet, RUX0012A land pattern | Eight 0.2 × 0.6 mm signal pads at 0.5 mm pitch, four 1.05 × 0.4 mm power pads (IN1, IN2, two OUT) |
| Castellated_1x33_P2.00mm_Edge_1-17_18-33 | Switch-board contract (D-41, D-43), JLCPCB castellated-hole rules | 0.8 mm plated holes centred on the board edge, 2.0 mm pitch, copper 1.4 × 2.4 mm reaching 1.8 mm into the board (the outer 0.6 mm is milled away); contacts 1–17 and 18–33 in two groups 15 mm apart |
| WirePads_Switch, _NTC, _Underglow; WireGrid_SWD, _Haptic | D-43 | Rows of 1.3 × 1.8 mm SMD pads at 2.0 mm pitch, or 3 × 2 grids of 1.2 × 1.4 mm pads at 2.0 × 2.8 mm, for soldering wires, each labelled on the silkscreen; copper only, excluded from BOM and position files |

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
- **Verification:** `hardware/core/tools/check_schematic.py` runs ERC and fails on any error. It exports KiCad's netlist, compares it pin by pin with the intended nets, and writes the PDF and BOM. Current result: 0 errors, 67 nets, 0 mismatches, no waived warnings.
- **Part numbers:** `hardware/core/bom/parts.csv` holds the LCSC numbers, resolved by `hardware/tools/jlc_lookup.py` with a lookup date. Re-check stock before ordering; 30.1 kΩ and 133 kΩ showed unknown stock.

**Sheets:** Battery and charger · Power rails · MCU and radio · USB · Switch board connector · Service and expansion.

**Design decisions made while drawing:**

| Item | Value | Why |
|---|---|---|
| Charger input limit (ILIM) | 5.1 kΩ → 490 mA | USB-compliant before firmware runs. Firmware reads CC1/CC2, then disables ILIM (EN_EXTILIM = 0) and sets IINDPM to 1.5 A or 3 A |
| CC sensing | CC1/CC2 to AIN0/AIN1, protected by a second USBLC6-2SC6 | Detects the source's current advertisement without a Type-C controller |
| Battery temperature | RT1 5.23 kΩ, RT2 30.1 kΩ, 10 kΩ NTC (103AT class) on pads J102, taped to the cell; board NTC RT101 unpopulated as fallback | TI datasheet values for 0–60 °C |
| Charger passives | VBUS 1 µF, PMID 10 µF + 100 nF, BTST 47 nF, REGN 4.7 µF, L 1 µH (WPN252012E1R0MT), SYS 2 × 10 µF, BAT 10 µF | TI application circuit |
| Boost output | 1 MΩ / 133 kΩ → 5.07 V; COUT 2 × 22 µF; L 1 µH | VREF 0.595 V; true output disconnect when off |
| 5 V mux | TPS2116 priority mode, MODE = VBUS, PR1 divider 100 kΩ / 33 kΩ → switches to boost below 4.03 V | Basic-part values |
| LED rail limit | AP22653 with 15 kΩ → 1.735 A | Datasheet table |
| 3.0 V LDO | 1 µF in, 2.2 µF out | ≥ 0.5 µF effective output required |
| Power switch | Off-board SPST switch on pads J103 (SYS ↔ PWR_EN), 1 MΩ pull-down (D-43) | Off = LDO disabled; charger and fuel gauge stay powered. A solder bridge on the pads keeps the board on |
| nRF52840 | VCC = VCCH = 3V0 (normal mode), 10 µF + 100 nF on VCC, 4.7 µF on VBUS | BMD-340 datasheet; total VBUS capacitance 6.7 µF (< 10 µF USB limit) |

**Owner review checklist:**
1. **Battery connector polarity:** J101 pin 1 = +. JST PH cells from different vendors swap polarity; check your cell before plugging in.
2. **Power switch:** wired to pads J103, so it can sit anywhere in the case (OPEN-07).
3. **Haptic driver:** solder pads J503 (V5, 3V0, GND, SDA, SCL, EN), nothing to fit (D-43). (The expansion header was dropped, D-42.)

**Layout:** done (§9). The custom footprints are in `lib/ko.pretty`; the TPS2116 uses KiCad's own SOT-583-8 footprint, which is drawn from TI's DRL package (same package as the TPS2116) with the usual numbering: pins 1–4 down the left side, 5–8 up the right.

## 12. Next steps

1. ~~Custom footprints, then PCB layout~~ done.
2. ~~DRC clean, 3D render, 1:1 print for fit check~~ done (`hardware/core/fab/`).
3. Owner review: fit check with the 1:1 print, renders, the review checklist in §11.
4. Order rev A at JLCPCB (see "Ordering at JLCPCB" in §9).
