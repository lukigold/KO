# Decisions and open items

Append new decisions at the end and never delete one; mark replaced decisions as superseded.
All decisions below were made on 2026-11-15 in the requirements interview with the owner.

## Decisions

| ID | Decision | Why |
|---|---|---|
| D-01 | Personal project, 1–3 units, published as open source; prototyping budget about CHF 2,000. | Owner's goal. Keeps scope realistic and decisions reversible. |
| D-02 | Two-board architecture: fixed core board + generated switch board, joined by a size-independent connector with a descriptor EEPROM. | Makes switch type, size and layout a board swap instead of a redesign, and is the basis for the generator. |
| D-03 | v1 MCU: nRF52840 in a pre-certified module with integrated antenna. | Mature Rust/RMK support, USB + BLE + proprietary radio in one chip, no RF design or certification risk. The nRF54L15 has no USB. |
| D-04 | 1,000 Hz in v1 (USB and 2.4 GHz). 8 kHz later via a new core board (nRF54LM20, High-Speed USB). | 8 kHz saves ~0.4 ms, needs High-Speed USB and costs battery. Must not compromise modularity. |
| D-05 | One switch board with combined MX + Kailh Choc hot-swap sockets (MiRage Mk2 precedent). v1 is built with Choc switches in the slim case. | Owner wants any switch. Plate height differs per family, so MX needs a taller top case. |
| D-06 | Slim build: ~20 mm including keycaps, ~2° built-in tilt. | Owner's height target; only reachable with low-profile switches. |
| D-07 | Flat LiPo pouch (~3 mm) under the switch board, sized to fit the smallest layout (40 %). | Same core and battery for every size; every extra mm of battery adds 1 mm of height. 18650 cells rejected (18 mm). |
| D-08 | Charging over USB-C at 5 V up to 3 A, no USB Power Delivery. | Simple and reliable; fast charging not needed. |
| D-09 | Per-key RGB through an I2C matrix LED driver with a hard power cut; on with USB power, off on battery by default. | One hour of RGB costs about a week of basic typing; chained LEDs waste power even when dark. |
| D-10 | No status LEDs. The per-key LEDs act as temporary indicators; behaviour configurable. | Owner's clean design goal. |
| D-11 | Two identical USB-C ports on the back edge, roles resolved in hardware; 7-port USB 2.0 HS hub; accessory port ≤ 500 mA, powered only from upstream VBUS. Fallback: port A defaults to upstream without firmware. | Owner wants full symmetry; the fallback keeps recovery guaranteed if hardware role detection proves unreliable. |
| D-12 | The hub works wired only. | Radio throughput (~150 kB/s) is far below a USB stick's (~30 MB/s) and would delay keystrokes. A Wi-Fi storage module remains possible later. |
| D-13 | Connections: USB-C any time; encrypted 1 kHz 2.4 GHz link with a USB-C dongle (+ bought USB-A adapter, no storage slot); Bluetooth for Mac/iOS. Automatic selection rules R1–R4; per-connection keymaps. | Gaming latency needs 2.4 GHz; Bluetooth covers Mac and iOS; owner wants "magical" automatic switching. |
| D-14 | Module interface: magnets only; 6 contacts (GND, VMOD, BUS_A, BUS_B, USB_DP, USB_DN); handedness rule (springs on right/back faces, pads on left/front faces); signature detection before power; sequential power-up for chain order; 5 V bidirectional rail; per-side current limit; one power source at a time; USB lane per side. | Meets: fits left and right, chainable, minimal, hot-pluggable, safe against paper clips, open, future screens. |
| D-15 | Module layout: chainable side modules left and right (1×6 macro column, numpad); one module on the back (knobs); one on the front (wrist rest/power, later). Modules are moved, never rotated, and aligned from the front edge. | Owner's request; translation-only keeps contacts and magnets simple. |
| D-16 | Licenses: GPL-3.0-or-later (software), CERN-OHL-S-2.0 (hardware), CC-BY-SA-4.0 (docs), CC-BY-4.0 for the module spec and MIT OR Apache-2.0 for its reference code. | Improvements stay open; anyone can build modules. |
| D-17 | Knobs: 3 upright FOC knobs, 15–20 mm flat caps, smallest solid-shaft gimbal motors that feel great (chosen by test), identical hardware, feel in software. No press, no screens, no touch sensor; wake on movement. | Owner's requirements; small knob radius means small motors suffice. |
| D-18 | Haptics in v1 come from the knobs only. Space and a connector are reserved for a future body actuator. | Base first; owner wants body haptics later. |
| D-19 | Firmware: Rust + Embassy on RMK. Vial for keymaps in P1–P2; own protocol and app from P5; Vial features kept in the backlog. | Rust's compiler gives AI agents a tight feedback loop; Vial gets the hardware tested sooner. |
| D-20 | Desktop app: Tauri 2 for macOS and Windows, running in the background. | Needed for per-app profiles, music knob and notices; a browser configurator can't do these and Safari can't talk to keyboards. |
| D-21 | Updates: through the app over USB, with UF2 drag-and-drop fallback; modules updated automatically by the keyboard; wireless updates later. | Safe and simple first, convenience later. |
| D-22 | PCB tool: KiCad, created and edited by scripts; the AI designs both boards, the owner reviews and tests. Fusion Electronics rejected. | Text files and `kicad-cli` make boards scriptable and checkable; KiCad is the open-hardware standard; the generator needs a headless tool. |
| D-23 | Case CAD: code-CAD skeleton (build123d) + owner refinement in Fusion, functional features locked. | Generator needs code; the owner is strong in Fusion. |
| D-24 | Industrial design: dark creamy warm silver anodized aluminium; no transparent window; tight module seams; soft, muted, deep sound; bought metallic-look keycaps; flat round knob caps with a line marker. | Owner's taste (Apple, Teenage Engineering, Nothing, Nomad [E]). |
| D-25 | Generator: local program first (Python), website later; outputs one complete folder per keyboard. | Prove the pipeline on the owner's own board first. |
| D-26 | Hardware-in-the-loop testing: the owner runs Claude Code on their own computer with boards attached (`probe-rs`, `defmt`). | Agents can then flash and read logs directly. |
| D-27 | Project name **KO** (Keyboard Organization); repository `KO`; docs in English. | Owner's choice. |
| D-28 | The knob module is a **new design with smaller knobs**; the owner's earlier knob project is not its base and is not kept in this repository. Motors: micro gimbal outrunners (1105 / 1806 / 2204 class), the smallest that passes KNOB-001. Caps 12–20 mm. KO defines its own profile format. Music-follow is a KO profile type, specified fresh. | Owner's instruction (2026-11-15). |
| D-29 | The core board is built in three revisions: rev A (P1) MCU, power, one USB-C port, switch-board connector; rev B (P2) hub, second identical port, role logic; rev C (P3) module ports. | One risky subsystem per revision; rev A gives a usable keyboard fast. |
| D-30 | Core rev A parts: BMD-340 (nRF52840 module), BQ25628E charger, MAX17048 fuel gauge, TPS7A02 **3.0 V** system rail, TPS61023 boost + TPS2116 mux for the 5 V rail, AP22653 LED rail switch, FH34SRJ 24-pin FFC, 1.0 mm 4-layer PCB. The power switch drives the LDO/boost enables. Details: [design/core-board-rev-a.md](design/core-board-rev-a.md). | Lowest quiescent currents in stock at JLCPCB; 3.0 V LDO gives nA quiescent current and a quiet radio supply. |
| D-31 | Module contacts sit on small edge boards (one per side) connected to the core board by FFC cables. | Keeps the switch-board interface size-independent; the back side's contacts can sit on the core board itself. |
| D-32 | The charger's hardware input limit defaults to 490 mA (ILIM = 5.1 kΩ). Firmware reads the USB-C current advertisement on CC1/CC2 (MCU analog inputs) and then raises the limit to 1.5 A or 3 A. | USB-compliant even before firmware runs; no Type-C controller needed in rev A. |
| D-33 | Schematics are generated from Python design data (`hardware/core/tools/gen_schematic.py`, library `hardware/tools/kisch`). The KiCad schematic files are outputs; every change runs `check_schematic.py` (ERC + pin-by-pin netlist comparison). | Agents can edit and verify text; deterministic output diffs cleanly; prevents GUI drift. |
| D-34 | Core board rev A outline 50 × 32 mm; custom footprints for BMD-340, BQ25628E (RYK) and FH34SRJ-24S generated from the manufacturers' drawings (`gen_footprints.py`); PCB placement generated from the schematic netlist (`gen_pcb.py`). | 45 × 30 mm reached ~60 % component coverage, too dense to route; generated footprints and placement stay reproducible and reviewable. |
| D-35 | Core rev A routing (2026-11-19). `hardware/core/tools/route_pcb.py` routes the board: power paths, the BMD-340 → FFC buses and the expansion-header escapes are drawn in code and locked; every SMD GND pad gets its own stub and via to the In1 plane; Freerouting 2.5.0 (GPL-3.0, run headless and offline) routes the remaining nets in two phases (supplies, then signals) and its session files in `hardware/core/route/` are the source of truth for those tracks; stitching vias and zone fill follow. Layout-driven pin changes (firmware board map must follow): ROW7, ROW6, ROW5, ROW4 on P1.12–P1.15; RSV_MISO, COL_LAT, COL_DAT, COL_CLK on P0.13–P0.16 (RSV_INT stays P0.17); EXP_IO4 P1.08 → P1.09; SWO (P1.00) not connected; expansion header J502 pin order re-assigned and EXP_AIN0 dropped (pin 12 = GND). Placement: L101 and C116 rotated 180°, J502 under the module, J503 and the test-point rows moved. Power net class 0.6 mm (router allowed 0.5 mm in tight spots), new Supply class 0.3 mm for 3V0. | The autorouter alone left long wandering power tracks and could not untangle the module escape; with the module pins matched to the FFC order both buses route without a crossing. SWO is unused (RTT over SWD); two analog-capable spares remain on test pads. Affects firmware board support (FW-019) and the expansion-header pinout only; the FFC interface (switch-board contract) is unchanged. |

### Rejected alternatives (do not reopen without new information)

| Rejected | Why |
|---|---|
| Hall-effect switches in v1 | Several mA per sensor (hundreds of mA total) conflicts with battery life; module magnets interfere. Later as its own switch board. |
| MX switches in the slim case | Physically ~30 mm tall with keycaps. |
| 8 kHz polling in v1 | Needs High-Speed USB on the MCU and dongle, large battery cost, ~0.4 ms gain. |
| Wireless USB-stick access | Bandwidth far too low; would delay keystrokes. |
| Qi charging through the aluminium case, Logitech Powerplay-style charging | Metal blocks Qi; Powerplay is proprietary. A front power module is the modular alternative. |
| Status LEDs, transparent bottom window | Owner's design decision. |
| Knob press (mechanical or force-sensed), screens in knobs, touch sensors | Owner's decision; simpler and smaller. |
| Browser-only configurator | No background features; Safari lacks WebHID. |
| EasyEDA / Fusion Electronics | Not scriptable enough; not the open-hardware standard. |

## Open items

| ID | Question | Decide in | Notes |
|---|---|---|---|
| ~~OPEN-01~~ | ~~Exact pre-certified nRF52840 module~~ | — | **Resolved:** BMD-340-A-R (D-30); fallback Ebyte E73-2G4M08S1CX |
| OPEN-02 | USB-C role-controller circuit details for rev B | P2 | Rev A power parts resolved (D-30); rev B concept and parts in design/core-board-rev-a.md §6 |
| OPEN-03 | Module bus: CAN FD (SPI controller), RS-485-style links with a helper MCU, or a faster shared link | P3 | The nRF52840 has two UARTs at ≤ 1 Mbit/s; 4 sides × 4 modules at 1 ms latency is tight. Prototype on rev A's expansion header. Criteria in module-interface.md §6 |
| OPEN-04 | Contact parts, final pin order, magnet sizing and pattern, signature resistor value | P3 | Test pull force and alignment with printed prototypes |
| OPEN-05 | Knob motor: 1105 vs 1806 vs 2204 class, specific model, and cap size | P0 → P4 | Comparison on a new 5 V test jig (KNOB-001); felt strength and cogging decide |
| OPEN-06 | RF path through the aluminium case without a bottom window | P1 (printed), P6 (CNC) | Must pass RF-011 in the final case |
| OPEN-07 | Power switch position | P6 | Discreet but reachable without lifting the keyboard |
| OPEN-08 | Keycap product: Choc-compatible, metallic look, RGB compatibility, legends | P1 | Metal caps block light and add weight |
| OPEN-09 | Number and layout of programmable keys on the knob module | P4 | |
| OPEN-10 | macOS playback state for the music knob | P5 | No stable public now-playing API; per-player integrations (Apple Music, Spotify) or another method |
| OPEN-11 | Exact stack-up heights and battery capacity | P1 | Core outline set to 50 × 32 mm (D-34); battery must fit beside it under a 40 % layout |
| OPEN-12 | One LED position serving both MX and Choc light windows | P1 | Choc takes priority if impossible |
| OPEN-13 | RMK integration: shift-register column scanning; Vial and KO protocol coexisting | P1–P2 | |
| OPEN-14 | 2.4 GHz pairing flow details | P2 | Must satisfy RF-013 |
| OPEN-15 | Module current budgets per side, on battery and on USB | P3 | Depends on knob module measurements |
| OPEN-16 | Knob module MCU | P4 | STM32G4 class; needs motor timers and Embassy support |
| OPEN-17 | Side-module heights for keyboards with fewer than 6 rows | P7 | Generator |
| ~~OPEN-18~~ | ~~The owner's tuned knob parameters from their existing test project~~ | — | Closed: not needed (D-28) |
| OPEN-19 | TMC6300 availability (JLCPCB showed 59 in stock on 2026-11-15) | P4 | Order early from Digi-Key/Mouser, or qualify an alternative 5 V three-phase driver |
