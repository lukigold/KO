# Contract: Switch board (and the core ↔ switch board interface)

**ID prefix:** `SWB` · **Status:** draft v0.1 · **First phase:** P1 · **License:** CERN-OHL-S-2.0
**Owns:** the core ↔ switch board interface.

## Purpose

The large board that carries switches, hot-swap sockets, diodes and per-key RGB. It is mostly passive
and is **generated** from a layout file ([generator.md](generator.md)), never hand-routed.
There is one switch board per layout and variant. All of them plug into the same core board through one
**size-independent** interface, and describe themselves to the firmware through an EEPROM.

## Variants

| Variant | Status | Notes |
|---|---|---|
| MX + Choc hot-swap (combined footprint), per-key RGB | **v1** | Same approach as Zack Freedman's MiRage Mk2. v1 is built with Choc switches in the slim case |
| Soldered multi-footprint | Later (generator, GEN-015) | Holes for every selected switch type in one footprint, e.g. Choc v1 + v2 + MX + Gateron LP + Alps; switches are soldered |
| Hall-effect | Later | Own board, same interface (uses the reserved lines) |
| Gateron low-profile | Later | Own board, same interface |

## Interface: core ↔ switch board

**Connector:** Hirose FH34SRJ-24S-0.5SH (24 pins, 0.5 mm pitch, 1.0 mm tall, flip lock) on the core,
a matching FFC to the switch board. This pinout is fixed from core rev A on and never changes.

| Pin | Signal | Direction | Description |
|---|---|---|---|
| 1 | `GND` | — | Ground (also LED return) |
| 2, 3, 4 | `LED_5V` | core → SWB | Switched LED supply, ≤ 1.5 A total (≤ 0.5 A per contact), off by default |
| 5 | `GND` | — | Ground (LED return) |
| 6 | `VLOGIC` | core → SWB | Logic supply, 3.0 V ±5 % (core rail `3V0`), ≤ 50 mA. Switch-board logic must work from 2.7 V to 3.6 V |
| 7 | `I2C_SCL` | core → SWB | LED driver(s) + descriptor EEPROM, 400 kHz (1 MHz allowed). Pull-ups (4.7 kΩ) on the core |
| 8 | `I2C_SDA` | bidir | |
| 9 | `LED_SDB` | core → SWB | LED driver hardware shutdown, active low |
| 10 | `RSV_INT` | SWB → core | Reserved for variants with their own scanning controller (Hall-effect) |
| 11 | `GND` | — | Ground, shields the column clock |
| 12 | `COL_CLK` | core → SWB | Column shift-register clock |
| 13 | `GND` | — | Ground |
| 14 | `COL_DAT` | core → SWB | Column shift-register data |
| 15 | `COL_LAT` | core → SWB | Column shift-register latch |
| 16 | `RSV_MISO` | SWB → core | Reserved (Hall-effect variant data) |
| 17–24 | `ROW0`–`ROW7` | SWB → core | Matrix rows, read directly by MCU GPIOs (wake-capable, internal pull-downs) |
| MP | `GND` | — | Connector mounting tabs |

**Matrix scheme:** columns are driven through a chain of shift registers on the switch board, so the
number of columns (and therefore keyboard size) never changes the connector. Rows (≤ 8) go directly to
the MCU. Diodes run column → row (COL2ROW).

**Guarantees: core → switch board**
- `VLOGIC` within 3.0 V ±5 %. `LED_5V` stays off unless firmware enables lighting.
- Shift-register clock ≤ 10 MHz. Full matrix scan ≥ 1 kHz while keys are active.
- In sleep, the core latches **all** columns active so any key press raises a row and wakes the MCU.

**Guarantees: switch board → core**
- Idle current on `VLOGIC` ≤ 1 mA. With `LED_5V` off, the LED subsystem draws 0 µA.
- A descriptor EEPROM answers at I2C address `0x50` and holds: format version, variant, layout ID,
  board revision, row/column count, matrix-to-key map, LED map, stabilizer positions, default keymap ID.
- Row count ≤ 8. Column count and LED count as declared in the descriptor.

**Preconditions**
- The core reads the descriptor before scanning or enabling LEDs. An unknown descriptor format
  version means: keys are scanned with a safe default, LEDs stay off, and the app reports the problem.

**Invariants**
- A switch board never sources power into the core.
- A new switch board of an existing variant needs **no firmware change**; the descriptor is enough.

## Requirements

| ID | Requirement | Phase | Verify |
|---|---|---|---|
| SWB-001 | Each key position shall accept both a Kailh MX hot-swap socket and a Kailh Choc (v1/v2) hot-swap socket. | P1 | T |
| SWB-002 | Key pitch shall be 19.05 mm. | P1 | I |
| SWB-003 | Keys 2u and wider shall have stabilizer footprints for both MX-style and Choc stabilizers. | P1 | I |
| SWB-004 | Each key shall have one reverse-mount RGB LED placed for the switches' light windows; if one position cannot serve both families, Choc takes priority (OPEN-12). | P1 | T |
| SWB-005 | LEDs shall be driven by I2C matrix LED driver(s) on the switch board, with hardware shutdown and a hard power cut. | P1 | M |
| SWB-006 | Every key shall have its own diode (full n-key rollover, no ghosting). | P1 | T |
| SWB-007 | The matrix shall use ≤ 8 directly-read rows and shift-register-driven columns, so the interface is independent of keyboard size. | P1 | T |
| SWB-008 | A descriptor EEPROM shall carry the data listed above; the generator writes it; the firmware configures itself from it. | P1 | T |
| SWB-009 | The board shall be generated entirely by the generator pipeline from a layout file, with no manual routing. | P1 | I |
| SWB-010 | ERC/DRC shall be clean, the board orderable at JLCPCB as generated, and sockets assemblable by JLCPCB or by hand. | P1 | I |
| SWB-011 | v1 shall include a 75 % ISO board (the owner's Swiss build) and a 75 % ANSI board. | P1 | I |
| SWB-012 | Mounting and soft-mount points shall support the Choc plate height (slim case) and the MX plate height (taller case). | P1 | I |
| SWB-013 | PCB thickness shall be 1.6 mm unless the height stack-up requires 1.2 mm (decided with OPEN-11). | P1 | I |
| SWB-014 | Hall-effect and Gateron low-profile switch boards shall use the same connector and descriptor, declaring their variant. | Later | A |
