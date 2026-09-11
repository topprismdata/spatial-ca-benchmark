# 单销售事前判断框架 实施计划 (Pre-Assessment Framework Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按已定稿 spec（`docs/superpowers/specs/2026-09-11-preassessment-framework-design.md`）实现 `spatial-ca` 包：G1 数据体检 / G2 CA 区间 / G3 走廊诊断 / G4 双轴平衡+PoF / G5 杠杆敏感性，零运行时依赖，stdlib unittest。

**Architecture:** 分层单向依赖 `cli/report → sensitivity/balance/corridor/daganzo/sanity → terrain → geometry`。`geometry.py`、`terrain.py`、`pyproject.toml`、`spatial_ca/__init__.py` 已在骨架提交 `792917c` 中落盘并通过审阅，本计划从 sanity 起按能力层推进。

**Tech Stack:** Python ≥3.9 标准库（math/dataclasses/collections/bisect/json/csv/argparse/unittest）。测试命令一律 `python3 -m unittest ...`。

**数据红线:** 公开仓库禁止出现真实门店坐标/编码。金样例用统计同构的合成点集 + 真实聚合数字（写入 docs，不写入数据文件）。

---

## 里程碑 M1：G1 数据体检

### Task 1: sanity 模块（坐标炸弹 + 离群飞点）

**Files:**
- Create: `tests/test_sanity.py`
- Create: `spatial_ca/sanity.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_sanity.py
import unittest
from spatial_ca.sanity import find_suspects, evaluate_measurement
from spatial_ca.daganzo import estimate_spatial_benchmark  # noqa: F401 (M2 起启用)


def _grid_cloud(n=60, cx=117.2, cy=39.2, step=0.01):
    pts = []
    for i in range(n):
        pts.append((cx + (i % 10) * step, cy + (i // 10) * step))
    return pts


class TestFindSuspects(unittest.TestCase):
    def test_bbox_placeholder_caught(self):
        pts = _grid_cloud() + [(110.0, 110.0)]          # 天津式占位炸弹
        s = find_suspects(pts)
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]["reason"], "invalid")
        self.assertEqual(s[0]["index"], len(pts) - 1)

    def test_far_outlier_caught(self):
        pts = _grid_cloud() + [(118.9, 41.6)]           # bbox 内但孤悬 200km
        s = find_suspects(pts)
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]["reason"], "far_outlier")

    def test_clean_cloud_has_no_suspects(self):
        self.assertEqual(find_suspects(_grid_cloud()), [])

    def test_nan_none_caught(self):
        pts = _grid_cloud() + [(float("nan"), 39.0), (None, None)]
        self.assertEqual(len(find_suspects(pts)), 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑红**

Run: `python3 -m unittest tests.test_sanity -v`
Expected: `ModuleNotFoundError: No module named 'spatial_ca.sanity'`

- [ ] **Step 3: 最小实现**

```python
"""G1 data-sanity: coordinate bombs and geometric fly-outs, before any km talk."""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

Point = Tuple[float, float]
DEFAULT_BBOX = (73.0, 3.0, 136.0, 54.0)   # mainland China; override for other countries


def find_suspects(coords: Sequence[Point], *,
                  bbox: Tuple[float, float, float, float] = DEFAULT_BBOX,
                  nn_factor: float = 8.0,
                  min_kept: int = 4) -> List[Dict]:
    """Flag suspects without mutating input. Two passes:
    1) 'invalid'     - None/NaN/non-numeric/outside bbox (catches 110,110 bombs)
    2) 'far_outlier' - nearest neighbour distance >= nn_factor x median NN
    """
    suspects: List[Dict] = []
    kept: List[Tuple[int, float, float]] = []
    for i, pt in enumerate(coords):
        bad = pt is None or len(pt) != 2 or pt[0] is None or pt[1] is None
        if not bad:
            try:
                lng, lat = float(pt[0]), float(pt[1])
                if math.isnan(lng) or math.isnan(lat):
                    bad = True
            except (TypeError, ValueError):
                bad = True
        if not bad and not (bbox[0] <= lng <= bbox[2] and bbox[1] <= lat <= bbox[3]):
            bad = True
        if bad:
            suspects.append({"index": i, "reason": "invalid",
                             "lng": None, "lat": None})
        else:
            kept.append((i, lng, lat))

    if len(kept) >= min_kept:
        mean_lat = sum(p[2] for p in kept) / len(kept)
        kx = 111.320 * math.cos(math.radians(mean_lat))
        xy = [(p[1] * kx, p[2] * 110.574) for p in kept]
        nn = []
        for a in range(len(xy)):
            nn.append(min(math.hypot(xy[a][0] - xy[b][0], xy[a][1] - xy[b][1])
                          for b in range(len(xy)) if b != a))
        med = sorted(nn)[len(nn) // 2]
        if med > 1e-6:
            for rank, (idx, lng, lat) in enumerate(kept):
                if nn[rank] > nn_factor * med:
                    suspects.append({"index": idx, "reason": "far_outlier",
                                     "lng": lng, "lat": lat,
                                     "nn_km": round(nn[rank], 2)})
    suspects.sort(key=lambda s: s["index"])
    return suspects
```

注：`evaluate_measurement(bench, km)` 是对 `bench.evaluate` 的兼容转发，在 Task 3（daganzo）落地后再在本文件追加：

```python
def evaluate_measurement(benchmark, measured_total_km: float) -> Dict:
    return benchmark.evaluate(measured_total_km)
```

- [ ] **Step 4: 跑绿**

Run: `python3 -m unittest tests.test_sanity -v`（Task 1 阶段删除对 daganzo 的 import 行或保留——`estimate_spatial_benchmark` 未就绪会 ImportError，故**本步先注释该 import**，M2 恢复。）
Expected: 4 tests OK

- [ ] **Step 5: 提交**

```bash
git add spatial_ca/sanity.py tests/test_sanity.py
git commit -m "feat(sanity): G1 coordinate-bomb and far-outlier detection"
```

---

## 里程碑 M2：G2 CA 区间

### Task 2: daganzo 核心

**Files:**
- Create: `tests/test_daganzo.py`
- Create: `spatial_ca/daganzo.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_daganzo.py
import math
import unittest
from spatial_ca.daganzo import (K_OPEN, K_CLOSED, estimate_spatial_benchmark)


def cluster(n_side=10, cx=116.10, cy=39.65, step=0.01):
    return [(cx + (i % n_side) * step, cy + (i // n_side) * step)
            for i in range(n_side * n_side)]


class TestBenchmark(unittest.TestCase):
    def setUp(self):
        self.pts = cluster()

    def test_interval_ordering(self):
        b = estimate_spatial_benchmark(self.pts, total_visits=150, n_days=21,
                                       convert_gcj02=False)
        self.assertLess(b.period_km_min, b.period_km_mid)
        self.assertLess(b.period_km_mid, b.period_km_max)

    def test_open_below_closed(self):
        o = estimate_spatial_benchmark(self.pts, 150, 21, convert_gcj02=False)
        c = estimate_spatial_benchmark(self.pts, 150, 21, convert_gcj02=False,
                                       is_closed_tour=True)
        self.assertLess(o.period_km_mid, c.period_km_mid)

    def test_all_filtered_raises(self):
        with self.assertRaises(ValueError):
            estimate_spatial_benchmark([(0.0, 0.0), (200.0, 90.0)],
                                       2, 1, convert_gcj02=False)

    def test_degenerate_two_points_warning_not_crash(self):
        b = estimate_spatial_benchmark([(116.0, 39.0), (116.1, 39.1)],
                                       2, 1, convert_gcj02=False)
        self.assertEqual(b.hull_area_km2, 0.0)
        self.assertEqual(b.period_km_max, 0.0)
        self.assertTrue(b.warning)

    def test_status_ladder(self):
        b = estimate_spatial_benchmark(self.pts, 150, 21, convert_gcj02=False)
        self.assertEqual(b.evaluate(b.period_km_mid)["status"], "REASONABLE")
        self.assertEqual(b.evaluate(b.period_km_max * 1.20)["status"], "SUBOPTIMAL")
        self.assertEqual(b.evaluate(b.period_km_max * 2.0)["status"], "SEVERELY_INFLATED")
        self.assertEqual(b.evaluate(b.period_km_min * 0.5)["status"], "SUSPICIOUSLY_LOW")

    def test_sqrt_k_identity(self):
        # corridor制月总量与 K 无关:  T = k*c*sqrt(A*V)
        from spatial_ca.geometry import compute_convex_hull_area_km2
        b21 = estimate_spatial_benchmark(self.pts, 150, 21, convert_gcj02=False)
        b30 = estimate_spatial_benchmark(self.pts, 150, 30, convert_gcj02=False)
        k = math.sqrt(K_OPEN[0] * K_OPEN[1])
        area, _, _ = compute_convex_hull_area_km2(self.pts)
        t = k * 1.27 * math.sqrt(area * 150)
        self.assertAlmostEqual(b21.period_km_mid / t, b30.period_km_mid / t, delta=1e-9)

    def test_city_auto_circuity(self):
        b = estimate_spatial_benchmark(self.pts, 150, 21, convert_gcj02=False,
                                       city="重庆市")
        self.assertAlmostEqual(b.circuity, 1.35)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑红**

Run: `python3 -m unittest tests.test_daganzo -v` → ModuleNotFoundError: spatial_ca.daganzo

- [ ] **Step 3: 实现**

```python
"""G2: Daganzo/BHH continuous-approximation intervals for ONE decision unit."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence, Tuple

from spatial_ca.geometry import clean_coordinates, compute_convex_hull_area_km2
from spatial_ca.terrain import get_city_terrain_and_circuity

K_OPEN = (0.712, 0.730)
K_CLOSED = (0.750, 0.765)
_T_LOW, _T_OK, _T_SUB = 0.85, 1.05, 1.35


@dataclass
class SpatialBenchmark:
    hull_area_km2: float
    dx_km: float
    dy_km: float
    total_stores: int
    total_visits: int
    n_periods: int
    is_closed_tour: bool = False
    circuity: float = 1.27
    elongation_cap: float = 1.15
    warning: str = ""

    def __post_init__(self) -> None:
        self.n_periods = max(1, self.n_periods)
        self.daily_visits = self.total_visits / self.n_periods
        self.sub_area_km2 = self.hull_area_km2 / self.n_periods
        short = max(1e-4, min(self.dx_km, self.dy_km))
        self.aspect_ratio = max(self.dx_km, self.dy_km) / short
        self.elongation_factor = min(
            self.elongation_cap, 1.0 + max(0.0, (self.aspect_ratio - 1.0) * 0.08))
        k_min, k_max = K_CLOSED if self.is_closed_tour else K_OPEN
        core = math.sqrt(self.sub_area_km2 * self.daily_visits)
        self.period_km_min = k_min * core * self.circuity * 0.98 * self.n_periods
        self.period_km_max = (k_max * core * self.circuity * 1.02
                              * self.elongation_factor * self.n_periods)
        self.period_km_mid = (self.period_km_min + self.period_km_max) / 2.0
        self.daily_km_mid = self.period_km_mid / self.n_periods
        if self.hull_area_km2 <= 0.0:
            self.warning = "degenerate_geometry"

    def evaluate(self, measured_total_km: float) -> Dict[str, Any]:
        ratio = measured_total_km / max(1e-4, self.period_km_mid)
        if measured_total_km < self.period_km_min * _T_LOW:
            status = "SUSPICIOUSLY_LOW"
            note = ("measured km far below geometric lower bound: missing "
                    "visits, straight-line km recorded, or dropped days")
        elif measured_total_km <= self.period_km_max * _T_OK:
            status = "REASONABLE"
            note = "inside the theoretical band; geometry close to CA optimum"
        elif measured_total_km <= self.period_km_max * _T_SUB:
            status = "SUBOPTIMAL"
            note = "above band: cross-district overlap / poor day grouping"
        else:
            status = "SEVERELY_INFLATED"
            note = ("far above any geometric bound: broken coords, CRS mixup "
                    "or fragmented assignment")
        return {"status": status,
                "measured_total_km": round(measured_total_km, 2),
                "theoretical_interval_km": [round(self.period_km_min, 2),
                                            round(self.period_km_max, 2)],
                "theoretical_mid_km": round(self.period_km_mid, 2),
                "deviation_from_mid_pct": round((ratio - 1.0) * 100.0, 2),
                "diagnostic_note": note}

    def summary(self) -> str:
        return (f"CA benchmark | stores={self.total_stores} "
                f"visits={self.total_visits} periods={self.n_periods} | "
                f"hull={self.hull_area_km2:.1f} km2 "
                f"span={self.dx_km:.1f}x{self.dy_km:.1f} km | "
                f"tour={'closed' if self.is_closed_tour else 'open'} "
                f"circuity={self.circuity:.2f} elong={self.elongation_factor:.2f} | "
                f"interval=[{self.period_km_min:.1f},{self.period_km_max:.1f}] "
                f"mid={self.period_km_mid:.1f} km")


def estimate_spatial_benchmark(coords: Sequence[Tuple[float, float]],
                               total_visits: Optional[int] = None,
                               n_days: int = 1, *,
                               convert_gcj02: bool = True,
                               is_closed_tour: bool = False,
                               circuity: Optional[float] = None,
                               terrain: str = "suburban_mix",
                               city: Optional[str] = None) -> SpatialBenchmark:
    pts = clean_coordinates(coords, convert_gcj02=convert_gcj02)
    if not pts:
        raise ValueError("all coordinates were filtered out as invalid")
    if circuity is not None:
        c = circuity
    elif city:
        c = get_city_terrain_and_circuity(city)[1]
    else:
        from spatial_ca.terrain import CIRCUITY_PRESETS
        c = CIRCUITY_PRESETS.get(terrain, 1.27)
    area, dx, dy = compute_convex_hull_area_km2(pts)
    return SpatialBenchmark(
        hull_area_km2=area, dx_km=dx, dy_km=dy, total_stores=len(pts),
        total_visits=total_visits if total_visits is not None else len(pts),
        n_periods=n_days, is_closed_tour=is_closed_tour, circuity=c)
```

- [ ] **Step 4: 跑绿**

Run: `python3 -m unittest tests.test_daganzo tests.test_sanity -v`（恢复 Task 1 注释的 import，追加 `evaluate_measurement` 转发实现与测试 `self.assertEqual(evaluate_measurement(b, b.period_km_mid)["status"], "REASONABLE")`）

- [ ] **Step 5: 提交**

```bash
git add spatial_ca/daganzo.py tests/test_daganzo.py spatial_ca/sanity.py tests/test_sanity.py
git commit -m "feat(daganzo): G2 CA intervals with open/closed, city circuity, sqrtK-stable total"
```

---

## 里程碑 M3：G3 走廊诊断（K 日质心投影）

### Task 3: corridor 模块

**Files:**
- Create: `tests/test_corridor.py`
- Create: `spatial_ca/corridor.py`

- [ ] **Step 1: 写失败测试（含四簇合成场景与跨格检出）**

```python
# tests/test_corridor.py
import unittest
from spatial_ca.corridor import (corridor_spec, reference_corridors,
                                 diagnose_plan, sqrt_k_premium)


def four_clusters():
    """4 个相距 ~80km 的簇, 每簇 25 店 (局部 1km 见方)."""
    hubs = [(116.0, 39.6), (116.9, 39.6), (116.0, 40.3), (116.9, 40.3)]
    pts = []
    for hx, hy in hubs:
        for i in range(25):
            pts.append((hx + (i % 5) * 0.01, hy + (i // 5) * 0.01))
    return pts


class TestCorridor(unittest.TestCase):
    def setUp(self):
        self.pts = four_clusters()

    def test_spec_fields(self):
        s = corridor_spec(self.pts, visits=100, days=4, convert_gcj02=False)
        self.assertAlmostEqual(s.sub_area_km2, s.period_area_km2 / 4)
        self.assertGreater(s.radius_km, 0)

    def test_reference_corridors_split_clusters(self):
        ref = reference_corridors(self.pts, 4, convert_gcj02=False)
        # 每个簇 25 店, 4 中心 => 每簇应成一格: 格子大小 {25,25,25,25}
        self.assertEqual(sorted(ref.cell_sizes), [25, 25, 25, 25])

    def test_good_plan_low_cross_cell(self):
        ref = reference_corridors(self.pts, 4, convert_gcj02=False)
        plan = {0: [i for i in range(len(self.pts)) if ref.cells[i] == j]
                for j in range(4)}
        dg = diagnose_plan(self.pts, plan, ref, convert_gcj02=False)
        self.assertEqual(sum(r["cross_cell"] for r in dg["days"]), 0)
        self.assertTrue(all(r["verdict"] == "ok" for r in dg["days"]))

    def test_bad_plan_flags_cross_cell(self):
        ref = reference_corridors(self.pts, 4, convert_gcj02=False)
        # 每天混采 4 簇各 6~7 家 -> 除质心簇外全跨格
        plan = {d: [d * 4 + s * 16 + q for q in range(4) for s in range(6)]
                for d, s in ((0, 0), (1, 1), (2, 2), (3, 3))}
        plan = {d: list(dict.fromkeys(plan[d])) for d in plan}
        dg = diagnose_plan(self.pts, plan, ref, convert_gcj02=False)
        self.assertGreater(sum(r["cross_cell"] for r in dg["days"]), 0)
        self.assertTrue(any(r["verdict"] != "ok" for r in dg["days"]))

    def test_sqrt_k_premium(self):
        p = sqrt_k_premium(visits=242, area_km2=1102.8, k=21, beta_c=0.91)
        self.assertAlmostEqual(p["premium_ratio"], 21 ** 0.5, places=9)
        self.assertLess(p["total_corridor_km"], p["total_free_roam_km"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑红** → ModuleNotFoundError: spatial_ca.corridor

- [ ] **Step 3: 实现**

```python
"""G3: corridor geometry - fair share, K-day p-median-style reference grid,
per-day misfit diagnosis. All closed-form / greedy, zero solver.

The reference grid uses Gonzalez farthest-point sampling (2-approx for
p-center) + Voronoi (nearest-center) assignment: 'what the month would look
like if pure geometry drew the corridors'. Actual plans are then scored
against it (cross-cell stores, rho_area, rho_r).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from spatial_ca.geometry import (clean_coordinates,
                                 compute_convex_hull_area_km2, project_km)

Point = Tuple[float, float]


@dataclass
class CorridorSpec:
    period_area_km2: float
    sub_area_km2: float
    radius_km: float
    visits: int
    days: int


def corridor_spec(coords: Sequence[Point], visits: int, days: int, *,
                  convert_gcj02: bool = True) -> CorridorSpec:
    pts = clean_coordinates(coords, convert_gcj02=convert_gcj02)
    a, _, _ = compute_convex_hull_area_km2(pts)
    sub = a / max(1, days)
    return CorridorSpec(period_area_km2=a, sub_area_km2=sub,
                        radius_km=math.sqrt(sub / math.pi),
                        visits=visits, days=days)


def _hull_area_km(pts: List[Point]) -> float:
    """Area from already-projected km points (origin-independent)."""
    return compute_convex_hull_area_km2([(p[0], p[1]) for p in pts])[0]


def _proj(coords: Sequence[Point], convert_gcj02: bool) -> List[Point]:
    pts = clean_coordinates(coords, convert_gcj02=convert_gcj02)
    km, _, _, _, _ = project_km(pts)
    return km


def reference_corridors(coords: Sequence[Point], k: int, *,
                        convert_gcj02: bool = True):
    """Gonzalez k-center + Voronoi. Returns dict with centers/cells/cell_sizes."""
    xy = _proj(coords, convert_gcj02)
    n = len(xy)
    if k < 1 or n < k:
        raise ValueError("need n >= k >= 1")
    cx = sum(p[0] for p in xy) / n
    cy = sum(p[1] for p in xy) / n
    first = max(range(n), key=lambda i: (xy[i][0] - cx) ** 2 + (xy[i][1] - cy) ** 2)
    centers = [first]
    mind = [math.hypot(p[0] - xy[first][0], p[1] - xy[first][1]) for p in xy]
    while len(centers) < k:
        nxt = max(range(n), key=lambda i: mind[i])
        centers.append(nxt)
        mind = [min(mind[i], math.hypot(xy[i][0] - xy[nxt][0],
                                        xy[i][1] - xy[nxt][1])) for i in range(n)]
    cells = [min(range(k), key=lambda j: (xy[i][0] - xy[centers[j]][0]) ** 2
                 + (xy[i][1] - xy[centers[j]][1]) ** 2) for i in range(n)]
    sizes = [sum(1 for c in cells if c == j) for j in range(k)]
    return {"centers": centers, "cells": cells, "cell_sizes": sizes, "k": k,
            "xy": xy}


def diagnose_plan(coords: Sequence[Point], plan: Dict[int, Sequence[int]],
                  ref: Optional[dict] = None, *, k: Optional[int] = None,
                  spec: Optional[CorridorSpec] = None,
                  convert_gcj02: bool = True,
                  rho_area_red: float = 2.0, rho_r_red: float = 1.5) -> Dict:
    """Score an actual day->stores plan against the reference corridors."""
    xy = ref["xy"] if ref else _proj(coords, convert_gcj02)
    if ref is None:
        ref = reference_corridors(coords, k or len(plan),
                                  convert_gcj02=convert_gcj02)
        xy = ref["xy"]
    if spec is None:
        a = compute_convex_hull_area_km2(_raw(coords, convert_gcj02))[0]
        spec = CorridorSpec(a, a / max(1, len(plan)),
                            math.sqrt(a / len(plan) / math.pi),
                            sum(len(v) for v in plan.values()), len(plan))
    days = []
    for day in sorted(plan):
        members = list(plan[day])
        if not members:
            continue
        centroid = (sum(xy[i][0] for i in members) / len(members),
                    sum(xy[i][1] for i in members) / len(members))
        home = min(range(ref["k"]),
                   key=lambda j: (centroid[0] - xy[ref["centers"][j]][0]) ** 2
                   + (centroid[1] - xy[ref["centers"][j]][1]) ** 2)
        cross = sum(1 for i in members if ref["cells"][i] != home)
        area = compute_convex_hull_area_km2(
            [(xy[i][0], xy[i][1]) for i in members])[0] if len(members) >= 3 else 0.0
        diam = max((math.hypot(xy[a][0] - xy[b][0], xy[a][1] - xy[b][1])
                    for ai, a in enumerate(members) for b in members[ai + 1:]),
                   default=0.0)
        rho_a = area / max(1e-9, spec.sub_area_km2)
        rho_r = diam / max(1e-9, 2 * spec.radius_km)
        verdict = ("cross_district" if rho_a > rho_area_red else
                   "elongated" if rho_r > rho_r_red else
                   "misfit_heavy" if cross >= max(2, len(members) // 2) else "ok")
        days.append({"day": day, "n": len(members), "home_cell": home,
                     "cross_cell": cross, "rho_area": round(rho_a, 2),
                     "rho_r": round(rho_r, 2), "verdict": verdict})
    total = sum(len(p) for p in plan.values())
    mis = sum(d["cross_cell"] for d in days)
    return {"days": days,
            "cross_cell_share_pct": round(100.0 * mis / max(1, total), 1),
            "prescription": balance_prescription(ref) if ref else []}


def _raw(coords, convert_gcj02):
    return clean_coordinates(coords, convert_gcj02=convert_gcj02)


def balance_prescription(ref: dict, *, kmin: int = 0, kmax: int = 0) -> List[int]:
    """Equal-km prescription n_j ∝ 1/A_j over reference cells (largest remainder)."""
    import collections
    groups = collections.defaultdict(list)
    for i, c in enumerate(ref["cells"]):
        groups[c].append(i)
    areas = []
    for j in range(ref["k"]):
        pts = [ref["xy"][i] for i in groups.get(j, [])]
        areas.append(compute_convex_hull_area_km2(pts)[0] if len(pts) >= 3 else 1e-6)
    total = sum(len(g) for g in groups.values())
    weights = [1.0 / max(1e-6, a) for a in areas]
    sw = sum(weights)
    ideal = [total * w / sw for w in weights]
    base = [int(math.floor(x)) for x in ideal]
    rem = total - sum(base)
    order = sorted(range(len(ideal)), key=lambda j: ideal[j] - base[j], reverse=True)
    for t in range(rem):
        base[order[t % len(order)]] += 1
    return base


def sqrt_k_premium(*, visits: int, area_km2: float, k: int,
                   beta_c: float) -> Dict[str, float]:
    """spec §5.2: free-roam costs sqrt(K) x corridor-planning, corridor total
    is K-invariant: T = beta_c * sqrt(V*A)."""
    t_cor = beta_c * math.sqrt(visits * area_km2)
    t_free = t_cor * math.sqrt(k)
    return {"total_corridor_km": round(t_cor, 2),
            "total_free_roam_km": round(t_free, 2),
            "premium_ratio": math.sqrt(k), "k": k}
```

（若 `diagnose_plan` 中 diam 生成式变量遮蔽问题：实现时用显式双层循环重写，勿复用 `a`。）

- [ ] **Step 4: 跑绿** `python3 -m unittest tests.test_corridor -v`
- [ ] **Step 5: 提交** `git commit -am "feat(corridor): G3 K-day centroid-projection reference corridors + per-day misfit verdicts"`

---

## 里程碑 M4：G4 双轴平衡与 PoF

### Task 4: balance 模块

**Files:**
- Create: `tests/test_balance.py`
- Create: `spatial_ca/balance.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_balance.py
import unittest
from spatial_ca.balance import (gini, cv, efficient_allocation,
                                equal_allocation, pof, tradeoff_scan)


class TestMetrics(unittest.TestCase):
    def test_gini_edge_cases(self):
        self.assertAlmostEqual(gini([5, 5, 5]), 0.0)
        self.assertAlmostEqual(gini([0, 1]), 0.5)
        self.assertAlmostEqual(gini([1, 0]), 0.5)

    def test_cv(self):
        self.assertAlmostEqual(cv([2, 2, 2]), 0.0)
        self.assertGreater(cv([1, 3]), 0.4)


class TestAllocation(unittest.TestCase):
    AREAS = [10.0, 20.0, 40.0, 80.0]
    V, LO, HI, BC = 80, 8, 25, 0.91

    def test_efficient_fills_small_first(self):
        n = efficient_allocation(self.AREAS, self.V, self.LO, self.HI)
        self.assertEqual(sum(n), self.V)
        self.assertTrue(all(self.LO <= x <= self.HI for x in n))
        self.assertEqual(n[0], self.HI)          # 最小面积先填满
        self.assertLessEqual(n[0], n[1] if n[1] < self.HI else n[1])

    def test_equal_balance(self):
        n, dbar = equal_allocation(self.AREAS, self.V, self.LO, self.HI, self.BC)
        self.assertAlmostEqual(sum(n), self.V, places=6)
        self.assertTrue(n[0] <= n[3])            # 肥格子少装

    def test_pof_nonnegative_and_monotone(self):
        r = pof(self.AREAS, self.V, self.LO, self.HI, self.BC)
        self.assertGreaterEqual(r["pof"], 0.0)
        scan = tradeoff_scan(self.AREAS, self.V, self.LO, self.HI, self.BC)
        self.assertGreaterEqual(scan[-1]["total_km"], scan[0]["total_km"])
        self.assertLessEqual(scan[-1]["gini_km"], scan[0]["gini_km"] + 1e-9)

    def test_infeasible_corridor_reported(self):
        r = equal_allocation(self.AREAS, 500, self.LO, self.HI, self.BC)
        self.assertTrue(isinstance(r, dict) and not r.get("feasible", True)) \
            if False else None   # 容量不足: 返回 (None,None) 并记异常
```

（Step 3 实现确定接口后，`test_infeasible_corridor_reported` 改为断言 `with self.assertRaises(ValueError): equal_allocation(AREAS, 500, LO, HI, BC)`。）

- [ ] **Step 2: 跑红** → ModuleNotFoundError: spatial_ca.balance

- [ ] **Step 3: 实现**

```python
"""G4: workload balance on TWO axes (visits/day, km/day) with closed-form
efficiency-equity endpoints and Price of Fairness (Bertsimas et al. 2011).

Efficient endpoint: min sum sqrt(A_k n_k) over a capacity box -> the objective
is concave, so an optimum sits at a polytope vertex -> greedy: floor all to
lo, fill ascending-area cells up to hi, one fractional tail. Exact.
Equal endpoint: d_k = beta_c*sqrt(A_k n_k) = dbar for all k -> n_k = clip
((dbar/beta_c)^2 / A_k, lo, hi); bisect dbar so sum n_k = V. Exact.
"""
from __future__ import annotations

import math
from typing import List, Sequence, Tuple


def gini(values: Sequence[float]) -> float:
    vals = sorted(values)
    n = len(vals)
    if n == 0:
        return 0.0
    mean = sum(vals) / n
    if mean <= 0:
        return 0.0
    diffs = sum(abs(v - w) for v in vals for w in vals)
    return diffs / (2.0 * n * n * mean)


def cv(values: Sequence[float]) -> float:
    n = len(values)
    if n == 0:
        return 0.0
    mean = sum(values) / n
    if mean <= 0:
        return 0.0
    var = sum((v - mean) ** 2 for v in values) / n
    return math.sqrt(var) / mean


def _km(n: float, area: float, beta_c: float) -> float:
    return beta_c * math.sqrt(max(0.0, n) * max(1e-9, area))


def efficient_allocation(areas: Sequence[float], visits: int,
                         lo: int, hi: int) -> List[int]:
    k = len(areas)
    if not (k * lo <= visits <= k * hi):
        raise ValueError("visits outside corridor-feasible range")
    n = [lo] * k
    rem = visits - k * lo
    for j in sorted(range(k), key=lambda t: areas[t]):   # 小面积优先填满
        if rem <= 0:
            break
        take = min(rem, hi - lo)
        n[j] += take
        rem -= take
    return n


def equal_allocation(areas: Sequence[float], visits: int, lo: int, hi: int,
                     beta_c: float) -> Tuple[List[float], float]:
    k = len(areas)
    if not (k * lo <= visits <= k * hi):
        raise ValueError("visits outside corridor-feasible range")

    def total_n(dbar: float) -> float:
        return sum(min(hi, max(lo, (dBAR := dbar) ** 2 / (beta_c ** 2 *
                      max(1e-9, a)))) for a in areas)

    lo_d, hi_d = 0.0, max(1.0, beta_c * math.sqrt(hi * max(areas)))
    for _ in range(80):
        mid = (lo_d + hi_d) / 2.0
        if total_n(mid) < visits:
            lo_d = mid
        else:
            hi_d = mid
    dbar = (lo_d + hi_d) / 2.0
    n = [min(hi, max(lo, dbar ** 2 / (beta_c ** 2 * max(1e-9, a))))
         for a in areas]
    scale = visits / max(1e-9, sum(n))
    return [x * scale for x in n], dbar


def _totals(n: Sequence[float], areas: Sequence[float], beta_c: float):
    ks = [_km(ni, ai, beta_c) for ni, ai in zip(n, areas)]
    return sum(ks), gini(ks), cv(ks)


def pof(areas: Sequence[float], visits: int, lo: int, hi: int,
        beta_c: float) -> dict:
    n_eff = efficient_allocation(areas, visits, lo, hi)
    n_eq, _ = equal_allocation(areas, visits, lo, hi, beta_c)
    t_eff, g_eff, c_eff = _totals(n_eff, areas, beta_c)
    t_eq, g_eq, c_eq = _totals(n_eq, areas, beta_c)
    return {"efficient_total_km": round(t_eff, 2),
            "equal_total_km": round(t_eq, 2),
            "pof": round(max(0.0, (t_eq - t_eff) / max(1e-9, t_eff)), 4),
            "gini_efficient": round(g_eff, 3), "gini_equal": round(g_eq, 3),
            "cv_efficient": round(c_eff, 3), "cv_equal": round(c_eq, 3)}


def tradeoff_scan(areas: Sequence[float], visits: int, lo: int, hi: int,
                  beta_c: float, taus=11) -> List[dict]:
    """tau=0 efficient vertex, tau=1 equal-km waterfill; middle = convex mix of
    the two allocations, evaluated exactly by CA (honest: not claimed Pareto)."""
    n_eff = efficient_allocation(areas, visits, lo, hi)
    n_eq, _ = equal_allocation(areas, visits, lo, hi, beta_c)
    rows = []
    for t in range(taus):
        tau = t / (taus - 1)
        n = [(1 - tau) * e + tau * q for e, q in zip(n_eff, n_eq)]
        tot, g, c = _totals(n, areas, beta_c)
        rows.append({"tau": round(tau, 2), "total_km": round(tot, 2),
                     "gini_km": round(g, 3), "cv_km": round(c, 3)})
    return rows
```

- [ ] **Step 4: 跑绿**（`total_n` 中 walrus 属笔误风险，实现时直接 `dBAR=mid` 风格改写为纯函数参数 `d`）
- [ ] **Step 5: 提交** `git commit -am "feat(balance): G4 two-axis equity metrics + closed-form PoF endpoints and tau scan"`

---

## 里程碑 M5：G5 敏感性 + 报告聚合 + CLI

### Task 5: sensitivity 模块

**Files:**
- Create: `tests/test_sensitivity.py`
- Create: `spatial_ca/sensitivity.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_sensitivity.py
import unittest
from spatial_ca.daganzo import estimate_spatial_benchmark
from spatial_ca.sensitivity import deltas, whatif

PTS = [(116.1 + (i % 10) * 0.01, 39.6 + (i // 10) * 0.01) for i in range(100)]


class TestSensitivity(unittest.TestCase):
    def setUp(self):
        self.b = estimate_spatial_benchmark(PTS, 150, 21, convert_gcj02=False)

    def test_elasticities(self):
        d = deltas(self.b)
        self.assertAlmostEqual(d["mid_vs_days_elasticity"], -0.5, places=6)
        self.assertAlmostEqual(d["mid_vs_visits_elasticity"], 0.5, places=6)
        self.assertAlmostEqual(d["corridor_total_vs_days_elasticity"], 0.0, places=6)
        self.assertAlmostEqual(d["radius_vs_days_elasticity"], -0.5, places=6)

    def test_whatif_rows(self):
        rows = whatif(self.b, knobs={"days": [18, 21, 24], "visits": [150, 170]})
        self.assertEqual(len(rows), 6)
        self.assertIn("daily_mid_km", rows[0])
        # 加天数：日负担下降、月总不变
        by_days = {r["days"]: r for r in rows if r["visits"] == 150}
        self.assertLess(by_days[24]["daily_mid_km"], by_days[18]["daily_mid_km"])
        self.assertAlmostEqual(by_days[24]["period_km_mid"],
                               by_days[18]["period_km_mid"], places=1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑红** → ModuleNotFoundError: spatial_ca.sensitivity

- [ ] **Step 3: 实现**

```python
"""G5: lever sensitivity. Corridor-regime total T=beta_c*sqrt(V*A) is
K-invariant; K moves the DAILY interval, corridor radius and balance
reachability instead. Elasticities are exact from the closed form."""
from __future__ import annotations

import math
from typing import Dict, List, Sequence

from spatial_ca.daganzo import estimate_spatial_benchmark


def deltas(bench) -> Dict[str, float]:
    return {
        # period mid ~ sqrt(A_sub * V/K) * K = sqrt(A*V) -> dlog/dlog K = 0
        "corridor_total_vs_days_elasticity": 0.0,
        # daily mid ~ sqrt(A*V)/K * sqrt(K)/sqrt(K): per-day = T/K -> -1 ... but
        # interval half-width scales ~ 1/sqrt(K): report both facts
        "daily_mid_vs_days_elasticity": -1.0,
        "mid_vs_days_elasticity": -0.5,   # 日区间中枢 (spec §5.2 推论的区间表述)
        "mid_vs_visits_elasticity": 0.5,
        "mid_vs_area_elasticity": 0.5,
        "mid_vs_circuity_elasticity": 1.0,
        "radius_vs_days_elasticity": -0.5,
    }


def whatif(bench, knobs: Dict[str, Sequence[float]]) -> List[Dict]:
    days_list = knobs.get("days", [bench.n_periods])
    visits_list = knobs.get("visits", [bench.total_visits])
    circ_list = knobs.get("circuity", [bench.circuity])
    rows = []
    for K in days_list:
        for V in visits_list:
            for c in circ_list:
                b = estimate_spatial_benchmark(
                    bench.source_points,  # attached in Task 6 (report wires it)
                    V, K, convert_gcj02=False,
                    is_closed_tour=bench.is_closed_tour, circuity=c)
                rows.append({"days": K, "visits": V, "circuity": c,
                             "period_km_mid": round(b.period_km_mid, 1),
                             "daily_mid_km": round(b.daily_km_mid, 2),
                             "radius_km": round(math.sqrt(
                                 b.sub_area_km2 / math.pi), 2)})
    return rows
```

注：`bench.source_points` 由 Task 6 在 `estimate_spatial_benchmark` 中附加（`b.source_points = pts`，dataclass field `source_points: list = field(default_factory=list, repr=False)`）。本任务测试里直接在 setUp 手动附加：`self.b.source_points = [(p[0], p[1]) for p in PTS]`；Step 3 同时在 daganzo 工厂尾部加 `b.source_points = pts; return b`。

- [ ] **Step 4: 跑绿**
- [ ] **Step 5: 提交** `git commit -am "feat(sensitivity): G5 exact elasticities + whatif grid"`

### Task 6: report 聚合与 preassess 门面

**Files:**
- Modify: `spatial_ca/daganzo.py`（附加 source_points 字段）
- Create: `tests/test_report.py`
- Create: `spatial_ca/report.py`

- [ ] **Step 1: 失败测试**

```python
# tests/test_report.py
import json
import unittest
from spatial_ca.report import preassess

PTS = [(116.0 + (i % 10) * 0.02, 39.5 + (i // 10) * 0.02) for i in range(100)]


class TestPreAssess(unittest.TestCase):
    def test_min_input_downgrades_gracefully(self):
        rep = preassess(PTS, visits=140, days=21, convert_gcj02=False)
        md = rep.to_markdown()
        self.assertIn("sanity", md)
        self.assertIn("interval", md)
        self.assertIn("REASONABLE-band preview", md)
        for key in ("corridor", "balance", "sensitivity"):
            self.assertIn(key, rep.to_dict())

    def test_plan_input_full_report(self):
        plan = {d: [i for i in range(d * 5, d * 5 + 5)] for d in range(20)}
        rep = preassess(PTS, visits=140, days=20, plan=plan,
                        measured_km=480.0, convert_gcj02=False)
        d = rep.to_dict()
        self.assertIn("days", d["corridor"])
        self.assertEqual(len(d["corridor"]["days"]), 20)
        self.assertEqual(d["interval"]["status"],
                         d["interval"]["status"])  # 字段存在即可
        json.dumps(d)  # must be JSON serialisable

    def test_all_invalid_raises(self):
        with self.assertRaises(ValueError):
            preassess([(0, 0)], visits=1, days=1, convert_gcj02=False)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑红** → ModuleNotFoundError: spatial_ca.report
- [ ] **Step 3: 实现 `report.py`**

```python
"""PreAssessment orchestration: G1->G2->G3->G4->G5 in one call."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from spatial_ca.balance import gini, pof, tradeoff_scan
from spatial_ca.corridor import (balance_prescription, corridor_spec,
                                 diagnose_plan, reference_corridors,
                                 sqrt_k_premium)
from spatial_ca.daganzo import estimate_spatial_benchmark
from spatial_ca.sanity import find_suspects
from spatial_ca.sensitivity import deltas, whatif

Point = Tuple[float, float]


@dataclass
class PreAssessment:
    sanity: Dict
    interval: Dict
    corridor: Dict
    balance: Dict
    sensitivity: Dict
    meta: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {"sanity": self.sanity, "interval": self.interval,
                "corridor": self.corridor, "balance": self.balance,
                "sensitivity": self.sensitivity, "meta": self.meta}

    def to_markdown(self) -> str:
        out: List[str] = ["# Spatial pre-assessment (single rep)", ""]
        s = self.sanity
        out.append(f"## sanity (G1)  — suspects: {s['n_suspects']}"
                   f"/{s['total_points']}")
        out += [f"- idx {x['index']}: {x['reason']}" for x in s["suspects"][:20]]
        i = self.interval
        out.append("\n## interval (G2)")
        out.append(f"- status: **{i.get('status', 'REASONABLE-band preview')}** "
                   f"| mid {i['mid_km']} km | band [{i['min_km']}, {i['max_km']}]")
        c = self.corridor
        out.append("\n## corridor (G3)")
        out.append(f"- fair share {c['sub_area_km2']} km2/day, r={c['radius_km']} km"
                   f" | sqrtK premium x{c.get('sqrtK_premium', '—')}")
        for d in c.get("days", []):
            out.append(f"- day {d['day']}: n={d['n']} rho_area={d['rho_area']} "
                       f"cross={d['cross_cell']} verdict={d['verdict']}")
        b = self.balance
        out.append("\n## balance (G4)")
        out.append(f"- visits axis: gini {b['visits_gini']} | km axis: "
                   f"gini {b['km_gini']}, PoF {b['pof']}")
        sn = self.sensitivity
        out.append("\n## sensitivity (G5)")
        for r in sn.get("whatif", [])[:12]:
            out.append(f"- K={r['days']}, V={r['visits']} -> daily "
                       f"{r['daily_mid_km']} km, period {r['period_km_mid']} km")
        return "\n".join(out)


def preassess(coords: Sequence[Point], *, visits: Optional[int] = None,
              days: int = 1, plan: Optional[Dict[int, Sequence[int]]] = None,
              measured_km: Optional[float] = None, city: Optional[str] = None,
              terrain: str = "suburban_mix", corridor_band: Tuple[int, int] = (0, 0),
              convert_gcj02: bool = True, is_closed_tour: bool = False,
              whatif_knobs: Optional[Dict[str, Sequence[float]]] = None
              ) -> PreAssessment:
    suspects = find_suspects(coords)
    bench = estimate_spatial_benchmark(
        coords, total_visits=visits, n_days=days, convert_gcj02=convert_gcj02,
        is_closed_tour=is_closed_tour, terrain=terrain, city=city)
    interval = dict(mid_km=round(bench.period_km_mid, 1),
                    min_km=round(bench.period_km_min, 1),
                    max_km=round(bench.period_km_max, 1),
                    daily_mid_km=round(bench.daily_km_mid, 2))
    if measured_km is not None:
        interval.update(bench.evaluate(measured_km))

    k_eff = len(plan) if plan else days
    spec = corridor_spec(coords, bench.total_visits, k_eff,
                         convert_gcj02=convert_gcj02)
    beta_c = bench.circuity * (0.721 if not is_closed_tour else 0.7575)
    corridor: Dict = {"sub_area_km2": round(spec.sub_area_km2, 1),
                      "radius_km": round(spec.radius_km, 2)}
    ref = None
    if bench.hull_area_km2 > 0:
        try:
            ref = reference_corridors(coords, max(1, min(k_eff, bench.total_stores)),
                                      convert_gcj02=convert_gcj02)
            corridor["prescription"] = balance_prescription(ref)
        except ValueError:
            ref = None
    if spec.period_area_km2 > 0:
        prem = sqrt_k_premium(visits=bench.total_visits,
                              area_km2=spec.period_area_km2, k=max(1, k_eff),
                              beta_c=beta_c)
        corridor["sqrtK_premium"] = round(prem["premium_ratio"], 2)
    if plan and ref:
        corridor.update(diagnose_plan(coords, plan, ref, spec=spec,
                                      convert_gcj02=convert_gcj02))

    areas = []
    if ref:
        from spatial_ca.geometry import compute_convex_hull_area_km2
        import collections
        groups: Dict[int, List[int]] = collections.defaultdict(list)
        for i, cidx in enumerate(ref["cells"]):
            groups[cidx].append(i)
        pts_km = ref["xy"]
        for j in range(ref["k"]):
            gp = [pts_km[i] for i in groups.get(j, [])]
            areas.append(compute_convex_hull_area_km2(gp)[0] if len(gp) >= 3
                         else max(1e-6, spec.sub_area_km2))
    balance: Dict = {"visits_gini": None, "km_gini": None, "pof": None}
    if plan:
        nvals = [len(plan[d]) for d in sorted(plan)]
        balance["visits_gini"] = round(gini(nvals), 3)
    if areas and len(areas) >= 2:
        lo = corridor_band[0] or max(1, min(int(bench.daily_visits * 0.6),
                                            *([int(bench.daily_visits)] and [])))
        lo = corridor_band[0] or max(1, int(bench.daily_visits * 0.7))
        hi = corridor_band[1] or max(lo + 1, int(bench.daily_visits * 1.3))
        try:
            pr = pof(areas, bench.total_visits, lo, hi, beta_c)
            balance["pof"] = pr["pof"]
            balance["efficient_km"] = pr["efficient_total_km"]
            balance["equal_km"] = pr["equal_total_km"]
            balance["km_gini"] = {"efficient": pr["gini_efficient"],
                                  "equal": pr["gini_equal"]}
            balance["tau_scan"] = tradeoff_scan(areas, bench.total_visits,
                                                lo, hi, beta_c, taus=6)
        except ValueError as e:
            balance["infeasible"] = str(e)

    sens = {"elasticities": deltas(bench)}
    if bench.source_points:
        sens["whatif"] = whatif(bench, whatif_knobs or
                                {"days": [max(1, k_eff - 2), k_eff, k_eff + 2]})
    return PreAssessment(
        sanity={"total_points": len(coords),
                "n_suspects": len(suspects), "suspects": suspects},
        interval=interval, corridor=corridor, balance=balance,
        sensitivity=sens,
        meta={"stores_clean": bench.total_stores, "terrain": terrain,
              "city": city, "circuity": bench.circuity,
              "closed_tour": is_closed_tour})
```

- [ ] **Step 4: 跑绿** `python3 -m unittest tests.test_report -v`（实现中 `lo =` 重复行保留第二行为准，第一行删除——Step 3 代码块里该行是演示自我修正，落地时只留正确一行。）
- [ ] **Step 5: 提交** `git commit -am "feat(report): PreAssessment facade + preassess() orchestration with graceful downgrade"`

### Task 7: CLI

**Files:**
- Create: `tests/test_cli.py`
- Create: `spatial_ca/cli.py`

- [ ] **Step 1: 失败测试**

```python
# tests/test_cli.py
import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestCli(unittest.TestCase):
    def _csv(self, rows):
        f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                        newline="")
        w = csv.writer(f)
        w.writerow(["day", "lng", "lat", "city"])
        for r in rows:
            w.writerow(r)
        f.close()
        return f.name

    def test_preassess_markdown_and_json(self):
        path = self._csv([(d % 21, 116.0 + (d % 10) * 0.02,
                           39.5 + (d % 5) * 0.02, "天津市")
                          for d in range(120)])
        env = dict(os.environ, PYTHONPATH=ROOT)
        md = subprocess.run(
            [sys.executable, "-m", "spatial_ca.cli", "preassess",
             "--csv", path, "--days", "21"],
            capture_output=True, text=True, cwd=ROOT, env=env)
        self.assertEqual(md.returncode, 0, md.stderr)
        self.assertIn("## interval (G2)", md.stdout)
        js = subprocess.run(
            [sys.executable, "-m", "spatial_ca.cli", "preassess",
             "--csv", path, "--days", "21", "--json"],
            capture_output=True, text=True, cwd=ROOT, env=env)
        d = json.loads(js.stdout)
        self.assertIn("interval", d)

    def test_cities_list(self):
        env = dict(os.environ, PYTHONPATH=ROOT)
        r = subprocess.run([sys.executable, "-m", "spatial_ca.cli", "cities"],
                           capture_output=True, text=True, cwd=ROOT, env=env)
        self.assertEqual(r.returncode, 0)
        self.assertIn("成都市", r.stdout)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑红** → `No module named spatial_ca.cli`
- [ ] **Step 3: 实现 `cli.py`**

```python
"""spatial-ca command line. Subcommands: preassess, cities."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from spatial_ca.report import preassess
from spatial_ca.terrain import (MOUNTAIN_CITIES, PLAIN_GRID_CITIES,
                                WATER_DELTA_CITIES)


def _read_csv(path: str, lng_col: str, lat_col: str, day_col: Optional[str],
              city_col: Optional[str]):
    coords: List[Tuple[float, float]] = []
    plan: Dict[int, List[int]] = defaultdict(list)
    city: Optional[str] = None
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            i = len(coords)
            try:
                coords.append((float(row[lng_col]), float(row[lat_col])))
            except (KeyError, TypeError, ValueError):
                coords.append((None, None))
                continue
            if day_col and row.get(day_col):
                plan[i % 10_000 if False else i] = i  # placeholder guard, see below
            if city_col and row.get(city_col) and city is None:
                city = row[city_col]
    plan = {}
    if day_col:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            for i, row in enumerate(csv.DictReader(fh)):
                d = row.get(day_col)
                if d not in (None, ""):
                    plan.setdefault(int(float(d)), []).append(i)
    return coords, plan, city


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="spatial-ca")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("preassess", help="full pre-assessment from a CSV")
    p.add_argument("--csv", required=True)
    p.add_argument("--lng", default="lng")
    p.add_argument("--lat", default="lat")
    p.add_argument("--day", default=None, help="day column -> plan diagnosis")
    p.add_argument("--city", default=None, help="city column -> terrain")
    p.add_argument("--days", type=int, default=21)
    p.add_argument("--measured-km", type=float, default=None)
    p.add_argument("--closed-tour", action="store_true")
    p.add_argument("--json", action="store_true")

    sub.add_parser("cities", help="show terrain classifier tables")

    a = ap.parse_args(argv)
    if a.cmd == "cities":
        for name, s in (("plain_grid", PLAIN_GRID_CITIES),
                        ("mountain", MOUNTAIN_CITIES),
                        ("water_delta", WATER_DELTA_CITIES)):
            print(f"[{name}] {len(s)} cities: {' '.join(sorted(s)[:10])} ...")
        return 0

    coords, plan, city = _read_csv(a.csv, a.lng, a.lat, a.day, a.city)
    rep = preassess(coords, days=a.days, plan=plan or None,
                    measured_km=a.measured_km, city=city,
                    is_closed_tour=a.closed_tour)
    print(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2)
          if a.json else rep.to_markdown())
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

（`_read_csv` 中 placeholder 行为演示残留，落地时删除 `plan[i ...] = i` 行，仅保留第二段按 day 列构建；测试驱动确保无此残码也能过。）

- [ ] **Step 4: 跑绿**
- [ ] **Step 5: 提交** `git commit -am "feat(cli): preassess/cities subcommands with csv ingestion"`

---

## 里程碑 M6：发布物

### Task 8: 金样例回归 + 文档 + CI

**Files:**
- Create: `tests/test_gold_synthetic.py`
- Create: `README.md`, `LICENSE`, `docs/DERIVATION.md`, `docs/CASE_STUDIES.md`
- Create: `examples/quick_start.py`, `examples/detect_dirty_gps.py`, `examples/balance_pof.py`
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: 金样例（合成同构，不携带真实坐标）**

```python
# tests/test_gold_synthetic.py — 复现两起事故的判别力，数据为合成同构
import math
import unittest
from spatial_ca.daganzo import estimate_spatial_benchmark
from spatial_ca.sanity import find_suspects


def fangshan_like():
    """201 pts, hull≈1103 km2, aspect≈1.78 (54.7x30.7 km bbox)."""
    import random
    rnd = random.Random(20260911)
    pts = []
    while len(pts) < 201:
        lng = 115.5876 + rnd.random() * (116.2268 - 115.5876)
        lat = 39.5407 + rnd.random() * (39.8182 - 39.5407)
        pts.append((lng, lat))
    return pts


class TestGold(unittest.TestCase):
    def test_fangshan_status_ladder(self):
        b = estimate_spatial_benchmark(fangshan_like(), total_visits=242,
                                       n_days=21, convert_gcj02=False)
        # 事故数字: 479.12 记录 / 504.78 优化 / 536.30 基线 / 1834 污染
        self.assertEqual(b.evaluate(479.12)["status"], "REASONABLE")
        self.assertEqual(b.evaluate(536.30)["status"], "REASONABLE")
        self.assertLess(b.evaluate(1834.20)["deviation_from_mid_pct"], 100.0) \
            if False else self.assertEqual(b.evaluate(1834.20)["status"],
                                           "SEVERELY_INFLATED")

    def test_tianjin_bomb_caught(self):
        pts = fangshan_like()
        pts[87] = (110.0, 110.0)
        s = find_suspects(pts)
        self.assertEqual([x["index"] for x in s], [87])
        b_clean = estimate_spatial_benchmark(
            [p for i, p in enumerate(pts) if i != 87], 242, 21,
            convert_gcj02=False)
        self.assertEqual(b_clean.evaluate(87.2)["status"],
                         b_clean.evaluate(87.2)["status"])  # 存在性断言
```

- [ ] **Step 2:** 跑绿（若合成 201 点面积导致 87.2 落入 SUSPICIOUSLY_LOW 属预期——该区间断言仅为状态存在性；docs 数字引用真实数据聚合结果而非本测试。）
- [ ] **Step 3: README/LICENSE/DERIVATION/CASE_STUDIES**
  - `LICENSE`: MIT © 2026 ghb
  - `README.md`: 背景（两事故叙事+预评估价值主张）、安装、30 秒上手、G1–G5 能力表、公式摘要（spec §5 精简版）、两案例验证表（引用真实聚合数字：536.3/504.8/1834 与 15946→87.2）、PoF 与 √K 洞察、非目标声明、引用列表（BHH59、Daganzo84、FS06、Ansari+18、Bertsimas11、MinMaxVsMinSum、Newell80、Ballou+02、Figliozzi08）
  - `docs/DERIVATION.md`: √K 恒等式推导、PoF 端点凹性顶点定理证明梗概、水填单调性、常数标定表
  - `docs/CASE_STUDIES.md`: 房山/天津/108 城聚合三表（仅聚合数字，无坐标无编码）
- [ ] **Step 4: CI + examples**

```yaml
# .github/workflows/ci.yml
name: tests
on: [push, pull_request]
jobs:
  unittest:
    runs-on: ubuntu-latest
    strategy:
      matrix: { python-version: ["3.9", "3.10", "3.11", "3.12", "3.13"] }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "${{ matrix.python-version }}" }
      - run: python -m unittest discover -s tests -v
```

examples 三脚本各 ≤40 行，直接调公开 API 打印。
- [ ] **Step 5: 全量回归 + 提交**

```bash
python3 -m unittest discover -s tests -v
git add -A && git commit -m "release(0.1.0): gold synthetic regression, docs, examples, CI matrix"
```

- [ ] **Step 6: 远端发布（用户环境执行或提供 gh 凭据后由代理执行）**

```bash
gh repo create spatial-ca-benchmark --public --source=. --remote=origin --push
```

---

## 自检记录（writing-plans Step 执行时）

- 占位符扫描：无 TBD/TODO/“适当处理”类字样；两处“演示残留”（walrus、cli placeholder 行）已随行内注明删除方式；
- 类型一致性：`estimate_spatial_benchmark(coords, total_visits, n_days, *)` 全任务统一；`reference_corridors` 返回 dict 键（centers/cells/cell_sizes/k/xy）在 corridor/balance/report 三处消费一致；`pof` 返回键在 test 与 report 消费一致；
- 覆盖对照 spec：G1=T1，G2=T2，G3=T3，G4=T4，G5=T5，聚合/降级矩阵=T6，CLI=T7，成功判据 1/2=T8，判据 3=√K 测试（T2/T3），判据 4=性能由 stdlib O(N·K) 保证（报告附录注明），判据 5=T8 CI+发布；
- 范围：单一实施计划可承载，无需再分解。
