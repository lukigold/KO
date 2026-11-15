# KO core board (KiCad project)

- **Contract:** [docs/contracts/core-board.md](../../docs/contracts/core-board.md)
- **Design note (parts, power tree, pin budget):** [docs/design/core-board-rev-a.md](../../docs/design/core-board-rev-a.md)
- **Status:** rev A skeleton. The block sheets are empty and only carry a note of what belongs on them; the schematic comes next.

| File | Content |
|---|---|
| `ko-core.kicad_pro` | Project with JLCPCB 4-layer design rules |
| `ko-core.kicad_sch` | Root sheet: one hierarchical sheet per block |
| `power.kicad_sch` | USB input, charger, battery, fuel gauge, 3.0 V and 5 V rails, LED rail switch |
| `mcu_radio.kicad_sch` | BMD-340 (nRF52840), crystal |
| `usb.kicad_sch` | USB-C port A, ESD |
| `switchboard_conn.kicad_sch` | 24-pin FFC to the switch board |
| `service.kicad_sch` | SWD, test points, expansion header, power switch, reserved haptic driver |
| `ko-core.kicad_pcb` | 4-layer, 1.0 mm board with a 45 × 30 mm placeholder outline |
| `tools/create_skeleton.py` | Regenerates the skeleton. Refuses to overwrite without `--force` |

## Checks (headless)

```bash
kicad-cli sch erc --output erc.rpt ko-core.kicad_sch
```

```bash
kicad-cli pcb drc --output drc.rpt ko-core.kicad_pcb
```

Both must report 0 errors before any commit that changes the design (AGENTS.md, Definition of Done).
