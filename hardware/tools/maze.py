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

import numpy as np
import pcbnew

FREE, BLOCKED = 0, -1
SQ2 = math.sqrt(2)


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

    def _route_items(self):
        items, nets, ids = [], [], []
        for rid, (net, its, _) in self.routes.items():
            items += its
            nets += [net] * len(its)
            ids += [rid] * len(its)
        return items, nets, ids

    def route_track(self, hw):
        """(owner-net map, owner-route-id map) of the maze routes for this track half-width."""
        if hw not in self._rt:
            items, nets, ids = self._route_items()
            self._rt[hw] = (self._raster(items, hw + self.clr, hw + self.hclr, self.L, nets),
                            self._raster(items, hw + self.clr, hw + self.hclr, self.L, [i + 1 for i in ids]))
        return self._rt[hw]

    def route_via(self, r, drill):
        key = (r, drill)
        if key not in self._rv:
            items, nets, ids = self._route_items()
            hole = max(r, drill / 2) + self.hclr
            self._rv[key] = (self._raster(items, r + self.clr, hole, 1, nets)[0],
                             self._raster(items, r + self.clr, hole, 1, [i + 1 for i in ids])[0])
        return self._rv[key]

    # ------------------------------------------------------------------ routes kept by the router
    def add(self, rid, net, segs, vias, hw, via_r, drill) -> None:
        its = []
        for layer, pts in segs:
            for a, c in zip(pts, pts[1:]):
                its.append(("seg", (a, c, hw), {layer}, net))
        for (x, y) in vias:
            its.append(("circle", ((x, y), via_r), set(range(self.L)), net))
            its.append(("hole", ((x, y), drill / 2), set(), net))
        self.routes[rid] = (net, its, (segs, vias, hw, via_r, drill))
        self._rt.clear()
        self._rv.clear()

    def remove(self, rid) -> None:
        self.routes.pop(rid, None)
        self._rt.clear()
        self._rv.clear()

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
        goal_set = {(l * NY + j) * W + i for (i, j), l in G}
        gi = [(i, j) for (i, j), _ in G]

        def h(i, j):
            best = math.inf
            for ib, jb in gi:
                dx, dy = abs(i - ib), abs(j - jb)
                best = min(best, dx + dy + (SQ2 - 2) * min(dx, dy))
            return best

        g, came, openh = {}, {}, []
        for (i, j), l in S:
            s = (l * NY + j) * W + i
            g[s] = 0.0
            came[s] = -1
            heapq.heappush(openh, (h(i, j), 0.0, s))
        dirs = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                (1, 1, SQ2), (1, -1, SQ2), (-1, 1, SQ2), (-1, -1, SQ2)]
        n = 0
        while openh:
            f, gc, s = heapq.heappop(openh)
            if gc > g.get(s, math.inf):
                continue
            if s in goal_set:
                path, crossed = [], set()
                while s != -1:
                    l, rem = divmod(s, NY * W)
                    j, i = divmod(rem, W)
                    path.append((float(self.X[i]), float(self.Y[j]), l))
                    if soft and r_other[l, j, i] and rt_id[l, j, i] > 0:
                        crossed.add(int(rt_id[l, j, i]) - 1)
                    s = came[s]
                path.reverse()
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
            n += 1
            if n > max_nodes:
                break
            l, rem = divmod(s, NY * W)
            j, i = divmod(rem, W)
            okl = ok[l]
            rol = r_other[l]
            for di, dj, c in dirs:
                i2, j2 = i + di, j + dj
                if i2 < i_lo or i2 > i_hi or j2 < j_lo or j2 > j_hi or not okl[j2, i2]:
                    continue
                if di and dj and not (okl[j, i2] or okl[j2, i]):
                    continue
                g2 = gc + c + (soft_cost if soft and rol[j2, i2] else 0.0)
                s2 = s + dj * W + di
                if g2 < g.get(s2, math.inf):
                    g[s2] = g2
                    came[s2] = s
                    heapq.heappush(openh, (g2 + h(i2, j2), g2, s2))
            if vok[j, i]:
                vc = via_cost + (soft_cost * 4 if soft and v_other[j, i] else 0.0)
                for l2 in range(self.L):
                    if l2 != l and ok[l2, j, i]:
                        s2 = (l2 * NY + j) * W + i
                        g2 = gc + vc
                        if g2 < g.get(s2, math.inf):
                            g[s2] = g2
                            came[s2] = s
                            heapq.heappush(openh, (g2 + h(i, j), g2, s2))
        return None, set()

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
        goal_set = {(l * NY + j) * W + i for (i, j), l in G}
        gi = [(i, j) for (i, j), _ in G]
        vfor = foreign.max(axis=0)
        histv = self.hist.max(axis=0)

        def h(i, j):
            best = math.inf
            for ib, jb in gi:
                dx, dy = abs(i - ib), abs(j - jb)
                best = min(best, dx + dy + (SQ2 - 2) * min(dx, dy))
            return best

        g, came, openh = {}, {}, []
        for (i, j), l in S:
            s = (l * NY + j) * W + i
            g[s] = 0.0
            came[s] = -1
            heapq.heappush(openh, (h(i, j), 0.0, s))
        dirs = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                (1, 1, SQ2), (1, -1, SQ2), (-1, 1, SQ2), (-1, -1, SQ2)]
        n = 0
        while openh:
            f, gc, s = heapq.heappop(openh)
            if gc > g.get(s, math.inf):
                continue
            if s in goal_set:
                path = []
                while s != -1:
                    l, rem = divmod(s, NY * W)
                    j, i = divmod(rem, W)
                    path.append((float(r.X[i]), float(r.Y[j]), l))
                    s = came[s]
                return path[::-1]
            n += 1
            if n > max_nodes:
                return None
            l, rem = divmod(s, NY * W)
            j, i = divmod(rem, W)
            okl, fl, hl = ok[l], foreign[l], self.hist[l]
            for di, dj, c in dirs:
                i2, j2 = i + di, j + dj
                if i2 < i_lo or i2 > i_hi or j2 < j_lo or j2 > j_hi or not okl[j2, i2]:
                    continue
                if di and dj and not (okl[j, i2] or okl[j2, i]):
                    continue
                g2 = gc + c * (1.0 + hist_w * hl[j2, i2]) + pres * fl[j2, i2]
                s2 = s + dj * W + di
                if g2 < g.get(s2, math.inf):
                    g[s2] = g2
                    came[s2] = s
                    heapq.heappush(openh, (g2 + h(i2, j2), g2, s2))
            if vok[j, i]:
                vc = via_cost * (1.0 + hist_w * histv[j, i]) + pres * 4 * vfor[j, i]
                for l2 in range(r.L):
                    if l2 != l and ok[l2, j, i]:
                        s2 = (l2 * NY + j) * W + i
                        g2 = gc + vc
                        if g2 < g.get(s2, math.inf):
                            g[s2] = g2
                            came[s2] = s
                            heapq.heappush(openh, (g2 + h(i, j), g2, s2))
        return None

    def conflicts(self, conns):
        """Connections whose path runs through cells another net's footprint also covers."""
        bad = set()
        for cid, path in self.paths.items():
            net = conns[cid][0]
            own = np.zeros_like(self.occ)
            for other, p in self.paths.items():
                if conns[other][0] == net:
                    self._apply(self.stamps[other], +1, own)
            foreign = self.occ - own
            for x, y, l in path[3:-3]:                 # the ends sit in their own pads
                i, j = self.r.cell(x, y)
                if foreign[l, j, i] > 0:
                    bad.add(cid)
                    break
        return bad

    def run(self, conns, iters=10, log=print):
        """conns: list of (net code, starts, goals, hw, via_r, drill). Returns {cid: path}."""
        nets_of = {cid: c[0] for cid, c in enumerate(conns)}
        todo = list(range(len(conns)))
        pres, hist_w = 1.0, 0.5
        for it in range(iters):
            for cid in todo:
                net, st, go, hw, vr, dr = conns[cid]
                path = self.route(cid, conns[cid], pres, hist_w, nets_of)
                if path:
                    self.set_path(cid, path, hw, vr)
            bad = self.conflicts(conns)
            unrouted = [c for c in range(len(conns)) if c not in self.paths]
            log(f"    iteration {it + 1}: {len(bad)} in conflict, {len(unrouted)} unroutable")
            if not bad:
                break
            for cid in bad:
                for x, y, l in self.paths[cid]:
                    i, j = self.r.cell(x, y)
                    self.hist[l, j, i] += 1.0
            todo = sorted(bad)
            pres *= 1.5
        return self.paths
