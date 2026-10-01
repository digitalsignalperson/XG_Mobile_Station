"""Small two-layer grid maze router for the low-speed nets.

Works on a 0.05 mm grid in board coordinates (mm).  Every copper item is kept
as a simple shape; for the net being routed all foreign shapes are inflated by
(trace half width + clearance) and rasterised, then a Dijkstra search with a
turn penalty finds the path.  Deterministic, so the board can be regenerated.
"""
import heapq
import math

import numpy as np

G = 0.05
MARGIN = 0.03                 # extra clearance to absorb grid quantisation
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]


class Shape:
    __slots__ = ("kind", "layer", "net", "a", "b", "r", "is_pad")

    def __init__(self, kind, layer, net, a, b=None, r=0.0, is_pad=False):
        self.kind, self.layer, self.net = kind, layer, net
        self.a, self.b, self.r, self.is_pad = a, b, r, is_pad


class Router:
    def __init__(self, x0, y0, x1, y1, clearance=0.1, via_d=0.45, via_drill=0.3):
        self.x0, self.y0 = x0, y0
        self.nx = int(round((x1 - x0) / G)) + 1
        self.ny = int(round((y1 - y0) / G)) + 1
        self.c = clearance
        self.via_r = via_d / 2
        self.drill_r = via_drill / 2
        self.shapes = []           # copper
        self.holes = []            # (x, y, r) of every drilled hole
        self.fences = []           # (layer or None, x0, y0, x1, y1) no-go rects
        self.new_tracks = []       # (layer, [(x, y), ...], width, net)
        self.new_vias = []         # (x, y, net)
        self.X = self.x0 + np.arange(self.nx) * G
        self.Y = self.y0 + np.arange(self.ny) * G

    # ------------------------------------------------------------- geometry
    def ij(self, x, y):
        return int(round((x - self.x0) / G)), int(round((y - self.y0) / G))

    def xy(self, i, j):
        return self.x0 + i * G, self.y0 + j * G

    def add_rect(self, layer, net, x0, y0, x1, y1, is_pad=True):
        self.shapes.append(Shape("rect", layer, net, (min(x0, x1), min(y0, y1)),
                                 (max(x0, x1), max(y0, y1)), 0.0, is_pad))

    def add_seg(self, layer, net, p, q, width):
        self.shapes.append(Shape("seg", layer, net, p, q, width / 2))

    def add_via(self, net, x, y, d=None, drill=None):
        r = self.via_r if d is None else d / 2
        for layer in (0, 1):
            self.shapes.append(Shape("seg", layer, net, (x, y), (x, y), r))
        self.holes.append((x, y, self.drill_r if drill is None else drill / 2))

    def add_hole(self, x, y, d):
        """Non-plated hole: blocks copper on both layers and other holes."""
        for layer in (0, 1):
            self.shapes.append(Shape("seg", layer, None, (x, y), (x, y), d / 2 + 0.1))
        self.holes.append((x, y, d / 2))

    def _raster(self, mask, s, infl):
        """OR the shape inflated by `infl` into the boolean mask[ny, nx]."""
        if s.kind == "rect":
            (ax, ay), (bx, by) = s.a, s.b
        else:
            ax, ay = min(s.a[0], s.b[0]) - s.r, min(s.a[1], s.b[1]) - s.r
            bx, by = max(s.a[0], s.b[0]) + s.r, max(s.a[1], s.b[1]) + s.r
        i0, j0 = self.ij(ax - infl - G, ay - infl - G)
        i1, j1 = self.ij(bx + infl + G, by + infl + G)
        i0, j0 = max(i0, 0), max(j0, 0)
        i1, j1 = min(i1, self.nx - 1), min(j1, self.ny - 1)
        if i0 > i1 or j0 > j1:
            return
        Xs = self.X[i0:i1 + 1][None, :]
        Ys = self.Y[j0:j1 + 1][:, None]
        if s.kind == "rect":
            dx = np.maximum(np.maximum(ax - Xs, Xs - bx), 0)
            dy = np.maximum(np.maximum(ay - Ys, Ys - by), 0)
            d = np.hypot(dx, dy)
        else:
            px, py = s.a
            vx, vy = s.b[0] - px, s.b[1] - py
            L2 = vx * vx + vy * vy
            if L2 < 1e-12:
                d = np.hypot(Xs - px, Ys - py) - s.r
            else:
                t = np.clip(((Xs - px) * vx + (Ys - py) * vy) / L2, 0, 1)
                d = np.hypot(Xs - (px + t * vx), Ys - (py + t * vy)) - s.r
        mask[j0:j1 + 1, i0:i1 + 1] |= d <= infl + 1e-9

    def blocked(self, net, half_w, fenced=True):
        """[layer][ny, nx] True where a trace centre for `net` may not go."""
        out = []
        for layer in (0, 1):
            m = np.zeros((self.ny, self.nx), dtype=bool)
            for s in self.shapes:
                if s.layer == layer and s.net != net:
                    self._raster(m, s, half_w + self.c + MARGIN)
            if fenced:
                for fl, fx0, fy0, fx1, fy1 in self.fences:
                    if fl is None or fl == layer:
                        i0, j0 = self.ij(fx0, fy0)
                        i1, j1 = self.ij(fx1, fy1)
                        m[max(j0, 0):max(j1 + 1, 0), max(i0, 0):max(i1 + 1, 0)] = True
            out.append(m)
        return out

    def own(self, net):
        """[layer][ny, nx] True on existing copper of `net` (no inflation)."""
        out = []
        for layer in (0, 1):
            m = np.zeros((self.ny, self.nx), dtype=bool)
            for s in self.shapes:
                if s.layer != layer or s.net != net:
                    continue
                if s.kind == "rect":               # stay a little inside pads
                    (ax, ay), (bx, by) = s.a, s.b
                    k = min(0.06, (bx - ax) / 4, (by - ay) / 4)
                    s = Shape("rect", layer, net, (ax + k, ay + k), (bx - k, by - k))
                self._raster(m, s, 0.0)
            out.append(m)
        return out

    def via_ok(self, net, fenced=True):
        """[ny, nx] True where a via of `net` may be dropped."""
        infl = self.via_r
        bad = np.zeros((self.ny, self.nx), dtype=bool)
        for m in self.blocked(net, infl, fenced):
            bad |= m
        tmp = np.zeros_like(bad)
        for x, y, r in self.holes:                     # hole to hole spacing
            self._raster(tmp, Shape("seg", 0, None, (x, y), (x, y), r),
                         self.drill_r + 0.25 + MARGIN)
        for s in self.shapes:                          # no vias in SMD pads
            if s.is_pad:
                self._raster(tmp, s, self.via_r * 0.6)
        return ~(bad | tmp)

    # -------------------------------------------------------------- search
    def _search(self, blocked, viaok, sources, is_target, via_cost=24.0, limit=None,
                allow_via=True):
        """Dijkstra over (layer, i, j, dir).  sources: iterable of (l, i, j).
        is_target(l, i, j) -> bool.  Returns list of (l, i, j) or None."""
        nx, ny = self.nx, self.ny
        dist, prev, heap = {}, {}, []
        for (l, i, j) in sources:
            k = (l, i, j, 8)
            dist[k] = 0.0
            heap.append((0.0, k))
        heapq.heapify(heap)
        turn = [0.0, 0.6, 3.0, 9.0, 20.0]
        while heap:
            d, k = heapq.heappop(heap)
            if d > dist.get(k, 1e18):
                continue
            l, i, j, dr = k
            if is_target(l, i, j):
                path = [k]
                while k in prev:
                    k = prev[k]
                    path.append(k)
                return [(a, b, c) for a, b, c, _ in reversed(path)]
            if limit is not None and d > limit:
                continue
            b = blocked[l]
            for nd, (di, dj) in enumerate(DIRS):
                ni, nj = i + di, j + dj
                if not (0 <= ni < nx and 0 <= nj < ny) or b[nj, ni]:
                    continue
                if di and dj and (b[j, ni] or b[nj, i]):
                    continue
                step = 1.0 if not (di and dj) else 1.5
                if dr != 8:
                    t = abs(nd - dr)
                    step += turn[min(t, 8 - t)]
                nk = (l, ni, nj, nd)
                ndist = d + step
                if ndist < dist.get(nk, 1e18):
                    dist[nk] = ndist
                    prev[nk] = k
                    heapq.heappush(heap, (ndist, nk))
            if allow_via and viaok[j, i] and not blocked[1 - l][j, i]:
                nk = (1 - l, i, j, 8)
                ndist = d + via_cost
                if ndist < dist.get(nk, 1e18):
                    dist[nk] = ndist
                    prev[nk] = k
                    heapq.heappush(heap, (ndist, nk))
        return None

    def _commit(self, net, path, width):
        """Turn a cell path into tracks/vias and register them as copper."""
        runs, cur = [], [path[0]]
        for a, b in zip(path, path[1:]):
            if a[0] != b[0]:
                runs.append(cur)
                x, y = self.xy(a[1], a[2])
                self.new_vias.append((x, y, net))
                self.add_via(net, x, y)
                cur = [b]
            else:
                cur.append(b)
        runs.append(cur)
        for run in runs:
            if len(run) < 2:
                continue
            pts = [run[0]]
            for a, b, c in zip(run, run[1:], run[2:]):
                if (b[1] - a[1], b[2] - a[2]) != (c[1] - b[1], c[2] - b[2]):
                    pts.append(b)
            pts.append(run[-1])
            xy = [self.xy(i, j) for _, i, j in pts]
            self.new_tracks.append((run[0][0], xy, width, net))
            for p, q in zip(xy, xy[1:]):
                self.add_seg(run[0][0], net, p, q, width)

    # --------------------------------------------------------------- public
    def groups(self, net):
        """Connected groups of existing copper of `net` -> list of cell sets."""
        own = self.own(net)
        from scipy import ndimage
        cells = []
        lab = []
        for layer in (0, 1):
            L, n = ndimage.label(own[layer], structure=np.ones((3, 3)))
            lab.append((L, n))
        parent = {}

        def find(a):
            while parent.setdefault(a, a) != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        for layer in (0, 1):
            for n in range(1, lab[layer][1] + 1):
                find((layer, n))
        for x, y, _ in self.holes:           # vias join the two layers
            i, j = self.ij(x, y)
            if 0 <= i < self.nx and 0 <= j < self.ny:
                a, b = lab[0][0][j, i], lab[1][0][j, i]
                if a and b:
                    parent[find((0, a))] = find((1, b))
        out = {}
        for layer in (0, 1):
            L, n = lab[layer]
            js, is_ = np.nonzero(L)
            for j, i in zip(js, is_):
                out.setdefault(find((layer, L[j, i])), set()).add((layer, int(i), int(j)))
        return list(out.values())

    def route_net(self, net, width=0.15, via_cost=24.0, fenced=True):
        """Join every group of `net`.  Returns number of joins that failed."""
        groups = self.groups(net)
        if len(groups) < 2:
            return 0
        groups.sort(key=lambda g: -len(g))
        fails = 0
        connected = set(groups[0])
        rest = groups[1:]
        while rest:
            target = {}
            for gi, g in enumerate(rest):
                for cell in g:
                    target[cell] = gi
            path = None
            for w in dict.fromkeys((width, 0.15)):     # fall back to a thin trace
                blocked = self.blocked(net, w / 2, fenced)
                viaok = self.via_ok(net, fenced)
                src = [c for c in connected if not blocked[c[0]][c[2], c[1]]] or list(connected)
                path = self._search(blocked, viaok, src,
                                    lambda l, i, j: (l, i, j) in target, via_cost)
                if path:
                    break
            if path is None:
                # nothing reachable from here: park the main group and carry on
                # from the next one so the remaining pads still get joined
                fails += 1
                connected = set(rest.pop(0))
                continue
            gi = target[path[-1]]
            self._commit(net, path, w)
            connected |= rest.pop(gi)
            connected |= set(path)
            for a, b in zip(path, path[1:]):
                if a[0] != b[0]:
                    connected.add(b)
        return fails

    def ground_stubs(self, net, width=0.25, reach=60.0, skip=None):
        """Give every group of `net` that has no via a short stub to a new via
        (the inner layers are solid planes of this net)."""
        fails = []
        while True:
            todo = None
            for g in self.groups(net):
                has_via = any((0, *self.ij(x, y)) in g or (1, *self.ij(x, y)) in g
                              for x, y, _ in self.holes)
                if has_via or g in fails:
                    continue
                if skip and any(skip(*self.xy(i, j)) for _, i, j in g):
                    continue
                todo = g
                break
            if todo is None:
                return fails
            for w in (width, 0.15):
                blocked = self.blocked(net, w / 2, fenced=False)
                viaok = self.via_ok(net, fenced=False)
                src = [c for c in todo if not blocked[c[0]][c[2], c[1]]]
                path = self._search(blocked, viaok, src,
                                    lambda l, i, j: bool(viaok[j, i]) and (l, i, j) not in todo,
                                    limit=reach, allow_via=False) if src else None
                if path:
                    break
            if not path:
                fails.append(todo)
                continue
            l, i, j = path[-1]
            path.append((1 - l, i, j))
            self._commit(net, path, w)
