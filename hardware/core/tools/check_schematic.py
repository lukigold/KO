#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify the generated core board schematic (Definition of Done, AGENTS.md).

1. Runs KiCad ERC and fails on any error (warnings are listed; waived ones are explained below).
2. Exports KiCad's own netlist and compares it pin-by-pin with the intended nets in
   gen_schematic.py, so a label or stub in the wrong place cannot go unnoticed.
3. Exports the schematic PDF and a BOM CSV to the given output directory.

Usage:  python3 hardware/core/tools/check_schematic.py [OUTDIR]
"""
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
CORE = HERE.parent
sys.path.insert(0, str(CORE.parent / "tools"))
from kisch.sexpr import find, find_all, parse  # noqa: E402

# Warnings accepted for now, with the reason. Remove an entry once it no longer applies.
WAIVED = {
    "footprint_link_issues": "custom footprints (BMD-340, BQ25628E RYK, FH34SRJ-24S) are drawn in the layout phase",
}


def run(*args) -> None:
    subprocess.run(["kicad-cli", *args], check=True, capture_output=True, text=True)


def main() -> int:
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(tempfile.mkdtemp())
    out.mkdir(parents=True, exist_ok=True)
    sch = CORE / "ko-core.kicad_sch"
    ok = True

    run("sch", "erc", "--severity-all", "--format", "json", "--output", str(out / "erc.json"), str(sch))
    erc = json.loads((out / "erc.json").read_text())
    for sheet in erc["sheets"]:
        for v in sheet["violations"]:
            waived = v["type"] in WAIVED and v["severity"] == "warning"
            ok &= waived
            items = ", ".join(i["description"] for i in v["items"])
            print(f"ERC {v['severity']:7s} {v['type']}: {v['description']} [{items}]"
                  + (f"  (waived: {WAIVED[v['type']]})" if waived else ""))

    run("sch", "export", "netlist", "--format", "kicadsexpr", "--output", str(out / "ko-core.net"), str(sch))
    tree = parse((out / "ko-core.net").read_text())
    kicad = set()
    for net in find_all(find(tree, "nets"), "net"):
        nodes = frozenset((str(find(n, "ref")[1]), str(find(n, "pin")[1])) for n in find_all(net, "node")
                          if not str(find(n, "ref")[1]).startswith("#"))
        if len(nodes) > 1:
            kicad.add(nodes)
    spec = importlib.util.spec_from_file_location("gen", HERE / "gen_schematic.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    intended = {name: frozenset((r, p) for _, r, p in members if not r.startswith("#"))
                for name, members in gen.design.nets().items() if name != "NC"}
    mismatches = [name for name, nodes in intended.items() if len(nodes) > 1 and nodes not in kicad]
    for name in mismatches:
        print(f"NETLIST MISMATCH: {name}")
    ok &= not mismatches
    print(f"netlist: {len(intended)} intended nets, {len(kicad)} multi-pin KiCad nets, {len(mismatches)} mismatches")

    run("sch", "export", "pdf", "--output", str(out / "ko-core-schematic.pdf"), str(sch))
    run("sch", "export", "bom", "--output", str(out / "ko-core-bom.csv"),
        "--fields", "Reference,Value,Footprint,LCSC,MPN,${DNP},${QUANTITY}",
        "--labels", "Refs,Value,Footprint,LCSC,MPN,DNP,Qty",
        "--group-by", "Value,Footprint,LCSC,${DNP}", "--exclude-dnp", str(sch))
    print(f"outputs in {out}")
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
