#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Core board rev A routing: GND fan-out, power-first autorouting with Freerouting, stitching, zone fill.

Run with KiCad's Python after gen_pcb.py has written the placed board:
    /usr/bin/python3 hardware/core/tools/route_pcb.py              # rebuild from the stored routing
    /usr/bin/python3 hardware/core/tools/route_pcb.py --autoroute  # run Freerouting again, store the result

The autorouted copper is stored as Specctra session files in hardware/core/route/ (one per phase). They
are the source of truth for those tracks, so the board can be rebuilt without Freerouting and the result
does not depend on the router version. The GND fan-out and the stitching vias are computed here and are
deterministic.

--autoroute needs Freerouting (GPL-3.0, https://github.com/freerouting/freerouting) and a Java runtime
it supports (2.5.0 needs Java 25):
    FREEROUTING_JAR=/path/freerouting-2.5.0-executable.jar FREEROUTING_JAVA=/path/to/java
Freerouting runs headless and offline: proxy settings are removed from its environment, analytics off.

Steps:
  0. GND fan-out (here): every SMD GND pad gets a short stub and a via to the In1 GND plane.
  1. Phase "power": supply nets only, on an otherwise empty board, so they get the direct paths.
  2. Phase "signal": all other nets, with the earlier copper locked.
  3. Stitching vias (here) on a grid wherever all layers are free, then all zones are filled.

KiCad's Python API returns broken objects when a second board is loaded in a process that removed zones,
so every step that loads a board runs in its own process (this script calls itself with --step).
"""
import argparse
import json
import math
import os
import pathlib
import re
import subprocess
import sys

import pcbnew

HERE = pathlib.Path(__file__).resolve().parent
CORE = HERE.parent
BOARD = CORE / "ko-core.kicad_pcb"
ROUTE = CORE / "route"
sys.path.insert(0, str(HERE))
import gen_pcb  # noqa: E402
sys.path.insert(0, str(CORE.parent / "tools"))
import maze  # noqa: E402
from gen_pcb import BOARD_W, BOARD_H, OX, OY, POWER_NETS, SUPPLY_NETS  # noqa: E402

# Specctra classes: width/clearance in um, via padstack names as KiCad exports them.
VIA_S = "Via[0-3]_500:250_um"
VIA_P = "Via[0-3]_600:300_um"
CLASSES = {
    "Power":  dict(width=500, clearance=150, via=VIA_P, layers=["F.Cu", "B.Cu"]),
    "Supply": dict(width=300, clearance=150, via=VIA_S, layers=None),
    "Ground": dict(width=300, clearance=150, via=VIA_S, layers=None),
    "USB":    dict(width=200, clearance=150, via=VIA_S, layers=None),
    "Signal": dict(width=150, clearance=150, via=VIA_S, layers=None),
}
PHASES = [
    dict(name="power", classes=["Power", "Supply", "Ground"], passes=30),
    dict(name="signal", classes=["Power", "Supply", "Ground", "USB", "Signal"], passes=60),
    # everything routed so far is locked; only the leftovers are searched for
    dict(name="cleanup", classes=["Power", "Supply", "Ground", "USB", "Signal"], passes=20),
]

FANOUT_VIA = (0.5, 0.25)       # diameter, drill (mm)
STITCH_VIA = (0.6, 0.3)
STITCH_PITCH = 2.5
CLR_VIA = 0.2                  # via copper to other-net copper (net classes ask 0.15)
CLR_STUB = 0.17
PRE_GND_PADS = {("U201", "55"), ("J502", "12")}   # GND pads already tied to a via by the hand routes
EXTRA_GND_VIAS = {("U101", "15"): 2, ("U103", "2"): 2, ("U104", "4"): 2, ("U106", "2"): 2}

# Hand-routed power copper (board mm, origin top-left). Every point was checked against the pad edges for
# >= 0.15 mm clearance; DRC verifies. Tracks: (net, layer, width, points). Vias: (net, (x, y), dia, drill).
PMID, SW, BTST = "/Battery and charger/CHG_PMID", "/Battery and charger/CHG_SW", "/Battery and charger/CHG_BTST"
F, I2, B = "F.Cu", "In2.Cu", "B.Cu"
PRE_TRACKS = [
    # charger (U101): PMID up to its capacitors, 0.2 mm while between the 0.4 mm-pitch pins
    (PMID, F, 0.2, [(6.18, 4.95), (6.18, 3.9)]),
    (PMID, F, 0.35, [(6.18, 3.9), (5.9, 3.4)]),
    (PMID, F, 0.4, [(5.65, 2.3), (6.1, 1.1)]),
    # SW node: up between PMID and GND, then right to the inductor and the bootstrap capacitor
    (SW, F, 0.2, [(6.57, 4.95), (6.57, 4.45), (7.0, 4.05)]),
    (SW, F, 0.6, [(7.0, 4.05), (10.5, 4.05), (10.8, 4.9)]),
    (SW, F, 0.4, [(9.78, 4.05), (9.78, 3.2)]),
    # bootstrap: corner pad -> via -> In2 -> via -> C104 (crosses under PMID and SW)
    (BTST, F, 0.3, [(4.85, 5.38), (4.3, 5.35)]),        # from the L pad's bottom leg
    (BTST, I2, 0.3, [(4.3, 5.35), (8.82, 2.35)]),
    (BTST, F, 0.3, [(8.82, 2.35), (8.82, 3.2)]),
    # VBUS into the charger and its 1 uF capacitor
    ("VBUS", F, 0.2, [(5.775, 5.0), (5.775, 4.25), (5.6, 4.1)]),
    ("VBUS", F, 0.4, [(5.6, 4.1), (3.9, 4.1), (3.4, 3.68)]),
    ("VBUS", F, 0.4, [(3.9, 4.1), (3.4, 4.6), (2.55, 4.25)]),
    # SYS out to the inductor and the SYS capacitors; BAT down to its capacitor
    ("SYS", F, 0.2, [(6.98, 7.4), (6.98, 7.95), (7.3, 8.25)]),
    ("SYS", F, 0.6, [(7.3, 8.25), (10.4, 8.25)]),
    ("SYS", F, 0.8, [(10.5, 7.5), (10.45, 9.4), (10.42, 11.1)]),
    ("VBAT", F, 0.2, [(6.57, 7.4), (6.57, 8.55)]),
    ("VBAT", F, 0.4, [(6.57, 8.55), (6.2, 9.0)]),
    # VBUS: receptacle pads -> vias -> 1 mm bottom trunk -> charger (west) and 5 V mux (south-east)
    ("VBUS", F, 0.6, [(16.55, 7.6), (16.55, 9.75)]),
    ("VBUS", F, 0.6, [(21.45, 7.6), (21.45, 9.0)]),
    ("VBUS", B, 1.0, [(21.45, 9.0), (16.55, 9.0), (13.4, 9.0), (13.4, 4.3), (4.2, 4.3), (3.4, 4.6), (2.55, 4.25)]),
    ("VBUS", B, 1.0, [(16.55, 9.0), (16.55, 9.75)]),
    ("VBUS", B, 1.0, [(21.45, 9.0), (23.0, 10.55), (23.0, 15.1), (25.9, 17.6)]),
    ("VBUS", B, 0.6, [(25.9, 17.6), (24.0, 19.6)]),
    ("VBUS", F, 0.5, [(25.9, 17.6), (25.2, 16.9)]),
    ("VBUS", F, 0.3, [(25.2, 16.75), (26.6, 16.65)]),
    # boost (U104): switch node straight up to the inductor; output via In2 to its capacitors and on to
    # the 5 V mux input (U105 pin 6); mux output pins joined under the package, then to C116
    ("/Power rails/BST_SW", F, 0.3, [(18.31, 18.4), (19.05, 18.4)]),
    ("/Power rails/BST_SW", F, 0.4, [(19.05, 18.4), (19.05, 16.4)]),
    ("VBOOST", F, 0.3, [(18.31, 17.9), (18.31, 17.2)]),
    ("VBOOST", I2, 0.6, [(18.31, 17.2), (19.85, 17.55)]),
    ("VBOOST", F, 0.6, [(19.85, 17.55), (20.6, 17.55)]),
    ("VBOOST", F, 0.6, [(21.0, 17.55), (23.2, 17.55), (23.2, 18.45)]),
    ("VBOOST", I2, 0.8, [(23.2, 18.45), (23.4, 18.55), (27.4, 18.55), (28.85, 18.0)]),
    ("VBOOST", F, 0.3, [(28.14, 16.65), (28.85, 16.65)]),
    ("VBOOST", F, 0.4, [(28.85, 16.65), (28.85, 18.0)]),
    ("V5", F, 0.3, [(26.66, 16.15), (28.7, 16.15), (29.5, 15.9)]),
    ("VBUS", F, 0.2, [(27.95, 17.15), (26.85, 16.65)]),
    # LED rail: LED switch -> via -> 0.8 mm bottom trunk between the test-point rows -> FFC pins 2-4
    ("LED_5V", F, 0.6, [(25.14, 20.85), (25.4, 19.95)]),
    ("LED_5V", B, 0.8, [(25.4, 19.95), (25.4, 21.1), (40.2, 21.1), (40.2, 26.0), (36.8, 26.0), (36.25, 27.1)]),
    ("LED_5V", B, 0.6, [(39.0, 21.1), (39.0, 19.6)]),
    ("LED_5V", B, 0.6, [(25.4, 21.1), (25.25, 21.4), (25.25, 23.6), (23.2, 25.95)]),
    ("LED_5V", F, 0.5, [(23.2, 25.95), (23.2, 25.0)]),
    ("LED_5V", F, 0.5, [(36.25, 27.1), (37.0, 26.7), (37.8, 25.8)]),
    ("LED_5V", F, 0.4, [(36.25, 27.1), (36.25, 27.45)]),
    ("LED_5V", F, 0.3, [(35.75, 27.45), (36.75, 27.45)]),
    ("LED_5V", F, 0.3, [(35.75, 27.45), (35.75, 28.1)]),
    ("LED_5V", F, 0.3, [(36.25, 27.45), (36.25, 28.1)]),
    ("LED_5V", F, 0.3, [(36.75, 27.45), (36.75, 28.1)]),
]
PRE_VIAS = [
    (BTST, (4.3, 5.35), 0.5, 0.25), (BTST, (8.82, 2.35), 0.5, 0.25),
    ("VBUS", (3.4, 4.6), 0.6, 0.3), ("VBUS", (2.55, 4.25), 0.6, 0.3),
    ("VBUS", (16.55, 9.0), 0.6, 0.3), ("VBUS", (16.55, 9.75), 0.6, 0.3), ("VBUS", (21.45, 9.0), 0.6, 0.3),
    ("VBUS", (25.9, 17.6), 0.6, 0.3),
    ("LED_5V", (25.4, 19.95), 0.6, 0.3), ("LED_5V", (36.25, 27.1), 0.6, 0.3),
    ("LED_5V", (37.0, 26.7), 0.6, 0.3), ("LED_5V", (23.2, 25.95), 0.6, 0.3),
    ("VBOOST", (18.31, 17.2), 0.6, 0.3), ("VBOOST", (19.85, 17.55), 0.6, 0.3),
    ("VBOOST", (23.2, 18.45), 0.6, 0.3), ("VBOOST", (28.85, 18.0), 0.6, 0.3),
]
LAYERS = {"F.Cu": pcbnew.F_Cu, "In2.Cu": pcbnew.In2_Cu, "B.Cu": pcbnew.B_Cu}


def switchboard_buses() -> tuple[list, list]:
    """BMD-340 -> FFC J401 buses (0.15 mm), planar thanks to the pin order chosen in gen_schematic.py.

    ROW0-7 run on In2: the four left-column pads escape west to vias, the four inner pads escape north to
    a staircase of vias inside the module outline; all eight turn south, then run at 45 deg to two
    staggered rows of vias above the FFC and drop onto pins 24..17. The shift-register and reserved lines
    (pads 31-35) leave the module's bottom edge on the top layer and run at 45 deg straight into pins 16..10.
    """
    tracks, vias = [], []
    w, via = 0.15, (0.5, 0.25)
    # (net, pad xy, escape-via xy or None, vertical x)   ordered west -> east at the FFC
    rows = [("ROW7", (35.45, 4.75), (34.5, 4.75), 32.0), ("ROW6", (35.45, 5.85), (34.5, 5.85), 32.5),
            ("ROW5", (35.45, 6.95), (34.5, 6.95), 33.0), ("ROW4", (35.45, 8.05), (34.5, 8.05), 33.5),
            ("ROW3", (44.05, 11.2), (44.05, 8.1), 35.0), ("ROW2", (42.95, 11.2), (42.95, 8.6), 35.5),
            ("ROW1", (41.85, 11.2), (41.85, 9.1), 36.0), ("ROW0", (40.75, 11.2), (40.75, 9.6), 36.5)]
    for i, (net, pad, esc, xv) in enumerate(rows):
        c = 50.0 + 0.6 * i                     # diagonal x + y = c, 0.42 mm apart
        xj = 25.75 + 0.5 * i                   # FFC pin 24 - i
        yv = 26.2 if i % 2 == 0 else 26.9      # staggered vias above the FFC
        tracks.append((net, F, w, [pad, esc]))
        vias.append((net, esc) + via)
        tracks.append((net, I2, w, [esc, (xv, esc[1]), (xv, c - xv), (xj, c - xj), (xj, yv)]))
        vias.append((net, (xj, yv)) + via)
        tracks.append((net, F, w, [(xj, yv), (xj, 28.1)]))
    cols = [("RSV_MISO", (37.45, 13.0), 29.75), ("COL_LAT", (38.0, 12.1), 30.25),
            ("COL_DAT", (38.55, 13.0), 30.75), ("COL_CLK", (39.1, 12.1), 31.75), ("RSV_INT", (39.65, 13.0), 32.75)]
    for i, (net, (xu, yu), xj) in enumerate(cols):
        c = 55.5 + 0.6 * i
        tracks.append((net, F, w, [(xu, yu), (xu, c - xu), (xj, c - xj), (xj, 28.1)]))
    return tracks, vias


def expansion_routes() -> tuple[list, list]:
    """BMD-340 -> expansion header J502 (DNP, bottom side, under the module), 0.15 mm.

    The header's pin order was chosen for this (D-35). Pads on the module's top side run down through the
    module interior to vias just above J502's upper pad row; pads on the bottom edge drop to vias between
    J502's two rows, or (TX, MOSI) below the header, and reach their pads on the bottom layer.
    """
    w, via = 0.15, (0.5, 0.25)
    # (net, F.Cu path from the module pad to the via, B.Cu path from the via to the header pad)
    spec = [
        ("GND", [(38.15, 9.7), (38.8, 10.3)], [(38.8, 10.3), (37.6, 11.2)]),   # module pad 55 + J502 pin 12
        ("EXP_IO4", [(39.65, 6.0), (39.65, 9.95), (39.5, 10.35)], [(39.5, 10.35), (38.87, 11.2)]),
        ("EXP_AIN1", [(40.2, 5.1), (40.2, 10.25)], [(40.2, 10.25), (40.14, 11.2)]),
        ("EXP_IO3", [(41.3, 5.1), (41.3, 10.3)], [(41.3, 10.3), (41.4, 11.2)]),
        ("EXP_IO1", [(42.4, 5.1), (42.4, 10.3)], [(42.4, 10.3), (42.68, 11.2)]),
        ("EXP_IO2", [(41.85, 4.2), (41.85, 3.4)], [(41.85, 3.4), (43.5, 5.0), (43.5, 10.6), (43.94, 11.2)]),
        ("EXP_CS", [(40.2, 12.1), (40.2, 14.4)], [(40.2, 14.4), (40.14, 15.0)]),
        ("EXP_RX", [(41.3, 12.1), (41.3, 14.4)], [(41.3, 14.4), (41.4, 15.0)]),
        ("EXP_SCK", [(42.4, 12.1), (42.4, 14.4)], [(42.4, 14.4), (42.68, 15.0)]),
        ("EXP_MISO", [(43.5, 12.1), (43.5, 14.4)], [(43.5, 14.4), (43.94, 15.0)]),
        ("EXP_TX", [(40.75, 13.0), (40.75, 17.75)], [(40.75, 17.75), (39.5, 17.75), (38.87, 17.15)]),
        ("EXP_MOSI", [(42.95, 13.0), (42.95, 18.4)], [(42.95, 18.4), (37.6, 18.4), (37.6, 17.15)]),
    ]
    tracks, vias = [], []
    for net, top, bottom in spec:
        tracks += [(net, F, w, top), (net, B, w, bottom)]
        vias.append((net, top[-1]) + via)
    # module interior escapes to vias outside the band the In2 row bus occupies (y 7.7-10.0)
    for net, path in (("I2C_SDA", [(37.25, 8.05), (38.65, 8.05), (38.65, 6.65)]),
                      ("I2C_SCL", [(37.25, 9.15), (39.15, 9.15), (39.15, 7.35)]),
                      ("CHG_INT", [(40.75, 6.0), (40.75, 7.2)]),
                      ("BOOST_EN", [(41.85, 6.0), (41.85, 7.0)]),
                      ("LED_EN", [(42.95, 6.0), (42.95, 7.0)]),
                      ("LED_FAULT", [(40.75, 4.2), (40.75, 3.45)])):
        tracks.append((net, F, w, path))
        vias.append((net, path[-1]) + via)
    # LED current-limit resistor sits west of the LED switch, its pin east: under the package and around
    tracks.append(("/Power rails/LED_ILIM", F, w, [(25.14, 21.8), (24.0, 21.8), (24.0, 23.45), (21.65, 23.45),
                                                   (21.65, 23.0), (20.09, 23.0), (20.09, 22.6)]))
    return tracks, vias


_bt, _bv = switchboard_buses()
_et, _ev = expansion_routes()
PRE_TRACKS += _bt + _et
PRE_VIAS += _bv + _ev


def mm(v: float) -> int:
    return pcbnew.FromMM(v)


def snap(v: float) -> int:
    """Board coordinate in nm on a 1 um grid (Specctra files carry 0.1 um, so it survives a round trip)."""
    return int(round(v / 1000.0)) * 1000


def net_class(name: str) -> str:
    bare = name.split("/")[-1]
    if name in POWER_NETS or any(p.startswith("*") and bare == p[1:] for p in POWER_NETS):
        return "Power"
    if name in SUPPLY_NETS:
        return "Supply"
    if name == "GND":
        return "Ground"
    if name.startswith("USB_D"):
        return "USB"
    return "Signal"


# --------------------------------------------------------------------------------------------- obstacles
class Obstacles:
    """Copper items with a coarse grid index, for clearance checks of new vias and stubs."""
    CELL = mm(2.0)

    def __init__(self, b: pcbnew.BOARD):
        self.grid: dict[tuple[int, int], list] = {}
        self.keepouts = [z.Outline() for z in b.Zones() if z.GetIsRuleArea() and z.GetDoNotAllowVias()]
        for fp in b.GetFootprints():
            self.keepouts += [z.Outline() for z in fp.Zones() if z.GetIsRuleArea() and z.GetDoNotAllowVias()]
            for p in fp.Pads():
                self.add(p)
        for t in b.GetTracks():
            self.add(t)

    def add(self, item) -> None:
        bb = item.GetBoundingBox()
        for gx in range(bb.GetLeft() // self.CELL, bb.GetRight() // self.CELL + 1):
            for gy in range(bb.GetTop() // self.CELL, bb.GetBottom() // self.CELL + 1):
                self.grid.setdefault((gx, gy), []).append(item)

    def near(self, pt: pcbnew.VECTOR2I) -> list:
        gx, gy = pt.x // self.CELL, pt.y // self.CELL
        seen, out = set(), []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for it in self.grid.get((gx + dx, gy + dy), ()):
                    if id(it) not in seen:
                        seen.add(id(it))
                        out.append(it)
        return out

    def via_ok(self, pt: pcbnew.VECTOR2I, dia: float, own=None) -> bool:
        r = dia / 2
        x, y = pcbnew.ToMM(pt.x) - OX, pcbnew.ToMM(pt.y) - OY
        if not (r + 0.4 <= x <= BOARD_W - r - 0.4 and r + 0.4 <= y <= BOARD_H - r - 0.4):
            return False
        for k in range(8):
            a = k * math.pi / 4
            q = pcbnew.VECTOR2I(pt.x + int(mm(r + 0.1) * math.cos(a)), pt.y + int(mm(r + 0.1) * math.sin(a)))
            if any(o.Contains(q) for o in self.keepouts):
                return False
        for it in self.near(pt):
            gnd = it.GetNetname() == "GND"
            cls = it.GetClass()
            if cls == "PAD":
                clr = 0.12 if (gnd or it is own) else CLR_VIA
            elif cls == "PCB_VIA":
                clr = 0.3 if gnd else CLR_VIA           # keeps hole-to-hole >= 0.25 mm
            else:
                if gnd:
                    continue
                clr = CLR_VIA
            if it.HitTest(pt, mm(r + clr)):
                return False
        return True

    def stub_ok(self, a: pcbnew.VECTOR2I, b: pcbnew.VECTOR2I, width: float, layer: int) -> bool:
        n = max(2, int(math.hypot(b.x - a.x, b.y - a.y) / mm(0.04)))
        acc = mm(width / 2 + CLR_STUB)
        for i in range(n + 1):
            q = pcbnew.VECTOR2I(a.x + (b.x - a.x) * i // n, a.y + (b.y - a.y) * i // n)
            for it in self.near(q):
                if it.GetNetname() == "GND" or not it.IsOnLayer(layer):
                    continue
                if it.HitTest(q, acc):
                    return False
        return True


def add_via(b, obs, pt, dia, drill, net):
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(pt)
    v.SetWidth(mm(dia))
    v.SetDrill(mm(drill))
    v.SetNet(net)
    b.Add(v)
    obs.add(v)
    return v


def add_track(b, obs, a, c, width, layer, net):
    t = pcbnew.PCB_TRACK(b)
    t.SetStart(a)
    t.SetEnd(c)
    t.SetWidth(mm(width))
    t.SetLayer(layer)
    t.SetNet(net)
    b.Add(t)
    obs.add(t)
    return t


# ------------------------------------------------------------------------------------------- GND fan-out
def p_mm(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(snap(mm(OX + x)), snap(mm(OY + y)))


def preroute(b: pcbnew.BOARD) -> int:
    """Add the hand-routed power copper (locked)."""
    n = 0
    for net, layer, width, pts in PRE_TRACKS:
        for a, c in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(p_mm(*a))
            t.SetEnd(p_mm(*c))
            t.SetWidth(mm(width))
            t.SetLayer(LAYERS[layer])
            t.SetNet(b.FindNet(net))
            t.SetLocked(True)
            b.Add(t)
            n += 1
    for net, (x, y), dia, drill in PRE_VIAS:
        v = pcbnew.PCB_VIA(b)
        v.SetPosition(p_mm(x, y))
        v.SetWidth(mm(dia))
        v.SetDrill(mm(drill))
        v.SetNet(b.FindNet(net))
        v.SetLocked(True)
        b.Add(v)
    return n


def gnd_fanout(b: pcbnew.BOARD) -> tuple[int, list[str]]:
    gnd = b.FindNet("GND")
    obs = Obstacles(b)
    pads = []
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == "GND" and not p.HasHole():
                bb = p.GetBoundingBox()
                minor = pcbnew.ToMM(min(bb.GetWidth(), bb.GetHeight()))
                pads.append((minor, fp.GetReference(), p.GetNumber(), p.GetPosition().x, p))
    pads.sort(key=lambda t: t[:4])
    tht_gnd = [p.GetBoundingBox() for fp in b.GetFootprints() for p in fp.Pads()
               if p.GetNetname() == "GND" and p.HasHole()]
    dia, drill = FANOUT_VIA
    vias, done, pending, failed = [], [], [], []
    for minor, ref, num, _, p in pads:
        if (ref, num) in PRE_GND_PADS:
            continue
        layer = pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
        width = max(0.15, min(0.3, minor))
        c = pcbnew.VECTOR2I(snap(p.GetPosition().x), snap(p.GetPosition().y))
        want = EXTRA_GND_VIAS.get((ref, num), 1)
        placed = []
        # reuse a nearby GND via, or a plated GND hole (connector shell), when a clear stub reaches it
        anchors = list(vias)
        for bb in tht_gnd:
            m = mm(0.2)
            anchors.append(pcbnew.VECTOR2I(snap(min(max(c.x, bb.GetLeft() + m), bb.GetRight() - m)),
                                           snap(min(max(c.y, bb.GetTop() + m), bb.GetBottom() - m))))
        for v in sorted(anchors, key=lambda v: (v.x - c.x) ** 2 + (v.y - c.y) ** 2):
            if math.hypot(v.x - c.x, v.y - c.y) > mm(1.0) or len(placed) >= want:
                break
            if obs.stub_ok(c, v, width, layer):
                add_track(b, obs, c, v, width, layer, gnd)
                placed.append(v)
        cands = []
        for k in range(16):
            a = k * math.pi / 8
            for i in range(int(2.0 / 0.05)):
                d = 0.3 + i * 0.05
                q = pcbnew.VECTOR2I(snap(c.x + mm(d) * math.cos(a)), snap(c.y + mm(d) * math.sin(a)))
                cands.append((d + (0.0 if k % 4 == 0 else 0.03), k, q))
        cands.sort(key=lambda t: (t[0], t[1]))
        for _, _, q in cands:
            if len(placed) >= want:
                break
            if any(math.hypot(q.x - v.x, q.y - v.y) < mm(0.9) for v in placed):
                continue
            if obs.via_ok(q, dia, own=p) and obs.stub_ok(c, q, width, layer):
                add_via(b, obs, q, dia, drill, gnd)
                add_track(b, obs, c, q, width, layer, gnd)
                vias.append(q)
                placed.append(q)
        if placed:
            done.append((c, layer))
        else:
            pending.append((ref, num, c, layer, width))
    # pads boxed in by other pads: a stub to a neighbouring GND pad that already has its via
    for ref, num, c, layer, width in pending:
        near = [(math.hypot(o.x - c.x, o.y - c.y), i) for i, (o, lay) in enumerate(done) if lay == layer]
        for d, i in sorted(near):
            o = done[i][0]
            if d > mm(1.6):
                failed.append(f"{ref}.{num}")
                break
            if obs.stub_ok(c, o, width, layer):
                add_track(b, obs, c, o, width, layer, gnd)
                break
        else:
            failed.append(f"{ref}.{num}")
    return len(vias), failed


def stitching(b: pcbnew.BOARD) -> int:
    gnd = b.FindNet("GND")
    obs = Obstacles(b)
    dia, drill = STITCH_VIA
    n = 0
    y = 1.0
    while y < BOARD_H - 0.9:
        x = 1.0
        while x < BOARD_W - 0.9:
            q = pcbnew.VECTOR2I(snap(mm(OX + x)), snap(mm(OY + y)))
            if obs.via_ok(q, dia + 0.2):        # extra margin so pours keep a ring around stitching vias
                add_via(b, obs, q, dia, drill, gnd)
                n += 1
            x += STITCH_PITCH
        y += STITCH_PITCH
    return n


# ----------------------------------------------------------------------------------------- board loading
def load_board(sessions: list[pathlib.Path], lock: bool) -> pcbnew.BOARD:
    """Placed board (built fresh by gen_pcb) + GND fan-out + the given sessions, imported in order."""
    b = gen_pcb.build()
    b.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
    print(f"  hand-routed power: {preroute(b)} segments, {len(PRE_VIAS)} vias")
    nvias, failed = gnd_fanout(b)
    print(f"  GND fan-out: {nvias} vias" + (f", no via for {', '.join(failed)}" if failed else ""))

    def key(t):
        s, e = t.GetStart(), t.GetEnd()
        return (t.GetClass(), t.GetLayer(), round(s.x, -3), round(s.y, -3), round(e.x, -3), round(e.y, -3))

    for ses in sessions:
        kept = [t.Duplicate() for t in b.GetTracks()]     # the importer replaces all tracks
        if not pcbnew.ImportSpecctraSES(b, str(ses)):
            raise SystemExit(f"session import failed: {ses}")
        have = {key(t) for t in b.GetTracks()}
        for t in kept:
            if key(t) not in have:
                b.Add(t)
    if lock:
        for t in b.GetTracks():
            t.SetLocked(True)
    return b


def export_dsn(b: pcbnew.BOARD, path: pathlib.Path, classes: list[str]) -> int:
    """Specctra DSN for one phase: only the nets of `classes`, our class rules, GND plane on In1."""
    for z in list(b.Zones()):
        if not z.GetIsRuleArea() and z.GetZoneName() != "GND plane":
            b.Remove(z)
    if not pcbnew.ExportSpecctraDSN(b, str(path)):
        raise SystemExit("DSN export failed")
    text = path.read_text()
    start = text.index("(network")
    depth, i = 0, start
    while True:
        depth += text[i] == "("
        depth -= text[i] == ")"
        i += 1
        if depth == 0:
            break
    net_re = re.compile(r'\(net ("[^"]*"|\S+)\s*\(pins([^)]*)\)\s*\)')
    # nets that already carry fixed copper must be in the network too, or Freerouting treats that copper
    # as netless and reports it as clashing with its own pads
    wired = {m.group(1).strip('"') for m in re.finditer(r'\(net ("[^"]*"|[^\s)]+)\)', text[i:])}
    nets = []
    for m in net_re.finditer(text, start, i):
        name = m.group(1).strip('"')
        if net_class(name) in classes or name in wired:
            nets.append((name, m.group(0)))
    classes = list(classes) + sorted({net_class(n) for n, _ in nets} - set(classes))
    out = ["(network"] + [f"    {blk}" for _, blk in nets]
    for cname in classes:
        members = [n for n, _ in nets if net_class(n) == cname]
        if not members:
            continue
        c = CLASSES[cname]
        layers = f" (use_layer {' '.join(c['layers'])})" if c["layers"] else ""
        out.append(f"    (class {cname} " + " ".join(f'"{n}"' for n in members))
        out.append(f'      (circuit (use_via "{c["via"]}"){layers})')
        out.append(f"      (rule (width {c['width']}) (clearance {c['clearance']}))")
        out.append("    )")
    out.append("  )")
    path.write_text(text[:start] + "\n".join(out) + text[i:])
    return len(nets)


# --------------------------------------------------------------------------------------------- steps
def step_export(phase: str) -> None:
    names = [ph["name"] for ph in PHASES]
    ph = PHASES[names.index(phase)]
    earlier = [ROUTE / f"ko-core-{n}.ses" for n in names[:names.index(phase)]]
    b = load_board(earlier, lock=True)
    n = export_dsn(b, ROUTE / f"ko-core-{phase}.dsn", ph["classes"])
    print(f"  {n} nets exported")


def step_finish(stitch: bool = True) -> None:
    sessions = [ROUTE / f"ko-core-{ph['name']}.ses" for ph in PHASES]
    sessions = [s for s in sessions if s.exists()]
    b = load_board(sessions, lock=False)
    thin = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetWidth() < mm(0.1)]
    for t in thin:                     # Freerouting neck-down slivers below the 0.1 mm fab minimum
        t.SetWidth(mm(0.1))
    if thin:
        print(f"  widened {len(thin)} neck-down slivers to 0.1 mm")
    nm = add_maze(b)
    if nm:
        print(f"  maze-routed leftovers: {nm} segments")
    dropped = drop_unused_escapes(b) if nm else []     # only once the router has had its chance to use them
    if dropped:
        print(f"  unused escape vias removed: {', '.join(dropped)}")
    if stitch:
        print(f"  stitching: {stitching(b)} vias")
    pcbnew.SaveBoard(str(BOARD), b)
    vias = sum(1 for t in b.GetTracks() if t.GetClass() == "PCB_VIA")
    print(f"board written: {len(b.GetTracks()) - vias} track segments, {vias} vias")


MAZE_JSON = ROUTE / "ko-core-maze.json"
MAZE_WIDTH = {"Power": (0.3, 0.6, 0.3), "Supply": (0.25, 0.5, 0.25), "USB": (0.2, 0.5, 0.25),
              "Ground": (0.25, 0.5, 0.25), "Signal": (0.15, 0.5, 0.25)}   # track, via dia, drill


def drc_unconnected(path: pathlib.Path) -> list:
    out = path.with_suffix(".drc.json")
    subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "-o", str(out), str(path)],
                   capture_output=True)
    data = json.loads(out.read_text())
    out.unlink()
    return data.get("unconnected_items", [])


ESCAPE_NETS = {"I2C_SDA", "I2C_SCL", "CHG_INT", "BOOST_EN", "LED_EN", "LED_FAULT"}


def step_maze() -> None:
    """Route every connection still open with the grid maze router (targeted rip-up); store in MAZE_JSON."""
    b = pcbnew.LoadBoard(str(BOARD))
    r = maze.Router(b, (OX, OY, OX + BOARD_W, OY + BOARD_H), [pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu],
                    clearance=0.18, hole_clearance=0.28)   # margin for the 0.05 mm grid
    names = {"F.Cu": 0, "In2.Cu": 1, "B.Cu": 2}
    escapes = {}
    for net, (x, y), _, _ in PRE_VIAS:
        if net in ESCAPE_NETS:
            escapes.setdefault(net, []).append((OX + x, OY + y))

    def ends(it, net):
        d = it["description"]
        xy = (it["pos"]["x"], it["pos"]["y"])
        for e in escapes.get(net, []):
            if math.dist(e, xy) < 2.5:             # start from the prepared escape via, not the pad
                return [(e[0], e[1], li) for li in range(3)]
        if d.startswith("Via") or "PTH pad" in d:
            return [(xy[0], xy[1], li) for li in (0, 2)]
        for k, li in names.items():
            if f" on {k}" in d:
                return [(xy[0], xy[1], li)]
        return [(xy[0], xy[1], 0)]

    conns = []
    for v in drc_unconnected(BOARD):
        a, c = v["items"][0], v["items"][1]
        m = re.search(r"\[([^\]]+)\]", a["description"])
        if not m or b.FindNet(m.group(1)) is None or m.group(1) == "GND":
            continue
        net = m.group(1)
        prio = {"Power": 0, "Supply": 1, "Ground": 1, "USB": 2, "Signal": 3}[net_class(net)]
        if any(f" of {ref} " in it["description"] for it in (a, c) for ref in ("U201", "U101")):
            prio -= 10                 # escape the dense module and charger pins while there is room
        pa, pc = (a["pos"]["x"], a["pos"]["y"]), (c["pos"]["x"], c["pos"]["y"])
        conns.append((prio, math.dist(pa, pc), net, ends(a, net), ends(c, net)))
    conns.sort(key=lambda t: t[:2])

    # negotiated congestion first: every connection gets a path, fights are priced out over iterations
    spec = []
    for _, _, net, st, go in conns:
        w0, vd, vdr = MAZE_WIDTH[net_class(net)]
        spec.append((b.FindNet(net).GetNetCode(), st, go, w0 / 2, vd / 2, vdr))
    cache = os.environ.get("MAZE_CACHE")              # optional: reuse a negotiation result while tuning
    key = json.dumps([[c[2], c[3], c[4]] for c in conns])
    if cache and pathlib.Path(cache).exists() and json.loads(pathlib.Path(cache).read_text())["key"] == key:
        paths = {int(k): [tuple(p) for p in v] for k, v in json.loads(pathlib.Path(cache).read_text())["paths"].items()}
        print("  negotiation result taken from cache")
    else:
        neg = maze.Negotiator(r)
        paths = neg.run(spec, iters=16, log=print)
        if cache:
            pathlib.Path(cache).write_text(json.dumps({"key": key, "paths": paths}))

    def legal(path, code, hw, vr, dr):
        bt, bv = r.base_track(hw), r.base_via(vr, dr)
        rt_net, _ = r.route_track(hw)
        rv_net, _ = r.route_via(vr, dr)
        ok = ((bt == maze.FREE) | (bt == code)) & ((rt_net == maze.FREE) | (rt_net == code))
        vok = ((bv == maze.FREE) | (bv == code)) & ((rv_net == maze.FREE) | (rv_net == code))
        for k, (x, y, l) in enumerate(path):
            i, j = r.cell(x, y)
            near_end = k < 3 or k > len(path) - 4
            if not ok[l, j, i] and not (near_end and bt[l, j, i] == code):
                return False
            if k and path[k - 1][2] != l and not vok[j, i]:
                return False
        return True

    def try_route(cid, soft=False, use_negotiated=False):
        _, _, net, st, go = conns[cid]
        if use_negotiated and cid in paths:
            code, _, _, hw, vr, dr = spec[cid]
            if legal(paths[cid], code, hw, vr, dr):
                segs, vias = r.simplify(paths[cid], code, hw)
                r.add(cid, code, segs, vias, hw, vr, dr)
                return True
        code = b.FindNet(net).GetNetCode()
        w0, vd, vdr = MAZE_WIDTH[net_class(net)]
        tries = [(w0, 60.0)] if soft else [(w0, 8.0), (w0, 60.0)] + ([(0.15, 60.0)] if w0 > 0.15 else [])
        for w, margin in tries:
            path, crossed = r.route(code, st, go, w / 2, vd / 2, vdr, margin=margin, soft=soft)
            if path:
                if soft:
                    return crossed
                segs, vias = r.simplify(path, code, w / 2)
                r.add(cid, code, segs, vias, w / 2, vd / 2, vdr)
                return True
        return None if soft else False

    def legalize(order):
        for rid in list(r.routes):
            r.remove(rid)
        failed = [cid for cid in order if not try_route(cid, use_negotiated=True)]
        return failed

    def ripup(failed):
        tries, gave_up = {}, []
        while failed:
            cid = failed.pop(0)
            tries[cid] = tries.get(cid, 0) + 1
            crossed = try_route(cid, soft=True) if tries[cid] <= 8 else None
            if not crossed:
                gave_up.append(cid)
                continue
            saved = {x: r.routes[x] for x in crossed if x in r.routes}
            for x in saved:
                r.remove(x)
            if not try_route(cid):
                for x, val in saved.items():
                    net_code, _, (segs, vias, hw, vr, dr) = val
                    r.add(x, net_code, segs, vias, hw, vr, dr)
                gave_up.append(cid)
                continue
            for x in saved:
                if not try_route(x):
                    failed.append(x)
        return gave_up

    order = list(range(len(conns)))
    best = None
    for attempt in range(4):
        failed = legalize(order)
        gave_up = ripup(list(failed))
        print(f"  legalisation {attempt + 1}: {len(conns) - len(gave_up)}/{len(conns)} routed")
        if best is None or len(gave_up) < len(best[0]):
            best = (list(gave_up), dict(r.routes))
        if not gave_up:
            break
        order = gave_up + [c for c in order if c not in gave_up]   # the hard ones first next time
    gave_up = best[0]
    r.routes = best[1]
    r._rt.clear()
    r._rv.clear()
    found = {"tracks": [], "vias": []}
    for cid, (code, _, (segs, vias, hw, vr, dr)) in sorted(r.routes.items()):
        net = conns[cid][2]
        for li, pts in segs:
            found["tracks"].append({"net": net, "layer": ["F.Cu", "In2.Cu", "B.Cu"][li], "width": round(hw * 2, 3),
                                    "points": [[round(x - OX, 4), round(y - OY, 4)] for x, y in pts]})
        for x, y in vias:
            found["vias"].append({"net": net, "x": round(x - OX, 4), "y": round(y - OY, 4),
                                  "dia": round(vr * 2, 3), "drill": dr})
    MAZE_JSON.write_text(json.dumps(found, indent=1) + "\n")
    print(f"  routed {len(r.routes)}/{len(conns)}" +
          (f"; not routed: {', '.join(conns[c][2] for c in gave_up)}" if gave_up else ""))


def add_maze(b: pcbnew.BOARD) -> int:
    if not MAZE_JSON.exists():
        return 0
    data = json.loads(MAZE_JSON.read_text())
    n = 0
    for t in data["tracks"]:
        for a, c in zip(t["points"], t["points"][1:]):
            tr = pcbnew.PCB_TRACK(b)
            tr.SetStart(p_mm(*a))
            tr.SetEnd(p_mm(*c))
            tr.SetWidth(mm(t["width"]))
            tr.SetLayer(LAYERS[t["layer"]])
            tr.SetNet(b.FindNet(t["net"]))
            b.Add(tr)
            n += 1
    for v in data["vias"]:
        via = pcbnew.PCB_VIA(b)
        via.SetPosition(p_mm(v["x"], v["y"]))
        via.SetWidth(mm(v["dia"]))
        via.SetDrill(mm(v["drill"]))
        via.SetNet(b.FindNet(v["net"]))
        b.Add(via)
    return n


def drop_unused_escapes(b: pcbnew.BOARD) -> list:
    """An escape via that nothing continues from (the router found another way) goes, with its stub."""
    gone = []
    for net, (x, y), _, _ in PRE_VIAS:
        if net not in ESCAPE_NETS:
            continue
        c = p_mm(x, y)
        via = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetPosition() == c]
        if not via:
            continue
        touching = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetNetname() == net
                    and (t.GetStart() == c or t.GetEnd() == c)]
        if any(t.GetLayer() != pcbnew.F_Cu for t in touching) or len(touching) > 1:
            continue
        chain = list(touching)                   # walk the stub back to its pad
        ends = {(c.x, c.y)}
        while chain:
            t = chain.pop()
            b.Remove(t)
            for e in (t.GetStart(), t.GetEnd()):
                if (e.x, e.y) in ends:
                    continue
                ends.add((e.x, e.y))
                nxt = [u for u in b.GetTracks() if u.GetClass() == "PCB_TRACK" and u.GetNetname() == net
                       and u.GetLayer() == pcbnew.F_Cu and (u.GetStart() == e or u.GetEnd() == e)]
                if len(nxt) == 1:                # a plain continuation of the stub, not a junction
                    chain += nxt
        for v in via:
            b.Remove(v)
        gone.append(net)
    return gone


def step_fill() -> None:
    """Zone fill on the board as loaded from file: only then is KiCad's rule engine (hole clearance etc.) set up."""
    b = pcbnew.LoadBoard(str(BOARD))
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(str(BOARD), b)
    print("zones filled")


def freerouting(dsn: pathlib.Path, ses: pathlib.Path, passes: int) -> None:
    jar = os.environ.get("FREEROUTING_JAR")
    java = os.environ.get("FREEROUTING_JAVA", "java")
    if not jar:
        raise SystemExit("set FREEROUTING_JAR (and FREEROUTING_JAVA if 'java' is not Java 25+)")
    env = {k: v for k, v in os.environ.items()
           if k not in ("JAVA_TOOL_OPTIONS", "HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy")}
    cmd = [java, "-Djava.awt.headless=true", "-jar", jar, "-de", str(dsn), "-do", str(ses),
           f"--router.autorouter.max_passes={passes}", "--router.fanout.enabled=false",
           "--router.optimizer.enabled=false", "--gui.enabled=false", "--api_server.enabled=false",
           "--usage_and_diagnostic_data.disable_analytics=true"]
    log = ses.with_suffix(".log")
    with open(log, "w") as f:
        subprocess.run(cmd, env=env, stdout=f, stderr=subprocess.STDOUT, check=True)
    best = None
    for line in log.read_text().splitlines():
        m = re.search(r"pass #(\d+).*?\((\d+) unrouted and (\d+) violation", line)
        if m:
            best = m.groups()
    if best:
        print(f"  last pass {best[0]}: {best[1]} unrouted, {best[2]} violations")
    if not ses.exists():
        raise SystemExit(f"Freerouting wrote no session, see {log}")


def run_step(*args: str) -> None:
    r = subprocess.run([sys.executable, __file__, "--step", *args], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        print(line)
    if r.returncode:
        sys.stderr.write("\n".join(l for l in r.stderr.splitlines() if "leak" not in l and "Debug:" not in l))
        raise SystemExit(f"step {args} failed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--autoroute", action="store_true", help="run Freerouting and store new sessions")
    ap.add_argument("--phase", help="with --autoroute: run only this phase")
    ap.add_argument("--maze", action="store_true", help="maze-route the connections still open, then rebuild")
    ap.add_argument("--step", nargs="+", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.step:
        if a.step[0] == "export":
            step_export(a.step[1])
        elif a.step[0] == "finish":
            step_finish(stitch="nostitch" not in a.step)
        elif a.step[0] == "fill":
            step_fill()
        elif a.step[0] == "maze":
            step_maze()
        sys.stdout.flush()
        os._exit(0)          # skip interpreter teardown: SWIG objects of removed items crash on exit
    if a.autoroute:
        ROUTE.mkdir(exist_ok=True)
        for ph in PHASES:
            if a.phase and ph["name"] != a.phase:
                continue
            print(f"phase {ph['name']}:")
            run_step("export", ph["name"])
            freerouting(ROUTE / f"ko-core-{ph['name']}.dsn", ROUTE / f"ko-core-{ph['name']}.ses", ph["passes"])
    if a.maze:
        print("maze (on the board without stitching vias):")
        run_step("finish", "nostitch")
        run_step("fill")
        run_step("maze")
    print("finish:")
    run_step("finish")
    try:
        run_step("fill")
    except SystemExit:                 # the KiCad zone filler occasionally crashes on exit; once more
        run_step("fill")
