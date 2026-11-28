#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Custom footprints of the generated switch boards, written to hardware/switch/lib/ko-switch.pretty.

    python3 generator/ko_gen/footprints.py

Coordinates: KiCad (x right, y DOWN = towards the user), millimetres, origin at the part centre. Every footprint is
drawn as seen from the TOP of the board; parts that sit on the bottom are flipped by the PCB generator.
Sources:
  * Key (Choc v1 + v2 hot-swap): generator/switches/compat.py (kiswitch keyswitch-kicad-library geometry, D-38):
    Choc v1 centre 3.45 / pegs +-5.5 (1.9), Choc v2 centre 5.05 / peg (-5.0, 5.15) (1.6), Kailh CPG1350 socket
    holes 3.05 at the pins (0, -5.9), (5.0, -3.8) and its pads 2.55 x 2.5 at (-3.5, -6.0), (8.5, -3.8) on B.Cu.
  * EKINGLUX E6CC1205RGBC3UDA (C2802677): datasheet Rev. 2.4 p. 4 "Recommended Soldering Pad Design":
    pads 0.75 x 0.7, 2.0 mm between the pad columns, 0.47 mm between the rows; light hole 2.0 mm wide with round
    ends (3.9 mm long, read from the drawing). Pins (top view of the LED): 1 R, 2 anode, 3 G, 4 B.
  * IS31FL3741A QFN-60 7 x 7: datasheet Rev. D p. 22 "Recommended land pattern": 0.22 x 0.74 pads, 0.40 pitch,
    15 per side, 6.05 mm between the inner pad edges, exposed pad 5.40 x 5.40; pin 1 at the top of the left side,
    counter-clockwise (p. 4).
  * Castellated contacts: mirror of the core's edge (hardware/core/tools/gen_footprints.py, SWB-016).
"""
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "hardware" / "core" / "tools"))
import gen_footprints as core  # noqa: E402

LIB = ROOT / "hardware" / "switch" / "lib"
OUT = LIB / "ko-switch.pretty"
OUT3D = LIB / "ko-switch.3dshapes"


class FP(core.FP):
    def model(self):
        self.items.append(f'\t(model "${{KIPRJMOD}}/../lib/ko-switch.3dshapes/{self.name}.wrl"\n\t\t(offset\n'
                          f'\t\t\t(xyz 0 0 0)\n\t\t)\n\t\t(scale\n\t\t\t(xyz 1 1 1)\n\t\t)\n\t\t(rotate\n'
                          f'\t\t\t(xyz 0 0 0)\n\t\t)\n\t)\n')

    def write(self):
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"{self.name}.kicad_mod").write_text(self.head + "".join(self.items) + "\t(embedded_fonts no)\n)\n")

    def npth_oval(self, x, y, w, h):
        self.items.append(f'\t(pad "" np_thru_hole oval\n\t\t(at {core.f(x)} {core.f(y)})\n'
                          f'\t\t(size {core.f(w)} {core.f(h)})\n\t\t(drill oval {core.f(w)} {core.f(h)})\n'
                          f'\t\t(layers "*.Cu" "*.Mask")\n\t\t(uuid "{core.uid(self.name, "npo", core.f(x), core.f(y))}")\n\t)\n')


def boxes(name, bx):
    core.OUT3D = OUT3D
    core.vrml_boxes(name, bx)


BCU = '"B.Cu" "B.Paste" "B.Mask"'
KEY = "Key_Choc_V1V2_Hotswap_CPG1350"
LED = "LED_E6CC1205RGBC3UDA_ReverseMount"
QFN = "Lumissil_QFN-60_7x7mm_P0.4mm_EP5.4mm"


def key():
    """One key position: switch holes for Choc v1 and v2 and the Kailh CPG1350 socket pads on the bottom.
    Pad 1 = socket pin at (0, -5.9) (column side), pad 2 = pin at (5.0, -3.8) (diode side)."""
    fp = FP(KEY, "Kailh Choc v1/v2 switch with CPG1350 hot-swap socket on the bottom (KO switch board, SWB-017)",
            "keyswitch choc v1 v2 hotswap CPG1350", -10.4, 10.4)
    fp.npth(0, 0, 5.05)                                    # Choc v2 centre (takes the v1 centre post too)
    for sx in (-1, 1):
        fp.npth(sx * 5.5, 0, 1.9)                          # Choc v1 pegs
    fp.npth(-5.0, 5.15, 1.6)                               # Choc v2 peg
    fp.npth(0, -5.9, 3.05)                                 # socket sleeves at the switch pins
    fp.npth(5.0, -3.8, 3.05)
    fp.pad("1", -3.5, -6.0, 2.55, 2.5, "roundrect", 0.1, BCU)
    fp.pad("2", 8.5, -3.8, 2.55, 2.5, "roundrect", 0.1, BCU)
    fp.rect(-7.5, -7.5, 7.5, 7.5, "F.Fab", 0.1)            # Choc switch body (15 x 15)
    fp.rect(-9.0, -8.5, 9.0, 8.5, "Dwgs.User", 0.1)        # Choc keycap (18 x 17)
    fp.rect(-2.45, -8.45, 7.75, -1.25, "B.Fab", 0.1)       # socket body
    fp.rect(-9.4, -9.4, 9.4, 9.4, "F.CrtYd", 0.05)
    fp.rect(-4.9, -8.6, 9.9, -1.0, "B.CrtYd", 0.05)
    boxes(KEY, [(-2.45, -8.45, -1.85, 7.75, -1.25, -1.6, (0.15, 0.15, 0.15)),        # socket under the board
                (-7.5, -7.5, 0, 7.5, 7.5, 3.0, (0.2, 0.2, 0.22)),                   # switch housing
                (-2.0, -1.5, 3.0, 2.0, 1.5, 6.0, (0.85, 0.2, 0.2))])                # stem
    fp.model()
    fp.write()


def led():
    """Reverse-mount RGB LED, drawn as seen from the top of the board with the LED on the bottom (its lens
    facing up through the light hole). The PCB generator flips it onto B.Cu, which mirrors x, so pads are
    written mirrored here: after the flip pin 1 sits top-left as in the datasheet's top view."""
    fp = FP(LED, "EKINGLUX E6CC1205RGBC3UDA reverse-mount RGB LED, common anode (pin 2), light hole 2.0 x 3.9",
            "LED RGB reverse mount common anode", -2.6, 2.6)
    # datasheet pads start right at the 2.0 mm hole; here the hole is 1.7 mm wide (lens 1.4 mm) and the pads
    # 0.7 mm wide from 1.15 mm out, so copper keeps 0.3 mm from the hole edge and still covers 0.45 mm of each lead
    for num, x, y in (("1", 1.5, -0.585), ("2", -1.5, -0.585), ("3", 1.5, 0.585), ("4", -1.5, 0.585)):
        fp.pad(num, x, y, 0.7, 0.7)
    fp.npth_oval(0, 0, 1.7, 3.9)
    fp.rect(-1.6, -0.625, 1.6, 0.625, "F.Fab", 0.1)
    fp.rect(-2.0, -2.2, 2.0, 2.2, "F.CrtYd", 0.05)
    fp.circle(2.2, -0.9, 0.12, "F.SilkS", 0.1)              # pin 1 marker (mirrored side before the flip)
    boxes(LED, [(-1.6, -0.625, 0, 1.6, 0.625, 0.5, (0.95, 0.95, 0.95)),
                (-0.7, -0.5, 0.5, 0.7, 0.5, 1.1, (0.9, 0.95, 1.0))])
    fp.model()
    fp.write()


GLOW = "LED_E6CC1205RGBC3UDA_Underglow"


def glow():
    """The same LED mounted normally on the bottom, lens facing down (underglow). Standard top-view land pattern
    (pin 1 top-left); the flip onto B.Cu turns it into the view from below. No light hole."""
    fp = FP(GLOW, "EKINGLUX E6CC1205RGBC3UDA RGB LED, common anode (pin 2), normal mount (underglow on the bottom)",
            "LED RGB common anode underglow", -1.6, 1.6)
    for num, x, y in (("1", -1.375, -0.585), ("2", 1.375, -0.585), ("3", -1.375, 0.585), ("4", 1.375, 0.585)):
        fp.pad(num, x, y, 0.75, 0.7)
    fp.rect(-1.6, -0.625, 1.6, 0.625, "F.Fab", 0.1)
    fp.rect(-2.0, -1.2, 2.0, 1.2, "F.CrtYd", 0.05)
    fp.circle(-2.2, -0.9, 0.12, "F.SilkS", 0.1)
    boxes(GLOW, [(-1.6, -0.625, 0, 1.6, 0.625, 1.1, (0.95, 0.95, 0.95))])
    fp.model()
    fp.write()


def qfn60():
    fp = FP(QFN, "Lumissil IS31FL3741A QFN-60 7x7 mm, 0.4 mm pitch, EP 5.4 mm, per datasheet Rev. D land pattern",
            "QFN-60 IS31FL3741A", -4.6, 4.6)
    c = 3.025 + 0.37                                       # pad centre from the inner edge
    for i in range(15):
        t = -2.8 + i * 0.4
        fp.pad(str(1 + i), -c, t, 0.74, 0.22, "roundrect", 0.25)      # left side, top to bottom
        fp.pad(str(16 + i), t, c, 0.22, 0.74, "roundrect", 0.25)      # bottom, left to right
        fp.pad(str(31 + i), c, -t, 0.74, 0.22, "roundrect", 0.25)     # right, bottom to top
        fp.pad(str(46 + i), -t, -c, 0.22, 0.74, "roundrect", 0.25)    # top, right to left
    fp.pad("61", 0, 0, 5.4, 5.4, "rect", 0.25, '"F.Cu" "F.Mask"')        # exposed pad (paste below)
    for ix in (-1, 1):
        for iy in (-1, 1):
            fp.pad("", ix * 1.35, iy * 1.35, 2.2, 2.2, "rect", 0.25, '"F.Paste"')
    fp.rect(-3.5, -3.5, 3.5, 3.5, "F.Fab", 0.1)
    fp.rect(-4.0, -4.0, 4.0, 4.0, "F.CrtYd", 0.05)
    fp.circle(-3.9, -3.3, 0.12, "F.SilkS", 0.1)
    boxes(QFN, [(-3.5, -3.5, 0, 3.5, 3.5, 0.9, (0.1, 0.1, 0.1))])
    fp.model()
    fp.write()


CAST = "Castellated_1x33_P2.00mm_Edge_Right_1-17_18-33"


def castellated(groups=((1, 17, 0.0), (18, 33, 47.0)), pitch=2.0):
    """The switch board's half of the core interface (SWB-016): board edge along x = 0, board at -x
    (the core sits to the right). Same contacts and positions as the core's edge, copper reaching into this board."""
    fp = FP(CAST, "33 castellated contacts to the KO core strip, 2.0 mm pitch, board edge at x=0, board at -x",
            "castellated edge half hole board-to-board", 0, 80.0)
    for first, last, y0 in groups:
        for i in range(first, last + 1):
            fp.thpad(str(i), 0.0, y0 + (i - first) * pitch, 2.4, 1.4, 0.8, "rect", offset=(-0.6, 0), castellated=True)
        y1 = y0 + (last - first) * pitch
        fp.line(0, y0 - 1.0, 0, y1 + 1.0, "F.Fab", 0.1)
        fp.rect(-2.1, y0 - 1.0, 0.4, y1 + 1.0, "F.CrtYd", 0.05)
    fp.circle(-2.4, 0.0, 0.15, "F.SilkS", 0.1)
    fp.write()


def copy_core(name):
    """Footprints shared with the core board (same part): copied with their render model."""
    src = ROOT / "hardware" / "core" / "lib"
    txt = (src / "ko.pretty" / f"{name}.kicad_mod").read_text().replace("${KIPRJMOD}/lib/ko.3dshapes",
                                                                         "${KIPRJMOD}/../lib/ko-switch.3dshapes")
    (OUT / f"{name}.kicad_mod").write_text(txt)
    wrl = src / "ko.3dshapes" / f"{name}.wrl"
    if wrl.exists():
        OUT3D.mkdir(parents=True, exist_ok=True)
        shutil.copy(wrl, OUT3D / wrl.name)


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    key()
    led()
    glow()
    qfn60()
    castellated()
    copy_core("USB_C_Receptacle_HX_TYPE-C-16P_L10.0")
    print(f"footprints written to {OUT}")


if __name__ == "__main__":
    main()
