#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Which keyboard switch types can share one key position on the switch board.

    python3 generator/switches/compat.py          # writes generator/switches/compat.json and prints the matrices

Geometry: switch seen from the top, centre at 0,0, y towards the user, pins "north" (negative y).
Sources: kiswitch/keyswitch-kicad-library (MX, KH, Alps, Choc v1/v2/mini, CPG1425, Kailh MX and Choc
hot-swap sockets) and siderakb/key-switches.pretty (Gateron Low Profile and its socket, Cherry MX Low Profile;
that library draws switches turned 180°, turned back here).

Two ways to mount:
  solder   every selected type gets its holes in one footprint; pins of different types that come close must
           belong to the same contact (the two contacts of a switch are interchangeable, so each type may swap them).
  hotswap  every selected type gets its hot-swap socket at every key, so all of them can be swapped any time.
           Choc v1 and v2 share one socket. Types without a socket cannot be hot-swapped.
Any type except the first one in PRIORITY may be turned 180° to make room; a turned type loses the per-key
LED position (its light window then faces the other way). Choc comes first (SWB-004: the LED serves Choc).

Per-key light: with it on, the first type (Choc, else MX) keeps a reverse-mount LED cut-out south of the centre,
3.6 x 3.0 mm at (0, 4.9), which covers the Choc (4.7) and MX (5.08) light windows. No other type's pin, pad or
socket may sit there. For a first type other than Choc or MX the LED position is not verified ("led": "unverified").

Rules (project DRC, hardware/core/ko-core.kicad_dru): copper to copper 0.2 mm, hole to hole 0.25 mm,
hole to copper 0.25 mm; plated pins get a 0.3 mm annular ring. Overlapping non-plated holes merge into one
milled cut-out; overlapping plated pins of the same contact merge into a plated slot.
"""
import itertools
import json
import math
import pathlib

CU, HOLE, RING = 0.2, 0.25, 0.3

# id: label, height class, solder pins [(x, y, drill)], non-plated holes [(x, y, dia)], socket family or None
TYPES = {
    "choc_v1":    ("Choc v1", "slim", [(0, -5.9, 1.2), (5.0, -3.8, 1.2)], [(0, 0, 3.45), (-5.5, 0, 1.9), (5.5, 0, 1.9)], "choc"),
    "choc_v2":    ("Choc v2", "slim", [(0, -5.9, 1.2), (5.0, -3.8, 1.2)], [(0, 0, 5.05), (-5.0, 5.15, 1.6)], "choc"),
    "mx":         ("MX", "tall", [(-3.81, -2.54, 1.5), (2.54, -5.08, 1.5)], [(0, 0, 4.0), (-5.08, 0, 1.75), (5.08, 0, 1.75)], "mx"),
    "gateron_lp": ("Gateron LP", "slim", [(4.40, -4.70, 1.5), (-2.60, -5.75, 1.5)], [(0, 0, 5.25)], "gateron_lp"),
    "mx_lp":      ("MX Low Profile", "slim", [(0, -6.05, 1.2), (-4.13, -3.30, 1.2)], [(0, 0, 6.25), (0, -3.7, 2.3)], None),
    "kh":         ("Kailh KH", "tall", [(-3.80, -2.55, 1.5), (3.00, -5.12, 1.5)], [(0, 0, 4.0), (-4.5, 0, 1.5), (4.5, 0, 1.5)], None),
    "alps":       ("Alps / Matias", "tall", [(-2.5, -4.0, 1.5), (2.5, -4.5, 1.5)], [], None),
    "choc_mini":  ("Choc mini", "slim", [(2.0, 5.4, 1.2), (-4.58, 5.1, 1.2)], [(-5.29, -4.75, 1.2), (5.29, -4.75, 1.2)], None),
    "kailh_x":    ("Kailh X (PG1425)", "slim", [(-2.0, -3.4, 1.1), (2.9, -3.4, 1.1)], [(5.5, -5.5, 1.3), (-5.5, 5.5, 1.3)], None),
}
PRIORITY = list(TYPES)          # first selected type in this order keeps its orientation
LED_KNOWN = {"choc_v1", "choc_v2", "mx"}
LED_CUT = (-1.8, 3.4, 1.8, 6.4)  # x0, y0, x1, y1
# hot-swap sockets: sleeve holes (one per pin, same order as the pins), bottom pads (w, h) per pin, body rectangle
SOCKETS = {
    "mx":         {"sleeves": 3.05, "pads": [(-7.085, -2.54, 2.55, 2.5), (5.842, -5.08, 2.55, 2.5)], "body": (-6.0, -6.8, 4.8, -0.8)},
    "choc":       {"sleeves": 3.05, "pads": [(-3.5, -6.0, 2.55, 2.5), (8.5, -3.8, 2.55, 2.5)], "body": (-2.45, -8.45, 7.75, -1.25)},
    "gateron_lp": {"sleeves": 3.0, "pads": [(8.075, -4.7, 2.5, 2.55), (-6.275, -5.75, 2.5, 2.55)], "body": (-5.03, -7.92, 6.82, -2.52)},
}


def turn(x, y, rot):
    return (-x, -y) if rot else (x, y)


def elements(tid, rot, swap, mode, led=False):
    """Copper, holes and (hot-swap) socket parts of one type in one orientation; nets 0/1 after the swap.
    led: add the per-key LED cut-out (first type only, never turned)."""
    _, _, pins, npth, fam = TYPES[tid]
    out = [("led", *LED_CUT, None)] if led else []
    for i, (x, y, d) in enumerate(pins):
        net = i ^ swap
        x, y = turn(x, y, rot)
        if mode == "solder":
            out.append(("pin", x, y, d, d + 2 * RING, net))
        else:
            out.append(("hole", x, y, SOCKETS[fam]["sleeves"], 0, net))
    for x, y, d in npth:
        x, y = turn(x, y, rot)
        out.append(("hole", x, y, d, 0, None))
    if mode == "hotswap":
        s = SOCKETS[fam]
        for i, (x, y, w, h) in enumerate(s["pads"]):
            x, y = turn(x, y, rot)
            out.append(("pad", x, y, w, h, i ^ swap))
        x0, y0, x1, y1 = s["body"]
        a, b = turn(x0, y0, rot), turn(x1, y1, rot)
        out.append(("body", min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]), None))
    return out


def circ_rect_gap(cx, cy, r, x0, y0, x1, y1):
    dx = max(x0 - cx, 0, cx - x1)
    dy = max(y0 - cy, 0, cy - y1)
    return math.hypot(dx, dy) - r


def rect_of(e):
    if e[0] in ("led", "body"):
        return e[1:5]
    if e[0] == "pad":
        _, x, y, w, h, _ = e
        return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
    return e[1:5]


def rect_gap(a, b):
    dx = max(a[0] - b[2], b[0] - a[2], 0)
    dy = max(a[1] - b[3], b[1] - a[3], 0)
    return math.hypot(dx, dy) if (dx or dy) else -1.0


def clash(ea, eb):
    """Reason two elements of different switch types cannot coexist, or None."""
    ka, kb = ea[0], eb[0]
    if "led" in (ka, kb):
        led, other = (ea, eb) if ka == "led" else (eb, ea)
        if other[0] in ("pad", "body"):
            return "a socket sits on the LED window" if rect_gap(rect_of(led), rect_of(other)) < CU else None
        if other[0] == "pin" and circ_rect_gap(other[1], other[2], other[4] / 2, *rect_of(led)) < HOLE:
            return "a pin sits in the LED window"
        return None
    if ka in ("pad", "body") and kb in ("pad", "body"):
        return "the sockets overlap underneath" if rect_gap(rect_of(ea), rect_of(eb)) < CU else None
    if ka in ("pad", "body") or kb in ("pad", "body"):
        sq, other = (ea, eb) if ka in ("pad", "body") else (eb, ea)
        if sq[0] == "body":
            return None                      # a hole under the socket's plastic body is fine
        r = other[3] / 2 if other[0] == "hole" else other[4] / 2
        if circ_rect_gap(other[1], other[2], r, *rect_of(sq)) < HOLE:
            return "a hole cuts a socket pad"
        return None
    dist = math.hypot(ea[1] - eb[1], ea[2] - eb[2])
    if ka == "hole" and kb == "hole":
        return None                          # non-plated holes may merge into one cut-out
    if ka == "pin" and kb == "pin":
        if dist < (ea[4] + eb[4]) / 2 + CU and ea[5] != eb[5]:
            return f"pins of different contacts {max(0, dist - (ea[4] + eb[4]) / 2):.2f} mm apart"
        return None
    pin, hole = (ea, eb) if ka == "pin" else (eb, ea)
    gap = dist - pin[4] / 2 - hole[3] / 2
    return f"a hole {max(0, gap):.2f} mm from a pin" if gap < HOLE else None


def pair_ok(a, sa, b, sb, mode, led=False):
    """sa, sb: (rot, swap); a is the first type (led: it carries the LED cut-out). Returns None or the first reason."""
    if mode == "hotswap" and TYPES[a][4] == TYPES[b][4]:
        if sa != sb:
            return "they share one socket"
        ea = [e for e in elements(a, *sa, "solder", led) if e[0] in ("hole", "led")]
        eb = [e for e in elements(b, *sb, "solder") if e[0] == "hole"]
    else:
        ea, eb = elements(a, *sa, mode, led), elements(b, *sb, mode)
    for x in ea:
        for y in eb:
            r = clash(x, y)
            if r:
                return r
    return None


STATES = [(rot, swap) for rot in (0, 1) for swap in (0, 1)]


def solve(sel, mode, light):
    """Orientation and contact assignment for a set of types, preferring no turned types. None if impossible."""
    sel = sorted(sel, key=PRIORITY.index)
    if mode == "hotswap" and any(TYPES[t][4] is None for t in sel):
        return None
    led = light and sel[0] in LED_KNOWN
    best = None
    for combo in itertools.product(STATES, repeat=len(sel) - 1):
        states = [(0, 0)] + list(combo)
        if all(pair_ok(sel[i], states[i], sel[j], states[j], mode, led and i == 0) is None
               for i in range(len(sel)) for j in range(i + 1, len(sel))):
            turned = [t for t, s in zip(sel, states) if s[0]]
            if best is None or len(turned) < len(best["turned"]):
                best = {"types": sel, "turned": turned, "swap": [t for t, s in zip(sel, states) if s[1]]}
                if light and not led:
                    best["led"] = "unverified"
                if not turned:
                    return best
    return best


def reason(a, b, mode, light):
    if mode == "hotswap":
        for t in (a, b):
            if TYPES[t][4] is None:
                return f"{TYPES[t][0]} has no hot-swap socket"
    first, second = sorted((a, b), key=PRIORITY.index)
    led = light and first in LED_KNOWN
    found = [pair_ok(first, (0, 0), second, st, mode, led) for st in STATES]
    return next((r for r in found if r and "LED" in r), None) or found[0] or found[2]


def main():
    ids = list(TYPES)
    out = {"rules": {"copper_mm": CU, "hole_mm": HOLE, "ring_mm": RING}, "types": {}, "sockets": SOCKETS, "modes": {}}
    for t, (label, height, pins, npth, fam) in TYPES.items():
        out["types"][t] = {"label": label, "height": height, "pins": pins, "holes": npth, "socket": fam}
    for mode in ("solder", "hotswap"):
        out["modes"][mode] = {}
        for light in (True, False):
            pairs, sets = {}, {}
            for a, b in itertools.combinations(ids, 2):
                sol = solve([a, b], mode, light)
                pairs[f"{a}|{b}"] = ({"ok": "turn" if sol["turned"] else "yes", "turned": sol["turned"]} if sol
                                     else {"ok": "no", "why": reason(a, b, mode, light)})
            for n in range(1, len(ids) + 1):
                for sel in itertools.combinations(ids, n):
                    if n > 1 and any(pairs[f"{a}|{b}"]["ok"] == "no" for a, b in itertools.combinations(sel, 2)):
                        continue
                    sol = solve(list(sel), mode, light)
                    if sol:
                        entry = {"turned": sol["turned"], "swap": sol["swap"]}
                        if "led" in sol:
                            entry["led"] = sol["led"]
                        sets[",".join(sorted(sel, key=PRIORITY.index))] = entry
            key = "light" if light else "dark"
            out["modes"][mode][key] = {"pairs": pairs, "sets": sets}
            print(f"\n{mode}, per-key light {'on' if light else 'off'}: {len(sets)} working sets")
            w = 12
            print(" " * w + "".join(TYPES[t][0][:w - 1].ljust(w) for t in ids))
            for a in ids:
                row = TYPES[a][0][:w - 1].ljust(w)
                for b in ids:
                    if a == b:
                        row += "·".ljust(w)
                        continue
                    pr = pairs.get(f"{a}|{b}") or pairs[f"{b}|{a}"]
                    row += {"yes": "✓", "turn": "↻", "no": "✕"}[pr["ok"]].ljust(w)
                print(row)
            big = max(sets, key=lambda k: (len(k.split(",")), -len(sets[k]["turned"])))
            print("largest set:", big, "turned:", sets[big]["turned"])
    data = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    path = pathlib.Path(__file__).with_name("compat.json")
    path.write_text(data + "\n")
    page = pathlib.Path(__file__).parents[1] / "configurator" / "index.html"
    html = page.read_text()
    a, b = html.index("/*COMPAT-BEGIN*/") + len("/*COMPAT-BEGIN*/"), html.index("/*COMPAT-END*/")
    page.write_text(html[:a] + data + html[b:])
    print("\nwritten", path, "and the layout builder page")


if __name__ == "__main__":
    main()
