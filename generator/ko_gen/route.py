# SPDX-License-Identifier: GPL-3.0-or-later
"""Switch board routing (SWB-009: no manual routing), on the board written by pcb.py.

Layers: F.Cu (switch side, only the switches' holes) carries the straight lines between the key rows,
In1.Cu is a solid GND plane, In2.Cu and B.Cu (parts) take everything the maze router finds.

1. Structured lines (locked), per key row, in the band between this row's LEDs and the next row's sockets:
   y + 7.6 mm   the row's own LED anode line (SW), 0.4 mm
   y + 8.6 mm   the matrix row (ROWn), 0.2 mm
   y + 9.4 / 10.1 / 10.8 mm  further SW lines used in this row (spare lines: wide rows, underglow)
   Each diode cathode and LED anode drops straight down on B.Cu to a via on its line. A line segment between two
   vias is drawn only where it keeps clear of every hole; the maze router closes the rest.
2. GND fan-out: a via beside every bottom-side GND pad (In1 plane), then GND pours on F and B.
3. Everything still open: hardware/tools/maze.py (grid A*, PathFinder negotiation) on F.Cu, In2.Cu and B.Cu.
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import subprocess
import sys
import tempfile

import pcbnew

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "hardware" / "tools"))
import maze  # noqa: E402

from pcb import MB, ML, OX, OY, mm  # noqa: E402

LINE_OWN, LINE_ROW, LINE_SPARE = 7.6, 8.6, (9.4, 10.1, 10.8)
LAYER = {"F.Cu": 0, "In2.Cu": 1, "B.Cu": 2}
KLAYER = [pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
VIA = (0.6, 0.3)


def P(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


class Copper:
    def __init__(self, board):
        self.b = board
        self.holes = []                    # (x, y, r) of every hole, board mm; LED holes as two circles
        for fp in board.GetFootprints():
            for p in fp.Pads():
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    c = p.GetPosition()
                    x, y = pcbnew.ToMM(c.x) - OX, pcbnew.ToMM(c.y) - OY
                    w, h = pcbnew.ToMM(p.GetDrillSize().x), pcbnew.ToMM(p.GetDrillSize().y)
                    if abs(w - h) < 1e-3:
                        self.holes.append((x, y, w / 2))
                    else:                  # vertical slot (LED light hole)
                        r = min(w, h) / 2
                        for t in (-1, 0, 1):
                            self.holes.append((x, y + t * (max(w, h) / 2 - r), r))

    def clear(self, a, c, hw, gap=0.27) -> bool:
        ax, ay = a
        cx, cy = c
        dx, dy = cx - ax, cy - ay
        ll = dx * dx + dy * dy
        for hx, hy, r in self.holes:
            t = 0 if ll == 0 else max(0.0, min(1.0, ((hx - ax) * dx + (hy - ay) * dy) / ll))
            if math.hypot(ax + t * dx - hx, ay + t * dy - hy) < r + hw + gap:
                return False
        return True

    def track(self, net, layer, a, c, w, lock=True):
        t = pcbnew.PCB_TRACK(self.b)
        t.SetStart(P(*a))
        t.SetEnd(P(*c))
        t.SetWidth(mm(w))
        t.SetLayer(layer)
        t.SetNet(net)
        t.SetLocked(lock)
        self.b.Add(t)

    def via(self, net, x, y, lock=True):
        v = pcbnew.PCB_VIA(self.b)
        v.SetPosition(P(x, y))
        v.SetWidth(mm(VIA[0]))
        v.SetDrill(mm(VIA[1]))
        v.SetNet(net)
        v.SetLocked(lock)
        self.b.Add(v)


def pad_xy(board, ref, num):
    fp = board.FindFootprintByReference(ref)
    p = next(p for p in fp.Pads() if p.GetNumber() == num)
    c = p.GetPosition()
    return pcbnew.ToMM(c.x) - OX, pcbnew.ToMM(c.y) - OY, p.GetNet()


def structured(board, b) -> int:
    cu = Copper(board)
    n = 0
    for r in range(b.rows):
        keys = [k for k in b.keys if k.row == r]
        row_cy = min(k.y for k in keys)                     # keys of this row on its nominal line (not ISO enter)
        line = [k for k in sorted(keys, key=lambda k: k.x) if abs(k.y - row_cy) < 1.0]
        spare = sorted({k.led[1] for k in line if k.led and k.led[1] != r and k.led[0] == 0})[:len(LINE_SPARE)]
        yrow = MB + row_cy
        lines = {}                                          # (net, y) -> [x]
        for k in line:
            cx, cy = ML + k.x, MB + k.y
            x, y, net = pad_xy(board, f"D{100 + k.ref}", "1")              # diode cathode
            cu.track(net, pcbnew.B_Cu, (x, y), (x, yrow + LINE_ROW), 0.2)
            cu.via(net, x, yrow + LINE_ROW)
            lines.setdefault((net.GetNetname(), yrow + LINE_ROW, 0.2), []).append((x, net))
            n += 2
            if k.led and k.led[0] == 0 and (k.led[1] == r or k.led[1] in spare):
                off = LINE_OWN if k.led[1] == r else LINE_SPARE[spare.index(k.led[1])]
                x, y, net = pad_xy(board, f"D{300 + k.ref}", "2")          # LED anode
                cu.track(net, pcbnew.B_Cu, (x, y), (x, yrow + off), 0.4)
                cu.via(net, x, yrow + off)
                lines.setdefault((net.GetNetname(), yrow + off, 0.4), []).append((x, net))
                n += 2
        for (name, y, w), xs in lines.items():
            xs.sort(key=lambda t: t[0])
            for (x0, net), (x1, _) in zip(xs, xs[1:]):
                if cu.clear((x0, y), (x1, y), w / 2):
                    cu.track(net, pcbnew.F_Cu, (x0, y), (x1, y), w)
                    n += 1
    return n


def gnd_fanout(board, router) -> int:
    """A via within 1.6 mm of every bottom-side SMD GND pad, on a free spot, with a 0.3 mm stub."""
    gnd = board.FindNet("GND")
    code = gnd.GetNetCode()
    bv = router.base_via(VIA[0] / 2, VIA[1])
    bt = router.base_track(0.15)
    placed = []
    cu = Copper(board)
    n = 0
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() != code or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or not p.IsOnLayer(pcbnew.B_Cu):
                continue
            c = p.GetPosition()
            px, py = pcbnew.ToMM(c.x) - OX, pcbnew.ToMM(c.y) - OY
            if p.GetSize().x > mm(4):                      # large pads (exposed pad) get vias inside
                for dx in (-1.2, 0, 1.2):
                    for dy in (-1.2, 0, 1.2):
                        cu.via(gnd, px + dx, py + dy)
                        n += 1
                continue
            done = False
            for d in (0.9, 1.2, 1.6):
                for ang in range(0, 360, 30):
                    vx, vy = px + d * math.cos(math.radians(ang)), py + d * math.sin(math.radians(ang))
                    i, j = router.cell(vx + OX, vy + OY)
                    if not (0 <= i < router.nx and 0 <= j < router.ny):
                        continue
                    if bv[j, i] not in (maze.FREE, code) or any(math.hypot(vx - a, vy - b_) < 0.95 for a, b_ in placed):
                        continue
                    steps = 8
                    ok = all(bt[2][router.cell(OX + px + (vx - px) * s / steps, OY + py + (vy - py) * s / steps)[::-1]]
                             in (maze.FREE, code) for s in range(steps + 1))
                    if ok:
                        cu.track(gnd, pcbnew.B_Cu, (px, py), (vx, vy), 0.3)
                        cu.via(gnd, vx, vy)
                        placed.append((vx, vy))
                        n += 1
                        done = True
                        break
                if done:
                    break
    return n


def drc_unconnected(pcb: pathlib.Path) -> list:
    out = pathlib.Path(tempfile.mkdtemp()) / "drc.json"
    subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "--severity-error", "-o", str(out), str(pcb)],
                   capture_output=True)
    return json.loads(out.read_text()).get("unconnected_items", [])


def ends(item):
    d = item["description"]
    x, y = item["pos"]["x"], item["pos"]["y"]           # KiCad page mm, as the router works in
    if "PTH pad" in d or d.startswith("Via"):
        return [(x, y, li) for li in range(3)]
    for name, li in LAYER.items():
        if f"on {name}" in d:
            return [(x, y, li)]
    return [(x, y, li) for li in range(3)]


def half_width(board, net: str, ends_desc: str) -> float:
    if net == "VBUS_B":
        return 0.3
    if " of U2" in ends_desc:                    # LED driver pads at 0.4 mm pitch: thin entry
        return 0.1
    if net.startswith("USB_B_D"):
        return 0.15
    if net == "LED_5V" or "_SW" in net:
        return 0.15
    return 0.1


def route(board_path: pathlib.Path, b, iters=40, workers=None) -> None:
    board = pcbnew.LoadBoard(str(board_path))
    print(f"  structured lines: {structured(board, b)} items")
    bb = board.GetBoardEdgesBoundingBox()
    box = (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()), pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))
    r0 = maze.Router(board, box, KLAYER, clearance=0.18, hole_clearance=0.28)
    print(f"  GND fan-out: {gnd_fanout(board, r0)} vias")
    pcbnew.SaveBoard(str(board_path), board)

    items = drc_unconnected(board_path)
    conns, nets = [], []
    for it in items:
        a, c = it["items"][0], it["items"][1]
        net = a["description"].split("[", 1)[1].split("]", 1)[0] if "[" in a["description"] else ""
        if not net or net == "GND":
            continue
        ni = board.FindNet(net)
        if ni is None:
            continue
        hw = half_width(board, net, a["description"] + c["description"])
        conns.append((ni.GetNetCode(), ends(a), ends(c), hw, VIA[0] / 2, VIA[1]))
        nets.append(net)
    print(f"  maze: {len(conns)} connections")
    board = pcbnew.LoadBoard(str(board_path))
    r = maze.Router(board, box, KLAYER, clearance=0.18, hole_clearance=0.28)
    neg = maze.Negotiator(r)
    paths = neg.run(conns, iters=iters, workers=workers or os.cpu_count(), max_nodes=4_000_000,
                    log=lambda s: print(s, flush=True))
    bad = neg.conflicts(conns, {})
    cu = Copper(board)
    done = 0
    for cid, path in paths.items():
        if cid in bad or not path:
            continue
        code, hw = conns[cid][0], conns[cid][3]
        net = board.FindNet(nets[cid])
        segs, vias = r.simplify(path, code, hw)
        for layer, pts in segs:
            for p0, p1 in zip(pts, pts[1:]):
                cu.track(net, KLAYER[layer], (p0[0] - OX, p0[1] - OY), (p1[0] - OX, p1[1] - OY), 2 * hw, lock=False)
        for x, y in vias:
            cu.via(net, x - OX, y - OY, lock=False)
        done += 1
    print(f"  maze: {done} of {len(conns)} routed, {len(bad)} in conflict, "
          f"{sum(1 for c in range(len(conns)) if c not in paths)} not found")
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    pcbnew.SaveBoard(str(board_path), board)
