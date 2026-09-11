"""Pre-registered synthetic validation v1 (design: docs/superpowers/plans/
2026-09-11-synthetic-validation-design.md, frozen before run).

148 configs: Part A sparse central (90) + A2 K-invariance (6) +
Part B dense upper-anchor (36) + Part C asymptotics (16).
Ground truth: recursive-bisection districting + closed TSP per district
(multi-start NN + neighbour-list 2-opt + Or-opt), Euclidean inter-stop,
circuity == 1.
Prediction: sparse mid = beta*sqrt(V*A_hull); dense anchor = beta*sqrt(V*A*K).
Solver-gap audit: Held-Karp exact on 30 instances n<=12.
"""
import json, math, os, random
import numpy as np
from scipy.spatial import ConvexHull

BETA = 0.7124
SEED0 = 20260911

# ---------------------------------------------------------------- shapes
def _scale_to_hull_area(pts, target):
    hull = ConvexHull(np.array(pts))
    s = math.sqrt(target / hull.volume)
    return [(x * s, y * s) for x, y in pts]

def sample_shape(shape, n, area, rng):
    """Sample n unit-space points, then scale so HULL area == area."""
    pts = []
    if shape == "square":
        pts = [(rng.random(), rng.random()) for _ in range(n)]
    elif shape == "rect4x1":
        pts = [(4 * rng.random(), rng.random()) for _ in range(n)]
    elif shape == "disk":
        while len(pts) < n:
            x, y = rng.uniform(-1, 1), rng.uniform(-1, 1)
            if x * x + y * y <= 1:
                pts.append((x, y))
    elif shape == "Lshape":
        while len(pts) < n:
            x, y = rng.random(), rng.random()
            if not (x > 0.4 and y > 0.4):
                pts.append((x, y))
    elif shape == "ring":
        while len(pts) < n:
            r = math.sqrt(rng.uniform(0.36, 1.0))
            t = rng.uniform(0, 2 * math.pi)
            pts.append((r * math.cos(t), r * math.sin(t)))
    elif shape == "gauss5":
        centers = [(0.15, 0.15), (0.85, 0.2), (0.5, 0.5), (0.2, 0.85), (0.85, 0.8)]
        for i in range(n):
            cx, cy = centers[i % 5]
            pts.append((rng.gauss(cx, 0.07), rng.gauss(cy, 0.07)))
    else:
        raise ValueError(shape)
    return _scale_to_hull_area(pts, area)

# ---------------------------------------------------------------- TSP
def _nn_tour(pts, start=0):
    n = len(pts)
    unv = set(range(n))
    unv.remove(start)
    tour = [start]
    while unv:
        last = tour[-1]
        lx, ly = pts[last]
        nxt = min(unv, key=lambda j: (pts[j][0] - lx) ** 2 + (pts[j][1] - ly) ** 2)
        tour.append(nxt)
        unv.remove(nxt)
    return tour

def tour_length(pts, tour):
    n = len(tour)
    return sum(math.dist(pts[tour[i]], pts[tour[(i + 1) % n]]) for i in range(n))

def _local_search(pts, start):
    n = len(pts)
    tour = _nn_tour(pts, start)
    d2 = ((np.array(pts)[:, None, :] - np.array(pts)[None, :, :]) ** 2).sum(-1)
    np.fill_diagonal(d2, np.inf)
    knn = [set(int(j) for j in row) for row in
           np.argsort(d2, axis=1)[:, :min(10, n - 1)]]
    pos = {v: i for i, v in enumerate(tour)}
    improved = True
    while improved:
        improved = False
        for i in range(n):
            ci = tour[i]
            ni = tour[(i + 1) % n]
            d_ab = math.dist(pts[ci], pts[ni])
            for cj in knn[ci]:
                j = pos[cj]
                if j == i or (j + 1) % n == i:
                    continue
                nj = tour[(j + 1) % n]
                gain = d_ab + math.dist(pts[cj], pts[nj]) - (
                    math.dist(pts[ci], pts[cj]) + math.dist(pts[ni], pts[nj]))
                if gain > 1e-10:
                    lo, hi = (i + 1, j + 1) if i < j else (j + 1, i + 1)
                    tour[lo:hi] = tour[lo:hi][::-1]
                    pos = {v: k for k, v in enumerate(tour)}
                    improved = True
                    break
            if improved:
                break
        if not improved:
            for seg in (1, 2, 3):
                done = False
                for i in range(n):
                    if done:
                        break
                    idx = [(i + q) % n for q in range(seg)]
                    segv = [tour[q] for q in idx]
                    sset = set(segv)
                    p_prev = tour[(i - 1) % n]
                    p_next = tour[(i + seg) % n]
                    save = (math.dist(pts[p_prev], pts[segv[0]])
                            + math.dist(pts[segv[-1]], pts[p_next]))
                    rest = [v for v in tour if v not in sset]
                    for j in range(len(rest)):
                        a, b = rest[j], rest[(j + 1) % len(rest)]
                        add = (math.dist(pts[a], pts[segv[0]])
                               + math.dist(pts[segv[-1]], pts[b])
                               + math.dist(pts[p_prev], pts[p_next]))
                        if add < save - 1e-10:
                            tour = rest[:j + 1] + segv + rest[j + 1:]
                            pos = {v: k for k, v in enumerate(tour)}
                            improved = done = True
                            break
                if done:
                    break
    return tour_length(pts, tour)

def tsp_solve(pts, restarts=3):
    """Multi-start NN + neighbour-list 2-opt + Or-opt, closed tour."""
    n = len(pts)
    if n == 2:
        return 2 * math.dist(pts[0], pts[1])
    if n < 4:
        return tour_length(pts, list(range(n)))
    return min(_local_search(pts, s) for s in range(min(restarts, n)))

def held_karp(pts):
    n = len(pts)
    INF = float("inf")
    dp = [[INF] * n for _ in range(1 << n)]
    dp[1][0] = 0.0
    for mask in range(1, 1 << n):
        for u in range(n):
            if not (mask >> u) & 1 or dp[mask][u] == INF:
                continue
            for v in range(n):
                if (mask >> v) & 1:
                    continue
                nm = mask | (1 << v)
                cand = dp[mask][u] + math.dist(pts[u], pts[v])
                if cand < dp[nm][v]:
                    dp[nm][v] = cand
    full = (1 << n) - 1
    return min(dp[full][u] + math.dist(pts[u], pts[0]) for u in range(1, n))

# ---------------------------------------------------------------- districting
def recursive_bisect(pts, K, want_siblings=False):
    """K compact districts by recursive median cuts along longer bbox axis.
    With want_siblings, also returns sibling map (paired by same split node).
    """
    import heapq
    arr = np.array(pts)
    groups = [list(range(len(pts)))]
    sib = {}
    heap = [(-len(groups[0]), 0)]
    while len(groups) < K:
        _, gi = heapq.heappop(heap)
        g = groups[gi]
        if len(g) < 2:
            continue
        sub = arr[g]
        ext = sub.max(0) - sub.min(0)
        axis = 0 if ext[0] >= ext[1] else 1
        order = sorted(g, key=lambda i: pts[i][axis])
        m = len(order) // 2
        groups[gi] = order[:m]
        b_idx = len(groups)
        groups.append(order[m:])
        sib[gi] = b_idx
        sib[b_idx] = gi
        heapq.heappush(heap, (-len(order[:m]), gi))
        heapq.heappush(heap, (-len(order[m:]), b_idx))
    out = [g for g in groups if g]
    return (out, sib) if want_siblings else out

# ---------------------------------------------------------------- configs
def build_configs():
    cfgs = []
    for shape in ["square", "rect4x1", "disk", "Lshape", "ring", "gauss5"]:
        for n in [100, 200, 400, 800, 1600]:
            for d in [0.15, 1.0, 4.0]:
                cfgs.append(dict(part="A", shape=shape, n=n, d=d, f=1.2, K=21))
    for shape in ["square", "rect4x1"]:
        for K in [4, 9, 21]:
            cfgs.append(dict(part="A2", shape=shape, n=200, d=1.0, f=1.2, K=K))
    for shape in ["square", "rect4x1", "disk", "gauss5"]:
        for n in [100, 200, 400]:
            for f in [3.0, 4.3, 6.0]:
                cfgs.append(dict(part="B", shape=shape, n=n, d=1.0, f=f, K=21))
    for shape in ["square", "disk"]:
        for n in [50, 100, 200, 400, 800, 1600, 3200, 6400]:
            cfgs.append(dict(part="C", shape=shape, n=n, d=1.0, f=1.2, K=21))
    return cfgs

def run_config(cid, cfg):
    rng = random.Random(SEED0 + cid)
    n, K, f = cfg["n"], cfg["K"], cfg["f"]
    area = n * cfg["d"]
    pts = sample_shape(cfg["shape"], n, area, rng)
    V = int(round(n * f))
    a_hull = ConvexHull(np.array(pts)).volume

    if cfg["part"] in ("A", "A2", "C"):
        # design §3.1 R1 (frozen): repeat visits land in the SIBLING
        # district (adjacent territory, different workday)
        districts, sib = recursive_bisect(pts, K, want_siblings=True)
        # design §3.1 R2 (frozen): boundary-clip repeats -> day sets stay
        # compact (sibling day tours a thin strip of shared-border territory)
        day_sets = [set(g) for g in districts]
        n_rep = V - n
        if n_rep > 0 and K > 1:
            per = max(1, n_rep // len(districts))
            extra = {di: 0 for di in range(len(districts))}
            rem = n_rep
            pairs = [(d, sib[d]) for d in sib if d < sib[d] and len(districts[d]) > 1]
            for di in range(len(districts)):
                j = sib.get(di)
                if j is None or len(districts[di]) < 2 or di > j:
                    continue
                dA, dB = districts[di], districts[j]
                # shared-border proxy: median of A and B centroids
                cx = (sum(pts[p][0] for p in dA) / len(dA)
                      + sum(pts[p][0] for p in dB) / len(dB)) / 2
                cy = (sum(pts[p][1] for p in dA) / len(dA)
                      + sum(pts[p][1] for p in dB) / len(dB)) / 2
                t = min(per + (1 if rem > di * per and rem > (di + 1) * per else 0),
                        len(dA), rem)
                if t <= 0:
                    continue
                rank = sorted(dA, key=lambda p: math.hypot(pts[p][0] - cx,
                                                           pts[p][1] - cy))
                for p in rank[:t]:
                    day_sets[j].add(p)
                extra[di] += t
                rem -= t
        true_km = 0.0
        a_eff = 0.0
        for ds in day_sets:
            sub = [pts[i] for i in sorted(ds)]
            true_km += tsp_solve(sub)
            if len(sub) >= 3:
                a_eff += ConvexHull(np.array(sub)).volume
        mid = BETA * math.sqrt(V * a_hull)
        return dict(cfg, V=V, A_hull=round(a_hull, 2), A_eff=round(a_eff, 2),
                    true_km=round(true_km, 2), pred=round(mid, 2),
                    ratio=round(true_km / mid, 4))
    classes = recursive_bisect(pts, K)
    true_km = sum(f * tsp_solve([pts[i] for i in g]) for g in classes)
    anchor = BETA * math.sqrt(V * a_hull * K)
    return dict(cfg, V=V, A_hull=round(a_hull, 2),
                true_km=round(true_km, 2), pred=round(anchor, 2),
                ratio=round(true_km / anchor, 4))

def main():
    cfgs = build_configs()
    print(f"configs: {len(cfgs)}")
    gaps = []
    for t in range(30):
        rng = random.Random(7000 + t)
        p = [(rng.random() * 10, rng.random() * 10) for _ in range(12)]
        gaps.append(tsp_solve(p) / held_karp(p) - 1)
    print(f"solver gap audit (n=12, 30 inst): mean={100*np.mean(gaps):.2f}% "
          f"max={100*max(gaps):.2f}%")

    rows = []
    for cid, cfg in enumerate(cfgs):
        r = run_config(cid, cfg)
        rows.append(r)
        print(f"[{r['part']:>2}] {r['shape']:<8} n={r['n']:>5} "
              f"{'d' if r['part'] != 'B' else 'f'}={r.get('d', r.get('f')):>4} "
              f"K={r['K']:>2} A={r['A_hull']:>8.1f} true={r['true_km']:>9.1f} "
              f"pred={r['pred']:>9.1f} ratio={r['ratio']:.3f}", flush=True)

    os.makedirs("output", exist_ok=True)
    json.dump(dict(solver_gap=dict(mean=float(np.mean(gaps)),
                                   max=float(max(gaps))),
                   rows=rows),
              open("output/synthetic_validation_v1.json", "w"), indent=1)

    okA = [r for r in rows if r["part"] == "A"
           and r["shape"] in ("square", "rect4x1", "disk", "Lshape")]
    rA = [r["ratio"] for r in okA]
    covA = sum(1 for x in rA if 0.75 <= x <= 1.30) / len(rA)
    print(f"\nPart A non-failing: median={np.median(rA):.3f} "
          f"coverage[0.75,1.30]={100*covA:.0f}%  (gate: median in [0.90,1.30], cov>=80%)")
    failA = [r for r in rows if r["part"] == "A"
             and r["shape"] in ("ring", "gauss5")]
    rF = [r["ratio"] for r in failA]
    print(f"Part A pre-declared failing (ring/gauss5): median={np.median(rF):.3f} "
          f"range=[{min(rF):.2f},{max(rF):.2f}]")
    a2 = [r for r in rows if r["part"] == "A2"]
    print("Part A2 K-invariance: "
          + ", ".join(f"{r['shape']}/K={r['K']}:{r['ratio']:.3f}" for r in a2))
    B = [r for r in rows if r["part"] == "B"]
    rB = [r["ratio"] for r in B]
    covB = sum(1 for x in rB if 0.25 <= x <= 1.40) / len(rB)
    print(f"Part B dense anchor: median={np.median(rB):.3f} "
          f"coverage[0.25,1.40]={100*covB:.0f}%  (gate: cov>=90%, median<=1.0)")
    C = sorted([r for r in rows if r["part"] == "C"],
               key=lambda r: (r["shape"], r["n"]))
    print("Part C asymptotics:")
    for r in C:
        print(f"  {r['shape']:<7} n={r['n']:>5} ratio={r['ratio']:.3f}")

if __name__ == "__main__":
    main()
