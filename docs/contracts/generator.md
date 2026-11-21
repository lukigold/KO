# Contract: Generator

**ID prefix:** `GEN` · **Status:** draft v0.2 · **First phase:** P1 (switch board), P7 (full package) · **License:** GPL-3.0-or-later

## Purpose

Turns a layout description into a complete, orderable KO keyboard package. In P1 it generates the
owner's own switch board, so the pipeline is proven on a real keyboard before it becomes the product.
A local program comes first; a website using the same engine comes later.

## Inputs

| Input | Values |
|---|---|
| Layout | **KO layout file v1** (below), written by the layout builder; or KLE JSON (key positions only, the other inputs then come from options) |
| Size | 40 % up to full size with numpad |
| Standard | ANSI or ISO (languages differ only in keycaps and OS settings) |
| Switch family for plate/case | Choc (slim case) or MX (tall case); the feel (linear, tactile, clicky, silent) only goes into the switch order |
| Connection | Wireless (USB-C and Bluetooth, battery fitted) or wired (USB-C only, no battery fitted); same core board either way |
| Options | RGB on/off |
| Extra keys | Up to two extra rows above and two extra columns on each side, each key with a default function (media, Discord, desktop, macros) |
| Style | Parameters from the owner's final design ([mechanical.md](mechanical.md)) |

## KO layout file (v1)

The interface between the layout builder (`generator/configurator/index.html`) and the generator.
Schema: `generator/schema/ko-layout-1.schema.json`. Example: `generator/examples/ko-75-iso-ch.json` (the owner's build).
JSON is also valid YAML, so this file is the "KO YAML" input as well.

**Guarantees (builder → generator)**
- `format` is `"ko-layout"` and `version` is `1`; any change to the meaning of a field raises `version`.
- Every key is listed once in `keys` with a unique `id`, its rectangle `x, y, w, h` in units of `unit_mm` = 19.05 mm,
  origin at the top-left of the whole key area, y towards the user. No two keys overlap.
- A switch sits at the centre of its key. `shape: "iso-enter"` marks the ISO enter: bounding box 1.5 × 2 u, top part
  1.5 u wide, lower part 1.25 u wide and right-aligned; its switch sits at (x + 0.875, y + 1).
- `code` is the default keycode (QMK/Vial name, positional); `label` is only the printed legend.
- Extra keys carry `block` and `action` (a function id, `"custom"`, or null for a blank key); `blocks` lists their rows and columns.
- `matrix` is `"auto"`: the generator assigns the matrix (≤ 8 rows, SWB-007).

**Preconditions (generator)**
- Refuses a file whose `format` or `version` it does not know, and a layout the core board or battery does not fit under (GEN-005).
- Derives stabilizers itself: keys 2 u or wider, and tall keys except the ISO enter.

## Output: one folder per keyboard

```
<name>/
  kicad/        switch board KiCad project (schematic + PCB), editable
  fab/          Gerbers, drill, JLCPCB BOM + CPL, assembly notes
  descriptor/   EEPROM image (layout, matrix, LED map; see switch-board.md)
  firmware/     default keymap (Vial JSON / KO profile)
  mech/         plate (DXF + STEP), case top/bottom (STEP), renders (PNG)
  report.md     ERC/DRC results, BOM and cost estimate, warnings
```

The core board is not generated. It is a released design, referenced by version.

## Guarantees and invariants

- **Same core board and battery for every size.** The generator refuses layouts they don't fit under.
- **Deterministic:** the same input gives the same files (timestamps excepted).
- **Valid or nothing:** a package with ERC/DRC errors is marked as failed, never silently emitted.
- Module contact positions follow [module-interface.md](module-interface.md) (measured from the front edge).

## Requirements

| ID | Requirement | Phase | Verify |
|---|---|---|---|
| GEN-001 | Generate the v1 75 % ISO and ANSI switch boards with zero manual routing, ERC/DRC clean. | P1 | T |
| GEN-002 | Write the descriptor EEPROM image matching the generated board. | P1 | T |
| GEN-003 | Support 40 % up to full size with numpad, ANSI and ISO. | P7 | T |
| GEN-004 | Output shall be deterministic. | P1 | T |
| GEN-005 | Verify that the core board and battery fit; refuse otherwise. | P1 | T |
| GEN-006 | Packages shall be orderable at JLCPCB without edits and remain editable in KiCad. | P1 | D |
| GEN-007 | Generate plate and case STEP files from the skeleton and style parameters. | P7 | T |
| GEN-008 | Run locally with Python 3.12+, KiCad 9+ and build123d on macOS and Linux. | P1 | T |
| GEN-009 | Define side-module heights for keyboards with fewer than 6 rows (OPEN-17). | P7 | A |
| GEN-010 | Website front end using the same engine. | Later | D |
| GEN-011 | A layout builder page shall write KO layout files v1 for every supported size and standard, with connection, switch family, lighting and extra keys, and read them back unchanged. | P1 | T |
| GEN-012 | The generator shall read KO layout files v1 and reject any other `format` or `version`. | P1 | T |
