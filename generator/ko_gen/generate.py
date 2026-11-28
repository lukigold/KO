#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""KO switch-board generator: KO layout file v3 -> KiCad project in hardware/switch/<slug>/.

    python3 generator/ko_gen/generate.py generator/examples/ko-65-iso-ch.json            # schematic + ERC
    /usr/bin/python3 generator/ko_gen/generate.py <layout.json> --pcb                      # + placed PCB (KiCad Python)

Steps: layout.read -> schematic.write (kisch) -> ERC and netlist export (kicad-cli) -> pcb.build (pcbnew).
Output is deterministic (GEN-004): same layout file, same files.
"""
import argparse
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import layout  # noqa: E402
import schematic  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / "hardware" / "switch"


def erc(outdir: pathlib.Path, slug: str) -> tuple[int, int]:
    rpt = outdir / "erc.rpt"
    subprocess.run(["kicad-cli", "sch", "erc", "--severity-all", "-o", str(rpt), str(outdir / f"{slug}.kicad_sch")],
                   capture_output=True, check=True)
    txt = rpt.read_text()
    errs = sum(1 for line in txt.splitlines() if line.strip().startswith("; error"))
    warns = sum(1 for line in txt.splitlines() if line.strip().startswith("; warning"))
    return errs, warns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("layout")
    ap.add_argument("--pcb", action="store_true")
    a = ap.parse_args()
    b = layout.read(a.layout)
    outdir = OUT / b.slug
    schematic.write(b, outdir)
    (outdir / "fp-lib-table").write_text(
        '(fp_lib_table\n\t(version 7)\n\t(lib (name "ko-switch")(type "KiCad")'
        '(uri "${KIPRJMOD}/../lib/ko-switch.pretty")(options "")(descr "KO switch-board footprints (generated)"))\n)\n')
    pro = outdir / f"{b.slug}.kicad_pro"
    if not pro.exists():                                  # kicad-cli reads the project's library tables through it
        pro.write_text('{"meta": {"filename": "%s.kicad_pro", "version": 1}}\n' % b.slug)
    errs, warns = erc(outdir, b.slug)
    print(f"{b.name}: {len(b.keys)} keys, {b.rows}x{b.cols} matrix, {len(b.glow)} underglow, {b.drivers} driver(s); "
          f"schematic in {outdir.relative_to(ROOT)}; ERC {errs} errors, {warns} warnings")
    if a.pcb:
        import pcb
        pcb.build(b, outdir)


if __name__ == "__main__":
    main()
