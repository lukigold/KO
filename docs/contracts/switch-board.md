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
| Hall-effect | Later | Own board, same interface (uses the reserved lines) |
| Gateron low-profile | Later | Own board, same interface |

## Interface: core ↔ switch board

**Connector:** one 24-pin, 0.5 mm pitch FFC/FPC (exact part: P1). Pin order is fixed at P1 rev A and
never changes afterwards.

| Signal | Count | Direction | Description |
|---|---|---|---|
| `3V3` | 1 | core → SWB | Logic supply, ≤ 50 mA |
| `GND` | 4 | — | Ground, spread across the connector (also LED return) |
| `LED_5V` | 3 | core → SWB | Switched LED supply, ≤ 1.5 A total (≤ 0.5 A per contact), off by default |
| `I2C_SDA`, `I2C_SCL` | 2 | bidir / core → SWB | LED driver(s) + descriptor EEPROM, 400 kHz (1 MHz allowed). Pull-ups on the core |
| `LED_SDB` | 1 | core → SWB | LED driver hardware shutdown, active low |
| `COL_DAT`, `COL_CLK`, `COL_LAT` | 3 | core → SWB | Column shift-register chain |
| `ROW0`–`ROW7` | 8 | SWB → core | Matrix rows, read directly by MCU GPIOs (wake-capable) |
| `RSV_MISO`, `RSV_INT` | 1 + 1 | SWB → core | Reserved for variants with their own scanning controller (Hall-effect) |

**Matrix scheme:** columns are driven through a chain of shift registers on the switch board, so the
number of columns (and therefore keyboard size) never changes the connector. Rows (≤ 8) go directly to
the MCU. Diodes run column → row (COL2ROW).

**Guarantees: core → switch board**
- `3V3` within ±5 %. `LED_5V` stays off unless firmware enables lighting.
- Shift-register clock ≤ 10 MHz. Full matrix scan ≥ 1 kHz while keys are active.
- In sleep, the core latches **all** columns active so any key press raises a row and wakes the MCU.

**Guarantees: switch board → core**
- Idle current on `3V3` ≤ 1 mA. With `LED_5V` off, the LED subsystem draws 0 µA.
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
