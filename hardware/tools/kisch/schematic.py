# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate KiCad 9 hierarchical schematics from a Python design description.

Connectivity is expressed with net names, not drawn wires: every pin gets a
short wire stub and a label (local label if the net stays on one sheet, global
label if it spans sheets, a GND power symbol for GND, a no-connect flag for
"NC"). Output is deterministic (UUIDs are derived from names), so the files
diff cleanly in git and the generator, not the KiCad GUI, is the source of truth.
"""
from __future__ import annotations

import copy
import math
import pathlib
import uuid
from dataclasses import dataclass, field

from .sexpr import Str, dumps, find, find_all, parse

KICAD_SYMBOLS = pathlib.Path("/usr/share/kicad/symbols")
SCH_VERSION = "20250114"
LIB_VERSION = "20241209"
GRID = 1.27
STUB = 2.54
FONT = 1.27
NS = uuid.UUID("6f1c8e4a-5b7d-4f2a-9a3e-2c1d0b9e8f7a")
PAPER = {"A4": (297.0, 210.0), "A3": (420.0, 297.0)}


def uid(*parts: str) -> str:
    return str(uuid.uuid5(NS, "/".join(parts)))


def snap(v: float, g: float = GRID) -> float:
    return round(round(v / g) * g, 4)


def fmt(v: float) -> str:
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def effects(hide: bool = False, justify: str | None = None) -> list:
    e = ["effects", ["font", ["size", fmt(FONT), fmt(FONT)]]]
    if justify:
        e.append(["justify", *justify.split()])
    if hide:
        e.append(["hide", "yes"])
    return e


# --------------------------------------------------------------------------- libraries

_lib_cache: dict[str, dict[str, list]] = {}


def _load_lib(path: pathlib.Path) -> dict[str, list]:
    key = str(path)
    if key not in _lib_cache:
        tree = parse(path.read_text())
        _lib_cache[key] = {str(s[1]): s for s in find_all(tree, "symbol")}
    return _lib_cache[key]


def _flatten(lib: dict[str, list], name: str) -> list:
    sym = copy.deepcopy(lib[name])
    ext = find(sym, "extends")
    if not ext:
        return sym
    parent = _flatten(lib, str(ext[1]))
    child_props = {str(p[1]): p for p in find_all(sym, "property")}
    out = [parent[0], Str(name)]
    for item in parent[2:]:
        if isinstance(item, list) and item and item[0] == "property" and str(item[1]) in child_props:
            out.append(child_props.pop(str(item[1])))
        elif isinstance(item, list) and item and item[0] == "symbol":
            sub = copy.deepcopy(item)
            sub[1] = Str(str(sub[1]).replace(str(ext[1]), name, 1))
            out.append(sub)
        else:
            out.append(item)
    out[2:2] = list(child_props.values())
    return out


def kicad_symbol(lib_id: str) -> list:
    lib, name = lib_id.split(":", 1)
    return _flatten(_load_lib(KICAD_SYMBOLS / f"{lib}.kicad_sym"), name)


@dataclass
class Pin:
    number: str
    name: str
    etype: str
    x: float          # symbol coordinates (y up)
    y: float
    angle: int
    hidden: bool = False

    def outward(self) -> tuple[int, int]:
        """Screen-space unit vector pointing away from the symbol body."""
        return {0: (-1, 0), 90: (0, 1), 180: (1, 0), 270: (0, -1)}[self.angle % 360]


def symbol_pins(sym: list) -> list[Pin]:
    name = str(sym[1]).split(":")[-1]
    pins = []
    for sub in find_all(sym, "symbol"):
        sub_name = str(sub[1])
        unit, style = sub_name[len(name) + 1:].split("_")
        if unit not in ("0", "1") or style not in ("0", "1"):
            continue
        for p in find_all(sub, "pin"):
            at = find(p, "at")
            hidden = "hide" in p or any(isinstance(x, list) and x[:2] == ["hide", "yes"] for x in p)
            pins.append(Pin(str(find(p, "number")[1]), str(find(p, "name")[1]), p[1],
                            float(at[1]), float(at[2]), int(float(at[3])) if len(at) > 3 else 0, hidden))
    return pins


def symbol_bbox(sym: list, pins: list[Pin]) -> tuple[float, float, float, float]:
    """Body bounding box in screen coordinates relative to the origin (x0, y0, x1, y1)."""
    xs, ys = [], []

    def walk(n):
        if not isinstance(n, list) or not n:
            return
        if n[0] in ("start", "end", "xy", "center", "mid") and len(n) >= 3:
            try:
                xs.append(float(n[1]))
                ys.append(-float(n[2]))
            except ValueError:
                pass
        if n[0] == "pin":
            return
        for c in n:
            walk(c)

    for sub in find_all(sym, "symbol"):
        walk(sub)
    if not xs:
        xs = [p.x for p in pins] or [0]
        ys = [-p.y for p in pins] or [0]
    return min(xs), min(ys), max(xs), max(ys)


def ic_symbol(name: str, left=(), right=(), top=(), bottom=(), ref: str = "U",
              datasheet: str = "", description: str = "", footprint: str = "") -> list:
    """Build a rectangular IC symbol. Pins are (number, name, electrical_type[, hidden]).
    Pins with the same name on the same side are stacked on one position (first one visible)."""

    def stack(side):
        groups, order = {}, []
        for p in side:
            key = p[1]
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(p)
        return [groups[k] for k in order]

    L, R, T, B = stack(left), stack(right), stack(top), stack(bottom)
    char = FONT * 0.8
    max_l = max((len(g[0][1]) for g in L), default=0)
    max_r = max((len(g[0][1]) for g in R), default=0)
    width = max((max_l + max_r) * char + 6, max(len(T), len(B), 1) * 2.54 + 5.08, 12.7)
    half_w = math.ceil(width / 2 / 2.54) * 2.54
    rows = max(len(L), len(R), 1)
    extra = (5.08 if T else 0) + (5.08 if B else 0)
    half_h = math.ceil(((rows - 1) * 2.54 / 2 + 2.54 + extra / 2) / 2.54) * 2.54
    pins = []

    def add(group, x, y, angle):
        for i, (num, pname, etype, *rest) in enumerate(group):
            hidden = i > 0 or (rest and rest[0])
            pins.append((num, pname, etype if i == 0 else "passive", x, y, angle, hidden))

    def col_y(i, n):
        top_y = (n - 1) * 2.54 / 2 + (2.54 if T and not B else 0) - (2.54 if B and not T else 0)
        return snap(top_y - i * 2.54)

    for i, g in enumerate(L):
        add(g, -(half_w + 2.54), col_y(i, len(L)), 0)
    for i, g in enumerate(R):
        add(g, half_w + 2.54, col_y(i, len(R)), 180)
    for i, g in enumerate(T):
        add(g, snap((i - (len(T) - 1) / 2) * 2.54), half_h + 2.54, 270)
    for i, g in enumerate(B):
        add(g, snap((i - (len(B) - 1) / 2) * 2.54), -(half_h + 2.54), 90)

    def prop(key, value, y, hide=False):
        return ["property", Str(key), Str(value), ["at", "0", fmt(y), "0"], effects(hide)]

    body = ["symbol", Str(f"{name}_0_1"),
            ["rectangle", ["start", fmt(-half_w), fmt(half_h)], ["end", fmt(half_w), fmt(-half_h)],
             ["stroke", ["width", "0.254"], ["type", "default"]], ["fill", ["type", "background"]]]]
    unit = ["symbol", Str(f"{name}_1_1")]
    for num, pname, etype, x, y, angle, hidden in pins:
        pin = ["pin", etype, "line", ["at", fmt(x), fmt(y), str(angle)], ["length", "2.54"]]
        if hidden:
            pin.append(["hide", "yes"])
        pin += [["name", Str(pname), effects()], ["number", Str(num), effects()]]
        unit.append(pin)
    return ["symbol", Str(name), ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"],
            prop("Reference", ref, half_h + 1.27), prop("Value", name, -half_h - 1.27),
            prop("Footprint", footprint, 0, True), prop("Datasheet", datasheet, 0, True),
            prop("Description", description, 0, True), body, unit, ["embedded_fonts", "no"]]


# --------------------------------------------------------------------------- design model

@dataclass
class Part:
    ref: str
    lib_id: str
    value: str
    pins: dict[str, str]
    footprint: str = ""
    lcsc: str = ""
    mpn: str = ""
    dnp: bool = False
    in_bom: bool = True
    datasheet: str = ""
    description: str = ""


@dataclass
class Sheet:
    name: str
    filename: str
    paper: str = "A3"
    note: str = ""
    parts: list[Part] = field(default_factory=list)

    def add(self, ref, lib_id, value, pins, **kw) -> Part:
        p = Part(ref, lib_id, value, pins, **kw)
        self.parts.append(p)
        return p


class Design:
    def __init__(self, project: str, title: str, rev: str, company: str, comments: list[str]):
        self.project, self.title, self.rev, self.company, self.comments = project, title, rev, company, comments
        self.sheets: list[Sheet] = []
        self.custom: dict[str, list] = {}   # "lib:Name" -> symbol
        self.custom_lib = ""

    def sheet(self, name, filename, **kw) -> Sheet:
        s = Sheet(name, filename, **kw)
        self.sheets.append(s)
        return s

    def add_symbol(self, lib: str, sym: list) -> None:
        self.custom_lib = lib
        self.custom[f"{lib}:{sym[1]}"] = sym

    def symbol(self, lib_id: str) -> list:
        return copy.deepcopy(self.custom[lib_id]) if lib_id in self.custom else kicad_symbol(lib_id)

    # ----------------------------------------------------------------------- checks

    def nets(self) -> dict[str, list[tuple[str, str, str]]]:
        """net -> [(sheet, ref, pin)], resolving name-based pin mappings."""
        out: dict[str, list] = {}
        for s in self.sheets:
            for p in s.parts:
                for pin, net in self.resolve_pins(p).items():
                    out.setdefault(net, []).append((s.name, p.ref, pin))
        return out

    def resolve_pins(self, part: Part) -> dict[str, str]:
        pins = symbol_pins(self.symbol(part.lib_id))
        out = {}
        for pin in pins:
            if pin.number in part.pins:
                out[pin.number] = part.pins[pin.number]
            elif pin.name in part.pins:
                out[pin.number] = part.pins[pin.name]
            elif pin.etype == "no_connect":
                out[pin.number] = "NC"
            else:
                raise ValueError(f"{part.ref}: pin {pin.number} ({pin.name}) has no net")
        unknown = set(part.pins) - {p.number for p in pins} - {p.name for p in pins}
        if unknown:
            raise ValueError(f"{part.ref}: unknown pins {sorted(unknown)}")
        return out

    def check(self) -> list[str]:
        problems = []
        for net, members in self.nets().items():
            if net in ("NC", "GND"):
                continue
            refs = {(s, r) for s, r, _ in members}
            if len(members) < 2:
                problems.append(f"net {net} has only one pin: {members}")
            elif len(refs) < 2 and not net.startswith("NC_"):
                problems.append(f"net {net} connects only pins of one part: {members}")
        return problems

    # ----------------------------------------------------------------------- writing

    def write(self, outdir: pathlib.Path) -> None:
        outdir.mkdir(parents=True, exist_ok=True)
        root_uuid = uid(self.project, "root")
        sheet_of_net: dict[str, set] = {}
        for net, members in self.nets().items():
            sheet_of_net[net] = {s for s, _, _ in members}
        global_nets = {n for n, ss in sheet_of_net.items() if len(ss) > 1 and n not in ("GND", "NC")}

        for i, s in enumerate(self.sheets):
            sheet_uuid = uid(self.project, "sheet", s.filename)
            path = f"/{root_uuid}/{sheet_uuid}"
            text = _SheetWriter(self, s, path, global_nets, i + 2).render()
            (outdir / s.filename).write_text(text)
        (outdir / f"{self.project}.kicad_sch").write_text(self._root(root_uuid))
        if self.custom:
            lib_dir = outdir / "lib"
            lib_dir.mkdir(exist_ok=True)
            syms = [s for k, s in sorted(self.custom.items())]
            lib = ["kicad_symbol_lib", ["version", LIB_VERSION], ["generator", Str("ko-kisch")],
                   ["generator_version", Str("9.0")], *syms]
            (lib_dir / f"{self.custom_lib}.kicad_sym").write_text(dumps(lib) + "\n")
            (outdir / "sym-lib-table").write_text(
                "(sym_lib_table\n\t(version 7)\n"
                f'\t(lib (name "{self.custom_lib}")(type "KiCad")(uri "${{KIPRJMOD}}/lib/{self.custom_lib}.kicad_sym")'
                '(options "")(descr "KO project symbols (generated)"))\n)\n')

    def _title_block(self, title: str) -> list:
        tb = ["title_block", ["title", Str(title)], ["rev", Str(self.rev)], ["company", Str(self.company)]]
        for i, c in enumerate(self.comments, 1):
            tb.append(["comment", str(i), Str(c)])
        return tb

    def _root(self, root_uuid: str) -> str:
        items = [["kicad_sch", ["version", SCH_VERSION], ["generator", Str("ko-kisch")],
                  ["generator_version", Str("9.0")], ["uuid", Str(root_uuid)], ["paper", Str("A4")],
                  self._title_block(self.title), ["lib_symbols"]]]
        root = items[0]
        root.append(_text(f"{self.title}: block overview. Every block is a hierarchical sheet; "
                          "nets between sheets use global labels.\nGenerated by hardware/core/tools/"
                          "gen_schematic.py. Do not edit in KiCad; edit the design data and regenerate.",
                          25.4, 25.4, uid(self.project, "root-note")))
        for i, s in enumerate(self.sheets):
            x, y = 25.4 + (i % 3) * 88.9, 50.8 + (i // 3) * 50.8
            su = uid(self.project, "sheet", s.filename)
            root.append(["sheet", ["at", fmt(x), fmt(y)], ["size", "63.5", "25.4"],
                         ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"], ["dnp", "no"],
                         ["fields_autoplaced", "yes"],
                         ["stroke", ["width", "0.1524"], ["type", "solid"]], ["fill", ["color", "0", "0", "0", "0.0000"]],
                         ["uuid", Str(su)],
                         ["property", Str("Sheetname"), Str(s.name), ["at", fmt(x), fmt(y - 0.7), "0"],
                          effects(justify="left bottom")],
                         ["property", Str("Sheetfile"), Str(s.filename), ["at", fmt(x), fmt(y + 26.0), "0"],
                          effects(justify="left top")],
                         ["instances", ["project", Str(self.project),
                                        ["path", Str(f"/{root_uuid}"), ["page", Str(str(i + 2))]]]]])
        root.append(["sheet_instances", ["path", Str("/"), ["page", Str("1")]]])
        root.append(["embedded_fonts", "no"])
        return dumps(root) + "\n"


def _text(s: str, x: float, y: float, u: str, size: float = 2.0) -> list:
    return ["text", Str(s), ["exclude_from_sim", "no"], ["at", fmt(x), fmt(y), "0"],
            ["effects", ["font", ["size", fmt(size), fmt(size)]], ["justify", "left", "top"]], ["uuid", Str(u)]]


class _NoFit(Exception):
    pass


class _SheetWriter:
    def __init__(self, design: Design, sheet: Sheet, path: str, global_nets: set, page: int):
        self.d, self.s, self.path, self.global_nets, self.page = design, sheet, path, global_nets, page
        self.items: list = []
        self.lib_ids: dict[str, list] = {}
        self.pwr = 0
        self.key = f"{design.project}/{sheet.filename}"

    def u(self, *parts) -> str:
        return uid(self.key, *parts)

    def label_len(self, net: str) -> float:
        if net == "GND":
            return 3.0
        if net == "NC":
            return 0.0
        return len(net) * FONT * 0.85 + (3.5 if net in self.global_nets else 1.0)

    def render(self) -> str:
        for paper in dict.fromkeys([self.s.paper, "A4", "A3"]):
            try:
                self.items, self.lib_ids, self.pwr = [], {}, 0
                self.s.paper = paper
                return self._render()
            except _NoFit:
                continue
        raise ValueError(f"sheet {self.s.name}: parts do not fit on A3")

    def _render(self) -> str:
        w, h = PAPER[self.s.paper]
        left, top, right, bottom = 20.32, 33.02, w - 20.32, h - 45.72
        x, y, row_h = left, top, 0.0
        if self.s.note:
            self.items.append(_text(self.s.note, left, 15.24, self.u("note"), 1.8))
        for part in self.s.parts:
            sym = self.d.symbol(part.lib_id)
            pins = symbol_pins(sym)
            nets = self.d.resolve_pins(part)
            bx0, by0, bx1, by1 = symbol_bbox(sym, pins)
            ex0, ey0, ex1, ey1 = bx0, by0, bx1, by1
            for p in pins:
                ux, uy = p.outward()
                reach = STUB + self.label_len(nets[p.number]) if nets[p.number] != "NC" else 0
                px, py = p.x + ux * reach, -p.y + uy * reach
                ex0, ex1 = min(ex0, px, p.x - 1), max(ex1, px, p.x + 1)
                ey0, ey1 = min(ey0, py, -p.y - 1), max(ey1, py, -p.y + 1)
            side_pins = any(p.outward()[0] != 0 for p in pins)
            if not side_pins:                     # room for ref/value text to the right
                ex1 = max(ex1, bx1 + 2 + max(len(part.ref), len(part.value)) * FONT * 0.8)
            ey0 -= 5.08 if side_pins else 0      # room for ref/value above the body
            ey1 += 2.54 if side_pins else 0
            pw, ph = ex1 - ex0 + 5.08, ey1 - ey0 + 5.08
            if x + pw > right and x > left:
                x, y, row_h = left, y + row_h, 0.0
            if y + ph > bottom:
                raise _NoFit()
            ox, oy = snap(x - ex0 + 2.54, 2.54), snap(y - ey0 + 2.54, 2.54)
            self.place(part, sym, pins, nets, ox, oy, (bx0, by0, bx1, by1), side_pins)
            x += pw
            row_h = max(row_h, ph)

        lib_symbols = ["lib_symbols"]
        for lib_id, sym in sorted(self.lib_ids.items()):
            s = copy.deepcopy(sym)
            s[1] = Str(lib_id)
            lib_symbols.append(s)
        root = ["kicad_sch", ["version", SCH_VERSION], ["generator", Str("ko-kisch")],
                ["generator_version", Str("9.0")], ["uuid", Str(self.u("sheet"))], ["paper", Str(self.s.paper)],
                self.d._title_block(f"{self.d.title}: {self.s.name}"), lib_symbols, *self.items,
                ["embedded_fonts", "no"]]
        return dumps(root) + "\n"

    def place(self, part, sym, pins, nets, ox, oy, bbox, side_pins):
        self.lib_ids.setdefault(part.lib_id, sym)
        bx0, by0, bx1, by1 = bbox
        bottom_pins = any(p.outward() == (0, 1) for p in pins)
        top_pins = any(p.outward() == (0, -1) for p in pins)
        if side_pins and top_pins:           # top-left corner, clear of the centred top pins
            ref_at, val_at, just = (ox + bx0, oy + by0 - 3.81), (ox + bx0, oy + by0 - 1.27), "left"
        elif side_pins and bottom_pins:      # both above the body: the bottom is taken by pins
            ref_at, val_at, just = (ox, oy + by0 - 3.81), (ox, oy + by0 - 1.27), None
        elif side_pins:
            ref_at, val_at, just = (ox, oy + by0 - 1.27), (ox, oy + by1 + 2.54), None
        else:
            ref_at, val_at, just = (ox + bx1 + 1.27, oy - 1.27), (ox + bx1 + 1.27, oy + 1.27), "left"
        hidden_ref = part.ref.startswith("#")
        props = [
            ["property", Str("Reference"), Str(part.ref), ["at", fmt(ref_at[0]), fmt(ref_at[1]), "0"],
             effects(hide=hidden_ref, justify=just)],
            ["property", Str("Value"), Str(part.value), ["at", fmt(val_at[0]), fmt(val_at[1]), "0"],
             effects(justify=just)],
            ["property", Str("Footprint"), Str(part.footprint), ["at", fmt(ox), fmt(oy), "0"], effects(hide=True)],
            ["property", Str("Datasheet"), Str(part.datasheet or "~"), ["at", fmt(ox), fmt(oy), "0"], effects(hide=True)],
            ["property", Str("Description"), Str(part.description), ["at", fmt(ox), fmt(oy), "0"], effects(hide=True)],
        ]
        if part.lcsc:
            props.append(["property", Str("LCSC"), Str(part.lcsc), ["at", fmt(ox), fmt(oy), "0"], effects(hide=True)])
        if part.mpn:
            props.append(["property", Str("MPN"), Str(part.mpn), ["at", fmt(ox), fmt(oy), "0"], effects(hide=True)])
        inst = ["symbol", ["lib_id", Str(part.lib_id)], ["at", fmt(ox), fmt(oy), "0"], ["unit", "1"],
                ["exclude_from_sim", "no"], ["in_bom", "yes" if part.in_bom else "no"], ["on_board", "yes"],
                ["dnp", "yes" if part.dnp else "no"], ["uuid", Str(self.u("sym", part.ref))], *props]
        for p in pins:
            inst.append(["pin", Str(p.number), ["uuid", Str(self.u("pin", part.ref, p.number))]])
        inst.append(["instances", ["project", Str(self.d.project),
                                   ["path", Str(self.path), ["reference", Str(part.ref)], ["unit", "1"]]]])
        self.items.append(inst)

        done = {}
        for p in pins:
            sx, sy = snap(ox + p.x), snap(oy - p.y)
            net = nets[p.number]
            key = (sx, sy)
            if key in done:
                if done[key] != net:
                    raise ValueError(f"{part.ref}: stacked pins at {key} on nets {done[key]} and {net}")
                continue
            done[key] = net
            self.connect(part.ref, p, sx, sy, net)

    def connect(self, ref, pin, sx, sy, net):
        tag = f"{ref}.{pin.number}"
        if net == "NC":
            self.items.append(["no_connect", ["at", fmt(sx), fmt(sy)], ["uuid", Str(self.u("nc", tag))]])
            return
        ux, uy = pin.outward()
        ex, ey = snap(sx + ux * STUB), snap(sy + uy * STUB)
        self.items.append(["wire", ["pts", ["xy", fmt(sx), fmt(sy)], ["xy", fmt(ex), fmt(ey)]],
                           ["stroke", ["width", "0"], ["type", "default"]], ["uuid", Str(self.u("wire", tag))]])
        if net == "GND":
            self.gnd(ex, ey, {(0, 1): 0, (0, -1): 180, (1, 0): 90, (-1, 0): 270}[(ux, uy)], tag)
            return
        angle, just = {(1, 0): (0, "left"), (-1, 0): (180, "right"),
                       (0, -1): (90, "left"), (0, 1): (270, "right")}[(ux, uy)]
        if net in self.global_nets:
            self.items.append(["global_label", Str(net), ["shape", "passive"], ["at", fmt(ex), fmt(ey), str(angle)],
                               ["fields_autoplaced", "yes"], effects(justify=just), ["uuid", Str(self.u("gl", tag))],
                               ["property", Str("Intersheetrefs"), Str("${INTERSHEET_REFS}"),
                                ["at", fmt(ex), fmt(ey), "0"], effects(hide=True)]])
        else:
            self.items.append(["label", Str(net), ["at", fmt(ex), fmt(ey), str(angle)], ["fields_autoplaced", "yes"],
                               effects(justify=f"{just} bottom"), ["uuid", Str(self.u("lbl", tag))]])

    def gnd(self, x, y, rot, tag):
        self.pwr += 1
        ref = f"#PWR0{self.page}{self.pwr:02d}"
        sym = kicad_symbol("power:GND")
        self.lib_ids.setdefault("power:GND", sym)
        vx, vy = {0: (x, y + 3.81), 180: (x, y - 3.81), 90: (x + 3.81, y), 270: (x - 3.81, y)}[rot]
        self.items.append(["symbol", ["lib_id", Str("power:GND")], ["at", fmt(x), fmt(y), str(rot)], ["unit", "1"],
                           ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"], ["dnp", "no"],
                           ["uuid", Str(self.u("gnd", tag))],
                           ["property", Str("Reference"), Str(ref), ["at", fmt(x), fmt(y), "0"], effects(hide=True)],
                           ["property", Str("Value"), Str("GND"), ["at", fmt(vx), fmt(vy), "0"], effects()],
                           ["property", Str("Footprint"), Str(""), ["at", fmt(x), fmt(y), "0"], effects(hide=True)],
                           ["property", Str("Datasheet"), Str(""), ["at", fmt(x), fmt(y), "0"], effects(hide=True)],
                           ["property", Str("Description"), Str(""), ["at", fmt(x), fmt(y), "0"], effects(hide=True)],
                           ["pin", Str("1"), ["uuid", Str(self.u("gndpin", tag))]],
                           ["instances", ["project", Str(self.d.project),
                                          ["path", Str(self.path), ["reference", Str(ref)], ["unit", "1"]]]]])
