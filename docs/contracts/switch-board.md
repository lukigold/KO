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
| Choc v1/v2 hot-swap, per-key RGB, optional underglow | **v1** | D-57: MX and Choc hot-swap with per-key light do not fit one key (D-38); v1 is Choc-only, in the slim case |
| Soldered multi-footprint | Later (generator, GEN-015) | Holes for every selected switch type in one footprint, e.g. Choc v1 + v2 + MX + Gateron LP + Alps; switches are soldered |
| Hall-effect | Later | Own board, same interface (uses the reserved lines) |
| Gateron low-profile | Later | Own board, same interface |

## Interface: core ↔ switch board

**Connection (v2, D-41):** the core board is a strip beside the key area at the right. Its left edge carries
**33 castellated contacts** (plated half holes, 2.0 mm pitch, contact 1 at the back) in two groups (D-43):
contacts 1–17 at 1, 3, … 33 mm from the core's back end, contacts 18–33 at 48, 50, … 78 mm. Between the
groups the radio module spans the full width of the strip. They are soldered to a matching castellated
contact row on the switch board's right edge, the core's back end level with the switch board's back edge.
This pinout replaces the 24-pin FFC of the first rev A layout and is fixed from then on.

| Contact | Signal | Direction | Description |
|---|---|---|---|
| 1, 2, 3 | `VBUS_B` | SWB → core | VBUS of USB-C port B (on the switch board), ≤ 3 A, passed straight from the receptacle |
| 4 | `GND` | — | Ground |
| 5 | `USB_B_DN` | bidir | Port B D− (after the switch board's ESD array) |
| 6 | `USB_B_DP` | bidir | Port B D+ |
| 7 | `GND` | — | Ground, shields the USB pair |
| 8 | `VLOGIC` | core → SWB | Logic supply, 3.0 V ±5 % (core rail `3V0`), ≤ 50 mA. Switch-board logic must work from 2.7 V to 3.6 V |
| 9 | `I2C_SCL` | core → SWB | LED driver(s) + descriptor EEPROM, 400 kHz (1 MHz allowed). Pull-ups (4.7 kΩ) on the core |
| 10 | `I2C_SDA` | bidir | |
| 11, 12, 13 | `GND` | — | Ground (also the LED return) |
| 14, 15, 16 | `LED_5V` | core → SWB | Switched LED supply, ≤ 1.5 A total (≤ 0.5 A per contact), off by default |
| 17 | `GND` | — | Ground (LED return) |
| 18 | `LED_SDB` | core → SWB | LED driver hardware shutdown, active low |
| 19, 20 | `ROW7`, `ROW6` | SWB → core | Matrix rows, read directly by MCU GPIOs (wake-capable, internal pull-downs) |
| 21 | `CC1_B` | SWB → core | Port B CC1; Rd 5.1 kΩ and sensing on the core |
| 22 | `ROW5` | SWB → core | Matrix row |
| 23 | `CC2_B` | SWB → core | Port B CC2; Rd 5.1 kΩ and sensing on the core |
| 24 | `ROW4` | SWB → core | Matrix row |
| 25 | `RSV_MISO` | SWB → core | Reserved (Hall-effect variant data) |
| 26 | `COL_LAT` | core → SWB | Column shift-register latch |
| 27 | `COL_DAT` | core → SWB | Column shift-register data |
| 28 | `COL_CLK` | core → SWB | Column shift-register clock (≤ 10 MHz; slow edges are enough, the switch board may add a series resistor) |
| 29 | `RSV_INT` | SWB → core | Reserved for variants with their own scanning controller (Hall-effect) |
| 30–33 | `ROW0`, `ROW1`, `ROW2`, `ROW3` | SWB → core | Matrix rows |

The order follows the core strip's layout: port B power and data at the back next to the core's VBUS mux and
data switch, 3V0, I²C and `LED_5V` beside the 5 V rail parts, and the matrix, its control lines and port B's
CC lines in front of the radio module.

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

**Preconditions (switch board, for port B)**
- USB-C port B sits at the back-left corner of the switch board: a long-body 16-pin receptacle (as on the core,
  mouth through the case wall), ESD arrays on D± and CC next to it, and VBUS_B traces for 3 A.
- USB_B_DP/DN run as a differential pair (90 Ω where the stackup allows, Full Speed only).

**Invariants**
- A switch board never sources power into the core; the only power it passes in is VBUS_B, straight from its USB-C port.
- A new switch board of an existing variant needs **no firmware change**; the descriptor is enough.

## Requirements

| ID | Requirement | Phase | Verify |
|---|---|---|---|
| ~~SWB-001~~ | ~~Each key position shall accept both a Kailh MX hot-swap socket and a Kailh Choc (v1/v2) hot-swap socket.~~ Superseded by SWB-017 (D-57). | P1 | T |
| SWB-002 | Key pitch shall be 19.05 mm. | P1 | I |
| SWB-003 | Keys 2u and wider shall have stabilizer footprints for both MX-style and Choc stabilizers. | P1 | I |
| SWB-004 | Each key shall have one reverse-mount RGB LED placed for the switches' light windows; if one position cannot serve both families, Choc takes priority (OPEN-12). | P1 | T |
| SWB-005 | LEDs shall be driven by I2C matrix LED driver(s) on the switch board, with hardware shutdown and a hard power cut. | P1 | M |
| SWB-006 | Every key shall have its own diode (full n-key rollover, no ghosting). | P1 | T |
| SWB-007 | The matrix shall use ≤ 8 directly-read rows and shift-register-driven columns, so the interface is independent of keyboard size. | P1 | T |
| SWB-008 | A descriptor EEPROM shall carry the data listed above; the generator writes it; the firmware configures itself from it. | P1 | T |
| SWB-009 | The board shall be generated entirely by the generator pipeline from a layout file, with no manual routing. | P1 | I |
| SWB-010 | ERC/DRC shall be clean, the board orderable at JLCPCB as generated, and sockets assemblable by JLCPCB or by hand. | P1 | I |
| ~~SWB-011~~ | ~~v1 shall include a 75 % ISO board (the owner's Swiss build) and a 75 % ANSI board.~~ Superseded by SWB-018 (D-57). | P1 | I |
| SWB-012 | Mounting and soft-mount points shall support the Choc plate height (slim case) and the MX plate height (taller case). | P1 | I |
| SWB-013 | PCB thickness shall be 1.6 mm unless the height stack-up requires 1.2 mm (decided with OPEN-11). | P1 | I |
| SWB-014 | Hall-effect and Gateron low-profile switch boards shall use the same connector and descriptor, declaring their variant. | Later | A |
| SWB-015 | The board shall carry USB-C port B at its back-left corner (long-body 16-pin receptacle, ESD on D± and CC) and pass VBUS_B, D±, CC1/CC2 to the core contacts. | P1 | I/T |
| SWB-016 | The board's right edge shall carry the 33 castellated contacts of the core interface (2.0 mm pitch, contact 1 at the back, two groups at the positions given under "Interface"), aligned so the core's back end is level with the board's back edge. | P1 | I |
| SWB-017 | Each key position shall accept a Kailh Choc v1/v2 hot-swap socket (CPG1350); the key footprint takes both switch generations (D-38). | P1 | T |
| SWB-018 | The generator shall build a switch board for every size, style and standard the layout builder offers, from the builder's KO layout file; v1 starts with the owner's 65 % ISO-CH board. | P1 | T |
| SWB-019 | With underglow selected in the layout file, the board shall carry underglow RGB LEDs on its underside on spare LED-driver channels (D-40 A, GEN-014). | P1 | T |
