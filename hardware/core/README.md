# KO core board (KiCad project)

- **Contract:** [docs/contracts/core-board.md](../../docs/contracts/core-board.md)
- **Design note (parts, power tree, pin map, schematic decisions):** [docs/design/core-board-rev-a.md](../../docs/design/core-board-rev-a.md)
- **Status:** rev A schematic done and verified. PCB layout is next.

## The schematic is generated

`tools/gen_schematic.py` is the source of truth: every part, value, footprint, LCSC number and net is defined
there. It writes the KiCad files below. **Do not edit the schematic in KiCad**; your changes would be overwritten.
Edit the Python, then regenerate and check:

```bash
python3 hardware/core/tools/gen_schematic.py
```

```bash
python3 hardware/core/tools/check_schematic.py out/
```

The check fails on any ERC error and on any difference between KiCad's netlist and the intended nets. It also
writes `ko-core-schematic.pdf` and `ko-core-bom.csv` to the output folder.

| File | Content |
|---|---|
| `ko-core.kicad_sch` | Root sheet with the six block sheets |
| `power.kicad_sch` | Battery and charger: BQ25628E, LiPo and NTC connectors, MAX17048 |
| `power_rails.kicad_sch` | Power switch, 3.0 V LDO, 5 V boost, 5 V mux, LED rail switch |
| `mcu_radio.kicad_sch` | BMD-340 (nRF52840), 32.768 kHz crystal, I²C pull-ups |
| `usb.kicad_sch` | USB-C port A, CC resistors, ESD |
| `switchboard_conn.kicad_sch` | 24-pin FFC to the switch board (pinout fixed by the contract) |
| `service.kicad_sch` | SWD header, test points, expansion header (DNP), haptic connector (DNP) |
| `lib/ko.kicad_sym`, `sym-lib-table` | Project symbols drawn from datasheets (generated) |
| `bom/parts_query.json`, `bom/parts.csv` | Part queries and resolved LCSC numbers (`hardware/tools/jlc_lookup.py`) |
| `ko-core.kicad_pcb`, `ko-core.kicad_pro` | 4-layer, 1.0 mm board with placeholder outline; JLCPCB design rules |
| `tools/` | `gen_schematic.py` (design data), `check_schematic.py` (verification) |

The generator library lives in [`hardware/tools/kisch`](../tools/kisch) and will be reused for the switch board,
the dongle and the modules.
