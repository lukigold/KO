# SPDX-License-Identifier: GPL-3.0-or-later
"""Read a KO layout file v3 and derive everything the switch board needs from it.

Positions are board millimetres of the key area: origin at the top-left corner of the key grid, x right,
y towards the user (KiCad's y). Nothing here depends on KiCad, so it runs and is tested on any host.

  key centres      from x/y/w/h in units (19.05 mm, SWB-002); the ISO enter's switch sits in its 1.25 u lower part
  matrix           rows = physical rows (<= 8, SWB-007), columns = 1 u buckets of the key centre, made unique per row;
                   columns are shift-register outputs (8 per 74HC595)
  LED channels     IS31FL3741A: 9 SW (anode) lines x 13 RGB slots (3 CS lines each) per driver. A key's slot follows
                   its x position, its SW line its row, so CS lines run front to back and SW lines along the rows;
                   rows longer than 13 keys or slot clashes spill to the spare SW lines. Underglow LEDs fill the rest.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

U = 19.05
SW_PER_DRIVER, SLOTS_PER_DRIVER = 9, 13
COLS_PER_REG = 8
MAX_ROWS = 8


@dataclass
class Key:
    id: str
    label: str
    x: float          # centre, mm
    y: float
    w: float          # units
    h: float
    shape: str = ""
    row: int = -1
    col: int = -1
    led: tuple | None = None      # (driver, sw, slot)

    @property
    def stab(self) -> bool:
        return self.w >= 2 or self.h >= 2


@dataclass
class Glow:
    x: float
    y: float
    led: tuple | None = None


@dataclass
class Board:
    name: str
    slug: str
    keys: list[Key]
    glow: list[Glow]
    rows: int
    cols: int
    regs: int
    drivers: int
    width: float      # key area, mm
    depth: float
    source: dict = field(repr=False, default_factory=dict)


def slug_of(name: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-").replace("--", "-")


def read(path: str) -> Board:
    d = json.load(open(path))
    if d.get("format") != "ko-layout" or d.get("version") != 3:
        raise SystemExit(f"{path}: not a KO layout file v3 (GEN-012)")
    if d["switch"]["mount"] != "hotswap" or not set(d["switch"]["types"]) <= {"choc_v1", "choc_v2"}:
        raise SystemExit("v1 switch boards are Choc v1/v2 hot-swap only (D-57)")
    unit = d.get("unit_mm", U)
    keys = []
    for k in d["keys"]:
        x, y, w, h = k["x"], k["y"], k["w"], k["h"]
        if k.get("shape") == "iso-enter":                  # switch in the 1.25 u wide lower part, centred in height
            cx, cy = x + 0.25 + 1.25 / 2, y + h / 2
        else:
            cx, cy = x + w / 2, y + h / 2
        keys.append(Key(k["id"], k.get("label", k["id"]), cx * unit, cy * unit, w, h, k.get("shape", "")))
    width = max(k["x"] + k["w"] for k in d["keys"]) * unit
    depth = max(k["y"] + k["h"] for k in d["keys"]) * unit
    rows = assign_matrix(keys, unit)
    cols = max(k.col for k in keys) + 1
    glow = underglow(keys, width, depth) if d["lighting"].get("underglow") else []
    leds = len(keys) * bool(d["lighting"].get("per_key")) + len(glow)
    drivers = max(1, math.ceil(leds / (SW_PER_DRIVER * SLOTS_PER_DRIVER)))
    if d["lighting"].get("per_key") or glow:
        assign_leds(keys if d["lighting"].get("per_key") else [], glow, width, drivers)
    return Board(d["name"], slug_of(d["name"]), keys, glow, rows, cols, math.ceil(cols / COLS_PER_REG), drivers,
                 width, depth, d)


def assign_matrix(keys: list[Key], unit: float) -> int:
    ys = sorted({round(k.y / unit * 4) / 4 for k in keys})
    # ISO enter's centre lies between two rows: it joins the row of its top edge
    rowy = sorted({round((k.y / unit - (k.h - 1) / 2) * 4) / 4 for k in keys})
    if len(rowy) > MAX_ROWS:
        raise SystemExit(f"{len(rowy)} key rows; at most {MAX_ROWS} (SWB-007)")
    for k in keys:
        k.row = rowy.index(round((k.y / unit - (k.h - 1) / 2) * 4) / 4)
    for r in range(len(rowy)):
        last = -1
        for k in sorted((k for k in keys if k.row == r), key=lambda k: k.x):
            k.col = max(last + 1, int(k.x / unit))
            last = k.col
    del ys
    return len(rowy)


def underglow(keys: list[Key], width: float, depth: float, spacing: float = 45.0) -> list[Glow]:
    """Underglow LEDs on a ring just inside the key area's outline, about every `spacing` mm. Each sits in the
    free bottom-side corner of the nearest key (offset (-6.0, +7.8) from its centre: clear of the socket, the
    per-key LED, the diode and the Choc pegs)."""
    perim = 2 * (width + depth)
    n = max(4, round(perim / spacing))
    pts = []
    for i in range(n):
        t = (i + 0.5) * perim / n
        if t < width:
            p = (t, 0)
        elif t < width + depth:
            p = (width, t - width)
        elif t < 2 * width + depth:
            p = (width - (t - width - depth), depth)
        else:
            p = (0, depth - (t - 2 * width - depth))
        pts.append(p)
    used, out = set(), []
    for px, py in pts:
        k = min((k for k in keys if k.id not in used), key=lambda k: (k.x - px) ** 2 + (k.y - py) ** 2)
        used.add(k.id)
        out.append(Glow(round(k.x - 6.0, 3), round(k.y + 7.8, 3)))
    return out


def assign_leds(keys: list[Key], glow: list[Glow], width: float, drivers: int) -> None:
    slots = SLOTS_PER_DRIVER * drivers
    free = {(d, s, c) for d in range(drivers) for s in range(SW_PER_DRIVER) for c in range(SLOTS_PER_DRIVER)}

    def ideal(x):                                      # slot column by x, over all drivers side by side
        return min(slots - 1, max(0, int(x / width * slots)))

    rows = sorted({k.row for k in keys})
    spare = list(range(len(rows), SW_PER_DRIVER))

    def take(x, sw_pref):
        want = ideal(x)
        order = sorted(free, key=lambda t: (abs(t[0] * SLOTS_PER_DRIVER + t[2] - want) * 3
                                            + (0 if t[1] in sw_pref else 8 if t[1] in spare else 30), t))
        t = order[0]
        free.discard(t)
        return t

    for r in rows:
        for k in sorted((k for k in keys if k.row == r), key=lambda k: k.x):
            k.led = take(k.x, [r] if r < SW_PER_DRIVER else spare)
    for g in glow:
        g.led = take(g.x, spare)


if __name__ == "__main__":
    import sys
    b = read(sys.argv[1])
    print(f"{b.name}: {len(b.keys)} keys, {b.rows} rows x {b.cols} cols ({b.regs} x 74HC595), "
          f"{len(b.glow)} underglow, {b.drivers} driver(s), key area {b.width:.2f} x {b.depth:.2f} mm")
    for r in range(b.rows):
        print(f"row {r}:", " ".join(f"{k.id}:c{k.col}/sw{k.led[1]}s{k.led[2]}" for k in sorted(b.keys, key=lambda k: k.x) if k.row == r))
    print("glow:", " ".join(f"({g.x:.0f},{g.y:.0f})sw{g.led[1]}s{g.led[2]}" for g in b.glow))
