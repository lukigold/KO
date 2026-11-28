# SPDX-License-Identifier: GPL-3.0-or-later
"""Switch board PCB: outline, net classes, footprints placed from the layout, linked to the schematic.

Board coordinates: mm, origin top-left (back-left corner), x right, y towards the user; KiCad page offset OX, OY.
Run through generate.py --pcb with KiCad's Python (/usr/bin/python3). Placement rules (docs/design/switch-board-v1.md
section 3): key footprint at the key centre (switch side); on the bottom the diode right of the per-key LED, anode
towards the socket; underglow LEDs at layout.underglow positions; port B in the back band (OPEN-24); control parts
in the free strip under the widest key of the front row, between its switch and its stabilizer reach.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import tempfile

import pcbnew

from kisch.sexpr import find, find_all, parse

ROOT = pathlib.Path(__file__).resolve().parents[2]
LIB = ROOT / "hardware" / "switch" / "lib" / "ko-switch.pretty"
OX, OY = 100.0, 100.0
ML, MF, MB, MR = 1.0, 2.5, 8.0, 3.0      # key area margins: left, front (lines behind the front row), back (port B band, OPEN-24), right
NETCLASSES = {
    "Default": {"track_width": 0.2, "clearance": 0.15, "via_diameter": 0.6, "via_drill": 0.3},
    "Power": {"track_width": 0.6, "clearance": 0.15, "via_diameter": 0.8, "via_drill": 0.4},
    "LEDsw": {"track_width": 0.4, "clearance": 0.15, "via_diameter": 0.6, "via_drill": 0.3},
    "USB": {"track_width": 0.3, "clearance": 0.15, "via_diameter": 0.6, "via_drill": 0.3},
}
PATTERNS = [("Power", "VBUS_B"), ("Power", "LED_5V"), ("LEDsw", "D*_SW*"), ("USB", "USB_B_D*")]


def mm(v: float) -> int:
    return int(round(v * 1e6))


def pt(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


def footprint(fpid: str) -> pcbnew.FOOTPRINT:
    lib, name = fpid.split(":", 1)
    path = LIB if lib == "ko-switch" else pathlib.Path(f"/usr/share/kicad/footprints/{lib}.pretty")
    fp = pcbnew.FootprintLoad(str(path), name)
    if fp is None:
        raise SystemExit(f"footprint not found: {fpid}")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def configure_project(outdir: pathlib.Path, slug: str) -> None:
    pro_path = outdir / f"{slug}.kicad_pro"
    pro = json.loads(pro_path.read_text()) if pro_path.exists() else {}
    if "board" not in pro:                       # start from KiCad's defaults (written by saving a board once)
        return
    ns = pro.setdefault("net_settings", {})
    base = next(c for c in ns["classes"] if c["name"] == "Default")
    ns["classes"] = [dict(base, name=n, **v) | ({} if n == "Default" else {"priority": i})
                     for i, (n, v) in enumerate(NETCLASSES.items())]
    ns["netclass_patterns"] = [{"netclass": c, "pattern": p} for c, p in PATTERNS]
    rules = pro["board"]["design_settings"]["rules"]
    rules.update({"min_clearance": 0.15, "min_track_width": 0.15, "min_via_diameter": 0.5,
                  "min_through_hole_diameter": 0.3, "min_via_annular_width": 0.1,
                  "min_copper_edge_clearance": 0.3, "min_hole_to_hole": 0.25, "min_hole_clearance": 0.25})
    pro["board"]["design_settings"].setdefault("rule_severities", {})["lib_footprint_mismatch"] = "ignore"
    pro_path.write_text(json.dumps(pro, indent=2) + "\n")


def export_netlist(outdir: pathlib.Path, slug: str) -> list:
    out = pathlib.Path(tempfile.mkdtemp()) / f"{slug}.net"
    subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr", "--output", str(out),
                    str(outdir / f"{slug}.kicad_sch")], check=True, capture_output=True)
    return parse(out.read_text())


def control_area(b) -> tuple[float, float, float]:
    """Centre x and y (board mm) of the widest front-row key, and its usable half width beside the switch."""
    front = max(k.row for k in b.keys)
    k = max((k for k in b.keys if k.row == front), key=lambda k: k.w)
    return ML + k.x, MB + k.y, k.w * 19.05 / 2


def placements(b) -> dict:
    """ref -> (x, y, rotation, side). Rotation is applied after the flip for bottom parts."""
    P = {}
    keys = sorted(b.keys, key=lambda k: (k.row, k.x))
    for k in keys:
        x, y = ML + k.x, MB + k.y
        P[f"SW{k.ref}"] = (x, y, 0, "T")
        P[f"D{100 + k.ref}"] = (x + 7.6, y + 5.0, 90, "B")         # SOD-123 upright, anode north (checked below)
        P[f"D{300 + k.ref}"] = (x, y + 4.9, 0, "B")
    for i, g in enumerate(b.glow):
        P[f"D{500 + i + 1}"] = (ML + g.x, MB + g.y, 0, "B")
    W = ML + b.width + MR
    P["J1"] = (W, 1.0, 0, "T")
    P["J2"] = (ML + 9.0, 5.0, 0, "B")                              # port B, mouth through the back edge
    P["U1"] = (ML + 18.0, 3.5, 0, "B")
    P["U2"] = (ML + 22.5, 3.5, 0, "B")
    cx, cy, half = control_area(b)
    # left of the space bar's switch: LED driver(s) with their caps; right of it: registers, EEPROM, PCA9306
    lx = cx - 22.0
    for n in range(b.drivers):
        dx = lx - n * 14.0
        P[f"U{20 + n}"] = (dx, cy, 0, "B")
        # the package's signals fan out to a ring of vias about 7 mm out (route.py); its parts sit outside it
        P[f"R{20 + n}"] = (dx - 10.0, cy + 4.6, 0, "B")              # ISET
        for j in range(6):                                          # supply caps beside the left fan
            P[f"C{20 + 10 * n + j}"] = (dx - 10.0, cy - 3.0 + 1.2 * j, 0, "B")
    P["C5"] = (lx - 10.3, cy - 4.8, 0, "B")
    P["U4"] = (lx + 12.5, cy - 3.0, 0, "B")
    P["R2"] = (lx + 12.5, cy - 5.6, 0, "B")
    P["C4"] = (lx + 12.5, cy - 6.8, 0, "B")
    P["R3"] = (lx + 11.9, cy - 0.4, 0, "B")
    P["R4"] = (lx + 11.9, cy + 0.8, 0, "B")
    P["R5"] = (lx + 11.9, cy + 2.0, 0, "B")
    rx = cx + 16.0
    for i in range(b.regs):
        P[f"U{10 + i}"] = (rx + i * 8.5, cy, 0, "B")
        P[f"C{10 + i}"] = (rx + i * 8.5, cy - 6.5, 0, "B")
    P["R1"] = (rx - 5.0, cy - 4.0, 90, "B")
    P["U3"] = (rx + b.regs * 8.5, cy, 0, "B")
    P["C3"] = (rx + b.regs * 8.5, cy - 4.0, 0, "B")
    return P


def outline(board, W, H, r=1.0) -> None:
    def seg(a, c):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        s.SetStart(pt(*a))
        s.SetEnd(pt(*c))
        board.Add(s)

    def arc(c, a0):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_ARC)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        s.SetCenter(pt(*c))
        s.SetStart(pt(c[0] + r * {0: 1, 90: 0, 180: -1, 270: 0}[a0], c[1] + r * {0: 0, 90: 1, 180: 0, 270: -1}[a0]))
        s.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(90, pcbnew.DEGREES_T), True)
        board.Add(s)
    # rounded corners on the left only; the right edge carries the castellations to its back end
    seg((r, 0), (W, 0))
    seg((W, 0), (W, H))
    seg((W, H), (r, H))
    seg((0, H - r), (0, r))
    arc((r, r), 180)
    arc((r, H - r), 90)


def build(b, outdir: pathlib.Path) -> None:
    tree = export_netlist(outdir, b.slug)
    pcb_path = outdir / f"{b.slug}.kicad_pcb"
    board = pcbnew.NewBoard(str(pcb_path))
    board.SetCopperLayerCount(4)
    board.GetDesignSettings().SetBoardThickness(mm(1.6))
    tb = board.GetTitleBlock()
    tb.SetTitle(f"KO switch board: {b.name}")
    tb.SetRevision("v1")
    tb.SetCompany("KO - Keyboard Organization")
    tb.SetComment(0, "SPDX-License-Identifier: CERN-OHL-S-2.0")
    tb.SetComment(1, "Generated by generator/ko_gen from the KO layout file")
    W, H = ML + b.width + MR, MB + b.depth + MF
    outline(board, W, H)

    nets = {}
    for n in find_all(find(tree, "nets"), "net"):
        name = str(find(n, "name")[1])
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        for node in find_all(n, "node"):
            nets[(str(find(node, "ref")[1]), str(find(node, "pin")[1]))] = ni

    P = placements(b)
    for comp in find_all(find(tree, "components"), "comp"):
        ref = str(find(comp, "ref")[1])
        fp = footprint(str(find(comp, "footprint")[1]))
        fp.SetReference(ref)
        fp.SetValue(str(find(comp, "value")[1]))
        fp.SetPath(pcbnew.KIID_PATH(str(find(find(comp, "sheetpath"), "tstamps")[1]) + str(find(comp, "tstamps")[1])))
        if ref not in P:
            raise SystemExit(f"no placement for {ref}")
        x, y, rot, side = P[ref]
        if ref == "J1":
            fp.SetExcludedFromBOM(True)
            fp.SetExcludedFromPosFiles(True)
        if ref.startswith("SW"):            # sockets: assembled by JLCPCB if stocked, else by hand (SWB-010)
            fp.Reference().SetVisible(False)
        elif ref[:1] in "RCD" and not ref.startswith("D5"):
            fp.Reference().SetVisible(False)
        else:
            fp.Reference().SetTextSize(pcbnew.VECTOR2I(mm(0.8), mm(0.8)))
            fp.Reference().SetTextThickness(mm(0.12))
        board.Add(fp)
        fp.SetPosition(pt(x, y))
        if side == "B":
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        fp.SetOrientationDegrees(rot)
        for pad in fp.Pads():
            if (ref, pad.GetNumber()) in nets:
                pad.SetNet(nets[(ref, pad.GetNumber())])
        if ref.startswith("D1") and len(ref) == 4:                    # diode: anode must face the socket (north)
            pa = next(p for p in fp.Pads() if p.GetNumber() == "2").GetPosition()
            pk = next(p for p in fp.Pads() if p.GetNumber() == "1").GetPosition()
            if pa.y > pk.y:
                fp.SetOrientationDegrees(rot + 180)

    gnd = board.FindNet("GND")
    for layer, name in ((pcbnew.In1_Cu, "GND plane"), (pcbnew.F_Cu, "GND top"), (pcbnew.B_Cu, "GND bottom")):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(gnd)
        o = z.Outline()
        o.NewOutline()
        for x, y in ((0.3, 0.3), (W - 0.3, 0.3), (W - 0.3, H - 0.3), (0.3, H - 0.3)):
            o.Append(mm(OX + x), mm(OY + y))
        z.SetZoneName(name)
        z.SetMinThickness(mm(0.2))
        z.SetLocalClearance(mm(0.25))
        z.SetThermalReliefGap(mm(0.25))
        z.SetThermalReliefSpokeWidth(mm(0.3))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        board.Add(z)
    t = pcbnew.PCB_TEXT(board)
    t.SetText(f"KO {b.name} v1\nCERN-OHL-S-2.0")
    t.SetLayer(pcbnew.B_SilkS)
    t.SetTextSize(pcbnew.VECTOR2I(mm(1.5), mm(1.5)))
    t.SetTextThickness(mm(0.2))
    t.SetMirrored(True)
    cx, cy, _ = control_area(b)
    t.SetPosition(pt(cx, cy + 7.0))
    board.Add(t)
    pro = outdir / f"{b.slug}.kicad_pro"
    if pro.exists() and "board" not in json.loads(pro.read_text()):
        pro.unlink()                                 # let KiCad write a full project file with its defaults
    pcbnew.SaveBoard(str(pcb_path), board)
    configure_project(outdir, b.slug)
    print(f"board written: {W:.2f} x {H:.2f} mm, {len(list(board.GetFootprints()))} footprints")
