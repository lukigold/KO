#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""JLCPCB fabrication and assembly files, the 1:1 fit-check drawing and renders for core board rev A.

    python3 hardware/core/tools/fab_outputs.py            # refuses unless DRC is clean
    python3 hardware/core/tools/fab_outputs.py --force    # write anyway (for review only, never order)

Writes hardware/core/fab/:
  ko-core-rev-a-gerbers.zip   Gerbers (4 copper layers, mask, paste, silkscreen, outline) + Excellon drills
  ko-core-rev-a-bom.csv       JLCPCB assembly BOM: Comment, Designator, Footprint, LCSC Part #
  ko-core-rev-a-cpl.csv       JLCPCB placement: Designator, Mid X, Mid Y, Layer, Rotation
  ko-core-rev-a-fit-1to1.pdf  print at 100 % to check the outline, connectors and parts against the case
  ko-core-rev-a-top.png, -bottom.png, -iso.png   renders
Unpopulated parts, test points and the castellated edge J401 (bare-board copper) are left out of BOM and CPL.
The castellated edge needs JLCPCB's "Castellated Holes" option when ordering.
"""
import argparse
import csv
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
CORE = HERE.parent
PCB = CORE / "ko-core.kicad_pcb"
SCH = CORE / "ko-core.kicad_sch"
FAB = CORE / "fab"
NAME = "ko-core-rev-a"
NOT_PLACED = ("TP", "J401")     # test points and the castellated edge: copper only, nothing to buy or place
LAYERS = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "F.Paste", "B.Paste", "F.Silkscreen", "B.Silkscreen",
          "F.Mask", "B.Mask", "Edge.Cuts"]


def cli(*args) -> None:
    r = subprocess.run(["kicad-cli", *args], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"kicad-cli {' '.join(args[:3])} failed:\n{r.stdout}\n{r.stderr}")


def drc() -> tuple[int, int]:
    with tempfile.TemporaryDirectory() as t:
        out = pathlib.Path(t) / "drc.json"
        subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "-o", str(out), str(PCB)], capture_output=True)
        d = json.loads(out.read_text())
    return len(d["violations"]), len(d["unconnected_items"])


def gerbers() -> None:
    with tempfile.TemporaryDirectory() as t:
        g = pathlib.Path(t)
        cli("pcb", "export", "gerbers", "--layers", ",".join(LAYERS), "--subtract-soldermask", "-o", str(g), str(PCB))
        cli("pcb", "export", "drill", "--format", "excellon", "--excellon-units", "mm",
            "--excellon-zeros-format", "decimal", "--excellon-separate-th", "-o", str(g), str(PCB))
        with zipfile.ZipFile(FAB / f"{NAME}-gerbers.zip", "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(g.iterdir()):
                z.write(f, f.name)


def cpl() -> None:
    with tempfile.TemporaryDirectory() as t:
        pos = pathlib.Path(t) / "pos.csv"
        cli("pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both", "--exclude-dnp",
            "-o", str(pos), str(PCB))
        rows = list(csv.DictReader(pos.open()))
    with (FAB / f"{NAME}-cpl.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for r in rows:
            if r["Ref"].startswith(NOT_PLACED):
                continue
            w.writerow([r["Ref"], f"{float(r['PosX']):.3f}mm", f"{float(r['PosY']):.3f}mm",
                        "Top" if r["Side"] == "top" else "Bottom", f"{float(r['Rot']):.0f}"])


def bom() -> None:
    with tempfile.TemporaryDirectory() as t:
        raw = pathlib.Path(t) / "bom.csv"
        cli("sch", "export", "bom", "--output", str(raw),
            "--fields", "Value,Reference,Footprint,LCSC",
            "--labels", "Comment,Designator,Footprint,LCSC Part #",
            "--group-by", "Value,Footprint,LCSC", "--exclude-dnp", str(SCH))
        rows = list(csv.DictReader(raw.open()))
    with (FAB / f"{NAME}-bom.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for r in rows:
            refs = [x.strip() for x in r["Designator"].split(",") if not x.strip().startswith(NOT_PLACED)]
            if refs:
                w.writerow([r["Comment"], ",".join(refs), r["Footprint"].split(":")[-1], r["LCSC Part #"]])


def drawing_and_renders() -> None:
    with tempfile.TemporaryDirectory() as t:
        t = pathlib.Path(t)
        top, bot = t / "top.pdf", t / "bottom.pdf"
        cli("pcb", "export", "pdf", "--layers", "Edge.Cuts,F.Fab,F.Courtyard,F.Silkscreen", "--mode-single",
            "--ibt", "-o", str(top), str(PCB))
        cli("pcb", "export", "pdf", "--layers", "Edge.Cuts,B.Fab,B.Courtyard,B.Silkscreen", "--mode-single",
            "--ibt", "--mirror", "-o", str(bot), str(PCB))
        if shutil.which("pdfunite"):
            subprocess.run(["pdfunite", str(top), str(bot), str(FAB / f"{NAME}-fit-1to1.pdf")], check=True)
        else:
            shutil.copy(top, FAB / f"{NAME}-fit-1to1.pdf")
            shutil.copy(bot, FAB / f"{NAME}-fit-1to1-bottom.pdf")
    # the strip is 22 x 80 mm: top and bottom views upright, the iso view turned so the strip runs across
    for side, size, extra in (("top", ("700", "1800"), []), ("bottom", ("700", "1800"), []),
                              ("iso", ("1800", "1000"), ["--rotate", "-50,0,-60", "--perspective"])):
        cli("pcb", "render", "--side", "bottom" if side == "bottom" else "top", "--quality", "high",
            "-w", size[0], "-h", size[1], "--background", "opaque", "--zoom", "0.9", *extra,
            "-o", str(FAB / f"{NAME}-{side}.png"), str(PCB))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="write outputs even if DRC is not clean")
    a = ap.parse_args()
    v, u = drc()
    print(f"DRC: {v} violations, {u} unconnected")
    if (v or u) and not a.force:
        sys.exit("refusing to write fabrication files for a board that fails DRC (use --force for review copies)")
    FAB.mkdir(exist_ok=True)
    gerbers()
    cpl()
    bom()
    drawing_and_renders()
    print(f"written to {FAB}")
