// SPDX-License-Identifier: GPL-3.0-or-later
// A* over a (layer, row, column) grid window: the inner loop of maze.py's routers, in C.
//
// Same costs, same expansion order and the same tie-breaking (f, then g, then state index, like Python's
// heapq on (f, g, s) tuples) as maze._astar_py, so the paths are identical; it only runs ~100x faster.
// Built by maze.py on first use: cc -O2 -shared -fPIC astar.c -o _astar.so
#include <math.h>
#include <stdint.h>
#include <stdlib.h>

typedef struct { double f, g; int64_t s; } node;

static int less(const node *a, const node *b) {
    if (a->f != b->f) return a->f < b->f;
    if (a->g != b->g) return a->g < b->g;
    return a->s < b->s;
}

typedef struct { node *v; int64_t n, cap; } heap;

static int hpush(heap *h, node x) {
    if (h->n == h->cap) {
        int64_t cap = h->cap ? h->cap * 2 : 4096;
        node *v = realloc(h->v, cap * sizeof(node));
        if (!v) return -1;
        h->v = v; h->cap = cap;
    }
    int64_t i = h->n++;
    while (i > 0) {
        int64_t p = (i - 1) / 2;
        if (!less(&x, &h->v[p])) break;
        h->v[i] = h->v[p]; i = p;
    }
    h->v[i] = x;
    return 0;
}

static node hpop(heap *h) {
    node top = h->v[0], last = h->v[--h->n];
    int64_t i = 0;
    for (;;) {
        int64_t c = 2 * i + 1;
        if (c >= h->n) break;
        if (c + 1 < h->n && less(&h->v[c + 1], &h->v[c])) c++;
        if (!less(&h->v[c], &last)) break;
        h->v[i] = h->v[c]; i = c;
    }
    if (h->n) h->v[i] = last;
    return top;
}

// ok: L*NY*W bytes, vok: NY*W bytes; M, A: L*NY*W doubles or NULL; vc: NY*W doubles or NULL (then vc0).
// starts/goals: state indices (l*NY + j)*W + i. Writes the path (state indices, start first) to out
// (capacity out_cap) and returns its length, 0 when no path, -1 when the node limit was hit, -2 on no memory.
int64_t astar(int L, int NY, int W, const uint8_t *ok, const uint8_t *vok, const double *M, const double *A,
              const double *vc, double vc0, const int64_t *starts, int ns, const int64_t *goals, int ng,
              int64_t max_nodes, int64_t *out, int64_t out_cap) {
    const double SQ2 = sqrt(2.0);
    const int di[8] = {1, -1, 0, 0, 1, 1, -1, -1}, dj[8] = {0, 0, 1, -1, 1, -1, 1, -1};
    const double dc[8] = {1.0, 1.0, 1.0, 1.0, SQ2, SQ2, SQ2, SQ2};
    int64_t NYW = (int64_t)NY * W, N = (int64_t)L * NYW, result = 0;
    double *g = malloc(N * sizeof(double)), *hc = malloc(NYW * sizeof(double));
    int64_t *came = malloc(N * sizeof(int64_t));
    uint8_t *isgoal = calloc(N, 1);
    int *gi = malloc(ng * sizeof(int)), *gj = malloc(ng * sizeof(int));
    heap h = {0};
    if (!g || !hc || !came || !isgoal || !gi || !gj) { result = -2; goto done; }
    for (int64_t k = 0; k < N; k++) g[k] = INFINITY;
    for (int64_t k = 0; k < NYW; k++) hc[k] = -1.0;
    for (int k = 0; k < ng; k++) {
        isgoal[goals[k]] = 1;
        int64_t rem = goals[k] % NYW;
        gj[k] = (int)(rem / W); gi[k] = (int)(rem % W);
    }
#define HEUR(i, j, out_) do { int64_t kk_ = (int64_t)(j) * W + (i); double v_ = hc[kk_]; \
        if (v_ < 0) { v_ = INFINITY; for (int q = 0; q < ng; q++) { double dx = abs((i) - gi[q]), dy = abs((j) - gj[q]); \
            double e = dx + dy + (SQ2 - 2) * (dx < dy ? dx : dy); if (e < v_) v_ = e; } hc[kk_] = v_; } (out_) = v_; } while (0)
    for (int k = 0; k < ns; k++) {
        int64_t s = starts[k], rem = s % NYW;
        double hv; HEUR((int)(rem % W), (int)(rem / W), hv);
        g[s] = 0.0; came[s] = -1;
        if (hpush(&h, (node){hv, 0.0, s})) { result = -2; goto done; }
    }
    int64_t n = 0;
    while (h.n) {
        node cur = hpop(&h);
        int64_t s = cur.s;
        double gc = cur.g;
        if (gc > g[s]) continue;
        if (isgoal[s]) {
            int64_t len = 0;
            for (int64_t t = s; t != -1; t = came[t]) len++;
            if (len > out_cap) { result = -2; goto done; }
            int64_t k = len;
            for (int64_t t = s; t != -1; t = came[t]) out[--k] = t;
            result = len;
            goto done;
        }
        if (++n > max_nodes) { result = -1; goto done; }
        int l = (int)(s / NYW);
        int64_t rem = s % NYW, base = (int64_t)l * NYW;
        int j = (int)(rem / W), i = (int)(rem % W);
        for (int d = 0; d < 8; d++) {
            int i2 = i + di[d], j2 = j + dj[d];
            if (i2 < 0 || i2 >= W || j2 < 0 || j2 >= NY) continue;
            int64_t s2 = s + (int64_t)dj[d] * W + di[d];
            if (!ok[s2]) continue;
            if (di[d] && dj[d] && !(ok[base + (int64_t)j * W + i2] || ok[base + (int64_t)j2 * W + i])) continue;
            double g2 = M ? gc + dc[d] * M[s2] + A[s2] : (A ? gc + dc[d] + A[s2] : gc + dc[d]);
            if (g2 < g[s2]) {
                double hv; HEUR(i2, j2, hv);
                g[s2] = g2; came[s2] = s;
                if (hpush(&h, (node){g2 + hv, g2, s2})) { result = -2; goto done; }
            }
        }
        if (vok[rem]) {
            double v = vc ? vc[rem] : vc0;
            for (int l2 = 0; l2 < L; l2++) {
                int64_t s2 = (int64_t)l2 * NYW + rem;
                if (l2 != l && ok[s2]) {
                    double g2 = gc + v;
                    if (g2 < g[s2]) {
                        double hv; HEUR(i, j, hv);
                        g[s2] = g2; came[s2] = s;
                        if (hpush(&h, (node){g2 + hv, g2, s2})) { result = -2; goto done; }
                    }
                }
            }
        }
    }
done:
    free(g); free(hc); free(came); free(isgoal); free(gi); free(gj); free(h.v);
    return result;
}
