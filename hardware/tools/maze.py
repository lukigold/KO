# SPDX-License-Identifier: GPL-3.0-or-later
"""Grid maze router with targeted rip-up, for the connections an autorouter or hand routing left open.

Works on a loaded pcbnew BOARD: every existing copper item (pads, holes, tracks, vias, keep-out rule
areas, board edge) is rasterised onto a fine grid per copper layer, inflated by half the new track width
plus the clearance, and tagged with its net. A* searches one connection at a time over the routed
layers; vias are allowed where every layer is free. Routes found here are kept apart from the board's
own copper, so a connection that cannot be routed can rip up exactly the routes in its way (found by a
"soft" search that may cross them at a cost) and those are routed again afterwards.

Copper pours are ignored on purpose: they are refilled afterwards and flow around the new tracks.
"""
import heapq
import math
import random
import multiprocessing

import numpy as np
import pcbnew

FREE, BLOCKED = 0, -1
SQ2 = math.sqrt(2)
DIRS = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
        (1, 1, SQ2), (1, -1, SQ2), (-1, 1, SQ2), (-1, -1, SQ2))


def _astar_py(ok, vok, box, S, G, max_nodes, via_cost, M=None, A=None):
    """A* over a (layer, row, column) grid inside box = (i_lo, i_hi, j_lo, j_hi); the search both routers share.

    ok: bool array (L, NY, NX) of passable cells; vok: bool array (NY, NX) where a via may stand.
    Step cost to a cell: gc + c*M + A (float arrays (L, NY, NX) or None); via cost: via_cost, a number or
    an array (NY, NX). S, G: [((i, j), layer)]. Returns the path as [(i, j, layer)] from a start to a
    goal, or None.

    Only the search window is copied, into plain Python lists (no numpy access per cell), and the
    heuristic is cached per cell. The arithmetic (float64) and the order of the states are those of the
    full-grid search, so the paths are identical; it is just several times faster."""
    i_lo, i_hi, j_lo, j_hi = box
    L = ok.shape[0]
    W, NY = i_hi - i_lo + 1, j_hi - j_lo + 1
    NYW = NY * W
    win = (slice(None), slice(j_lo, j_hi + 1), slice(i_lo, i_hi + 1))
    flat = lambda arr: arr[win].ravel().tolist()
    okl = flat(ok)
    vokl = vok[win[1:]].ravel().tolist()
    Ml = flat(M) if M is not None else None
    Al = flat(A) if A is not None else None
    vc_list = not isinstance(via_cost, (int, float))
    vcl = via_cost[win[1:]].ravel().tolist() if vc_list else via_cost
    S = [((i - i_lo, j - j_lo), l) for (i, j), l in S]
    G = [((i - i_lo, j - j_lo), l) for (i, j), l in G]
    goal_set = {(l * NY + j) * W + i for (i, j), l in G}
    gi = [ij for ij, _ in G]
    inf = math.inf
    hc = {}

    def h(i, j):
        k = j * W + i
        v = hc.get(k)
        if v is None:
            v = inf
            for ib, jb in gi:
                dx, dy = abs(i - ib), abs(j - jb)
                v = min(v, dx + dy + (SQ2 - 2) * min(dx, dy))
            hc[k] = v
        return v

    g = [inf] * (L * NYW)
    came, openh = {}, []
    push, pop = heapq.heappush, heapq.heappop
    for (i, j), l in S:
        s = (l * NY + j) * W + i
        g[s] = 0.0
        came[s] = -1
        push(openh, (h(i, j), 0.0, s))
    n = 0
    imax, jmax = W - 1, NY - 1
    while openh:
        f, gc, s = pop(openh)
        if gc > g[s]:
            continue
        if s in goal_set:
            path = []
            while s != -1:
                l, rem = divmod(s, NYW)
                j, i = divmod(rem, W)
                path.append((i + i_lo, j + j_lo, l))
                s = came[s]
            return path[::-1]
        n += 1
        if n > max_nodes:
            return None
        l, rem = divmod(s, NYW)
        j, i = divmod(rem, W)
        base = l * NYW
        for di, dj, c in DIRS:
            i2, j2 = i + di, j + dj
            if i2 < 0 or i2 > imax or j2 < 0 or j2 > jmax:
                continue
            s2 = s + dj * W + di
            if not okl[s2]:
                continue
            if di and dj and not (okl[base + j * W + i2] or okl[base + j2 * W + i]):
                continue
            if Ml is not None:
                g2 = gc + c * Ml[s2] + Al[s2]
            elif Al is not None:
                g2 = gc + c + Al[s2]
            else:
                g2 = gc + c
            if g2 < g[s2]:
                g[s2] = g2
                came[s2] = s
                push(openh, (g2 + h(i2, j2), g2, s2))
        if vokl[rem]:
            vc = vcl[rem] if vc_list else vcl
            for l2 in range(L):
                s2 = l2 * NYW + rem
                if l2 != l and okl[s2]:
                    g2 = gc + vc
                    if g2 < g[s2]:
                        g[s2] = g2
                        came[s2] = s
                        push(openh, (g2 + h(i, j), g2, s2))
    return None



_LIB = None


def _lib():
    """The C search (astar.c), compiled next to this file on first use; None when no C compiler is there."""
    global _LIB
    if _LIB is None:
        import ctypes, os, pathlib, subprocess
        src = pathlib.Path(__file__).with_name("astar.c")
        so = src.with_name("_astar.so")
        try:
            if not so.exists() or so.stat().st_mtime < src.stat().st_mtime:
                tmp = so.with_suffix(f".{os.getpid()}.tmp")
                subprocess.run([os.environ.get("CC", "cc"), "-O3", "-march=native", "-shared", "-fPIC",
                                str(src), "-o", str(tmp), "-lm"], check=True, capture_output=True)
                os.replace(tmp, so)
            lib = ctypes.CDLL(str(so))
            P = ctypes.c_void_p
            lib.astar.restype = ctypes.c_int64
            lib.astar.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, P, P, P, P, P, ctypes.c_double,
                                  P, ctypes.c_int, P, ctypes.c_int, ctypes.c_int64, P, ctypes.c_int64]
            _LIB = lib
        except (OSError, subprocess.CalledProcessError, FileNotFoundError):
            _LIB = False
    return _LIB or None


def _astar(ok, vok, box, S, G, max_nodes, via_cost, M=None, A=None):
    """A* over the grid window (see _astar_py for the arguments); in C when it can be built, with the same
    paths as the Python search."""
    lib = _lib()
    if lib is None:
        return _astar_py(ok, vok, box, S, G, max_nodes, via_cost, M, A)
    i_lo, i_hi, j_lo, j_hi = box
    L = ok.shape[0]
    W, NY = i_hi - i_lo + 1, j_hi - j_lo + 1
    win = (slice(None), slice(j_lo, j_hi + 1), slice(i_lo, i_hi + 1))
    c = lambda a, t: np.ascontiguousarray(a, dtype=t)
    okw = c(ok[win], np.uint8)
    vokw = c(vok[win[1:]], np.uint8)
    Mw = c(M[win], np.float64) if M is not None else None
    Aw = c(A[win], np.float64) if A is not None else None
    vcw = None if isinstance(via_cost, (int, float)) else c(via_cost[win[1:]], np.float64)
    st = np.array([(l * NY + (j - j_lo)) * W + (i - i_lo) for (i, j), l in S], dtype=np.int64)
    go = np.array([(l * NY + (j - j_lo)) * W + (i - i_lo) for (i, j), l in G], dtype=np.int64)
    cap = L * NY * W
    out = np.empty(cap, dtype=np.int64)
    ptr = lambda a: a.ctypes.data if a is not None else None
    n = lib.astar(L, NY, W, ptr(okw), ptr(vokw), ptr(Mw), ptr(Aw), ptr(vcw),
                  float(via_cost) if vcw is None else 0.0, ptr(st), len(st), ptr(go), len(go),
                  int(max_nodes), ptr(out), cap)
    if n <= 0:
        return None
    NYW = NY * W
    res = []
    for s in out[:n].tolist():
        l, rem = divmod(s, NYW)
        j, i = divmod(rem, W)
        res.append((i + i_lo, j + j_lo, l))
    return res

def _mm(v: int) -> float:
    return v / 1e6


class Router:
    def __init__(self, board: pcbnew.BOARD, box: tuple, layers: list, pitch: float = 0.05,
                 clearance: float = 0.16, edge: float = 0.3, hole_clearance: float = 0.25):
        self.b = board
        self.x0, self.y0, x1, y1 = box                 # board area in mm (KiCad page coordinates)
        self.box = box
        self.p = pitch
        self.nx = int(round((x1 - self.x0) / pitch)) + 1
        self.ny = int(round((y1 - self.y0) / pitch)) + 1
        self.X = self.x0 + np.arange(self.nx) * pitch
        self.Y = self.y0 + np.arange(self.ny) * pitch
        self.layers = layers
        self.L = len(layers)
        self.clr = clearance
        self.edge = edge
        self.hclr = hole_clearance
        self.base = self._collect()
        self.routes: dict[int, tuple] = {}             # route id -> (net, items, result)
        self._base_t, self._base_v = {}, {}
        self._rt, self._rv = {}, {}

    # ------------------------------------------------------------------ geometry
    def _collect(self) -> list:
        """Copper shapes as (kind, data, layer indices, net) in mm."""
        items = []
        for fp in self.b.GetFootprints():
            for pad in fp.Pads():
                net = pad.GetNetCode()
                for li, layer in enumerate(self.layers):
                    if pad.IsOnLayer(layer):
                        poly = pad.GetEffectivePolygon(layer, pcbnew.ERROR_INSIDE)
                        for k in range(poly.OutlineCount()):
                            ol = poly.COutline(k)
                            pts = [(_mm(ol.CPoint(i).x), _mm(ol.CPoint(i).y)) for i in range(ol.PointCount())]
                            if len(pts) >= 3:
                                items.append(("poly", pts, {li}, net))
                if pad.HasHole():
                    c, d = pad.GetPosition(), pad.GetDrillSize()
                    items.append(("hole", ((_mm(c.x), _mm(c.y)), _mm(max(d.x, d.y)) / 2), set(), net))
            for z in fp.Zones():
                self._keepout(z, items)
        for z in self.b.Zones():
            self._keepout(z, items)
        for t in self.b.GetTracks():
            net = t.GetNetCode()
            if t.GetClass() == "PCB_VIA":
                c = t.GetPosition()
                xy = (_mm(c.x), _mm(c.y))
                items.append(("circle", (xy, _mm(t.GetWidth(pcbnew.F_Cu)) / 2), set(range(self.L)), net))
                items.append(("hole", (xy, _mm(t.GetDrillValue()) / 2), set(), net))
            elif t.GetLayer() in self.layers:
                s, e = t.GetStart(), t.GetEnd()
                items.append(("seg", ((_mm(s.x), _mm(s.y)), (_mm(e.x), _mm(e.y)), _mm(t.GetWidth()) / 2),
                              {self.layers.index(t.GetLayer())}, net))
        return items

    def _keepout(self, z, items) -> None:
        if not (z.GetIsRuleArea() and z.GetDoNotAllowTracks()):
            return
        ol = z.Outline().COutline(0)
        pts = [(_mm(ol.CPoint(i).x), _mm(ol.CPoint(i).y)) for i in range(ol.PointCount())]
        lis = {i for i, layer in enumerate(self.layers) if z.IsOnLayer(layer)}
        items.append(("poly", pts, lis, BLOCKED))

    # ------------------------------------------------------------------ rasterisation
    def _window(self, xmin, ymin, xmax, ymax):
        i0 = max(0, int(math.floor((xmin - self.x0) / self.p)))
        i1 = min(self.nx, int(math.ceil((xmax - self.x0) / self.p)) + 1)
        j0 = max(0, int(math.floor((ymin - self.y0) / self.p)))
        j1 = min(self.ny, int(math.ceil((ymax - self.y0) / self.p)) + 1)
        return i0, i1, j0, j1

    def _dist(self, kind, data, i0, i1, j0, j1):
        X = self.X[i0:i1][None, :]
        Y = self.Y[j0:j1][:, None]
        if kind in ("circle", "hole"):
            (cx, cy), r = data
            return np.hypot(X - cx, Y - cy) - r
        if kind == "seg":
            (ax, ay), (bx, by), hw = data
            dx, dy = bx - ax, by - ay
            ll = dx * dx + dy * dy
            if ll == 0:
                return np.hypot(X - ax, Y - ay) - hw
            t = np.clip(((X - ax) * dx + (Y - ay) * dy) / ll, 0, 1)
            return np.hypot(X - (ax + t * dx), Y - (ay + t * dy)) - hw
        pts = data                                      # polygon: 0 inside, distance to outline outside
        d = np.full((j1 - j0, i1 - i0), np.inf)
        inside = np.zeros((j1 - j0, i1 - i0), dtype=bool)
        n = len(pts)
        for k in range(n):
            (ax, ay), (bx, by) = pts[k], pts[(k + 1) % n]
            dx, dy = bx - ax, by - ay
            ll = dx * dx + dy * dy or 1e-12
            t = np.clip(((X - ax) * dx + (Y - ay) * dy) / ll, 0, 1)
            d = np.minimum(d, np.hypot(X - (ax + t * dx), Y - (ay + t * dy)))
            inside ^= ((ay > Y) != (by > Y)) & (X < (bx - ax) * (Y - ay) / ((by - ay) or 1e-12) + ax)
        return np.where(inside, 0.0, d)

    @staticmethod
    def _bounds(kind, data):
        if kind in ("circle", "hole"):
            (cx, cy), r = data
            return cx - r, cy - r, cx + r, cy + r
        if kind == "seg":
            (ax, ay), (bx, by), hw = data
            return min(ax, bx) - hw, min(ay, by) - hw, max(ax, bx) + hw, max(ay, by) + hw
        xs, ys = zip(*data)
        return min(xs), min(ys), max(xs), max(ys)

    @staticmethod
    def _stamp(arr, mask, tag) -> None:
        if tag == BLOCKED:
            arr[mask] = BLOCKED
            return
        sub = arr[mask]
        arr[mask] = np.where(sub == FREE, tag, np.where((sub == tag) | (sub == BLOCKED), sub, BLOCKED))

    def _raster(self, items, infl_track, infl_hole, planes: int, tag_of=None):
        """Owner map (planes, ny, nx): planes == L for tracks, 1 for vias (all layers merged)."""
        m = np.zeros((planes, self.ny, self.nx), dtype=np.int32)
        for idx, (kind, data, lis, net) in enumerate(items):
            tag = net if tag_of is None else tag_of[idx]
            if tag_of is None and net <= 0:
                tag = BLOCKED                           # netless copper and plain holes block every net
            if kind == "hole":
                infl, lis, tag = infl_hole, set(range(self.L)), (BLOCKED if planes == 1 else tag)
            else:
                infl = infl_track
            if not lis:
                continue
            x0, y0, x1, y1 = self._bounds(kind, data)
            i0, i1, j0, j1 = self._window(x0 - infl, y0 - infl, x1 + infl, y1 + infl)
            if i0 >= i1 or j0 >= j1:
                continue
            mask = self._dist(kind, data, i0, i1, j0, j1) <= infl
            for li in (lis if planes > 1 else (0,)):
                self._stamp(m[li, j0:j1, i0:i1], mask, tag)
        return m

    def _edge(self, m, hw) -> None:
        bx0, by0, bx1, by1 = self.box
        d = self.edge + hw
        m[:, :, (self.X < bx0 + d) | (self.X > bx1 - d)] = BLOCKED
        m[:, (self.Y < by0 + d) | (self.Y > by1 - d), :] = BLOCKED

    def base_track(self, hw):
        if hw not in self._base_t:
            m = self._raster(self.base, hw + self.clr, hw + self.hclr, self.L)
            self._edge(m, hw)
            self._base_t[hw] = m
        return self._base_t[hw]

    def base_via(self, r, drill):
        key = (r, drill)
        if key not in self._base_v:
            m = self._raster(self.base, r + self.clr, max(r, drill / 2) + self.hclr, 1)[0]   # via copper to holes
            self._edge(m[None], r)
            self._base_v[key] = m
        return self._base_v[key]

    # Maps of the routes the router keeps, per track half-width / via size, updated in place when a route is
    # added or removed (re-rasterising every route on every change was most of the legalisation time). Per
    # cell: number of stamps, sum and sum of squares of the route ids and of the nets (all stamps of one value
    # <=> cnt * sum2 == sum**2), and stamps of plain holes (via maps); from these the owner maps follow exactly
    # as _raster would draw them: FREE, the one owner, or BLOCKED.
    def _new_layer(self, planes, infl_track, infl_hole):
        z = lambda dt: np.zeros((planes, self.ny, self.nx), dtype=dt)
        lay = {"planes": planes, "it": infl_track, "ih": infl_hole, "cnt": z(np.int32), "sid": z(np.int64),
               "sid2": z(np.int64), "snet": z(np.int64), "snet2": z(np.int64), "blk": z(np.int32),
               "net": z(np.int32), "id": z(np.int32), "masks": {}}
        for rid, (net, its, _) in self.routes.items():
            self._stamp_route(lay, rid, net, its, +1)
        return lay

    def _stamp_route(self, lay, rid, net, its, sign) -> None:
        planes = lay["planes"]
        if sign > 0:
            ms = []
            for kind, data, lis, _ in its:
                if kind == "hole":
                    infl, lis = lay["ih"], set(range(self.L))
                    blocked = planes == 1
                else:
                    infl, blocked = lay["it"], False
                if not lis:
                    continue
                x0, y0, x1, y1 = self._bounds(kind, data)
                i0, i1, j0, j1 = self._window(x0 - infl, y0 - infl, x1 + infl, y1 + infl)
                if i0 >= i1 or j0 >= j1:
                    continue
                mask = self._dist(kind, data, i0, i1, j0, j1) <= infl
                ms.append((tuple(lis) if planes > 1 else (0,), i0, i1, j0, j1, mask, blocked))
            lay["masks"][rid] = ms
        else:
            ms = lay["masks"].pop(rid, [])
        tag, idt = net, rid + 1
        for lis, i0, i1, j0, j1, mask, blocked in ms:
            for li in lis:
                w = (li, slice(j0, j1), slice(i0, i1))
                if blocked:
                    lay["blk"][w] += sign * mask
                else:
                    lay["cnt"][w] += sign * mask
                    lay["sid"][w] += (sign * idt) * mask
                    lay["sid2"][w] += (sign * idt * idt) * mask
                    lay["snet"][w] += (sign * tag) * mask
                    lay["snet2"][w] += (sign * tag * tag) * mask
                c, b = lay["cnt"][w], lay["blk"][w]
                cs = np.maximum(c, 1)
                one_id = c * lay["sid2"][w] == lay["sid"][w] ** 2
                one_net = c * lay["snet2"][w] == lay["snet"][w] ** 2
                lay["id"][w] = np.where(b > 0, BLOCKED, np.where(c == 0, FREE,
                                        np.where(one_id, lay["sid"][w] // cs, BLOCKED)))
                lay["net"][w] = np.where(b > 0, BLOCKED, np.where(c == 0, FREE,
                                         np.where(one_net, lay["snet"][w] // cs, BLOCKED)))

    def route_track(self, hw):
        """(owner-net map, owner-route-id map) of the maze routes for this track half-width."""
        if hw not in self._rt:
            self._rt[hw] = self._new_layer(self.L, hw + self.clr, hw + self.hclr)
        lay = self._rt[hw]
        return lay["net"], lay["id"]

    def route_via(self, r, drill):
        key = (r, drill)
        if key not in self._rv:
            self._rv[key] = self._new_layer(1, r + self.clr, max(r, drill / 2) + self.hclr)
        lay = self._rv[key]
        return lay["net"][0], lay["id"][0]

    # ------------------------------------------------------------------ routes kept by the router
    def add(self, rid, net, segs, vias, hw, via_r, drill) -> None:
        if rid in self.routes:
            self.remove(rid)
        its = []
        for layer, pts in segs:
            for a, c in zip(pts, pts[1:]):
                its.append(("seg", (a, c, hw), {layer}, net))
        for (x, y) in vias:
            its.append(("circle", ((x, y), via_r), set(range(self.L)), net))
            its.append(("hole", ((x, y), drill / 2), set(), net))
        self.routes[rid] = (net, its, (segs, vias, hw, via_r, drill))
        for lay in list(self._rt.values()) + list(self._rv.values()):
            self._stamp_route(lay, rid, net, its, +1)

    def set_routes(self, routes: dict) -> None:
        """Make the kept routes equal to `routes` (a snapshot of self.routes), changing only what differs."""
        for rid in [k for k, v in self.routes.items() if routes.get(k) is not v]:
            self.remove(rid)
        for rid, val in routes.items():
            if rid not in self.routes:
                self.routes[rid] = val
                for lay in list(self._rt.values()) + list(self._rv.values()):
                    self._stamp_route(lay, rid, val[0], val[1], +1)

    def remove(self, rid) -> None:
        val = self.routes.pop(rid, None)
        if val is None:
            return
        for lay in list(self._rt.values()) + list(self._rv.values()):
            self._stamp_route(lay, rid, val[0], val[1], -1)

    # ------------------------------------------------------------------ search
    def cell(self, x, y):
        return (min(self.nx - 1, max(0, int(round((x - self.x0) / self.p)))),
                min(self.ny - 1, max(0, int(round((y - self.y0) / self.p)))))

    def route(self, net, starts, goals, hw, via_r, drill, via_cost=30.0, margin=8.0, soft=False,
              soft_cost=6.0, max_nodes=2_500_000):
        """A* from any of `starts` to any of `goals` ([(x, y, layer index)]).

        soft=True lets the search cross other maze routes at `soft_cost` per cell; the second return value
        is then the set of route ids it crossed. Returns (path [(x, y, layer)], crossed) or (None, set()).
        """
        bt = self.base_track(hw)
        bv = self.base_via(via_r, drill)
        rt_net, rt_id = self.route_track(hw)
        rv_net, rv_id = self.route_via(via_r, drill)
        ok = (bt == FREE) | (bt == net)
        vok = ((bv == FREE) | (bv == net)) & ~(bt == net).any(axis=0)
        r_other = (rt_net != FREE) & (rt_net != net)
        v_other = (rv_net != FREE) & (rv_net != net)
        if not soft:
            ok &= ~r_other
            vok &= ~v_other
        S = [(self.cell(x, y), l) for x, y, l in starts]
        G = [(self.cell(x, y), l) for x, y, l in goals]
        for (i, j), l in S + G:                         # leave/enter their own copper
            sl = (l, slice(max(0, j - 2), j + 3), slice(max(0, i - 2), i + 3))
            ok[sl] |= bt[sl] == net
        allij = [ij for ij, _ in S + G]
        m = int(margin / self.p)
        i_lo = max(0, min(i for i, _ in allij) - m)
        i_hi = min(self.nx - 1, max(i for i, _ in allij) + m)
        j_lo = max(0, min(j for _, j in allij) - m)
        j_hi = min(self.ny - 1, max(j for _, j in allij) + m)
        W, NY = self.nx, self.ny
        if soft:
            A = np.where(r_other, soft_cost, 0.0)
            vc = np.where(v_other, via_cost + soft_cost * 4, via_cost)
        else:
            A, vc = None, via_cost
        cells = _astar(ok, vok, (i_lo, i_hi, j_lo, j_hi), S, G, max_nodes, vc, A=A)
        if cells is None:
            return None, set()
        path, crossed = [], set()
        for i, j, l in cells:
            path.append((float(self.X[i]), float(self.Y[j]), l))
            if soft and r_other[l, j, i] and rt_id[l, j, i] > 0:
                crossed.add(int(rt_id[l, j, i]) - 1)
        if soft:
            amb = []                           # cells where several routes overlap: resolve by geometry
            for x, y, l in path:
                i, j = self.cell(x, y)
                if r_other[l, j, i] and rt_id[l, j, i] <= 0:
                    amb.append((x, y, l, hw + self.clr, False))
            for a, c in zip(path, path[1:]):
                if a[2] != c[2]:
                    i, j = self.cell(a[0], a[1])
                    if v_other[j, i] and rv_id[j, i] > 0:
                        crossed.add(int(rv_id[j, i]) - 1)
                    elif v_other[j, i]:
                        amb.append((a[0], a[1], None, via_r + self.clr, True))
            if amb:
                crossed |= self._who(amb, net, drill)
        return path, crossed

    def _who(self, pts, net, drill) -> set:
        """Route ids whose copper comes too close to any of pts [(x, y, layer|None, reach, is_via)]."""
        hit = set()
        for rid, val in self.routes.items():
            if val[0] == net:
                continue
            for kind, data, lis, _ in val[1]:
                for x, y, l, reach, is_via in pts:
                    if kind == "hole":
                        if not is_via:
                            continue
                        (cx, cy), rr = data
                        d = math.hypot(x - cx, y - cy) - rr - drill / 2 - self.hclr
                    else:
                        if l is not None and l not in lis:
                            continue
                        if kind == "circle":
                            (cx, cy), rr = data
                            d = math.hypot(x - cx, y - cy) - rr - reach
                        elif kind == "seg":
                            (ax, ay), (bx, by), shw = data
                            dx, dy = bx - ax, by - ay
                            ll = dx * dx + dy * dy
                            t = 0.0 if ll == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / ll))
                            d = math.hypot(x - (ax + t * dx), y - (ay + t * dy)) - shw - reach
                        else:
                            continue
                    if d < 0:
                        hit.add(rid)
                        break
                if rid in hit:
                    break
        return hit

    # ------------------------------------------------------------------ results
    def simplify(self, path, net, hw):
        """Split at layer changes and string-pull each run. Returns (segments, vias) in mm.

        Shortcuts are checked against maps inflated by an extra 0.04 mm: a straight line between grid cells
        can pass up to ~0.035 mm closer to an obstacle than the cell centres the check samples.
        """
        bt = self.base_track(round(hw + 0.04, 4))
        rt_net, _ = self.route_track(round(hw + 0.04, 4))
        ok = ((bt == FREE) | (bt == net)) & ((rt_net == FREE) | (rt_net == net))
        runs, cur, vias = [], [path[0]], []
        for p in path[1:]:
            if p[2] != cur[-1][2]:
                runs.append(cur)
                vias.append((p[0], p[1]))
                cur = [p]
            else:
                cur.append(p)
        runs.append(cur)
        segs = []
        for run in runs:
            layer = run[0][2]
            raw = [(x, y) for x, y, _ in run]
            pts = [raw[0]]                             # keep only the corners of the grid path
            for k in range(1, len(raw) - 1):
                d1 = (round((raw[k][0] - raw[k - 1][0]) / self.p), round((raw[k][1] - raw[k - 1][1]) / self.p))
                d2 = (round((raw[k + 1][0] - raw[k][0]) / self.p), round((raw[k + 1][1] - raw[k][1]) / self.p))
                if d1 != d2:
                    pts.append(raw[k])
            if len(raw) > 1:
                pts.append(raw[-1])
            out, k = [pts[0]], 0
            while k < len(pts) - 1:
                m = len(pts) - 1
                while m > k + 1 and not self._line_free(ok[layer], pts[k], pts[m]):
                    m -= 1
                out.append(pts[m])
                k = m
            if len(out) >= 2:
                segs.append((layer, out))
        return segs, vias

    def _line_free(self, ok_l, a, b) -> bool:
        n = max(2, int(math.hypot(b[0] - a[0], b[1] - a[1]) / (self.p / 2)))
        for k in range(n + 1):
            i, j = self.cell(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)
            if not ok_l[j, i]:
                return False
        return True


# ---------------------------------------------------------------------------------------------- negotiation
def _runs(path):
    """Cell path -> list of ('seg', ((x0, y0), (x1, y1)), layer) straight runs and ('via', (x, y)) changes."""
    out = []
    if len(path) == 1:
        return [("seg", ((path[0][0], path[0][1]), (path[0][0], path[0][1])), path[0][2])]
    start = path[0]
    prev = path[0]
    d = None
    for p in path[1:]:
        if p[2] != prev[2]:
            out.append(("seg", ((start[0], start[1]), (prev[0], prev[1])), prev[2]))
            out.append(("via", (prev[0], prev[1])))
            start, prev, d = p, p, None
            continue
        nd = (round((p[0] - prev[0]) * 1e4), round((p[1] - prev[1]) * 1e4))
        if d is not None and nd != d:
            out.append(("seg", ((start[0], start[1]), (prev[0], prev[1])), prev[2]))
            start = prev
        d = nd
        prev = p
    out.append(("seg", ((start[0], start[1]), (prev[0], prev[1])), prev[2]))
    return out


class Negotiator:
    """PathFinder-style negotiated congestion on top of a Router's base obstacles.

    Routes may overlap other nets' routes at a price that grows every iteration (present cost) and with
    how often a cell was fought over (history cost), until every route has its own room.
    """
    REF_HW = 0.075        # footprints are stamped as if the other route were a 0.15 mm track

    def __init__(self, router: Router):
        self.r = router
        L, ny, nx = router.L, router.ny, router.nx
        self.occ = np.zeros((L, ny, nx), dtype=np.int16)
        self.hist = np.zeros((L, ny, nx), dtype=np.float32)
        self.paths: dict[int, list] = {}
        self.stamps: dict[int, list] = {}
        self._hver, self._hcache_key, self._hcache = 0, None, None

    def _footprint(self, path, hw, via_r):
        r = self.r
        stamps = []
        for run in _runs(path):
            if run[0] == "seg":
                (a, c), layer = run[1], run[2]
                kind, data, lis = "seg", (a, c, hw), (layer,)
            else:
                kind, data, lis = "circle", (run[1], via_r), tuple(range(r.L))
            infl = r.clr + self.REF_HW - 0.75 * r.p     # touching at the legal minimum is not a fight
            x0, y0, x1, y1 = r._bounds(kind, data)
            i0, i1, j0, j1 = r._window(x0 - infl, y0 - infl, x1 + infl, y1 + infl)
            mask = r._dist(kind, data, i0, i1, j0, j1) <= infl
            for li in lis:
                stamps.append((li, j0, j1, i0, i1, mask))
        return stamps

    def _apply(self, stamps, sign, arr=None):
        arr = self.occ if arr is None else arr
        for li, j0, j1, i0, i1, mask in stamps:
            arr[li, j0:j1, i0:i1] += sign * mask.astype(np.int16)

    def set_path(self, cid, path, hw, via_r):
        if cid in self.stamps:
            self._apply(self.stamps[cid], -1)
        self.paths[cid] = path
        self.stamps[cid] = self._footprint(path, hw, via_r)
        self._apply(self.stamps[cid], +1)

    def route(self, cid, conn, pres, hist_w, nets_of, margin=60.0, via_cost=30.0, max_nodes=2_500_000):
        """Cheapest path for one connection given the current occupancy (other nets cost `pres` per cell)."""
        r = self.r
        net, starts, goals, hw, via_r, drill = conn
        own = np.zeros_like(self.occ)
        for other, n in nets_of.items():
            if n == net and other in self.stamps and other != cid:
                self._apply(self.stamps[other], +1, own)
        if cid in self.stamps:
            self._apply(self.stamps[cid], +1, own)
        foreign = self.occ - own
        bt = r.base_track(hw)
        bv = r.base_via(via_r, drill)
        ok = (bt == FREE) | (bt == net)
        vok = ((bv == FREE) | (bv == net)) & ~(bt == net).any(axis=0)
        S = [(r.cell(x, y), l) for x, y, l in starts]
        G = [(r.cell(x, y), l) for x, y, l in goals]
        for (i, j), l in S + G:
            sl = (l, slice(max(0, j - 2), j + 3), slice(max(0, i - 2), i + 3))
            ok[sl] |= bt[sl] == net
        allij = [ij for ij, _ in S + G]
        m = int(margin / r.p)
        i_lo = max(0, min(i for i, _ in allij) - m)
        i_hi = min(r.nx - 1, max(i for i, _ in allij) + m)
        j_lo = max(0, min(j for _, j in allij) - m)
        j_hi = min(r.ny - 1, max(j for _, j in allij) + m)
        W, NY = r.nx, r.ny
        M, vbase = self._hist_costs(hist_w, via_cost)
        A = pres * foreign.astype(np.float64)
        vc = vbase + pres * 4 * foreign.max(axis=0).astype(np.float64)
        cells = _astar(ok, vok, (i_lo, i_hi, j_lo, j_hi), S, G, max_nodes, vc, M=M, A=A)
        if cells is None:
            return None
        return [(float(r.X[i]), float(r.Y[j]), l) for i, j, l in cells]

    def _hist_costs(self, hist_w, via_cost):
        """Step multiplier per cell and via base cost, from the history; computed once per iteration (in
        the parent before the workers fork, so they inherit it)."""
        key = (self._hver, hist_w, via_cost)
        if self._hcache_key != key:
            h64 = self.hist.astype(np.float64)
            self._hcache = (1.0 + hist_w * h64,
                            via_cost * (1.0 + hist_w * self.hist.max(axis=0).astype(np.float64)))
            self._hcache_key = key
        return self._hcache

    def conflicts(self, conns, cells=None):
        """Connections whose path runs through cells another net's footprint also covers. With a dict as
        `cells`, the shared cells of each such path are collected in it (cid -> [(l, j, i)])."""
        bad = set()
        foreign_of = {}                                # one occupancy-minus-own-net map per net, not per path
        for cid, path in self.paths.items():
            net = conns[cid][0]
            if net not in foreign_of:
                own = np.zeros_like(self.occ)
                for other in self.paths:
                    if conns[other][0] == net:
                        self._apply(self.stamps[other], +1, own)
                foreign_of[net] = self.occ - own
            foreign = foreign_of[net]
            for x, y, l in path[3:-3]:                 # the ends sit in their own pads
                i, j = self.r.cell(x, y)
                if foreign[l, j, i] > 0:
                    bad.add(cid)
                    if cells is None:
                        break
                    cells.setdefault(cid, []).append((l, j, i))
        return bad

    def _route_batch(self, batch, conns, pres, hist_w, nets_of, max_nodes, workers):
        """Route a batch against the same occupancy; in parallel worker processes when workers > 1.

        Workers are forked from this process, so they see the occupancy as it is now; only the connection
        ids go out and the paths come back."""
        if workers <= 1 or len(batch) <= 1:
            return [(cid, self.route(cid, conns[cid], pres, hist_w, nets_of, max_nodes=max_nodes)) for cid in batch]
        global _WORK
        self._hist_costs(hist_w, 30.0)                 # once here, inherited by every worker
        _WORK = (self, conns, pres, hist_w, nets_of, max_nodes)

        def span(cid):                                 # rough search effort: start-to-goal distance
            (x0, y0, _), (x1, y1, _) = conns[cid][1][0], conns[cid][2][0]
            return -math.hypot(x1 - x0, y1 - y0)
        # the longest searches go out first, so no worker is left with one at the end of the batch;
        # the results come back in batch order (the paths do not depend on the order they are found in)
        order = sorted(batch, key=span)
        with multiprocessing.get_context("fork").Pool(min(workers, len(batch))) as pool:
            found = dict(pool.imap_unordered(_route_worker, order, chunksize=1))
        return [(cid, found[cid]) for cid in batch]

    def run(self, conns, iters=10, log=print, workers=1, max_nodes=2_500_000, give_up=2, reroute_all=False,
            seed=11):
        """conns: list of (net code, starts, goals, hw, via_r, drill). Returns {cid: path}.

        With workers > 1 each iteration is routed in batches of 2 x workers connections: a batch sees the
        paths of the batches before it, the members of one batch are routed side by side. A connection
        that finds no path at all in `give_up` iterations is left out of later ones (it would only search
        the whole board again)."""
        nets_of = {cid: c[0] for cid, c in enumerate(conns)}
        todo = list(range(len(conns)))
        rnd = random.Random(seed)
        pres, hist_w = 1.0, 0.5
        nofail = {}
        size = 2 * workers if workers > 1 else 1
        for it in range(iters):
            todo = [c for c in todo if nofail.get(c, 0) < give_up]
            for k in range(0, len(todo), size):
                batch = todo[k:k + size]
                for cid, path in self._route_batch(batch, conns, pres, hist_w, nets_of, max_nodes, workers):
                    hw, vr = conns[cid][3], conns[cid][4]
                    if path:
                        self.set_path(cid, path, hw, vr)
                    else:
                        nofail[cid] = nofail.get(cid, 0) + 1
            shared = {}
            bad = self.conflicts(conns, shared)
            unrouted = [c for c in range(len(conns)) if c not in self.paths]
            log(f"    iteration {it + 1}: {len(bad)} in conflict, {len(unrouted)} unroutable")
            if not bad:
                break
            # history only where paths actually overlap (PathFinder), widened by a cell: raising it along the
            # whole path of every connection in conflict spread it over the board and it stopped steering
            for cid, cl in shared.items():
                for l, j, i in cl:
                    self.hist[l, max(0, j - 1):j + 2, max(0, i - 1):i + 2] += 1.0
            self._hver += 1
            # a fresh order every iteration: connections that fight each other must not share a batch (the
            # members of one batch never see each other's paths) iteration after iteration
            # reroute_all: every connection again (classic PathFinder), so a path that is in nobody's way yet
            # sits where others need room moves too; else only the ones in conflict
            todo = list(range(len(conns))) if reroute_all else sorted(bad)
            rnd.shuffle(todo)
            pres *= 1.5
        return self.paths


_WORK = None


def _route_worker(cid):
    """Negotiation worker (forked): one connection against the parent's occupancy at fork time."""
    neg, conns, pres, hist_w, nets_of, max_nodes = _WORK
    return cid, neg.route(cid, conns[cid], pres, hist_w, nets_of, max_nodes=max_nodes)
