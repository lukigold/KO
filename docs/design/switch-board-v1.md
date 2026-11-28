# Switch board v1: design note

**Implements:** [switch-board.md](../contracts/switch-board.md) (P1), [generator.md](../contracts/generator.md) (GEN-001, 002, 004, 011–015) ·
**Status:** architecture and parts chosen; generator in progress · **Date:** 2026-11-28

## 1. What is generated

`generator/ko_gen/` turns a KO layout file v3 (written by the layout builder `generator/configurator/index.html`)
into a complete KiCad project for the switch board: schematic, PCB with every part placed and routed, BOM/CPL,
Gerbers and the descriptor EEPROM image. Nothing is drawn by hand (SWB-009). Every size, style and standard the
builder offers goes through the same code (SWB-018); the owner changes the layout in the builder and regenerates.

First board: `generator/examples/ko-65-iso-ch.json` (65 % ISO-CH, 69 keys, Choc v1 + v2 hot-swap, per-key RGB,
underglow), D-57.

## 2. Circuit (per board, independent of size)

| Block | Parts | Notes |
|---|---|---|
| Key | Kailh Choc hot-swap socket CPG1350 (Choc v1 + v2, SWB-017), 1N4148W SOD-123 (C81598, basic) | COL2ROW: column → switch → diode anode → cathode → row. One diode per key (SWB-006) |
| Columns | 74HC595 SOIC-16 (C431479), daisy-chained (Q7S → SER), 100 nF each | One register per 8 columns: 65 % = 2, full size = 3. Powered from `VLOGIC` (3.0 V; the 74HC595 runs from 2 V). `COL_CLK` gets 33 Ω series resistance at the first register (slow edges, contract) |
| Rows | none | ≤ 8 rows straight to the core contacts; pull-downs are the MCU's |
| Per-key light | EKINGLUX E6CC1205RGBC3UDA (C2802677), reverse mount, common anode, at (0, +4.9 mm) of every key (D-39) | Anode on an SW line, R/G/B cathodes on three CS lines |
| Underglow | Same LED, mounted on the underside facing down | On spare driver channels (SWB-019) |
| LED driver | Lumissil IS31FL3741A QFN-60 7 × 7 (C2940604) | 9 SW × 39 CS = 13 × 9 = 117 RGB LEDs per driver. 65 % with underglow: 69 + underglow ≤ 117. Two drivers above 117 LEDs (ADDR = GND → 0x30, ADDR = SCL → 0x31). AVCC/PVCC from `LED_5V`, 1 µF + 100 nF at each of pins 14, 15, 25; RISET 10 kΩ (38 mA peak, firmware sets GCC); thermal pad to GND with vias. SW traces wider than CS (datasheet layout notes). The datasheet's optional 20/51 Ω per-colour resistors are left out; brightness and heat are limited by GCC |
| I²C isolation | TI PCA9306 VSSOP-8 (C33196) | The driver is unpowered while `LED_5V` is off; its SDA/SCL must not load the shared bus (charger, fuel gauge, EEPROM). VREF1 = `VLOGIC`, VREF2 = `LED_5V` through 200 kΩ with EN tied to VREF2 (TI's application circuit): the switch opens when `LED_5V` is off. 10 kΩ pull-ups to `LED_5V` on the driver side. `LED_5V` off ⇒ the LED subsystem draws 0 µA (contract) |
| Descriptor | BL24C02F SOT-23-5 (C7436803) at 0x50, `VLOGIC`, 100 nF | No address pins (fixed 0x50); the generator writes the image (GEN-002); programmed by the core over I²C at first start |
| `LED_SDB` | to the driver's SDB, 100 kΩ pull-down | Driver in hardware shutdown unless the core raises it |
| Port B | HX TYPE-C 16P L10.0 (C41427495, same footprint as the core's port A), 2 × USBLC6-2SC6 (D±, CC) | Back-left corner, mouth through the back wall (SWB-015). VBUS_B for 3 A to contacts 1–3 |
| Core contacts | 33 castellated half holes on the right edge, 2.0 mm pitch, at the core's positions (SWB-016) | The core's back end level with the board's back edge |

I²C addresses on the shared bus: EEPROM 0x50, LED drivers 0x30/0x31, core: MAX17048 0x36, BQ25628E 0x6A. No clash.

## 3. Board

- **Stackup:** 2 layers, 1.6 mm (SWB-013). All parts on the **bottom** side (single-sided assembly; switches and
  plate on the top). Bottom-side heights stay under the battery foam (MECH-003; battery position: OPEN-11).
- **Rules:** 0.15 mm track and clearance, 0.3/0.6 mm vias, matching the core (JLCPCB standard 2-layer rules allow
  0.127 mm). Power: `LED_5V`, SW lines and `VBUS_B` 0.5 mm or wider.
- **Key area:** 19.05 mm pitch (SWB-002), key centres from the layout file; 1.0 mm margin to the left, front and
  right edges of the key area, more at the right for the castellations.
- **Port B and the back edge:** the receptacle reaches 7 mm into the board from the back edge and is 10 mm wide;
  it does not fit between the top-row sockets. v1 leaves an 8 mm band behind the top row (OPEN-24).
- **Control parts** (driver, registers, EEPROM, PCA9306): in the free space under the space bar and the wide
  modifier keys, chosen by the generator from the layout.

## 4. Open items

- **OPEN-24:** port B needs about 8 mm behind the top row (or a tab at the back-left corner); owner to confirm the
  back band or choose a tab.
- **OPEN-12:** LED position checked against Choc v1/v2 light windows when the key footprint is drawn.
- Kailh CPG1350 socket: no LCSC stock found by the API; check JLCPCB's catalogue (often a consigned part) or
  solder the sockets by hand (SWB-010 allows both).
- Stabilizers (SWB-003): Choc and MX-style stabilizer holes on 2u and wider keys, if they fit beside the sockets.
- Mounting / soft-mount points (SWB-012): with the plate design (P1 mechanical).
