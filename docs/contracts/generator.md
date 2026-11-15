# Contract: Generator

**ID prefix:** `GEN` · **Status:** draft v0.1 · **First phase:** P1 (switch board), P7 (full package) · **License:** GPL-3.0-or-later

## Purpose

Turns a layout description into a complete, orderable KO keyboard package. In P1 it generates the
owner's own switch board, so the pipeline is proven on a real keyboard before it becomes the product.
A local program comes first; a website using the same engine comes later.

## Inputs

| Input | Values |
|---|---|
| Layout | KLE JSON or KO YAML |
| Size | 40 % up to full size with numpad |
| Standard | ANSI or ISO (languages differ only in keycaps and OS settings) |
| Switch family for plate/case | Choc (slim case) or MX (tall case) |
| Options | RGB on/off |
| Style | Parameters from the owner's final design ([mechanical.md](mechanical.md)) |

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
