#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Core board rev A PCB: netlist import, board setup and placement.

Builds hardware/core/ko-core.kicad_pcb from the schematic, so the PCB always matches it:
  * exports KiCad's netlist from the schematic and places every footprint, linked to its symbol
    (KiCad's "Update PCB from Schematic" keeps working afterwards),
  * board outline, 4-layer 1.0 mm stackup, net classes (Default / Power / USB),
  * GND planes, the BMD-340 antenna keep-out strip at the right board edge beside the module,
  * the placement below (board coordinates in mm, origin top-left, x right, y down).

Routing is a separate step. Run with KiCad's Python:
    /usr/bin/python3 hardware/core/tools/gen_pcb.py

Board orientation (D-41): a 22 x 80 mm strip right of the key area. Left edge = 33 castellated contacts
soldered to the switch board, top edge = back of the keyboard (USB-C port A), right edge = case wall
(antenna, power switch), bottom edge = front (battery). See docs/design/core-board-rev-a.md section 9.
"""
import json
import math
import pathlib
import subprocess
import sys
import tempfile

import pcbnew

HERE = pathlib.Path(__file__).resolve().parent
CORE = HERE.parent
sys.path.insert(0, str(CORE.parent / "tools"))
from kisch.sexpr import find, find_all, parse  # noqa: E402

BOARD_W, BOARD_H = 16.0, 80.0
OX, OY = 100.0, 100.0           # board origin in KiCad page coordinates
RF_STRIP = 4.2                   # BMD-340 datasheet 6.1: no copper within 4.4 mm of the antenna edge, which
                                 # stands 0.2 mm beyond the board edge
RF_Y = (32.0, 51.0)              # keep-out strip along the right edge, beside the module and ~4.1 mm beyond it
USB_SHELL = (6.0, 15.6, 5.3)     # x0, x1, y1: no top-layer copper under the receptacle body but its pads

# Blocks of the 50 x 32 mm placement whose hand routes (route_pcb.py) move with them.
CHARGER_SHIFT = (3.1, 49.0)      # charger: BQ25628E and its parts, translated
RAILS_ROT = ((22.7, 20.8), (10.1, 22.9))   # boost / 5 V mux / LED switch: turned 90 deg CCW about the first
                                          # point (block centre on the old board), which lands on the second


def _shift(d: dict, dx: float, dy: float) -> dict:
    return {k: (round(x + dx, 3), round(y + dy, 3), r, side) for k, (x, y, r, side) in d.items()}


def rot90(x: float, y: float, rr=RAILS_ROT) -> tuple:
    """Point of the rails block turned 90 deg counter-clockwise on screen (KiCad's +90) and moved."""
    (cx, cy), (tx, ty) = rr
    return round(tx + (y - cy), 3), round(ty - (x - cx), 3)


def _turn(d: dict) -> dict:
    return {k: (*rot90(x, y), (r + 90) % 360, side) for k, (x, y, r, side) in d.items()}


# ref: (x, y, rotation_deg, side)   side "T" top or "B" bottom. Rotation is KiCad's (CCW positive).
# Strip of 16 x 80 mm (D-43): x = 0 is the castellated edge soldered to the switch board, x = 16 the right
# case wall (antenna), y = 0 the back edge (USB-C port A), y = 80 the front edge (battery).
PLACEMENT = {
    # --- back: USB-C port A, VBUS mux, ESD, data switch
    "J301": (10.8, 5.0, 180, "T"),     # long-body USB-C, mouth through the back wall
    "J401": (0.0, 1.0, 0, "T"),        # castellated contacts: 1-17 at y 1..33, 18-33 at y 48..78
    "U303": (4.2, 4.0, 0, "T"),        # TPS2121: IN2 = port B from the contacts, IN1 = port A from the right
    "C303": (3.05, 1.2, 90, "T"),      # VBUS_B input, at contact 1
    "C301": (4.1, 1.2, 90, "T"),       # SS
    "R309": (5.15, 1.2, 90, "T"),      # ILIM
    "R307": (3.1, 8.4, 90, "T"),       # OV2 divider (VBUS_B), below the TPS2121's divider pins
    "R305": (4.25, 8.4, 90, "T"),      # OV1 divider (VBUS_A)
    "R303": (5.4, 8.4, 90, "T"),       # PR1 divider (VBUS_A)
    "R308": (3.1, 10.6, 270, "T"),
    "R306": (4.25, 10.6, 270, "T"),
    "R304": (5.4, 10.6, 270, "T"),
    "C302": (6.6, 8.4, 90, "T"),       # VBUS_A input
    "U301": (9.6, 9.4, 0, "T"),        # D+/D- ESD below the receptacle's data pins
    "U302": (13.8, 9.4, 0, "T"),       # CC ESD
    "R301": (12.6, 13.0, 0, "T"),      # CC1 Rd
    "R302": (14.6, 13.0, 0, "T"),      # CC2 Rd
    "U304": (4.8, 13.3, 90, "T"),      # TS3USB221A next to contacts 5/6
    "C304": (2.75, 13.3, 90, "T"),
    "R310": (7.1, 13.3, 90, "T"),      # TPS2121 ST pull-up (USB_SEL)
    # --- beside the 5 V block at the right wall: underglow data buffer (LED_5V leaves the block there)
    "U501": (13.9, 28.0, 0, "T"),
    "C501": (14.6, 25.6, 90, "T"),
    "R501": (13.9, 30.4, 0, "T"),
    # --- in front of the 5 V block: crystal and module decoupling above the module
    "Y201": (6.0, 34.8, 180, "T"),     # 32.768 kHz next to module pads 13/14
    "C204": (8.6, 34.8, 90, "T"),
    "C205": (9.6, 34.8, 90, "T"),
    "C202": (3.15, 34.95, 90, "T"),    # VCC 100n next to VCC pad 17
    "C201": (10.8, 34.5, 90, "T"),     # VCC 10u
    "C401": (2.95, 15.6, 90, "T"),     # 3V0 at contact 8
    "C402": (4.2, 32.6, 0, "T"),       # LED_5V, between the 5 V block and the crystal
    # --- module across the full width, antenna flush with the right edge
    "U201": (8.7, 41.5, 180, "T"),     # antenna 0.2 mm beyond the right edge: room for 3 tracks left of the
                                       # left pad column (VCC, VBUS, USB D+/D-)
    "C203": (3.1, 47.6, 0, "T"),       # VBUS 4u7 next to module pad 66
    # --- front: charger (moved block), CC_B Rd at their contacts, LDO, fuel gauge, pull-ups, battery
    "R311": (2.65, 54.0, 270, "T"),    # CC1_B Rd at contact 21, tucked against the edge (the lane beside it
    "R312": (2.65, 58.0, 270, "T"),    # CC2_B Rd at contact 23   carries the matrix lines to contacts 24-33)
    "U103": (13.6, 64.1, 0, "T"),      # 3.0 V LDO
    "C110": (10.8, 64.1, 90, "T"),     # SYS input
    "C111": (13.6, 66.9, 0, "T"),      # 3V0 output
    "R107": (10.8, 66.9, 90, "T"),     # PWR_EN pull-down (switch on pads J103)
    "U102": (6.9, 63.4, 180, "T"),     # fuel gauge: VBAT pins towards the VBAT track, I2C towards the pull-ups
    "C109": (7.0, 65.4, 180, "T"),     # VBAT, pin 1 on the VBAT track
    "R106": (7.5, 66.9, 0, "T"),       # FG_ALRT pull-up, out of the edge lane
    "R201": (5.3, 66.4, 0, "T"),       # I2C pull-ups below the fuel gauge, out of the edge lane
    "R202": (5.3, 67.5, 0, "T"),
    "J101": (7.4, 74.9, 0, "T"),       # battery, opening to the front edge
    # --- bottom side: solder pads for wires (D-43)
    "J102": (5.7, 69.6, 0, "B"),       # pack NTC          } under the battery connector, right-aligned
    "J103": (13.7, 69.6, 0, "B"),      # power switch      } so the edge lane stays free for contacts 30-33
    "J501": (3.2, 38.0, 0, "B"),       # SWD, under the module next to its SWD pins
    "J503": (3.2, 43.75, 0, "B"),      # haptic driver, under the module next to I2C and HAPTIC_EN
    "J504": (12.2, 27.6, 0, "B"),      # underglow strip, under its buffer
}
PLACEMENT.update(_shift({                # charger, as placed and hand-routed on the 50 x 32 mm board
    "U101": (6.4, 6.2, 0, "T"),
    "C102": (6.6, 2.8, 0, "T"),        # PMID 10u 0805, right above PMID/GND pads
    "C103": (6.6, 1.1, 0, "T"),        # PMID 100n
    "C101": (3.4, 3.2, 90, "T"),       # VBUS 1u
    "C104": (9.3, 3.2, 0, "T"),        # BTST 47n
    "L101": (11.2, 6.2, 270, "T"),     # 1 uH, SW -> SYS
    "C105": (2.4, 6.4, 90, "T"),       # REGN 4u7
    "C106": (11.2, 9.4, 0, "T"),       # SYS 10u
    "C107": (11.2, 11.1, 0, "T"),      # SYS 10u
    "C108": (6.8, 9.4, 0, "T"),        # BAT 10u
    "R101": (2.4, 9.4, 90, "T"),       # ILIM 5.1k
    "R104": (3.6, 9.4, 90, "T"),       # CE pull-down
    "R102": (6.8, 11.1, 0, "T"),       # TS bias
    "R103": (6.8, 12.4, 0, "T"),       # TS
    "RT101": (3.6, 12.4, 0, "T"),      # fallback NTC (DNP)
    "R105": (8.8, 12.6, 0, "T"),       # INT pull-up
}, *CHARGER_SHIFT))
PLACEMENT.update(_turn({                 # boost, 5 V mux and LED switch, as on the 50 x 32 mm board
    "L102": (17.6, 15.6, 0, "T"),      # boost inductor
    "U104": (17.6, 18.4, 0, "T"),      # boost
    "C112": (14.6, 18.6, 90, "T"),
    "C113": (21.0, 16.6, 90, "T"),
    "C114": (23.2, 16.6, 90, "T"),
    "R108": (20.6, 19.6, 0, "T"),
    "R109": (20.6, 20.8, 0, "T"),
    "R110": (16.6, 20.6, 0, "T"),
    "U105": (27.4, 16.4, 0, "T"),      # 5 V mux
    "C115": (25.2, 16.4, 90, "T"),
    "C116": (29.8, 16.4, 270, "T"),
    "R111": (27.4, 19.0, 0, "T"),
    "R112": (27.4, 20.2, 0, "T"),
    "U106": (24.0, 21.8, 0, "T"),      # LED rail switch
    "R113": (20.6, 23.6, 180, "T"),
    "R114": (20.6, 22.4, 180, "T"),
    "R115": (28.0, 22.6, 0, "T"),
    "C117": (22.56, 18.85, 180, "T"),  # LED switch input cap, next to its V5 pin
    "C118": (24.0, 24.8, 0, "T"),
}))

# Test points on the bottom side, next to the copper they probe (nets with a wire pad are probed there).
TP_POS = {
    "TP501": (2.6, 16.5), "TP522": (11.6, 9.4),                                   # on the VBUS and VBUS_A copper
    "TP509": (9.2, 13.8), "TP510": (11.4, 13.8),                                  # USB_DP, USB_DN
    "TP506": (8.6, 33.6), "TP516": (13.6, 60.6),                                  # VBOOST, CHG_QON
    "TP503": (9.7, 69.6),                                                         # VBAT
}

STANDIN_MODELS = {"J101": "JST_PH_S2B-PH-SM4-TB_standin"}

NETCLASSES = {
    "Default": dict(track_width=0.15, clearance=0.15, via_diameter=0.5, via_drill=0.25),
    "Power": dict(track_width=0.6, clearance=0.15, via_diameter=0.6, via_drill=0.3),
    "Supply": dict(track_width=0.3, clearance=0.15, via_diameter=0.5, via_drill=0.25),
    "USB": dict(track_width=0.2, clearance=0.15, via_diameter=0.5, via_drill=0.25,
                diff_pair_width=0.2, diff_pair_gap=0.2),
}
POWER_NETS = ["VBUS", "VBUS_A", "VBUS_B", "SYS", "VBAT", "V5", "VBOOST", "LED_5V", "*CHG_SW", "*CHG_PMID", "*BST_SW"]
SUPPLY_NETS = ["3V0"]


DRU = """(version 1)
# Generated by hardware/core/tools/gen_pcb.py.
# Every SMD GND pad is also tied to the GND plane by its own track and via (route_pcb.py fan-out),
# so one thermal spoke from a GND pour is enough.
(rule "gnd_pour_spokes"
    (condition "A.Type == 'Zone' && A.NetName == 'GND'")
    (constraint min_resolved_spokes 1))
"""


def mm(v: float) -> int:
    return pcbnew.FromMM(v)


def pt(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


def export_netlist() -> list:
    out = pathlib.Path(tempfile.mkdtemp()) / "ko-core.net"
    subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr", "--output", str(out),
                    str(CORE / "ko-core.kicad_sch")], check=True, capture_output=True)
    return parse(out.read_text())


def configure_project() -> None:
    pro_path = CORE / "ko-core.kicad_pro"
    pro = json.loads(pro_path.read_text())
    ns = pro.setdefault("net_settings", {})
    base = next(c for c in ns["classes"] if c["name"] == "Default")
    classes = []
    for name, vals in NETCLASSES.items():
        c = dict(base, name=name, **vals)
        if name != "Default":
            c["priority"] = 0 if name == "USB" else 1
        classes.append(c)
    ns["classes"] = classes
    ns["netclass_patterns"] = [{"netclass": "Power", "pattern": p} for p in POWER_NETS] + \
                              [{"netclass": "Supply", "pattern": p} for p in SUPPLY_NETS] + \
                              [{"netclass": "USB", "pattern": "USB_D*"}]
    rules = pro["board"]["design_settings"]["rules"]
    rules.update({"min_clearance": 0.1, "min_track_width": 0.1, "min_via_diameter": 0.45,
                  "min_through_hole_diameter": 0.2, "min_via_annular_width": 0.1,
                  "min_copper_edge_clearance": 0.3, "min_hole_to_hole": 0.25})
    # Footprints are regenerated from the libraries on every run; the only intended difference is the
    # silkscreen clipped at the board edge (tidy_silk), so the library-mismatch check is not useful here.
    pro["board"]["design_settings"].setdefault("rule_severities", {})["lib_footprint_mismatch"] = "ignore"
    pro_path.write_text(json.dumps(pro, indent=2) + "\n")
    (CORE / "ko-core.kicad_dru").write_text(DRU)


def footprint(fpid: str) -> pcbnew.FOOTPRINT:
    lib, name = fpid.split(":", 1)
    path = CORE / "lib" / "ko.pretty" if lib == "ko" else pathlib.Path(f"/usr/share/kicad/footprints/{lib}.pretty")
    fp = pcbnew.FootprintLoad(str(path), name)
    if fp is None:
        raise SystemExit(f"footprint not found: {fpid}")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def add_zone(board, net, layers, poly, name, priority=0, rule_area=False, allow_pads=False):
    z = pcbnew.ZONE(board)
    ls = pcbnew.LSET()
    for layer in layers:
        ls.AddLayer(layer)
    z.SetLayerSet(ls)
    if net is not None:
        z.SetNet(net)
    o = z.Outline()
    o.NewOutline()
    for x, y in poly:
        o.Append(mm(OX + x), mm(OY + y))
    z.SetZoneName(name)
    z.SetAssignedPriority(priority)
    if rule_area:
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowPads(not allow_pads)
        z.SetDoNotAllowCopperPour(True)
        z.SetDoNotAllowFootprints(False)
    else:
        z.SetMinThickness(mm(0.25))
        z.SetLocalClearance(mm(0.2))
        z.SetThermalReliefGap(mm(0.25))
        z.SetThermalReliefSpokeWidth(mm(0.3))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    board.Add(z)
    return z


def build() -> pcbnew.BOARD:
    configure_project()
    tree = export_netlist()
    board = pcbnew.NewBoard(str(CORE / "ko-core.kicad_pcb"))
    board.SetCopperLayerCount(4)
    board.GetDesignSettings().SetBoardThickness(mm(1.0))
    tb = board.GetTitleBlock()
    tb.SetTitle("KO core board rev A")
    tb.SetRevision("A")
    tb.SetCompany("KO - Keyboard Organization")
    tb.SetComment(0, "SPDX-License-Identifier: CERN-OHL-S-2.0")
    tb.SetComment(1, "Generated by hardware/core/tools/gen_pcb.py (placement) and route_pcb.py (routing)")

    # outline
    for (ax, ay), (bx, by) in zip([(0, 0), (BOARD_W, 0), (BOARD_W, BOARD_H), (0, BOARD_H)],
                                  [(BOARD_W, 0), (BOARD_W, BOARD_H), (0, BOARD_H), (0, 0)]):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        s.SetStart(pt(ax, ay))
        s.SetEnd(pt(bx, by))
        board.Add(s)

    # nets
    nets = {}
    for n in find_all(find(tree, "nets"), "net"):
        name = str(find(n, "name")[1])
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        nets[name] = ni
        for node in find_all(n, "node"):
            nets.setdefault(("pin", str(find(node, "ref")[1]), str(find(node, "pin")[1])), ni)

    # footprints
    for comp in find_all(find(tree, "components"), "comp"):
        ref = str(find(comp, "ref")[1])
        fpid = str(find(comp, "footprint")[1])
        fp = footprint(fpid)
        fp.SetReference(ref)
        fp.SetValue(str(find(comp, "value")[1]))
        sheet_ts = str(find(find(comp, "sheetpath"), "tstamps")[1])
        sym_ts = str(find(comp, "tstamps")[1])
        fp.SetPath(pcbnew.KIID_PATH(sheet_ts + sym_ts))
        props = {str(find(p, "name")[1]): (str(find(p, "value")[1]) if find(p, "value") else "")
                 for p in find_all(comp, "property")}
        dnp = "dnp" in props or ref == "RT101"
        if ref.startswith("TP"):
            x, y = TP_POS[ref]
            rot, side = 0, "B"
            fp.SetExcludedFromBOM(True)
            fp.SetExcludedFromPosFiles(True)
        else:
            if ref not in PLACEMENT:
                raise SystemExit(f"no placement for {ref}")
            x, y, rot, side = PLACEMENT[ref]
            if ref == "J401":                   # castellated edge: copper of the bare board, nothing to place
                fp.SetExcludedFromBOM(True)
                fp.SetExcludedFromPosFiles(True)
        if dnp:                                 # DNP keeps it out of BOM and CPL; the symbol stays "in BOM"
            fp.SetDNP(True)
            fp.SetExcludedFromPosFiles(True)
        # silkscreen: passives carry their reference only on the assembly (Fab) layer
        ref_text = fp.Reference()
        if ref[:1] in "RCL" or ref.startswith("RT"):
            ref_text.SetVisible(False)
        else:
            ref_text.SetTextSize(pcbnew.VECTOR2I(mm(0.8), mm(0.8)))
            ref_text.SetTextThickness(mm(0.12))
        if ref in STANDIN_MODELS:      # library STEP model missing from KiCad's package: render stand-in
            m = pcbnew.FP_3DMODEL()
            m.m_Filename = f"${{KIPRJMOD}}/lib/ko.3dshapes/{STANDIN_MODELS[ref]}.wrl"
            fp.Models().clear()
            fp.Models().push_back(m)
        board.Add(fp)
        fp.SetPosition(pt(x, y))
        if side == "B":
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        fp.SetOrientationDegrees(rot)
        for pad in fp.Pads():
            key = ("pin", ref, pad.GetNumber())
            if key in nets:
                pad.SetNet(nets[key])

    # planes: GND on In1 (solid reference), GND pours on outer layers and In2 (filled after routing)
    inset = 0.3
    full = [(inset, inset), (BOARD_W - inset, inset), (BOARD_W - inset, BOARD_H - inset), (inset, BOARD_H - inset)]
    gnd = nets["GND"]
    add_zone(board, gnd, [pcbnew.In1_Cu], full, "GND plane", priority=0)
    add_zone(board, gnd, [pcbnew.In2_Cu], full, "GND In2", priority=0)
    add_zone(board, gnd, [pcbnew.F_Cu], full, "GND top", priority=0)
    add_zone(board, gnd, [pcbnew.B_Cu], full, "GND bottom", priority=0)
    # antenna keep-out strip along the right edge (all copper layers)
    x0, (y0, y1) = BOARD_W - RF_STRIP, RF_Y
    add_zone(board, None, [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu],
             [(x0, y0), (BOARD_W + 0.5, y0), (BOARD_W + 0.5, y1), (x0, y1)],
             "antenna keep-out", rule_area=True)
    # no top-layer tracks or vias under the USB-C receptacle's metal body (only its own pads)
    ux0, ux1, uy1 = USB_SHELL
    add_zone(board, None, [pcbnew.F_Cu], [(ux0, -0.5), (ux1, -0.5), (ux1, uy1), (ux0, uy1)],
             "USB-C shell keep-out", rule_area=True, allow_pads=True)
    tidy_silk(board)
    return board


# ------------------------------------------------------------------------------------------- silkscreen
SILK_EDGE = 0.4          # silkscreen to board edge
BOARD_TEXTS = [          # (text, layer, height mm): placed at the first free spot on the bottom side
    ("KO core rev A", pcbnew.B_SilkS, 1.0),
    ("CERN-OHL-S-2.0", pcbnew.B_SilkS, 0.8),
    ("JLCJLCJLCJLC", pcbnew.B_SilkS, 0.8),      # tells JLCPCB where to print its order number
]


def _bb(item, grow: float = 0.0) -> tuple:
    bb = item.GetBoundingBox()
    return (pcbnew.ToMM(bb.GetLeft()) - OX - grow, pcbnew.ToMM(bb.GetTop()) - OY - grow,
            pcbnew.ToMM(bb.GetRight()) - OX + grow, pcbnew.ToMM(bb.GetBottom()) - OY + grow)


def _overlap(a: tuple, b: tuple) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _clip(x0, y0, x1, y1, lo_x, lo_y, hi_x, hi_y):
    """Liang-Barsky: clip segment to the rectangle, None if fully outside."""
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - lo_x), (dx, hi_x - x0), (-dy, y0 - lo_y), (dy, hi_y - y0)):
        if p == 0:
            if q < 0:
                return None
            continue
        r = q / p
        if p < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return None
    return x0 + t0 * dx, y0 + t0 * dy, x0 + t1 * dx, y0 + t1 * dy


def tidy_silk(board: pcbnew.BOARD) -> None:
    """Keep silkscreen off the board edge, off pads and off other silkscreen.

    Footprint outlines of edge-mounted parts (USB-C, slide switch) are clipped at the edge. Reference
    designators of ICs and connectors move to the first free spot around their part (hidden if there is
    none); test-point references stay on the assembly layer only (the test-point map is in the docs).
    """
    silk = (pcbnew.F_SilkS, pcbnew.B_SilkS)
    lo, hi_x, hi_y = SILK_EDGE, BOARD_W - SILK_EDGE, BOARD_H - SILK_EDGE
    for fp in board.GetFootprints():
        for g in list(fp.GraphicalItems()):
            if g.GetLayer() not in silk or g.GetClass() == "PCB_TEXT":
                continue
            x0, y0, x1, y1 = _bb(g)
            if x0 >= lo and y0 >= lo and x1 <= hi_x and y1 <= hi_y:
                continue
            c = None
            if g.GetShape() == pcbnew.SHAPE_T_SEGMENT:
                s, e = g.GetStart(), g.GetEnd()
                c = _clip(pcbnew.ToMM(s.x) - OX, pcbnew.ToMM(s.y) - OY, pcbnew.ToMM(e.x) - OX,
                          pcbnew.ToMM(e.y) - OY, lo, lo, hi_x, hi_y)
            if c and math.hypot(c[2] - c[0], c[3] - c[1]) > 0.2:
                g.SetStart(pt(c[0], c[1]))
                g.SetEnd(pt(c[2], c[3]))
            else:
                fp.Remove(g)

    obstacles = {layer: [] for layer in silk}
    for fp in board.GetFootprints():
        for g in fp.GraphicalItems():           # outlines and the wire pads' labels
            if g.GetLayer() in silk:
                obstacles[g.GetLayer()].append(_bb(g, 0.05))
        for p in fp.Pads():
            if p.IsOnLayer(pcbnew.F_Cu):
                obstacles[pcbnew.F_SilkS].append(_bb(p, 0.1))
            if p.IsOnLayer(pcbnew.B_Cu):
                obstacles[pcbnew.B_SilkS].append(_bb(p, 0.1))

    def free(t, layer) -> bool:
        b = _bb(t, 0.08)
        if b[0] < lo or b[1] < lo or b[2] > hi_x or b[3] > hi_y:
            return False
        return not any(_overlap(b, o) for o in obstacles[layer])

    fps = sorted(board.GetFootprints(), key=lambda f: f.GetReference())
    for fp in fps:
        t = fp.Reference()
        if not t.IsVisible():
            continue
        if fp.GetReference().startswith("TP"):
            t.SetVisible(False)
            continue
        layer = t.GetLayer()
        if layer not in obstacles:              # reference kept on the assembly layer (wire pads)
            continue
        cy = fp.GetCourtyard(pcbnew.F_Cu if fp.GetSide() == 0 else pcbnew.B_Cu).BBox()
        x0, y0 = pcbnew.ToMM(cy.GetLeft()) - OX, pcbnew.ToMM(cy.GetTop()) - OY
        x1, y1 = pcbnew.ToMM(cy.GetRight()) - OX, pcbnew.ToMM(cy.GetBottom()) - OY
        t.SetTextAngleDegrees(0)
        t.SetPosition(pt(0, 0))
        w, h = (lambda b: (b[2] - b[0], b[3] - b[1]))(_bb(t))
        xm, ym, g = (x0 + x1) / 2, (y0 + y1) / 2, 0.15
        cands = [(xm, y0 - h / 2 - g), (xm, y1 + h / 2 + g), (x0 - w / 2 - g, ym), (x1 + w / 2 + g, ym),
                 (x0 + w / 2, y0 - h / 2 - g), (x1 - w / 2, y0 - h / 2 - g), (x0 + w / 2, y1 + h / 2 + g),
                 (x1 - w / 2, y1 + h / 2 + g), (xm, ym)]
        for cx, cyy in cands:
            t.SetPosition(pt(cx, cyy))
            if free(t, layer):
                obstacles[layer].append(_bb(t, 0.05))
                break
        else:
            t.SetVisible(False)

    for text, layer, height in BOARD_TEXTS:
        t = pcbnew.PCB_TEXT(board)
        t.SetText(text)
        t.SetLayer(layer)
        t.SetTextSize(pcbnew.VECTOR2I(mm(height), mm(height)))
        t.SetTextThickness(mm(0.15))
        t.SetMirrored(layer == pcbnew.B_SilkS)
        board.Add(t)
        y = BOARD_H - 1.0
        placed = False
        while y > 1.0 and not placed:
            x = 3.0
            while x < BOARD_W - 3.0:
                t.SetPosition(pt(x, y))
                if free(t, layer):
                    obstacles[layer].append(_bb(t, 0.05))
                    placed = True
                    break
                x += 0.5
            y -= 0.5
        if not placed:
            board.Remove(t)


if __name__ == "__main__":
    b = build()
    pcbnew.SaveBoard(str(CORE / "ko-core.kicad_pcb"), b)
    print(f"board written: {len(list(b.GetFootprints()))} footprints, {b.GetNetCount()} nets")
