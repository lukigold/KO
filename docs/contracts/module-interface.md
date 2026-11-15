# Contract: Module interface (open spec)

**ID prefix:** `MOD` · **Status:** draft v0.1 · **First phase:** P3
**License of this document:** CC-BY-4.0. Reference code (`ko-module-bus`) is MIT OR Apache-2.0.
Anyone may build KO modules, including closed commercial ones.
**Owns:** module mechanics, contacts, detection, power, module bus, chaining, USB lane, module descriptor.

## 1. Topology

| Side | Name | Modules |
|---|---|---|
| Left of keyboard | `L` | Chain of up to 4 side modules |
| Right of keyboard | `R` | Chain of up to 4 side modules |
| Back edge | `B` | One module (the knob module in v1) |
| Front edge | `F` | One module (wrist rest / power module, later) |

Side modules fit on either `L` or `R` and in any chain position. **Modules are moved, never rotated.**

## 2. Mechanics

- **Holding:** magnets only. No mechanical lock. Detaching may need two hands.
- **Handedness rule.** This is what makes every side module work on both sides and in any order:
  - surfaces facing **right (+X)** or **back (+Y)** carry **spring contacts**
  - surfaces facing **left (−X)** or **front (−Y)** carry **flat pads**
  - This applies to the keyboard and to every module.
- **Magnet patterns:** pattern **A** on −X/−Y surfaces, pattern **B** on +X/+Y surfaces.
  A attracts B and repels A, so a wrong pairing pushes apart instead of touching (pattern and sizing: OPEN-04).
- **Contact block:** 6 contacts in a row along the edge, inside an insulating insert (the case is aluminium),
  flush and minimal, iPad-style. Magnets are hidden.
- **Reference point:** contact and magnet positions are measured from the keyboard's **front edge**
  and from the desk plane, so modules line up on every keyboard size.
- **Gap between housings:** as small as manufacturing allows ([mechanical.md](mechanical.md)).

## 3. Contacts

Draft pin order, to be confirmed in P3 (OPEN-04):

| # | Name | Function |
|---|---|---|
| 1 | `GND` | Ground. Makes contact first (longer spring pin) |
| 2 | `VMOD` | 5 V module power, bidirectional, **unpowered until detection succeeds** |
| 3 | `BUS_A` | Module bus, differential + |
| 4 | `BUS_B` | Module bus, differential − |
| 5 | `USB_DP` | USB 2.0 lane D+ |
| 6 | `USB_DN` | USB 2.0 lane D− |

## 4. Attach sequence (the core contract)

1. **Idle side:** `VMOD` off, bus transceiver disabled, nothing driven.
2. **Detect:** the upstream side applies a current-limited probe on `VMOD` and measures the module's
   **signature resistance**, like Power-over-Ethernet does. A short, an open circuit or a wrong value
   (e.g. a paper clip on the magnets) means: stay off, retry with back-off. Value and window: OPEN-04.
3. **Power up:** `VMOD` on with soft start, limited to an initial budget of 100 mA.
4. **Identify:** within 200 ms the module sends its **descriptor** over the bus (§7).
5. **Grant:** the keyboard assigns an address and a power budget. Only now may the module draw more.
6. **Chain:** a module with a downstream side keeps that side unpowered until it has been granted.
   Then it runs steps 1–5 for the next module. Because power-up is strictly sequential,
   the keyboard learns the **physical order** of the chain.
7. **Detach:** a missed bus heartbeat (≤ 50 ms) or a current drop removes the module; that side returns to step 1.

## 5. Power

- `VMOD` nominal 5.0 V (4.75–5.25 V) at the keyboard's contact.
- **Per-side current limit** by an electronic fuse. Budgets depend on the source (USB or battery) and
  are granted per module from its descriptor (exact numbers: OPEN-15).
- **Battery mode:** the keyboard tells modules whether it runs on battery. Motor and screen modules
  shall then run in a reduced mode; full power only with USB or a power-source module.
- **Power-source modules** (battery wrist rest, dock) declare source capability. The keyboard then turns
  off its own `VMOD` output and accepts power on that side. **Only one source is active per keyboard
  at a time**; the keyboard's own USB input has priority. Both sides need reverse-current blocking.
- **Fault isolation:** each module switches its own downstream `VMOD`, so a fault in module *k*
  cannot take down modules before *k*.

## 6. Module bus

- **Physical layer:** two-wire differential, half-duplex, multi-drop along a chain. RS-485-style vs CAN FD: OPEN-03.
  Selection criteria: hot-plug robustness, idle power, MCU availability in Rust/Embassy, cost.
- **Rate:** ≥ 1 Mbit/s.
- **Latency:** a key event from any module, up to 4 deep in a chain, shall reach the keyboard within
  **1 ms**. Macro keys must feel as fast as main keys.
- **Frames:** address, type, payload, CRC-16, protocol version. Host-scheduled with event slots.
- **Firmware updates:** every module has a bootloader that can be updated over the bus. The keyboard
  updates modules automatically when its firmware bundle contains a newer image.

## 7. Descriptor (self-description)

Each module reports: descriptor format version, vendor ID, product ID, serial, firmware version,
connector set (upstream only, or upstream + downstream), capabilities (keys with layout, knobs,
sliders, LEDs, display, power source), power classes (battery-mode current, full-mode current), and
whether it uses the USB lane.

An unknown capability or product is listed by the app but never crashes the firmware.

## 8. USB lane

- Each side has its own downstream port on the keyboard's hub.
- The first module on a side is designed for USB 2.0 **High-Speed**. Further down a chain only
  **Full-Speed** (12 Mbit/s) is guaranteed, and there is at most one USB device per side unless a module
  contains its own hub.
- The lane only works while the keyboard is wired to a computer. **Basic module functions shall never
  depend on it**; they must also work over 2.4 GHz and Bluetooth through the module bus.

## 9. Requirements

| ID | Requirement | Phase | Verify |
|---|---|---|---|
| MOD-001 | Any side module shall work on `L` or `R`, in any chain position, without configuration. | P3 | T |
| MOD-002 | 100 attach/detach cycles per side under power shall cause no reset, fault or corrupted state. | P3 | T |
| MOD-003 | A short, a paper clip or steel debris across any contacts shall cause no damage and no power on `VMOD`. | P3 | T |
| MOD-004 | Key event latency through up to 4 chained modules shall be ≤ 1 ms more than the main matrix. | P3 | M |
| MOD-005 | Chain order shall be detected correctly for every arrangement of 3 macro modules + numpad. | P3 | T |
| MOD-006 | A power fault in module *k* shall leave the keyboard and modules before *k* running. | P3 | T |
| MOD-007 | Modules shall work over USB, 2.4 GHz and Bluetooth; the USB lane is optional. | P3 | T |
| MOD-008 | The descriptor format shall be versioned; unknown modules are reported, not fatal. | P3 | T |
| MOD-009 | A power-source module shall power and charge the keyboard; only one source at a time. | Later | T |
| MOD-010 | Presenting a wrong face (pads to pads, springs to springs) shall repel magnetically and cannot make electrical contact. A module on a side it is not made for is identified, refused a power grant and reported by the app. | P3 | T |
| MOD-011 | Module firmware shall update automatically through the keyboard; an interrupted update shall be recoverable. | P3 | T |
| MOD-012 | The first module on a side shall enumerate at USB High-Speed through the lane. | Later | T |
| MOD-013 | This spec shall be published under CC-BY-4.0 and the reference crate under MIT OR Apache-2.0. | P3 | I |

## 10. Module catalog

| Module | Side | Phase | Contents |
|---|---|---|---|
| Macro column 1×6 | `L` or `R` | P3 | 6 keys in one column, aligned to the keyboard rows, per-key RGB, same switches |
| Numpad | `L` or `R` | P3 | Standard numpad, per-key RGB |
| Knob module | `B` | P4 | See [knob-module.md](knob-module.md) |
| Wrist rest / power | `F` | Later | Battery or charging dock (power source) |
| Touch strip, sliders, screens | any | Later | Screens may stream over the USB lane when wired |
