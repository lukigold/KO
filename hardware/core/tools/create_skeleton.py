#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Create the KO core board rev A KiCad project skeleton.

Generates the project file (JLCPCB design rules), a root schematic with one
hierarchical sheet per block, empty block sheets with a note of what belongs
there, and a 4-layer 1.0 mm board with a placeholder outline.

Run with the Python that ships with KiCad (it needs `pcbnew`):
    /usr/bin/python3 hardware/core/tools/create_skeleton.py

The script refuses to overwrite existing files unless --force is given, so it
never destroys schematic work.
"""
import argparse
import json
import pathlib
import uuid

import pcbnew

PROJECT = "ko-core"
HERE = pathlib.Path(__file__).resolve().parent.parent  # hardware/core
SCH_VERSION = "20250114"  # KiCad 9 schematic format

# One sheet per block of docs/design/core-board-rev-a.md.
SHEETS = [
    ("Power", "power.kicad_sch",
     "USB VBUS input, BQ25628E charger + power path, LiPo + NTC, MAX17048,\n"
     "TPS7A02 3.0 V LDO (EN = power switch), TPS61023 boost, TPS2116 5 V mux,\n"
     "AP22653 LED rail switch. See design note sections 3 and 4."),
    ("MCU and radio", "mcu_radio.kicad_sch",
     "BMD-340 (nRF52840), 32.768 kHz crystal, decoupling, antenna keep-out.\n"
     "Pin budget: design note section 5."),
    ("USB", "usb.kicad_sch",
     "USB-C receptacle (port A, Rd 5.1 kOhm on CC1/CC2), USBLC6-2SC6 ESD,\n"
     "D+/D- to the nRF52840. Rev B replaces this sheet with hub + role logic."),
    ("Switch board connector", "switchboard_conn.kicad_sch",
     "FH34SRJ-24S-0.5SH, pinout per docs/contracts/switch-board.md:\n"
     "3V3, 4x GND, 3x LED_5V, I2C, LED_SDB, COL_DAT/CLK/LAT, ROW0-7, RSV_MISO, RSV_INT."),
    ("Service and expansion", "service.kicad_sch",
     "SWD header (2x5, 1.27 mm), test points for every rail/USB/I2C/SWD,\n"
     "expansion header (UART, SPI, 4 GPIO, 2 analog), power slide switch,\n"
     "reserved haptic driver footprint (DNP)."),
]


def uid() -> str:
    return str(uuid.uuid4())


def title_block(title: str) -> str:
    return (
        f'\t(title_block\n\t\t(title "{title}")\n\t\t(rev "A")\n'
        '\t\t(company "KO - Keyboard Organization")\n'
        '\t\t(comment 1 "SPDX-License-Identifier: CERN-OHL-S-2.0")\n'
        '\t\t(comment 2 "Implements docs/contracts/core-board.md, see docs/design/core-board-rev-a.md")\n'
        "\t)\n"
    )


def note(text: str, x: float, y: float) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return (
        f'\t(text "{escaped}"\n\t\t(exclude_from_sim no)\n\t\t(at {x} {y} 0)\n'
        "\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 2 2)\n\t\t\t)\n\t\t\t(justify left bottom)\n\t\t)\n"
        f"\t\t(uuid \"{uid()}\")\n\t)\n"
    )


def sub_sheet(name: str, description: str) -> str:
    return (
        f'(kicad_sch\n\t(version {SCH_VERSION})\n\t(generator "ko-skeleton")\n'
        f'\t(generator_version "9.0")\n\t(uuid "{uid()}")\n\t(paper "A4")\n'
        + title_block(f"KO core board - {name}")
        + "\t(lib_symbols)\n"
        + note(f"{name}\n\n{description}", 25.4, 38.1)
        + "\t(embedded_fonts no)\n)\n"
    )


def root_sheet(root_uuid: str) -> str:
    parts = [
        f'(kicad_sch\n\t(version {SCH_VERSION})\n\t(generator "ko-skeleton")\n'
        f'\t(generator_version "9.0")\n\t(uuid "{root_uuid}")\n\t(paper "A4")\n',
        title_block("KO core board rev A"),
        "\t(lib_symbols)\n",
        note("KO core board rev A - block overview\n"
             "Each block is a hierarchical sheet. Contract: docs/contracts/core-board.md", 25.4, 30.48),
    ]
    for i, (name, filename, _) in enumerate(SHEETS):
        x = 25.4 + (i % 3) * 88.9
        y = 50.8 + (i // 3) * 50.8
        parts.append(
            f"\t(sheet\n\t\t(at {x} {y})\n\t\t(size 63.5 25.4)\n\t\t(exclude_from_sim no)\n"
            "\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(dnp no)\n\t\t(fields_autoplaced yes)\n"
            "\t\t(stroke\n\t\t\t(width 0.1524)\n\t\t\t(type solid)\n\t\t)\n"
            "\t\t(fill\n\t\t\t(color 0 0 0 0.0000)\n\t\t)\n"
            f'\t\t(uuid "{uid()}")\n'
            f'\t\t(property "Sheetname" "{name}"\n\t\t\t(at {x} {y - 0.7} 0)\n'
            "\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n"
            "\t\t\t\t(justify left bottom)\n\t\t\t)\n\t\t)\n"
            f'\t\t(property "Sheetfile" "{filename}"\n\t\t\t(at {x} {y + 26.0} 0)\n'
            "\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n"
            "\t\t\t\t(justify left top)\n\t\t\t)\n\t\t)\n"
            f'\t\t(instances\n\t\t\t(project "{PROJECT}"\n'
            f'\t\t\t\t(path "/{root_uuid}"\n\t\t\t\t\t(page "{i + 2}")\n\t\t\t\t)\n'
            "\t\t\t)\n\t\t)\n\t)\n"
        )
    parts.append('\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n')
    parts.append("\t(embedded_fonts no)\n)\n")
    return "".join(parts)


def project_file() -> str:
    """KiCad template project with JLCPCB 4-layer design rules (conservative values)."""
    pro = json.loads(pathlib.Path("/usr/share/kicad/template/kicad.kicad_pro").read_text())
    pro["meta"]["filename"] = f"{PROJECT}.kicad_pro"
    rules = pro.setdefault("board", {}).setdefault("design_settings", {}).setdefault("rules", {})
    rules.update({
        "min_clearance": 0.1,             # JLCPCB 4-layer: 0.09 mm
        "min_track_width": 0.1,           # JLCPCB 4-layer: 0.09 mm
        "min_via_diameter": 0.45,
        "min_via_annular_width": 0.075,
        "min_through_hole_diameter": 0.2,
        "min_hole_clearance": 0.25,
        "min_hole_to_hole": 0.25,
        "min_copper_edge_clearance": 0.3,
        "min_silk_clearance": 0.05,
        "min_text_height": 0.8,
        "min_text_thickness": 0.12,
    })
    return json.dumps(pro, indent=2) + "\n"


def board(path: pathlib.Path) -> None:
    b = pcbnew.BOARD()
    b.SetCopperLayerCount(4)
    ds = b.GetDesignSettings()
    ds.SetBoardThickness(pcbnew.FromMM(1.0))
    # Placeholder outline 45 x 30 mm (design note section 9), origin at (100, 100) mm.
    x0, y0, w, h = 100.0, 100.0, 45.0, 30.0
    corners = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]
    for (ax, ay), (bx, by) in zip(corners, corners[1:] + corners[:1]):
        seg = pcbnew.PCB_SHAPE(b)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(pcbnew.FromMM(0.1))
        seg.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(ax), pcbnew.FromMM(ay)))
        seg.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(bx), pcbnew.FromMM(by)))
        b.Add(seg)
    tb = b.GetTitleBlock()
    tb.SetTitle("KO core board rev A")
    tb.SetRevision("A")
    tb.SetCompany("KO - Keyboard Organization")
    tb.SetComment(0, "SPDX-License-Identifier: CERN-OHL-S-2.0")
    pcbnew.SaveBoard(str(path), b)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="overwrite existing files")
    args = ap.parse_args()

    targets = [HERE / f"{PROJECT}.kicad_pro", HERE / f"{PROJECT}.kicad_sch", HERE / f"{PROJECT}.kicad_pcb"]
    targets += [HERE / f for _, f, _ in SHEETS]
    existing = [t for t in targets if t.exists()]
    if existing and not args.force:
        raise SystemExit(f"refusing to overwrite {', '.join(t.name for t in existing)} (use --force)")

    root_uuid = uid()
    (HERE / f"{PROJECT}.kicad_pro").write_text(project_file())
    (HERE / f"{PROJECT}.kicad_sch").write_text(root_sheet(root_uuid))
    for name, filename, description in SHEETS:
        (HERE / filename).write_text(sub_sheet(name, description))
    board(HERE / f"{PROJECT}.kicad_pcb")
    print("created:", ", ".join(t.name for t in targets))


if __name__ == "__main__":
    main()
