#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate the three custom footprints of the core board into lib/ko.pretty.

All dimensions come from the manufacturers' drawings (see each function):
  * u-blox BMD-340: "Recommended PCB land pads" (datasheet UBX-19033353 R13, fig. 12) for pad
    positions, "Pin assignment (top view)" (fig. 2) for pad numbers, sec. 6.1 for the antenna keep-out.
  * TI BQ25628E, package RYK0018A (WQFN-HR 18): "Example board layout", datasheet SLUSFA4C p. 75.
  * Hirose FH34SRJ-24S-0.5SH: "Recommended PCB mounting pattern", catalogue 2018-10 p. 4.

Coordinates in this file follow KiCad: x right, y DOWN, millimetres, origin at the part centre.
Datasheet drawings use y up, so their y values are negated here.
"""
import pathlib
import uuid

OUT = pathlib.Path(__file__).resolve().parent.parent / "lib" / "ko.pretty"
OUT3D = OUT.parent / "ko.3dshapes"


def vrml_boxes(name, boxes):
    """Write a simple VRML 2.0 model made of coloured boxes for 3D renders (not for MCAD).
    boxes: (x0, y0, z0, x1, y1, z1, (r, g, b)) in mm, x right, y DOWN (KiCad footprint), z up.
    KiCad reads VRML in units of 0.1 inch."""
    u = 1 / 2.54
    parts = []
    for x0, y0, z0, x1, y1, z1, (r, g, b) in boxes:
        ya, yb = -y1, -y0                      # VRML y up
        v = [(x, y, z) for z in (z0, z1) for y in (ya, yb) for x in (x0, x1)]
        pts = ", ".join(f"{x * u:.4f} {y * u:.4f} {z * u:.4f}" for x, y, z in v)
        faces = "0 2 3 1 -1 4 5 7 6 -1 0 1 5 4 -1 2 6 7 3 -1 0 4 6 2 -1 1 3 7 5 -1"
        parts.append(f"Shape {{ appearance Appearance {{ material Material {{ diffuseColor {r} {g} {b} "
                     f"specularColor 0.3 0.3 0.3 shininess 0.4 }} }} geometry IndexedFaceSet {{ "
                     f"coord Coordinate {{ point [ {pts} ] }} coordIndex [ {faces} ] }} }}")
    OUT3D.mkdir(parents=True, exist_ok=True)
    (OUT3D / f"{name}.wrl").write_text("#VRML V2.0 utf8\n" + "\n".join(parts) + "\n")
NS = uuid.UUID("2b7f0c1e-9a4d-4c3b-8e5f-6d1a2b3c4d5e")
VERSION = "20241229"


def uid(*p) -> str:
    return str(uuid.uuid5(NS, "/".join(p)))


def f(v: float) -> str:
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


class FP:
    def __init__(self, name, descr, tags, ref_y, val_y):
        self.name, self.items = name, []
        self.head = (f'(footprint "{name}"\n\t(version {VERSION})\n\t(generator "ko-gen")\n'
                     f'\t(generator_version "9.0")\n\t(layer "F.Cu")\n\t(descr "{descr}")\n\t(tags "{tags}")\n')
        self.prop("Reference", "REF**", 0, ref_y, "F.SilkS")
        self.prop("Value", name, 0, val_y, "F.Fab")
        self.prop("Datasheet", "", 0, 0, "F.Fab", hide=True)
        self.prop("Description", descr, 0, 0, "F.Fab", hide=True)
        self.items.append("\t(attr smd)\n")

    def prop(self, key, value, x, y, layer, hide=False):
        h = "\n\t\t(hide yes)" if hide else ""
        self.items.append(f'\t(property "{key}" "{value}"\n\t\t(at {f(x)} {f(y)} 0)\n\t\t(layer "{layer}"){h}\n'
                          f'\t\t(uuid "{uid(self.name, key)}")\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1 1)\n'
                          f'\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)\n\t)\n')

    def line(self, x1, y1, x2, y2, layer, w):
        self.items.append(f'\t(fp_line\n\t\t(start {f(x1)} {f(y1)})\n\t\t(end {f(x2)} {f(y2)})\n'
                          f'\t\t(stroke\n\t\t\t(width {f(w)})\n\t\t\t(type solid)\n\t\t)\n\t\t(layer "{layer}")\n'
                          f'\t\t(uuid "{uid(self.name, "line", layer, str(len(self.items)))}")\n\t)\n')

    def rect(self, x1, y1, x2, y2, layer, w):
        for a, b, c, d in ((x1, y1, x2, y1), (x2, y1, x2, y2), (x2, y2, x1, y2), (x1, y2, x1, y1)):
            self.line(a, b, c, d, layer, w)

    def circle(self, x, y, r, layer, w):
        self.items.append(f'\t(fp_circle\n\t\t(center {f(x)} {f(y)})\n\t\t(end {f(x + r)} {f(y)})\n'
                          f'\t\t(stroke\n\t\t\t(width {f(w)})\n\t\t\t(type solid)\n\t\t)\n\t\t(fill yes)\n'
                          f'\t\t(layer "{layer}")\n\t\t(uuid "{uid(self.name, "circ", str(len(self.items)))}")\n\t)\n')

    def pad(self, num, x, y, w, h, shape="rect", rratio=0.25, layers='"F.Cu" "F.Paste" "F.Mask"'):
        rr = f"\n\t\t(roundrect_rratio {rratio})" if shape == "roundrect" else ""
        self.items.append(f'\t(pad "{num}" smd {shape}\n\t\t(at {f(x)} {f(y)})\n\t\t(size {f(w)} {f(h)})\n'
                          f'\t\t(layers {layers}){rr}\n\t\t(uuid "{uid(self.name, "pad", num, f(x), f(y))}")\n\t)\n')

    def thpad(self, num, x, y, w, h, drill, shape="rect", offset=None, castellated=False):
        """Plated through-hole pad; drill is a diameter or (width, height) for an oval slot."""
        d = f"oval {f(drill[0])} {f(drill[1])}" if isinstance(drill, tuple) else f(drill)
        off = f"\n\t\t\t(offset {f(offset[0])} {f(offset[1])})" if offset else ""
        prop = "\n\t\t(property pad_prop_castellated)" if castellated else ""
        self.items.append(f'\t(pad "{num}" thru_hole {shape}\n\t\t(at {f(x)} {f(y)})\n\t\t(size {f(w)} {f(h)})\n'
                          f'\t\t(drill {d}{off}\n\t\t)\n\t\t(layers "*.Cu" "*.Mask"){prop}\n'
                          f'\t\t(remove_unused_layers no)\n\t\t(uuid "{uid(self.name, "th", num, f(x), f(y))}")\n\t)\n')

    def npth(self, x, y, dia):
        self.items.append(f'\t(pad "" np_thru_hole circle\n\t\t(at {f(x)} {f(y)})\n\t\t(size {f(dia)} {f(dia)})\n'
                          f'\t\t(drill {f(dia)})\n\t\t(layers "*.Cu" "*.Mask")\n'
                          f'\t\t(uuid "{uid(self.name, "npth", f(x), f(y))}")\n\t)\n')

    def custom_pad(self, num, ax, ay, poly):
        """Pad anchored at (ax, ay) with a polygon outline given in absolute footprint coordinates."""
        pts = " ".join(f"(xy {f(x - ax)} {f(y - ay)})" for x, y in poly)
        self.items.append(f'\t(pad "{num}" smd custom\n\t\t(at {f(ax)} {f(ay)})\n\t\t(size 0.2 0.2)\n'
                          f'\t\t(layers "F.Cu" "F.Paste" "F.Mask")\n\t\t(options\n\t\t\t(clearance outline)\n'
                          f'\t\t\t(anchor rect)\n\t\t)\n\t\t(primitives\n\t\t\t(gr_poly\n\t\t\t\t(pts {pts})\n'
                          f'\t\t\t\t(width 0)\n\t\t\t\t(fill yes)\n\t\t\t)\n\t\t)\n'
                          f'\t\t(uuid "{uid(self.name, "pad", num)}")\n\t)\n')

    def keepout(self, name, poly):
        pts = " ".join(f"(xy {f(x)} {f(y)})" for x, y in poly)
        self.items.append(f'\t(zone\n\t\t(net 0)\n\t\t(net_name "")\n\t\t(layers "*.Cu")\n'
                          f'\t\t(uuid "{uid(self.name, "zone", name)}")\n\t\t(name "{name}")\n'
                          f'\t\t(hatch edge 0.5)\n\t\t(connect_pads\n\t\t\t(clearance 0)\n\t\t)\n'
                          f'\t\t(min_thickness 0.25)\n\t\t(filled_areas_thickness no)\n\t\t(keepout\n'
                          f'\t\t\t(tracks not_allowed)\n\t\t\t(vias not_allowed)\n\t\t\t(pads not_allowed)\n'
                          f'\t\t\t(copperpour not_allowed)\n\t\t\t(footprints allowed)\n\t\t)\n'
                          f'\t\t(placement\n\t\t\t(enabled no)\n\t\t\t(sheetname "")\n\t\t)\n'
                          f'\t\t(fill\n\t\t\t(thermal_gap 0.5)\n\t\t\t(thermal_bridge_width 0.5)\n\t\t)\n'
                          f'\t\t(polygon\n\t\t\t(pts {pts})\n\t\t)\n\t)\n')

    def text(self, txt, x, y, layer="F.SilkS", size=0.8):
        self.items.append(f'\t(fp_text user "{txt}"\n\t\t(at {f(x)} {f(y)} 0)\n\t\t(layer "{layer}")\n'
                          f'\t\t(uuid "{uid(self.name, "text", txt, f(x), f(y))}")\n\t\t(effects\n\t\t\t(font\n'
                          f'\t\t\t\t(size {f(size)} {f(size)})\n\t\t\t\t(thickness 0.12)\n\t\t\t)\n\t\t)\n\t)\n')

    def model(self):
        self.items.append(f'\t(model "${{KIPRJMOD}}/lib/ko.3dshapes/{self.name}.wrl"\n\t\t(offset\n\t\t\t(xyz 0 0 0)\n'
                          f'\t\t)\n\t\t(scale\n\t\t\t(xyz 1 1 1)\n\t\t)\n\t\t(rotate\n\t\t\t(xyz 0 0 0)\n\t\t)\n\t)\n')

    def write(self):
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"{self.name}.kicad_mod").write_text(self.head + "".join(self.items) + "\t(embedded_fonts no)\n)\n")


# --------------------------------------------------------------------------- BMD-340

def bmd340():
    """68 pads, 0.50 x 0.50 mm. Grid measured from fig. 12 (1.10 mm column pitch, staggered rows),
    numbering from fig. 2. Datasheet coordinates (y up) listed per pad, converted below."""
    cols_a = [-2.85, -1.75, -0.65, 0.45, 1.55, 2.65, 3.75, 4.85, 5.95]       # rows A and F (9 pads)
    cols_b = [-2.30, -1.20, -0.10, 1.00, 2.10, 3.20, 4.30]                    # rows B and E (7 pads)
    cols_c = [-1.75, -0.65, 0.45, 1.55, 2.65]                                 # rows C and D (5 pads)
    pads = {}
    for n, x in zip([45, 43, 41, 39, 37, 35, 33, 31, 30], cols_a):
        pads[n] = (x, 4.40)
    for n, x in zip([1, 3, 5, 7, 9, 11, 13, 15, 16], cols_a):
        pads[n] = (x, -4.40)
    for n, x in zip([44, 42, 40, 38, 36, 34, 32], cols_b):
        pads[n] = (x, 3.50)
    for n, x in zip([2, 4, 6, 8, 10, 12, 14], cols_b):
        pads[n] = (x, -3.50)
    for n, x in zip([60, 59, 58, 57, 56], cols_c):
        pads[n] = (x, 2.60)
    for n, x in zip([48, 49, 50, 51, 52], cols_c):
        pads[n] = (x, -2.60)
    for n, y in zip([29, 27, 25, 23, 21, 19, 17], [3.30, 2.20, 1.10, 0.0, -1.10, -2.20, -3.30]):
        pads[n] = (5.95, y)                                                   # column X2
    for n, y in zip([28, 26, 24, 22, 20, 18], [2.75, 1.65, 0.55, -0.55, -1.65, -2.75]):
        pads[n] = (5.05, y)                                                   # column X1
    for n, y in zip([68, 67, 66, 65, 64, 63, 62, 61], [3.85, 2.75, 1.65, 0.55, -0.55, -1.65, -2.75, -3.85]):
        pads[n] = (6.85, y)                                                   # column X3
    for n, y in zip([55, 54, 53], [1.10, 0.0, -1.10]):
        pads[n] = (4.15, y)                                                   # inner column
    pads[46], pads[47] = (-2.85, 1.65), (-2.85, -1.65)
    assert sorted(pads) == list(range(1, 69)), "BMD-340 must have pads 1..68"
    assert len(set(pads.values())) == 68, "duplicate pad position"

    fp = FP("u-blox_BMD-340", "u-blox BMD-340 nRF52840 module, 15.0x10.2 mm LGA, antenna on the left edge (place at board edge)",
            "nRF52840 BLE module u-blox BMD-340", -6.3, 6.3)
    hw, hh = 7.5, 5.1
    fp.rect(-hw, -hh, hw, hh, "F.Fab", 0.1)
    fp.line(-3.1, -hh, -3.1, hh, "F.Fab", 0.1)                               # antenna section boundary
    c = 0.25
    fp.rect(-hw - c, -hh - c, hw + c, hh + c, "F.CrtYd", 0.05)
    s = 0.11
    fp.line(-hw - s, -hh - s, hw + s, -hh - s, "F.SilkS", 0.12)
    fp.line(hw + s, -hh - s, hw + s, hh + s, "F.SilkS", 0.12)
    fp.line(hw + s, hh + s, -hw - s, hh + s, "F.SilkS", 0.12)
    fp.line(-hw - s, hh + s, -hw - s, -hh - s, "F.SilkS", 0.12)
    fp.circle(-2.85, 5.6, 0.15, "F.SilkS", 0.1)                              # pin 1 marker below pad 1
    for n, (x, y) in sorted(pads.items()):
        fp.pad(str(n), x, -y, 0.5, 0.5)
    # Antenna keep-out on all copper layers: the 4.4 mm antenna section of the module (datasheet 6.1).
    # The board adds a matching strip along its edge.
    fp.keepout("BMD-340 antenna keep-out", [(-hw, -hh - 0.3), (-3.1, -hh - 0.3), (-3.1, hh + 0.3), (-hw, hh + 0.3)])
    vrml_boxes(fp.name, [(-hw, -hh, 0, hw, hh, 0.5, (0.12, 0.35, 0.22)),            # module PCB
                         (-2.9, -4.6, 0.5, 6.9, 4.6, 1.9, (0.75, 0.75, 0.73))])     # shield can
    fp.model()
    fp.write()


# --------------------------------------------------------------------------- BQ25628E (RYK0018A)

def ryk18():
    """WQFN-HR 18, 3.0 x 2.5 mm body. Pads measured from TI's land pattern (scale 20x) and checked
    against its dimension labels. Narrow pad dimension 0.2 mm, corner radius 0.05 mm.
    Datasheet coordinates (y up): left/right pad rows at y = 0.393 / -0.007 / -0.407."""
    fp = FP("Texas_RYK_WQFN-HR-18", "TI RYK0018A WQFN-HR 18-pin 3.0x2.5 mm (BQ25628E), per TI example board layout",
            "WQFN-HR RYK0018A BQ25628E", -2.4, 2.4)
    rr = 0.25
    def vpad(n, x, y0, y1):          # vertical bar, datasheet y range
        fp.pad(n, x, -(y0 + y1) / 2, 0.2, abs(y1 - y0), "roundrect", rr)
    def hpad(n, x0, x1, y):          # horizontal bar
        fp.pad(n, (x0 + x1) / 2, -y, abs(x1 - x0), 0.2, "roundrect", rr)
    # top row (pins 15..18), bottom row (6..9)
    vpad("18", -0.625, 0.831, 1.450)
    vpad("17", -0.225, 0.450, 1.450)
    vpad("16", 0.175, 0.450, 1.450)
    vpad("15", 0.575, 0.450, 1.450)
    vpad("6", -0.625, -0.850, -1.450)
    vpad("7", -0.225, -0.850, -1.450)
    vpad("8", 0.175, -0.450, -1.450)
    vpad("9", 0.575, -0.450, -1.450)
    # left column (pins 2..4), right column (11..13)
    for n, y in (("2", 0.393), ("3", -0.007), ("4", -0.407)):
        hpad(n, -1.7005, -1.0755, y)
    for n, y in (("13", 0.393), ("12", -0.007), ("11", -0.407)):
        hpad(n, 1.100, 1.700, y)
    # corner L-shaped pads 1, 5, 10, 14 (horizontal leg 0.2 high, vertical leg 0.2 wide, 0.7 long)
    def L(n, xh0, xh1, yh, xv, yv_end):
        """Horizontal leg from xh0..xh1 at yh (centre), vertical leg at xv (centre) from yh to yv_end."""
        sgn = 1 if yv_end > yh else -1
        hx0, hx1 = min(xh0, xh1), max(xh0, xh1)
        vx0, vx1 = xv - 0.1, xv + 0.1
        ya, yb = yh - 0.1 * sgn, yv_end     # outer edge of horizontal leg ... end of vertical leg
        if xv - 0.1 <= hx0 + 1e-9:           # vertical leg on the left end of the horizontal leg
            poly = [(hx0, ya), (hx1, ya), (hx1, yh + 0.1 * sgn), (vx1, yh + 0.1 * sgn), (vx1, yb), (vx0, yb)]
        else:                                 # vertical leg on the right end
            poly = [(hx0, ya), (hx1, ya), (hx1, yb), (vx0, yb), (vx0, yh + 0.1 * sgn), (hx0, yh + 0.1 * sgn)]
        fp.custom_pad(n, xv, -yh, [(x, -y) for x, y in poly])
    L("1", -1.7005, -0.925, 0.85, -1.025, 1.45)
    L("14", 0.875, 1.700, 0.85, 0.975, 1.45)
    L("5", -1.7005, -0.925, -0.85, -1.025, -1.45)
    L("10", 0.875, 1.700, -0.85, 0.975, -1.45)
    bw, bh = 1.5, 1.25
    fp.rect(-bw, -bh, bw, bh, "F.Fab", 0.1)
    fp.rect(-1.95, -1.7, 1.95, 1.7, "F.CrtYd", 0.05)
    fp.circle(-1.95, -1.55, 0.12, "F.SilkS", 0.1)                            # pin 1 marker (top-left)
    vrml_boxes(fp.name, [(-bw, -bh, 0, bw, bh, 0.75, (0.1, 0.1, 0.1))])
    fp.model()
    fp.write()


# --------------------------------------------------------------------------- Hirose FH34SRJ-24S-0.5SH

def fh34srj(n=24):
    """Signal pads 0.30 x 0.80 mm at 0.5 mm pitch (B = 11.5 mm for 24 pins), mounting tabs 0.40 x 0.80 mm,
    tab outer edges 3.3 mm from the signal pad edge, tab span E = 13.1 / F = 13.9 mm.
    Contact 1 is at +x (right) with the leads at the top (-y), as in Hirose's top view.
    The FFC enters from the tab side (+y), so that side faces the board edge."""
    b = 0.5 * (n - 1)
    fp = FP(f"Hirose_FH34SRJ-{n}S-0.5SH_1x{n}-1MP_P0.50mm_Horizontal",
            f"Hirose FH34SRJ {n}-pin 0.5 mm FFC/FPC connector, back-flip, 1.0 mm high, top/bottom contact; FFC enters from +y",
            "Hirose FH34SRJ FFC FPC connector 0.5mm", -1.6, 4.6)
    for i in range(n):
        fp.pad(str(i + 1), b / 2 - i * 0.5, 0, 0.3, 0.8)
    tab_x = (13.1 + 13.9) / 4
    tab_y = -0.4 + 3.3 - 0.4
    fp.pad("MP", -tab_x, tab_y, 0.4, 0.8)
    fp.pad("MP", tab_x, tab_y, 0.4, 0.8)
    a = (b + 2.5) / 2                    # body length A = 0.5*(n-1) + 2.5
    fp.rect(-a, -0.4, a, 3.4, "F.Fab", 0.1)
    fp.rect(-a - 0.25, -0.65, a + 0.25, 3.65, "F.CrtYd", 0.05)
    fp.line(-a, 1.0, -a, 2.0, "F.SilkS", 0.12)
    fp.line(a, 1.0, a, 2.0, "F.SilkS", 0.12)
    fp.circle(b / 2, -0.85, 0.12, "F.SilkS", 0.1)                            # contact 1 marker
    fp.line(-a, 3.4, a, 3.4, "F.Fab", 0.1)
    vrml_boxes(fp.name, [(-a, 0.2, 0, a, 3.4, 0.75, (0.08, 0.08, 0.08)),             # body
                         (-a + 0.6, -0.1, 0.75, a - 0.6, 1.4, 1.0, (0.2, 0.2, 0.2)),   # back-flip actuator
                         (-b / 2 - 0.15, -0.4, 0, b / 2 + 0.15, 0.2, 0.15, (0.85, 0.7, 0.3))])  # leads
    fp.model()
    fp.write()


# --------------------------------------------------------------------------- HX TYPE-C 16P L10.0 (long body)

def usbc_hx_l10():
    """HANXIA HX TYPE-C 16P L10.0 (LCSC C41427495), USB 2.0 receptacle with a 10.0 mm long body, so the
    mouth reaches through a case wall. From the maker's drawing (recommended PCB layout and side view),
    distances along the plug axis measured from the far end of the signal pads (R0):
    pad length 1.15, rear shell legs at R0+1.14 (2.10 x 0.6 slot, drill 1.70), pegs (0.65) at R0+1.70,
    front shell legs at R0+5.32 (1.80 x 0.6, drill 1.40), mouth at R0+10.59 (front legs + 5.27).
    Origin here: midpoint of the two pegs; mouth towards +y. Pads 12 positions: 6.40 / 4.80 spans for the
    wide pads (0.6), 3.50 / 2.50 / 1.50 / 0.50 for the narrow ones (0.3). The board edge goes at y = +5.0,
    so the shell sticks out 3.9 mm beyond it."""
    fp = FP("USB_C_Receptacle_HX_TYPE-C-16P_L10.0", "HX TYPE-C 16P L10.0 USB 2.0 Type-C receptacle, 10 mm long body, board edge at y=+5.0 (shell overhangs 3.9 mm)",
            "USB C Type-C receptacle long body HX L10.0", -3.0, 9.6)
    pad_y = -1.70 + 0.575
    pads = [("A1", -3.20, 0.6), ("B12", -3.20, 0.6), ("A4", -2.40, 0.6), ("B9", -2.40, 0.6), ("B8", -1.75, 0.3),
            ("A5", -1.25, 0.3), ("B7", -0.75, 0.3), ("A6", -0.25, 0.3), ("A7", 0.25, 0.3), ("B6", 0.75, 0.3),
            ("A8", 1.25, 0.3), ("B5", 1.75, 0.3), ("B4", 2.40, 0.6), ("A9", 2.40, 0.6), ("B1", 3.20, 0.6), ("A12", 3.20, 0.6)]
    for n, x, w in pads:
        fp.pad(n, x, pad_y, w, 1.15)
    for sx in (-1, 1):
        fp.npth(sx * 2.89, 0, 0.65)
        fp.thpad("S1", sx * 4.32, -0.56, 1.0, 2.10, (0.6, 1.70), "oval")
        fp.thpad("S1", sx * 4.32, 3.62, 1.0, 1.80, (0.6, 1.40), "oval")
    rear, mouth, edge = -1.11, 8.89, 5.0
    fp.rect(-4.47, rear, 4.47, mouth, "F.Fab", 0.1)
    fp.line(-5.5, edge, 5.5, edge, "F.Fab", 0.1)                                # PCB edge
    fp.rect(-5.0, -2.0, 5.0, edge, "F.CrtYd", 0.05)
    fp.line(-5.0, -0.9, -5.0, -1.9, "F.SilkS", 0.12)
    fp.line(5.0, -0.9, 5.0, -1.9, "F.SilkS", 0.12)
    vrml_boxes(fp.name, [(-4.47, rear, 0, 4.47, mouth, 3.26, (0.78, 0.78, 0.8))])
    fp.model()
    fp.write()


# --------------------------------------------------------------------------- TPS2121 (RUX0012A)

def rux12():
    """TI RUX0012A VQFN-HR 12, 2.0 x 2.5 mm, per TI's example board layout (datasheet SLVSEA3F p. 39), top view,
    pin 1 upper left: eight 0.2 x 0.6 pads at 0.5 mm pitch in rows at y = -/+1.15 (12..9 top, 3..6 bottom),
    four 1.05 x 0.4 power pads at x = -/+0.675, y = -/+0.35 (1, 2 left; 8, 7 right), corner radius 0.05."""
    fp = FP("Texas_RUX_VQFN-HR-12_2x2.5mm", "TI RUX0012A VQFN-HR 12-pin 2.0x2.5 mm (TPS2121), per TI example board layout",
            "VQFN-HR RUX0012A TPS2121", -2.3, 2.3)
    for n, x in (("12", -0.75), ("11", -0.25), ("10", 0.25), ("9", 0.75)):
        fp.pad(n, x, -1.15, 0.2, 0.6, "roundrect", 0.25)
    for n, x in (("3", -0.75), ("4", -0.25), ("5", 0.25), ("6", 0.75)):
        fp.pad(n, x, 1.15, 0.2, 0.6, "roundrect", 0.25)
    for n, x, y in (("1", -0.675, -0.35), ("2", -0.675, 0.35), ("8", 0.675, -0.35), ("7", 0.675, 0.35)):
        fp.pad(n, x, y, 1.05, 0.4, "roundrect", 0.125)
    fp.rect(-1.0, -1.25, 1.0, 1.25, "F.Fab", 0.1)
    fp.rect(-1.45, -1.7, 1.45, 1.7, "F.CrtYd", 0.05)
    fp.circle(-1.3, -1.45, 0.1, "F.SilkS", 0.1)                                # pin 1 marker
    vrml_boxes(fp.name, [(-1.0, -1.25, 0, 1.0, 1.25, 0.9, (0.1, 0.1, 0.1))])
    fp.model()
    fp.write()


# --------------------------------------------------------------------------- castellated board edge

def castellated(groups=((1, 17, 0.0), (18, 33, 47.0)), pitch=2.0):
    """Castellated edge (plated half holes) joining the core board to the switch board (switch-board
    contract, D-43). The board edge runs along x = 0, the board lies at +x. Contacts come in groups
    (first, last, y of the first); the origin is contact 1, contact 1 at the back (-y). Each contact: 0.8 mm
    hole centred on the edge, copper 1.4 x 2.4 mm reaching 1.8 mm into the board on both sides."""
    n = groups[-1][1]
    name = f"Castellated_1x{n}_P{pitch:.2f}mm_Edge_" + "_".join(f"{a}-{b}" for a, b, _ in groups)
    y_end = groups[-1][2] + (groups[-1][1] - groups[-1][0]) * pitch
    fp = FP(name, f"{n} castellated edge contacts in {len(groups)} groups, {pitch} mm pitch, board edge at x=0, board at +x",
            "castellated edge half hole board-to-board", 0, y_end + 2.0)
    for first, last, y0 in groups:
        for i in range(first, last + 1):
            # pad position = hole position (on the edge); the offset moves the copper 0.6 mm into the board
            fp.thpad(str(i), 0.0, y0 + (i - first) * pitch, 2.4, 1.4, 0.8, "rect", offset=(0.6, 0), castellated=True)
        y1 = y0 + (last - first) * pitch
        fp.line(0, y0 - 1.0, 0, y1 + 1.0, "F.Fab", 0.1)                         # board edge
        fp.rect(-0.4, y0 - 1.0, 2.1, y1 + 1.0, "F.CrtYd", 0.05)
    fp.circle(2.4, 0.0, 0.15, "F.SilkS", 0.1)                                  # contact 1 marker
    fp.write()
    return name


# --------------------------------------------------------------------------- solder pads for wires (D-43)

WIRE_PADS = {
    "Switch": ("POWER SW", ["SYS", "EN"]),
    "NTC": ("NTC", ["NTC", "GND"]),
    "SWD": ("SWD", ["3V0", "DIO", "CLK", "RST", "GND"]),
    "Haptic": ("HAPTIC", ["V5", "3V0", "GND", "SDA", "SCL", "EN"]),
    "Underglow": ("UNDERGLOW", ["LED", "DAT", "GND"]),
}


def wire_pads(key, pitch=2.2, w=1.5, h=2.0):
    """A row of bare SMD pads to solder wires to, each labelled on the silkscreen (the group name is the Value,
    on the assembly layer). Copper only: excluded from BOM and position files. Placed on the bottom side by
    gen_pcb.py (KiCad mirrors pads and text)."""
    title, labels = WIRE_PADS[key]
    n = len(labels)
    fp = FP(f"WirePads_{key}", f"{n} solder pads for wires ({title}), {pitch} mm pitch, {w} x {h} mm",
            "solder pad wire", -(h / 2 + 2.0), h / 2 + 2.2)
    fp.items[-1] = "\t(attr smd exclude_from_pos_files exclude_from_bom)\n"
    fp.items[0] = fp.items[0].replace('(layer "F.SilkS")', '(layer "F.Fab")')     # the labels say enough
    x0 = -(n - 1) * pitch / 2
    for i, lab in enumerate(labels):
        x = x0 + i * pitch
        fp.pad(str(i + 1), x, 0, w, h, "roundrect", 0.15, layers='"F.Cu" "F.Mask"')
        fp.text(lab, x, -(h / 2 + 0.7))
    fp.rect(x0 - w / 2 - 0.25, -(h / 2 + 1.25), -x0 + w / 2 + 0.25, h / 2 + 0.25, "F.CrtYd", 0.05)
    fp.write()


def standins():
    """Stand-in 3D models for library footprints whose STEP model is missing from KiCad's package
    (used by gen_pcb.py for J301 and J101; renders only)."""
    vrml_boxes("USB_C_HRO_TYPE-C-31-M-12_standin", [(-4.47, -3.65, 0, 4.47, 3.65, 3.2, (0.78, 0.78, 0.8))])
    vrml_boxes("JST_PH_S2B-PH-SM4-TB_standin", [(-3.0, -1.6, 0, 3.0, 4.4, 4.2, (0.92, 0.92, 0.88)),
                                                (-1.6, 3.4, 1.0, 1.6, 4.41, 3.6, (0.3, 0.3, 0.3))])


if __name__ == "__main__":
    standins()
    bmd340()
    ryk18()
    fh34srj()
    usbc_hx_l10()
    rux12()
    castellated()
    for k in WIRE_PADS:
        wire_pads(k)
    print("footprints written to", OUT)
