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
import shutil
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
PRE_GND_PADS = {("U106", "2"), ("U303", "3"), ("U201", "45"), ("C114", "2"), ("C115", "2"),
                ("R311", "2"), ("R312", "2")}   # U303.3: through the top pour (a via there walls
# in OV2); U201.45: hand-routed via clear of SWDIO's only way out   # GND pads tied to a via by the hand routes
EXTRA_GND_VIAS = {("U101", "15"): 2, ("U103", "2"): 2, ("U104", "4"): 2, ("U106", "2"): 2}

# Hand-routed power copper (board mm, origin top-left). Every point was checked against the pad edges for
# >= 0.15 mm clearance; DRC verifies. Tracks: (net, layer, width, points). Vias: (net, (x, y), dia, drill).
PMID, SW, BTST = "/Battery and charger/CHG_PMID", "/Battery and charger/CHG_SW", "/Battery and charger/CHG_BTST"
F, I2, B = "F.Cu", "In2.Cu", "B.Cu"
BST_SW, LED_ILIM = "/Power rails/BST_SW", "/Power rails/LED_ILIM"


def _turned(tracks: list, vias: list) -> tuple[list, list]:
    """Hand routes of the rails block, which gen_pcb.py turned by 90 degrees (gen_pcb.RAILS_ROT)."""
    rot = gen_pcb.rot90
    return ([(n, layer, w, [rot(*q) for q in pts]) for n, layer, w, pts in tracks],
            [(n, rot(*q), dia, drill) for n, q, dia, drill in vias])


def _moved(tracks: list, vias: list, d: tuple) -> tuple[list, list]:
    """Hand routes of a block of parts that gen_pcb.py moved as a whole by d = (dx, dy)."""
    dx, dy = d
    mv = lambda x, y: (round(x + dx, 3), round(y + dy, 3))
    return ([(n, layer, w, [mv(*q) for q in pts]) for n, layer, w, pts in tracks],
            [(n, mv(*q), dia, drill) for n, q, dia, drill in vias])


# Charger (U101), routed on the 50 x 32 mm board and moved with its parts (gen_pcb.CHARGER_SHIFT).
_ct, _cv = _moved([
    # PMID up to its capacitors, 0.2 mm while between the 0.4 mm-pitch pins
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
    # VBUS into the charger and its 1 uF capacitor (the trunk arrives at the two vias)
    ("VBUS", F, 0.2, [(5.775, 5.0), (5.775, 4.25), (5.6, 4.1)]),
    ("VBUS", F, 0.4, [(5.6, 4.1), (3.9, 4.1), (3.4, 3.68)]),
    ("VBUS", F, 0.4, [(3.9, 4.1), (3.4, 4.6), (2.55, 4.25)]),
    # SYS out to the inductor and the SYS capacitors; BAT down to its capacitor
    ("SYS", F, 0.2, [(6.98, 7.4), (6.98, 7.95), (7.3, 8.25)]),
    ("SYS", F, 0.6, [(7.3, 8.25), (10.4, 8.25)]),
    ("SYS", F, 0.8, [(10.5, 7.5), (10.45, 9.4), (10.42, 11.1)]),
    ("VBAT", F, 0.2, [(6.57, 7.4), (6.57, 8.55)]),
    ("VBAT", F, 0.4, [(6.57, 8.55), (6.2, 9.0)]),
], [
    (BTST, (4.3, 5.35), 0.5, 0.25), (BTST, (8.82, 2.35), 0.5, 0.25),
    ("VBUS", (3.4, 4.6), 0.6, 0.3), ("VBUS", (2.55, 4.25), 0.6, 0.3),
], gen_pcb.CHARGER_SHIFT)

# Boost (U104), 5 V mux (U105) and LED rail switch (U106), turned with their parts (gen_pcb.RAILS_ROT).
_rt, _rv = _turned([
    # boost switch node straight up to the inductor; output via In2 to its capacitors and on to the 5 V mux
    # input (U105 pin 6); mux output pins joined under the package, then to C116
    (BST_SW, F, 0.3, [(18.31, 18.4), (19.05, 18.4)]),
    (BST_SW, F, 0.4, [(19.05, 18.4), (19.05, 16.4)]),
    ("VBOOST", F, 0.3, [(18.31, 17.9), (18.31, 17.2)]),
    ("VBOOST", I2, 0.6, [(18.31, 17.2), (19.85, 17.55)]),
    ("VBOOST", F, 0.6, [(19.85, 17.55), (20.6, 17.55)]),
    ("VBOOST", F, 0.6, [(21.0, 17.55), (24.3, 17.55)]),
    ("VBOOST", I2, 0.8, [(24.3, 17.55), (25.3, 18.55), (27.4, 18.55), (28.85, 18.0)]),
    ("VBOOST", F, 0.3, [(28.14, 16.65), (28.85, 16.65)]),
    ("VBOOST", F, 0.4, [(28.85, 16.65), (28.85, 18.0)]),
    ("V5", F, 0.3, [(26.66, 16.15), (28.7, 16.15), (29.5, 15.9)]),
    # mux output -> LED switch input (up to 1.7 A): from C116 via In2 round the boost output to U106 pin 1
    ("V5", F, 0.5, [(30.0, 15.6), (30.8, 15.6), (30.8, 16.6)]),
    ("V5", I2, 0.5, [(30.8, 16.6), (22.3, 16.6), (22.3, 19.2), (22.7, 19.6)]),
    ("V5", F, 0.5, [(22.7, 19.6), (22.75, 20.8)]),
    ("V5", F, 0.3, [(22.7, 19.6), (23.04, 18.9)]),
    # VBUS from the trunk via into the 5 V mux and its capacitor
    ("VBUS", F, 0.2, [(27.95, 17.15), (26.85, 16.65)]),
    ("VBUS", F, 0.5, [(25.9, 17.6), (25.2, 16.9)]),
    ("VBUS", F, 0.3, [(25.2, 16.75), (26.6, 16.65)]),
    # LED rail out of U106 to the bottom layer (trunk below) and to C118
    ("LED_5V", F, 0.6, [(25.14, 20.85), (25.4, 19.95)]),
    ("LED_5V", B, 0.6, [(25.4, 19.95), (25.4, 21.1), (25.25, 21.4), (25.25, 23.6), (23.2, 25.95)]),
    ("LED_5V", F, 0.5, [(23.2, 25.95), (23.2, 25.0)]),
    # LED current-limit resistor west of the switch, its pin east: under the package and around
    (LED_ILIM, F, 0.15, [(25.14, 21.8), (24.0, 21.8), (24.0, 23.45), (21.6, 23.45), (21.2, 23.6)]),
    ("LED_EN", F, 0.15, [(22.86, 22.75), (21.6, 22.5), (21.2, 22.4)]),
    ("GND", F, 0.3, [(22.86, 21.8), (21.75, 21.8)]),       # LED switch GND pin, boxed in
], [
    ("LED_5V", (25.4, 19.95), 0.6, 0.3), ("LED_5V", (23.2, 25.95), 0.6, 0.3),
    ("V5", (30.8, 16.6), 0.6, 0.3), ("V5", (22.7, 19.6), 0.6, 0.3),
    ("VBOOST", (18.31, 17.2), 0.6, 0.3), ("VBOOST", (19.85, 17.55), 0.6, 0.3),
    ("VBOOST", (24.3, 17.55), 0.6, 0.3), ("VBOOST", (28.85, 18.0), 0.6, 0.3),
    ("VBUS", (25.9, 17.6), 0.6, 0.3),
    ("GND", (21.75, 21.8), 0.5, 0.25),
])

# Strip-specific copper (D-43, 16 x 80 mm). Floor plan from the back: USB-C and VBUS mux, 5 V block (turned),
# crystal, module across the full width, charger (moved), LDO and fuel gauge, battery.
#  - VBUS_B: contacts 1-3 joined on top, into the TPS2121's IN2 and its capacitor.
#  - VBUS_A: both receptacle VBUS pads; the right one reaches the left one on the bottom layer under the ESD
#    arrays (the data and CC lines cross above it on In2), the left one runs on top round the dividers to IN1.
#  - VBUS: the TPS2121's two OUT pads joined under the package, one 0.8/0.4 via, then a 1 mm bottom trunk along
#    the castellated edge to the 5 V mux and on under the module to the charger.
#  - USB port A: D- pads joined on top and straight into the ESD array; D+ pads through vias, across on In2.
#    CC1 straight down, CC2 across on In2 to the CC array's far pin.
#  - SYS: from the charger's SYS capacitors on a 1 mm bottom trunk under the module to the boost input.
#  - VBAT: from the charger's BAT capacitor on top past the fuel gauge to the battery connector.
#  - LED_5V: from the LED switch on In2 to contacts 14-16 and on the bottom layer to the underglow pads.
STRIP_TRACKS = [
    ("VBUS_B", F, 0.8, [(1.2, 1.0), (1.2, 5.0)]),
    ("VBUS_B", F, 0.4, [(1.2, 1.68), (2.75, 1.68)]),
    ("VBUS_B", F, 0.6, [(1.2, 4.6), (2.7, 4.6)]),
    ("VBUS_B", F, 0.4, [(2.7, 4.6), (3.1, 4.35), (3.53, 4.35)]),
    ("VBUS", F, 0.4, [(3.53, 3.65), (4.88, 3.65)]),
    ("VBUS", F, 0.4, [(2.5, 3.5), (3.0, 3.65), (3.53, 3.65)]),
    ("VBUS", B, 1.0, [(2.5, 3.5), (2.6, 4.0), (2.6, 5.5)]),
    ("VBUS", B, 0.8, [(2.6, 5.5), (2.6, 14.5)]),           # 0.8 mm past the dividers' and C304's GND vias
    ("VBUS", B, 1.0, [(2.6, 14.5), (2.6, 19.0), (3.3, 19.7), (6.9, 19.7)]),
    # on to the charger inside the castellated edge's lane, so the matrix lines to contacts 18-33 keep the bottom
    # layer along the edge in front of the module
    ("VBUS", B, 1.0, [(3.3, 19.7), (3.3, 37.0), (5.65, 39.35), (5.65, 53.25), (6.5, 53.6)]),
    ("VBUS_A", F, 0.6, [(8.4, 6.12), (8.4, 7.45)]),
    ("VBUS_A", F, 0.5, [(8.4, 7.15), (5.53, 7.15), (5.53, 4.35), (4.88, 4.35)]),
    ("VBUS_A", F, 0.6, [(13.2, 6.12), (13.2, 7.45)]),
    ("VBUS_A", B, 0.6, [(8.4, 7.45), (8.4, 9.4), (13.2, 9.4), (13.2, 7.45)]),
    ("/USB/USB_A_DN", F, 0.2, [(10.55, 6.12), (10.55, 8.45)]),
    ("/USB/USB_A_DN", F, 0.2, [(11.55, 6.12), (11.55, 7.95), (10.55, 7.95)]),
    ("/USB/USB_A_DP", F, 0.2, [(10.05, 6.12), (10.05, 7.35)]),
    ("/USB/USB_A_DP", F, 0.2, [(11.05, 6.12), (11.05, 7.35)]),
    ("/USB/USB_A_DP", I2, 0.2, [(10.05, 7.35), (11.05, 7.35), (11.7, 8.0), (11.7, 11.65)]),
    ("/USB/USB_A_DP", F, 0.2, [(11.7, 11.65), (11.1, 11.05), (11.1, 10.35)]),
    ("CC1", F, 0.15, [(12.05, 6.12), (12.05, 7.5), (12.66, 8.1), (12.66, 8.45)]),
    ("CC2", F, 0.15, [(9.05, 6.12), (9.05, 6.95), (9.2, 7.4)]),
    ("CC2", I2, 0.15, [(9.2, 7.4), (9.2, 12.25), (12.4, 12.25), (12.7, 11.95), (12.7, 11.65)]),
    ("CC2", F, 0.15, [(12.7, 11.65), (12.66, 10.35)]),
    ("/USB/USB_SEL", F, 0.15, [(4.95, 2.85), (5.25, 2.6), (5.65, 2.6)]),   # ST pin boxed in: via to In2
    ("GND", F, 0.25, [(11.15, 45.9), (11.2, 46.9), (11.25, 47.45)]),         # module pad 45, beside SWDIO
    ("GND", F, 0.3, [(4.95, 22.4), (4.95, 21.2)]),                           # boost output cap C114, beside VBUS
    ("CC1_B", F, 0.2, [(1.6, 53.49), (2.65, 53.49)]),                        # port B Rd at the edge: contact 21,
    ("GND", F, 0.3, [(2.65, 54.51), (2.65, 55.15)]),                         #   its GND via against the edge
    ("CC2_B", F, 0.2, [(1.6, 57.49), (2.65, 57.49)]),                        #   contact 23
    ("GND", F, 0.3, [(2.65, 58.51), (2.65, 59.15)]),
    ("GND", F, 0.25, [(5.22, 20.4), (4.95, 21.2)]),                          # and the mux input cap C115
    ("SYS", F, 0.8, [(13.52, 59.25), (12.4, 59.25)]),
    ("SYS", B, 1.0, [(12.4, 59.25), (12.4, 53.6), (10.3, 51.5), (10.3, 31.7), (9.6, 31.0)]),   # clear of the charger's GND vias
    ("SYS", F, 0.8, [(9.6, 31.0), (8.67, 31.0)]),
    ("SYS", B, 1.0, [(9.6, 31.0), (9.0, 30.4), (4.9, 30.4)]),
    ("SYS", F, 0.8, [(4.9, 30.4), (4.9, 29.07)]),
    ("SYS", F, 0.3, [(8.2, 28.71), (8.2, 29.35)]),
    ("SYS", F, 0.6, [(8.2, 29.35), (8.67, 29.8), (8.67, 31.0)]),
    ("VBAT", F, 0.8, [(9.12, 58.4), (8.55, 58.95), (8.55, 61.85), (8.9, 62.2), (8.9, 68.8), (6.4, 69.4), (6.4, 70.6)]),
    ("LED_5V", I2, 1.0, [(9.25, 20.2), (10.0, 20.95), (10.0, 24.4), (3.0, 24.4), (3.0, 27.0), (1.2, 27.0), (1.2, 31.0)]),
    ("LED_5V", B, 0.6, [(9.25, 20.2), (9.75, 20.7), (9.75, 26.7)]),
]
STRIP_VIAS = [
    ("VBUS", (2.5, 3.5), 0.8, 0.4),
    ("VBUS_A", (8.4, 7.45), 0.6, 0.3), ("VBUS_A", (13.2, 7.45), 0.6, 0.3),
    ("/USB/USB_A_DP", (10.05, 7.35), 0.5, 0.25), ("/USB/USB_A_DP", (11.05, 7.35), 0.5, 0.25),
    ("/USB/USB_A_DP", (11.7, 11.65), 0.5, 0.25),
    ("CC2", (9.2, 7.4), 0.5, 0.25), ("CC2", (12.7, 11.65), 0.5, 0.25),
    ("SYS", (12.4, 59.25), 0.8, 0.4), ("SYS", (9.6, 31.0), 0.8, 0.4), ("SYS", (4.9, 30.4), 0.8, 0.4),
    ("/USB/USB_SEL", (5.65, 2.6), 0.5, 0.25), ("GND", (11.25, 47.45), 0.5, 0.25), ("GND", (4.95, 21.2), 0.5, 0.25),
    ("GND", (2.65, 55.15), 0.5, 0.25), ("GND", (2.65, 59.15), 0.5, 0.25),
]
PRE_TRACKS = _ct + _rt + STRIP_TRACKS
PRE_VIAS = _cv + _rv + STRIP_VIAS
LAYERS = {"F.Cu": pcbnew.F_Cu, "In2.Cu": pcbnew.In2_Cu, "B.Cu": pcbnew.B_Cu}


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


def bridge_narrow_forks(b: pcbnew.BOARD, max_angle: float = 25.0, at: float = 0.5) -> int:
    """Two tracks of one net that leave (nearly) the same point less than max_angle apart leave a thin
    V-shaped notch between them, which KiCad reports as a copper sliver. A short bridge between the two
    tracks, `at` mm from the fork, closes the tip of the V. The bridge lies inside the gap between the two
    tracks (at most a few hundredths of a mm wide), so it cannot come closer to anything else than they do.
    Both tracks are split at the bridge ends, so every track end meets another track end."""
    segs = {}
    for t in b.GetTracks():
        if t.GetClass() == "PCB_TRACK" and t.GetLength() > mm(0.05):
            segs.setdefault((t.GetNetCode(), t.GetLayer()), []).append(t)
    splits, bridges = {}, []
    for (net, layer), ts in segs.items():
        ends = []                      # (fork point, unit direction away from it, length, width, track)
        for t in ts:
            a = (t.GetStart().x / 1e6, t.GetStart().y / 1e6)
            e = (t.GetEnd().x / 1e6, t.GetEnd().y / 1e6)
            n = math.dist(a, e)
            for p, q in ((a, e), (e, a)):
                ends.append((p, ((q[0] - p[0]) / n, (q[1] - p[1]) / n), n, t.GetWidth() / 1e6, t))
        done = set()
        for i, (p1, d1, n1, w1, t1) in enumerate(ends):
            for j in range(i + 1, len(ends)):
                p2, d2, n2, w2, t2 = ends[j]
                if t1 is t2 or math.dist(p1, p2) > 0.15 or n1 < at + 0.1 or n2 < at + 0.1:
                    continue
                cos = d1[0] * d2[0] + d1[1] * d2[1]
                if cos > 0.9999 or math.degrees(math.acos(max(-1.0, min(1.0, cos)))) >= max_angle:
                    continue           # collinear (overlapping trunk) or wide enough
                q1 = (mm(p1[0] + d1[0] * at), mm(p1[1] + d1[1] * at))
                q2 = (mm(p2[0] + d2[0] * at), mm(p2[1] + d2[1] * at))
                if (q1, q2) in done or math.dist(q1, q2) < mm(0.01):
                    continue
                done.add((q1, q2))
                for t, q in ((t1, q1), (t2, q2)):
                    splits.setdefault(t.m_Uuid.AsString(), (t, set()))[1].add(q)
                bridges.append((q1, q2, mm(min(w1, w2)), layer, net))
    for t, pts in splits.values():
        a = (t.GetStart().x, t.GetStart().y)
        chain = [a] + sorted(pts, key=lambda q: math.dist(a, q)) + [(t.GetEnd().x, t.GetEnd().y)]
        t.SetEnd(pcbnew.VECTOR2I(*chain[1]))
        for u, v in zip(chain[1:-1], chain[2:]):
            bridges.append((u, v, t.GetWidth(), t.GetLayer(), t.GetNetCode()))
    for u, v, w, layer, net in bridges:
        tr = pcbnew.PCB_TRACK(b)
        tr.SetStart(pcbnew.VECTOR2I(*u))
        tr.SetEnd(pcbnew.VECTOR2I(*v))
        tr.SetWidth(w)
        tr.SetLayer(layer)
        tr.SetNetCode(net)
        b.Add(tr)
    return len(bridges) - sum(len(pts) for _, pts in splits.values())


def step_finish(stitch: bool = True, use_maze: bool = True) -> None:
    sessions = [ROUTE / f"ko-core-{ph['name']}.ses" for ph in PHASES]
    sessions = [s for s in sessions if s.exists()]
    b = load_board(sessions, lock=False)
    thin = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetWidth() < mm(0.1)]
    for t in thin:                     # Freerouting neck-down slivers below the 0.1 mm fab minimum
        t.SetWidth(mm(0.1))
    if thin:
        print(f"  widened {len(thin)} neck-down slivers to 0.1 mm")
    nm = add_maze(b) if use_maze else 0
    if nm:
        print(f"  maze-routed leftovers: {nm} segments")
    dropped = drop_unused_escapes(b) if nm else []     # only once the router has had its chance to use them
    if dropped:
        print(f"  unused escape vias removed: {', '.join(dropped)}")
    if nm:
        lone = drop_single_layer_vias(b)
        if lone:
            print(f"  vias joining only one layer removed: {lone}")
        stubs = drop_dangling_tracks(b)
        if stubs:
            print(f"  dangling router stubs removed: {stubs}")
    forks = bridge_narrow_forks(b)
    if forks:
        print(f"  narrow forks bridged: {forks}")
    if stitch:
        print(f"  stitching: {stitching(b)} vias")
    pcbnew.SaveBoard(str(BOARD), b)
    vias = sum(1 for t in b.GetTracks() if t.GetClass() == "PCB_VIA")
    print(f"board written: {len(b.GetTracks()) - vias} track segments, {vias} vias")


MAZE_JSON = ROUTE / "ko-core-maze.json"
MAZE_WIDTH = {"Power": (0.3, 0.6, 0.3), "Supply": (0.25, 0.5, 0.25), "USB": (0.2, 0.5, 0.25),
              "Ground": (0.25, 0.5, 0.25), "Signal": (0.15, 0.5, 0.25)}   # track, via dia, drill


def drc_violations(path: pathlib.Path) -> list:
    out = path.with_suffix(".drcv.json")
    subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "-o", str(out), str(path)], capture_output=True)
    data = json.loads(out.read_text())
    out.unlink()
    return data.get("violations", [])


def drc_unconnected(path: pathlib.Path) -> list:
    out = path.with_suffix(".drc.json")
    subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "-o", str(out), str(path)],
                   capture_output=True)
    data = json.loads(out.read_text())
    out.unlink()
    return data.get("unconnected_items", [])


ESCAPE_NETS: set = set()      # nets whose hand routes end in an escape via the router should start from


def conn_ends(it, net):
    """Start/goal points of one end of a DRC 'unconnected' pair: (x, y, layer index) candidates."""
    names = {"F.Cu": 0, "In2.Cu": 1, "B.Cu": 2}
    d = it["description"]
    xy = (it["pos"]["x"], it["pos"]["y"])
    for n, (x, y), _, _ in PRE_VIAS:
        if n == net and net in ESCAPE_NETS and math.dist((OX + x, OY + y), xy) < 2.5:
            return [(OX + x, OY + y, li) for li in range(3)]     # the prepared escape via, not the pad
    if "of J401" in d:                 # castellated contact: the hole sits on the board edge, start in its copper
        return [(xy[0] + 1.2, xy[1], li) for li in (0, 1, 2)]
    if d.startswith("Via") or "PTH pad" in d:
        return [(xy[0], xy[1], li) for li in (0, 2)]
    for k, li in names.items():
        if f" on {k}" in d:
            return [(xy[0], xy[1], li)]
    return [(xy[0], xy[1], 0)]


def step_maze() -> None:
    """Route every connection still open with the grid maze router (targeted rip-up); store in MAZE_JSON.
    With MAZE_MERGE=1 the routes already stored (and on the board) stay, and the new ones are added to them."""
    keep = json.loads(MAZE_JSON.read_text()) if os.environ.get("MAZE_MERGE") and MAZE_JSON.exists() else None
    b = pcbnew.LoadBoard(str(BOARD))
    r = maze.Router(b, (OX, OY, OX + BOARD_W, OY + BOARD_H), [pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu],
                    clearance=0.18, hole_clearance=0.28)   # margin for the 0.05 mm grid
    islands = {}

    def ends(it, net):
        """Start/goal points: every point of the copper island the DRC item belongs to (a hand-routed stub
        then counts as a whole, not just the end DRC happens to name), else conn_ends."""
        if net not in islands:
            islands[net] = net_islands(b, net)
        q = pcbnew.VECTOR2I(int(round(it["pos"]["x"] * 1e6)), int(round(it["pos"]["y"] * 1e6)))
        hit = [g for g in islands[net] if any(item.HitTest(q, 20000) for item, _ in g)]
        pts = []
        for item, pp in (hit[0] if hit else []):
            ref = item.GetParentFootprint().GetReference() if item.GetClass() == "PAD" else ""
            if ref == "J401":                          # castellated contact: start in its copper, not on the edge
                pts += [(x + 1.2, y, li) for x, y, li in pp]
            else:
                pts += pp
        return pts[:60] or conn_ends(it, net)
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
    cached = None
    if cache and pathlib.Path(cache).exists():         # matched per connection: DRC lists them in varying order
        old = json.loads(pathlib.Path(cache).read_text())
        by_conn = {json.dumps(k): old["paths"].get(str(i)) for i, k in enumerate(json.loads(old["key"]))}
        mine = [json.dumps([c[2], c[3], c[4]]) for c in conns]
        hit = {i: [tuple(p) for p in by_conn[m]] for i, m in enumerate(mine) if by_conn.get(m)}
        if len(hit) >= 0.9 * len(conns):              # the rest (DRC picked other end points) is routed fresh
            cached = hit
    if cached is not None:
        paths = cached
        print(f"  negotiation result taken from cache ({len(cached)} of {len(conns)} connections)")
    else:
        neg = maze.Negotiator(r)
        paths = neg.run(spec, iters=16, log=print, workers=int(os.environ.get("MAZE_WORKERS", os.cpu_count() or 1)),
                        max_nodes=1_200_000)
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

    def save(routes) -> None:
        found = {"tracks": [], "vias": []}
        for cid, (code, _, (segs, vias, hw, vr, dr)) in sorted(routes.items()):
            net = conns[cid][2]
            for li, pts in segs:
                found["tracks"].append({"net": net, "layer": ["F.Cu", "In2.Cu", "B.Cu"][li], "width": round(hw * 2, 3),
                                        "points": [[round(x - OX, 4), round(y - OY, 4)] for x, y in pts]})
            for x, y in vias:
                found["vias"].append({"net": net, "x": round(x - OX, 4), "y": round(y - OY, 4),
                                      "dia": round(vr * 2, 3), "drill": dr})
        MAZE_JSON.write_text(json.dumps(found, indent=1) + "\n")

    order = list(range(len(conns)))
    best = None
    for attempt in range(int(os.environ.get("MAZE_ATTEMPTS", "4"))):
        failed = legalize(order)
        gave_up = ripup(list(failed))
        print(f"  legalisation {attempt + 1}: {len(conns) - len(gave_up)}/{len(conns)} routed" +
              (f"; open: {', '.join(sorted(conns[c][2] for c in gave_up))}" if gave_up else ""), flush=True)
        if best is None or len(gave_up) < len(best[0]):
            best = (list(gave_up), dict(r.routes))
            save(best[1])                              # kept after every attempt: a long run may be cut off
        if not gave_up:
            break
        order = gave_up + [c for c in order if c not in gave_up]   # the hard ones first next time
    gave_up = best[0]
    if keep is not None:                               # merge mode: the routes stored before stay
        found = json.loads(MAZE_JSON.read_text())
        found["tracks"] = keep["tracks"] + found["tracks"]
        found["vias"] = keep["vias"] + found["vias"]
        MAZE_JSON.write_text(json.dumps(found, indent=1) + "\n")
    print(f"  routed {len(best[1])}/{len(conns)}" +
          (f"; not routed: {', '.join(conns[c][2] for c in gave_up)}" if gave_up else ""))


OPEN_JSON = ROUTE / "_open.json"
LAYER_NAMES = ["F.Cu", "In2.Cu", "B.Cu"]


def net_islands(b: pcbnew.BOARD, net: str) -> list:
    """Copper islands of one net (pads, tracks, vias), each as a list of (item, [(x, y, layer index)])."""
    lay = {pcbnew.F_Cu: 0, pcbnew.In2_Cu: 1, pcbnew.B_Cu: 2}
    items = []
    for fp in b.GetFootprints():
        for pd in fp.Pads():
            if pd.GetNetname() == net:
                c = pd.GetPosition()
                pts = [(c.x / 1e6, c.y / 1e6, li) for l, li in lay.items() if pd.IsOnLayer(l)]
                items.append((pd, pts))
    for t in b.GetTracks():
        if t.GetNetname() != net:
            continue
        if t.GetClass() == "PCB_VIA":
            c = t.GetPosition()
            items.append((t, [(c.x / 1e6, c.y / 1e6, li) for li in range(3)]))
        elif t.GetLayer() in lay:
            li = lay[t.GetLayer()]
            s0, e0 = t.GetStart(), t.GetEnd()
            items.append((t, [(s0.x / 1e6, s0.y / 1e6, li), (e0.x / 1e6, e0.y / 1e6, li),
                              ((s0.x + e0.x) / 2e6, (s0.y + e0.y) / 2e6, li)]))
    inv = {v: k for k, v in lay.items()}
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, (a, pa) in enumerate(items):
        for j in range(i + 1, len(items)):
            bitem, pb = items[j]
            touch = False
            for x, y, li in pa:
                q = pcbnew.VECTOR2I(int(round(x * 1e6)), int(round(y * 1e6)))
                if bitem.IsOnLayer(inv[li]) and bitem.HitTest(q, 1000):
                    touch = True
                    break
            if not touch:
                for x, y, li in pb:
                    q = pcbnew.VECTOR2I(int(round(x * 1e6)), int(round(y * 1e6)))
                    if a.IsOnLayer(inv[li]) and a.HitTest(q, 1000):
                        touch = True
                        break
            if touch:
                parent[find(i)] = find(j)
    groups = {}
    for i, it in enumerate(items):
        groups.setdefault(find(i), []).append(it)
    return list(groups.values())


def step_repair_prep() -> None:
    """Record the connections still open on the full board, each as start/goal point sets (whole islands)."""
    b = pcbnew.LoadBoard(str(BOARD))
    opens = []
    for v in drc_unconnected(BOARD):
        m = re.search(r"\[([^\]]+)\]", v["items"][0]["description"])
        if not m or m.group(1) == "GND":
            continue
        net = m.group(1)
        isl = net_islands(b, net)
        sides = []
        for it in v["items"][:2]:
            q = pcbnew.VECTOR2I(int(round(it["pos"]["x"] * 1e6)), int(round(it["pos"]["y"] * 1e6)))
            hit = [g for g in isl if any(item.HitTest(q, 20000) for item, _ in g)]
            pts = [p for item, pp in (hit[0] if hit else []) for p in pp] or conn_ends(it, net)
            if net in ESCAPE_NETS:                     # the prepared escape via counts as part of its pad
                for n, (x, y), _, _ in PRE_VIAS:
                    if n == net and any(math.dist((OX + x, OY + y), pt[:2]) < 2.5 for pt in pts):
                        pts = [(OX + x, OY + y, li) for li in range(3)] + pts
            sides.append(pts[:60])
        opens.append({"net": net, "starts": sides[0], "goals": sides[1]})
    bad = []
    for v in drc_violations(BOARD):
        if v["type"] in ("clearance", "hole_clearance", "shorting_items", "tracks_crossing", "hole_to_hole"):
            for it in v["items"]:
                m = re.search(r"^(Track|Via) \[([^\]]+)\]", it["description"])
                if m:
                    bad.append((m.group(2), it["pos"]["x"], it["pos"]["y"]))
    OPEN_JSON.write_text(json.dumps({"opens": opens, "violations": bad}))
    print(f"  {len(opens)} connections open, {len(bad)} copper items in DRC violations")


def maze_components(data, on_base=lambda net, x, y, li: False):
    """Group stored maze tracks/vias into routes: connected pieces with exactly two ends.

    Points on existing copper of the net (pads, hand routes) are ends, never joints: two routes that meet
    at a pad stay two routes.
    """
    tr = [(t["net"], LAYER_NAMES.index(t["layer"]), t["width"], [(OX + x, OY + y) for x, y in t["points"]])
          for t in data["tracks"]]
    vi = [(v["net"], OX + v["x"], OY + v["y"], v["dia"], v["drill"]) for v in data["vias"]]
    parent = list(range(len(tr) + len(vi)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def key(x, y):
        return (round(x, 3), round(y, 3))
    at = {}
    for i, (net, li, w, pts) in enumerate(tr):
        for x, y in (pts[0], pts[-1]):
            at.setdefault((net, key(x, y)), []).append((i, li))
    for k, (net, x, y, d, dr) in enumerate(vi):
        at.setdefault((net, key(x, y)), []).append((len(tr) + k, None))
    for (net, (kx, ky)), lst in at.items():
        if any(li is not None and on_base(net, kx, ky, li) for _, li in lst):
            continue
        for (i, li), (j, lj) in zip(lst, lst[1:]):
            if li is None or lj is None or li == lj:
                parent[find(i)] = find(j)
            else:                                      # different layers only join through a via
                for k, lk in lst:
                    if lk is None:
                        parent[find(i)] = find(k)
                        parent[find(j)] = find(k)
    comps = {}
    for i in range(len(parent)):
        comps.setdefault(find(i), []).append(i)
    out = []
    for members in comps.values():
        ts = [tr[i] for i in members if i < len(tr)]
        vs = [vi[i - len(tr)] for i in members if i >= len(tr)]
        if not ts:
            continue
        vxy = {key(v[1], v[2]) for v in vs}
        cnt = {}
        for net, li, w, pts in ts:
            for x, y in (pts[0], pts[-1]):
                cnt[(li, key(x, y))] = cnt.get((li, key(x, y)), 0) + 1
        free = [(x, y, li) for (li, (x, y)), n in cnt.items()
                if (x, y) not in vxy and (n == 1 or on_base(ts[0][0], x, y, li))]
        out.append({"net": ts[0][0], "tracks": ts, "vias": vs, "ends": free})
    return out


def step_repair() -> None:
    """Route the recorded open connections, ripping up only the stored maze routes in their way."""
    b = pcbnew.LoadBoard(str(BOARD))              # rebuilt without maze routes
    r = maze.Router(b, (OX, OY, OX + BOARD_W, OY + BOARD_H), [pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu],
                    clearance=0.18, hole_clearance=0.28)
    lay = [pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
    base_cu = {}
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            base_cu.setdefault(pad.GetNetname(), []).append(pad)
    for t in b.GetTracks():
        base_cu.setdefault(t.GetNetname(), []).append(t)

    def on_base(net, x, y, li):
        q = pcbnew.VECTOR2I(int(round(x * 1e6)), int(round(y * 1e6)))
        return any(it.IsOnLayer(lay[li]) and it.HitTest(q, 10000) for it in base_cu.get(net, ()))

    data = json.loads(MAZE_JSON.read_text())
    comps = maze_components(data, on_base)
    ends_of, width_of, chain_of, fixed_ids, orig_of = {}, {}, {}, set(), {}
    rid = 0
    for c in comps:
        code = b.FindNet(c["net"]).GetNetCode()
        hw = max(t[2] for t in c["tracks"]) / 2       # mixed widths: the widest one keeps the others clear
        orig_of[rid] = c                               # written back exactly as stored unless it is moved
        vr = (c["vias"][0][3] / 2) if c["vias"] else MAZE_WIDTH[net_class(c["net"])][1] / 2
        dr = c["vias"][0][4] if c["vias"] else MAZE_WIDTH[net_class(c["net"])][2]
        segs = [(li, pts) for _, li, _, pts in c["tracks"]]
        vias = [(x, y) for _, x, y, _, _ in c["vias"]]
        r.add(rid, code, segs, vias, hw, vr, dr)
        width_of[rid] = hw * 2
        if len(c["ends"]) == 2:
            ends_of[rid] = (c["net"], [c["ends"][0]], [c["ends"][1]])
        else:                                          # branched piece: never ripped up as a whole
            fixed_ids.add(rid)
            chain_of[rid] = (c["net"], c["ends"])
        rid += 1
    clash = []
    viol = json.loads(OPEN_JSON.read_text())["violations"]
    for k, (code, its, (segs, vias, hw, vr, dr)) in list(r.routes.items()):
        bad = False                                    # only what KiCad's DRC flags counts as a clash
        for vnet, vx, vy in viol:
            if bad or vnet != b.FindNet(code).GetNetname():
                continue
            for li, pts in segs:
                for a, e in zip(pts, pts[1:]):
                    dx, dy = e[0] - a[0], e[1] - a[1]
                    ll = dx * dx + dy * dy
                    t = 0.0 if ll == 0 else max(0.0, min(1.0, ((vx - a[0]) * dx + (vy - a[1]) * dy) / ll))
                    if math.hypot(vx - a[0] - t * dx, vy - a[1] - t * dy) < hw + 0.02:
                        bad = True
            for x, y in vias:
                if math.hypot(vx - x, vy - y) < vr + 0.02:
                    bad = True
        if bad:
            clash.append(k)
    print(f"  {len(clash)} stored routes fail DRC and are routed again")
    print(f"  {len(r.routes) - len(fixed_ids)} stored routes can be moved, {len(fixed_ids)} branched ones kept")

    def hard(net, st, go, w0):
        code = b.FindNet(net).GetNetCode()
        _, vd, vdr = MAZE_WIDTH[net_class(net)]
        for w, margin in [(w0, 8.0), (w0, 60.0)] + ([(0.15, 60.0)] if w0 > 0.15 else []):
            path, _ = r.route(code, st, go, w / 2, vd / 2, vdr, margin=margin)
            if path:
                segs, vias = r.simplify(path, code, w / 2)
                return code, segs, vias, w / 2, vd / 2, vdr
        return None

    def soft(net, st, go, w0):
        code = b.FindNet(net).GetNetCode()
        _, vd, vdr = MAZE_WIDTH[net_class(net)]
        _, crossed = r.route(code, st, go, w0 / 2, vd / 2, vdr, margin=60.0, soft=True)
        return crossed

    state = {"rid": rid, "budget": 1500}

    def snapshot():
        return dict(r.routes), dict(ends_of), dict(width_of), state["rid"]

    def restore(snap):
        routes, e, w, nrid = snap
        r.routes = dict(routes)
        r._rt.clear()
        r._rv.clear()
        ends_of.clear()
        ends_of.update(e)
        width_of.clear()
        width_of.update(w)
        state["rid"] = nrid

    def place(net, st, go, res):
        k = state["rid"]
        r.add(k, *res)
        ends_of[k] = (net, st, go)
        width_of[k] = res[3] * 2
        state["rid"] += 1
        return k

    def attempt(net, st, go, w0, depth, protected):
        """Route one connection; may rip up and re-route others. All or nothing."""
        state["budget"] -= 1
        if state["budget"] < 0:
            return False
        res = hard(net, st, go, w0)
        if res:
            protected.add(place(net, st, go, res))
            return True
        if depth == 0:
            return False
        crossed = soft(net, st, go, w0)
        crossed = {x for x in crossed if x in r.routes}
        if not crossed or crossed & protected or len(crossed) > 8:
            return False
        snap = snapshot()
        ripped = []
        for x in crossed:
            if x in fixed_ids:                         # branched piece: back as a chain of connections
                n2, ends2 = chain_of[x]
                ripped += [(x, n2, [e1], [e2], width_of[x]) for e1, e2 in zip(ends2, ends2[1:])]
            else:
                ripped.append((x,) + ends_of[x] + (width_of[x],))
        for x in crossed:
            r.remove(x)
        res = hard(net, st, go, w0)
        if not res:
            restore(snap)
            return False
        mine = set(protected) | {place(net, st, go, res)}
        for _, n2, s2, g2, w2 in sorted(ripped, key=lambda t: math.dist(t[2][0][:2], t[3][0][:2])):
            if not attempt(n2, s2, g2, w2, depth - 1, mine):
                restore(snap)
                return False
        protected |= mine
        return True

    opens = []
    for k in clash:
        if k in fixed_ids:                             # a branched piece goes back as a chain of connections
            net, ends = chain_of[k]
            for e1, e2 in zip(ends, ends[1:]):
                opens.append((net, [e1], [e2], width_of[k]))
            fixed_ids.discard(k)
        else:
            net, st, go = ends_of[k]
            opens.append((net, st, go, width_of[k]))
        r.remove(k)
    for v in json.loads(OPEN_JSON.read_text())["opens"]:
        if b.FindNet(v["net"]) is not None:
            opens.append((v["net"], [tuple(p) for p in v["starts"]], [tuple(p) for p in v["goals"]],
                          MAZE_WIDTH[net_class(v["net"])][0]))
    failed = []
    for depth in (1, 2, 3, 4):                      # cheap fixes first, deeper rip-up chains for the rest
        left = []
        for net, st, go, w0 in (opens if depth == 1 else failed_conns):
            if not attempt(net, st, go, w0, depth, set()):
                left.append((net, st, go, w0))
        failed_conns = left
        print(f"  rip-up depth {depth}: {len(left)} still open")
        if not left:
            break
    failed = [c[0] for c in failed_conns]
    found = {"tracks": [], "vias": []}
    allr = dict(r.routes)
    for k in sorted(allr):
        if k in orig_of:                               # untouched stored route: keep every width as it was
            c = orig_of[k]
            for net, li, w, pts in c["tracks"]:
                found["tracks"].append({"net": net, "layer": LAYER_NAMES[li], "width": w,
                                        "points": [[round(x - OX, 4), round(y - OY, 4)] for x, y in pts]})
            for net, x, y, d, dr in c["vias"]:
                found["vias"].append({"net": net, "x": round(x - OX, 4), "y": round(y - OY, 4),
                                      "dia": d, "drill": dr})
            continue
        code, _, (segs, vias, hw, vr, dr) = allr[k][:3]
        net = b.FindNet(code).GetNetname()
        for li, pts in segs:
            found["tracks"].append({"net": net, "layer": LAYER_NAMES[li], "width": round(hw * 2, 3),
                                    "points": [[round(x - OX, 4), round(y - OY, 4)] for x, y in pts]})
        for x, y in vias:
            found["vias"].append({"net": net, "x": round(x - OX, 4), "y": round(y - OY, 4),
                                  "dia": round(vr * 2, 3), "drill": dr})
    used = {(v[0], round(v[1], 3), round(v[2], 3)) for c in comps for v in c["vias"]}
    found["vias"] += [v for v in data["vias"]           # vias no stored track touches stay as they are
                      if (v["net"], round(OX + v["x"], 3), round(OY + v["y"], 3)) not in used]
    MAZE_JSON.write_text(json.dumps(found, indent=1) + "\n")
    OPEN_JSON.unlink()
    print("  repaired" + (f"; still open: {', '.join(failed)}" if failed else ": nothing left open"))


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


def drop_single_layer_vias(b: pcbnew.BOARD) -> int:
    """A signal via whose tracks are all on one layer (and no pad on another) does nothing: remove it."""
    n = 0
    tracks = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK"]
    pads = [p for fp in b.GetFootprints() for p in fp.Pads()]
    for v in [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]:
        net = v.GetNetname()
        if net == "GND" or v.IsLocked():
            continue                                   # GND vias also join the In1 plane; hand vias stay
        c = v.GetPosition()
        layers = {t.GetLayer() for t in tracks if t.GetNetname() == net and (t.GetStart() == c or t.GetEnd() == c)}
        layers |= {l for p in pads if p.GetNetname() == net and p.HitTest(c, 0)
                   for l in (pcbnew.F_Cu, pcbnew.B_Cu) if p.IsOnLayer(l)}
        if len(layers) <= 1:
            b.Remove(v)
            n += 1
    return n


def drop_dangling_tracks(b: pcbnew.BOARD) -> int:
    """Router copper (unlocked) left over after rip-ups: islands of a net that reach no pad, and branches with
    an end that touches nothing. Repeated until none is left."""
    total = 0
    pads = [p for fp in b.GetFootprints() for p in fp.Pads()]

    def touch(a, c) -> bool:
        if a.GetClass() == "PCB_TRACK" and c.GetClass() == "PCB_TRACK":
            if a.GetLayer() != c.GetLayer():
                return False
            return any(c.HitTest(q, 0) for q in (a.GetStart(), a.GetEnd())) or \
                any(a.HitTest(q, 0) for q in (c.GetStart(), c.GetEnd()))
        if a.GetClass() == "PCB_VIA":
            a, c = c, a
        if c.GetClass() == "PCB_VIA":            # a is a track
            return any(c.HitTest(q, 0) for q in (a.GetStart(), a.GetEnd()))
        return False

    while True:
        by_net = {}
        for t in b.GetTracks():
            by_net.setdefault(t.GetNetCode(), []).append(t)
        dead = []
        for code, items in by_net.items():
            net = b.FindNet(code)
            if net is None or net.GetNetname() == "GND":
                continue
            npads = [p for p in pads if p.GetNetCode() == code]
            parent = list(range(len(items)))

            def find(i):
                while parent[i] != i:
                    parent[i] = parent[parent[i]]
                    i = parent[i]
                return i
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    if touch(items[i], items[j]):
                        parent[find(i)] = find(j)
            on_pad = set()
            for i, t in enumerate(items):
                pts = [t.GetPosition()] if t.GetClass() == "PCB_VIA" else [t.GetStart(), t.GetEnd()]
                for p in npads:
                    if any(p.HitTest(q, 0) for q in pts) and (t.GetClass() == "PCB_VIA" or p.IsOnLayer(t.GetLayer())):
                        on_pad.add(find(i))
                        break
            for i, t in enumerate(items):
                if not t.IsLocked() and find(i) not in on_pad:
                    dead.append(t)
                    continue
                if t.IsLocked() or t.GetClass() != "PCB_TRACK":
                    continue
                for end in (t.GetStart(), t.GetEnd()):
                    if any(o is not t and (o.GetClass() == "PCB_VIA" or o.GetLayer() == t.GetLayer())
                           and o.HitTest(end, 0) for o in items):
                        continue
                    if any(p.IsOnLayer(t.GetLayer()) and p.HitTest(end, 0) for p in npads):
                        continue
                    dead.append(t)
                    break
        if not dead:
            return total
        for t in dead:
            b.Remove(t)
        total += len(dead)


def _on_seg(p, seg) -> bool:
    """True when point p lies on the segment (within 1 um)."""
    (ax, ay), (bx, by) = seg
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    t = 0.0 if ll == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / ll))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy) < 0.001


def step_polish() -> int:
    """Remove router segments and vias that KiCad reports as dangling from MAZE_JSON (hand routes stay)."""
    found = json.loads(MAZE_JSON.read_text())
    segs = []
    for t in found["tracks"]:                          # one entry per segment, so single segments can go
        for a, c in zip(t["points"], t["points"][1:]):
            segs.append({"net": t["net"], "layer": t["layer"], "width": t["width"], "points": [a, c]})
    bad = [v for v in drc_violations(BOARD) if v["type"] in ("track_dangling", "via_dangling")]
    removed = 0
    for v in bad:
        it = v["items"][0]
        m = re.search(r"\[([^\]]+)\]", it["description"])
        net = m.group(1) if m else None
        x, y = it["pos"]["x"] - OX, it["pos"]["y"] - OY
        if it["description"].startswith("Via"):
            keep = [q for q in found["vias"] if not (q["net"] == net and math.dist((q["x"], q["y"]), (x, y)) < 0.02)]
            removed += len(found["vias"]) - len(keep)
            found["vias"] = keep
            continue
        lm = re.search(r"length ([0-9.]+) mm", it["description"])
        length = float(lm.group(1)) if lm else None
        cand = [sg for sg in segs if sg["net"] == net and not sg.get("gone")
                and min(math.dist(sg["points"][0], (x, y)), math.dist(sg["points"][1], (x, y))) < 0.02]
        exact = [sg for sg in cand if length is None or abs(math.dist(*sg["points"]) - length) <= 0.01]
        if not exact and len(cand) == 1:               # the board copy was trimmed at a pad: same segment
            exact = cand
        if exact:
            exact[0]["gone"] = True
            removed += 1
    # A removed dead end can leave the next piece of the same dead branch dangling: follow the branch while
    # its joints join exactly two router segments, with no via, pad or hand route there.
    b = pcbnew.LoadBoard(str(BOARD))
    fixed = [it for fp in b.GetFootprints() for it in fp.Pads()] + [t for t in b.GetTracks() if t.IsLocked()]

    def anchored(net, layer, x, y):
        q = pcbnew.VECTOR2I(int(round((x + OX) * 1e6)), int(round((y + OY) * 1e6)))
        return any(it.GetNetname() == net and it.IsOnLayer(LAYERS[layer]) and it.HitTest(q, 10000) for it in fixed)

    def at(sg, x, y):
        return [i for i in (0, 1) if math.dist(sg["points"][i], (x, y)) < 0.001]
    todo = [(sg, i) for sg in segs if sg.get("gone") for i in (0, 1)]
    while todo:
        sg, i = todo.pop()
        x, y = sg["points"][i]
        if any(q["net"] == sg["net"] and math.dist((q["x"], q["y"]), (x, y)) < 0.02 for q in found["vias"]):
            continue
        if anchored(sg["net"], sg["layer"], x, y):
            continue
        near = [o for o in segs if not o.get("gone") and o is not sg and o["net"] == sg["net"]
                and o["layer"] == sg["layer"] and at(o, x, y)]
        if len(near) != 1:                             # a junction, or nothing left: stop here
            continue
        o = near[0]
        mid = any(not q.get("gone") and q is not o and q["net"] == o["net"] and q["layer"] == o["layer"]
                  and _on_seg((x, y), q["points"]) for q in segs)
        if mid:                                        # something else meets this point: not a dead end
            continue
        o["gone"] = True
        removed += 1
        j = 1 - at(o, x, y)[0]
        todo.append((o, j))
    found["tracks"] = [{k: sg[k] for k in ("net", "layer", "width", "points")} for sg in segs if not sg.get("gone")]
    MAZE_JSON.write_text(json.dumps(found, indent=1) + "\n")
    print(f"  polish: {removed} dangling router items removed")
    return removed


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
    ap.add_argument("--repair", action="store_true",
                    help="route what is still open, moving only the stored maze routes in the way, then rebuild")
    ap.add_argument("--polish", action="store_true",
                    help="remove router leftovers KiCad reports as dangling, then rebuild")
    ap.add_argument("--step", nargs="+", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.step:
        if a.step[0] == "export":
            step_export(a.step[1])
        elif a.step[0] == "finish":
            step_finish(stitch="nostitch" not in a.step, use_maze="nomaze" not in a.step)
        elif a.step[0] == "fill":
            step_fill()
        elif a.step[0] == "maze":
            step_maze()
        elif a.step[0] == "repair-prep":
            step_repair_prep()
        elif a.step[0] == "repair":
            step_repair()
        elif a.step[0] == "polish":
            step_polish()
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
    if a.repair:
        best_copy = MAZE_JSON.with_suffix(".best")

        def measure():
            r = subprocess.run([sys.executable, __file__, "--step", "repair-prep"], capture_output=True, text=True)
            m = re.search(r"(\d+) connections open, (\d+) copper", r.stdout)
            print("  " + (r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:]))
            return int(m.group(1)) + int(m.group(2)) if m else 10 ** 6

        print("repair:")
        best = measure()
        shutil.copy(MAZE_JSON, best_copy)
        for n in range(5):                             # again while it keeps closing connections
            if best == 0:
                break
            run_step("finish", "nostitch", "nomaze")
            run_step("repair")
            run_step("finish", "nostitch")
            run_step("fill")
            count = measure()
            if count < best:
                best = count
                shutil.copy(MAZE_JSON, best_copy)
            else:                                      # no better: keep the best routes and stop
                shutil.copy(best_copy, MAZE_JSON)
                print("  no improvement, best result kept")
                break
        best_copy.unlink(missing_ok=True)
        OPEN_JSON.unlink(missing_ok=True)
    if a.polish:
        print("polish:")
        for n in range(4):                             # removing one dead piece can expose the next
            run_step("finish", "nostitch")
            run_step("fill")
            r = subprocess.run([sys.executable, __file__, "--step", "polish"], capture_output=True, text=True)
            print(r.stdout.strip())
            if " 0 dangling" in r.stdout:
                break
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
