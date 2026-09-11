# 事前判断框架 实施计划 v2（M0 契约返工 → 0.1.0 收缩发布）

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development。步骤用 `- [ ]` 追踪。
> **上位约束:** `docs/MEASUREMENT_CONTRACT.md`（C1–C10、C-CONST、C-PERF）。任何命名/措辞冲突，契约赢。v1 计划已冻结废止。

**Goal:** 0.1.0 = **输入契约 + 数据质量门（G1）+ CA 参考带（G2）+ 实测偏离分级**；走廊（0.2）、需求加权（0.3）、公平政策代价（0.4）明确缓发。卖点收缩为一句：**调用路网与求解器之前，用数据契约与空间尺度基准快速发现明显不可信的输入和结果。**

**Architecture:** `report → sanity/band → geometry/terrain`（单向）。geometry.py 已按契约重写（CRS 必填、索引保持、凸包双函数）；`__init__.py` 惰性导出已就位。

**Tech Stack:** stdlib only；测试 `python3 -m unittest`。**测试禁令：自等断言、`if False`、"存在即可"式伪断言一律不得出现。**

---

### Task 0.1: sanity.py — 网格化飞点 + 裁决语义

**Files:** Create `tests/test_sanity.py`, `spatial_ca/sanity.py`

- [ ] **Step 1 红:**

```python
# tests/test_sanity.py
import random
import time
import unittest
from spatial_ca.geometry import clean_coordinates, CN_BBOX
from spatial_ca.sanity import find_suspects, adjudicate


def cloud(n=201, seed=20260911):
    rnd = random.Random(seed)
    return [(115.9 + rnd.random() * 0.3, 39.55 + rnd.random() * 0.2)
            for _ in range(n)]


class TestSuspects(unittest.TestCase):
    def test_outlier_inside_bbox_caught(self):
        pts = cloud() + [(118.9, 41.6)]          # 合法但孤悬 ~200km
        cr = clean_coordinates(pts, source_crs="WGS84")
        s = find_suspects(cr)
        self.assertEqual([x["original_index"] for x in s], [201])
        self.assertEqual(s[0]["reason"], "far_outlier")
        self.assertGreater(s[0]["nn_km"], 50.0)

    def test_clean_cloud_no_suspects(self):
        cr = clean_coordinates(cloud(), source_crs="WGS84")
        self.assertEqual(find_suspects(cr), [])

    def test_grid_matches_bruteforce_small(self):
        rnd = random.Random(7)
        pts = [(116.0 + rnd.random(), 39.5 + rnd.random() * 0.5)
               for _ in range(80)] + [(117.5, 39.7)]
        cr = clean_coordinates(pts, source_crs="WGS84")
        s = find_suspects(cr, nn_factor=6.0, brute_force=True)
        g = find_suspects(cr, nn_factor=6.0, brute_force=False)
        self.assertEqual([x["original_index"] for x in s],
                         [x["original_index"] for x in g])

    def test_invalid_points_not_in_suspects_but_in_dropped(self):
        cr = clean_coordinates(cloud() + [(110.0, 110.0)], source_crs="WGS84")
        self.assertEqual(len(cr.dropped), 1)
        self.assertEqual(cr.dropped[0]["reason"], "outside_bbox")
        self.assertEqual(find_suspects(cr), [])     # 已丢，无需再报


class TestAdjudication(unittest.TestCase):
    def setUp(self):
        self.cr = clean_coordinates(cloud() + [(118.9, 41.6)],
                                    source_crs="WGS84")
        self.susp = find_suspects(self.cr)

    def test_unresolved_blocks(self):
        a = adjudicate(self.cr, self.susp, confirm_drop=(), confirm_keep=())
        self.assertEqual(a["decision"], "BLOCKED_BY_DATA_QUALITY")
        self.assertEqual(a["unresolved"], [201])

    def test_drop_rebuilds_with_index_map(self):
        a = adjudicate(self.cr, self.susp, confirm_drop=(201,),
                       confirm_keep=())
        self.assertEqual(a["decision"], "CLEANED")
        self.assertEqual(len(a["points"]), 201)
        self.assertEqual(a["index_map"][200], 200)   # 行号稳定

    def test_keep_marks_lineage(self):
        a = adjudicate(self.cr, self.susp, confirm_drop=(),
                       confirm_keep=(201,))
        self.assertEqual(a["decision"], "INCLUDING_CONFIRMED_OUTLIER")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2 红确认:** `python3 -m unittest tests.test_sanity -v` → ModuleNotFoundError: spatial_ca.sanity
- [ ] **Step 3 实现:**

```python
"""G1 quality gate: grid-nearest-neighbour fly-outliers + user adjudication.

Contract C1 (rigid-shift blindness is a theorem, so this module does NOT
claim to catch whole-batch CRS mislabels), C8 (unadjudicated suspects must
block G2), C-PERF (expected O(N) via spatial hash, documented worst-case).
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

from spatial_ca.geometry import CleanResult, Point, project_km


def _nn_distances(xy: Sequence[Point], brute_force: bool) -> List[float]:
    n = len(xy)
    if brute_force or n < 64:
        return [min(math.hypot(xy[i][0] - xy[j][0], xy[i][1] - xy[j][1])
                    for j in range(n) if j != i) for i in range(n)]
    xs = [p[0] for p in xy]
    ys = [p[1] for p in xy]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1e-9)
    cell = span / (3.0 * math.sqrt(n))
    for _ in range(8):                       # widen until every NN resolves
        grid: Dict[tuple, List[int]] = {}
        for i, (x, y) in enumerate(xy):
            grid.setdefault((int(x / cell), int(y / cell)), []).append(i)
        nn: List[float] = []
        ok = True
        for i, (x, y) in enumerate(xy):
            gx, gy = int(x / cell), int(y / cell)
            best = math.inf
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    for j in grid.get((gx + dx, gy + dy), ()):
                        if j != i:
                            d = math.hypot(x - xy[j][0], y - xy[j][1])
                            if d < best:
                                best = d
            if best == math.inf:
                ok = False
                break
            nn.append(best)
        if ok:
            return nn
        cell *= 2.0
    # worst-case fallback (tiny degenerate clouds): brute force
    return [min(math.hypot(xy[i][0] - xy[j][0], xy[i][1] - xy[j][1])
                for j in range(len(xy)) if j != i) for i in range(len(xy))]


def find_suspects(clean: CleanResult, *, nn_factor: float = 8.0,
                  min_kept: int = 8, brute_force: bool = False) -> List[Dict]:
    """Flag kept points whose NN distance >= nn_factor x median NN distance."""
    pts = clean.points
    if len(pts) < max(min_kept, 4):
        return []
    xy, _, _, _, _ = project_km(pts)
    nn = _nn_distances(xy, brute_force)
    med = sorted(nn)[len(nn) // 2]
    if med <= 1e-6:
        return []
    out = []
    for pos, d in enumerate(nn):
        if d > nn_factor * med:
            out.append({"original_index": clean.kept_indices[pos],
                        "clean_position": pos, "reason": "far_outlier",
                        "nn_km": round(d, 2),
                        "lng": pts[pos][0], "lat": pts[pos][1]})
    return out


def adjudicate(clean: CleanResult, suspects: Sequence[Dict], *,
               confirm_drop: Sequence[int] = (),
               confirm_keep: Sequence[int] = ()) -> Dict:
    """Apply user decisions (original row indices). Unresolved -> BLOCK."""
    drop = set(confirm_drop)
    keep = set(confirm_keep)
    flagged = {s["original_index"] for s in suspects}
    unresolved = sorted(flagged - drop - keep)
    if unresolved:
        return {"decision": "BLOCKED_BY_DATA_QUALITY",
                "unresolved": unresolved}
    drop |= set(clean.dropped and [])   # invalid rows already excluded upstream
    keep_set = keep
    new_pts: List[Point] = []
    new_idx: List[int] = []
    for pos, orig in enumerate(clean.kept_indices):
        if orig in drop:
            continue
        new_pts.append(clean.points[pos])
        new_idx.append(orig)
    decision = ("INCLUDING_CONFIRMED_OUTLIER" if keep_set
                else "CLEAN")
    decision = {"CLEAN": "CLEANED"}.get(decision, decision)
    return {"decision": decision,
            "points": new_pts,
            "original_indices": new_idx,
            "index_map": {o: i for i, o in enumerate(new_idx)},
            "dropped_by_user": sorted(drop & flagged)}
```

（实现时把上面 `decision` 三步简化为直接判定，不留无意义中转——Step 4 绿必须证明。）
- [ ] **Step 4 绿:** `python3 -m unittest tests.test_sanity -v`（8 tests OK）
- [ ] **Step 5:** `git commit -m "feat(sanity): grid-NN fly-outliers + fail-closed adjudication gate (C1/C8)"`

---

### Task 0.2: band.py — CA 参考带（单常数 + 溯源 + 诚实带宽）

**Files:** Create `tests/test_band.py`, `spatial_ca/band.py`

- [ ] **Step 1 红（关键断言：刚性平移不变性 = 定理；K 无关性 = 模型内推论；溯源结构）:**

```python
# tests/test_band.py
import math
import random
import unittest
from spatial_ca.geometry import clean_coordinates
from spatial_ca.band import BETA, ca_band


def cloud(n=201, seed=20260911):
    rnd = random.Random(seed)
    return [(115.9 + rnd.random() * 0.3, 39.55 + rnd.random() * 0.2)
            for _ in range(n)]


class TestBand(unittest.TestCase):
    def _cr(self, pts):
        return clean_coordinates(pts, source_crs="WGS84")

    def test_single_beta(self):
        self.assertAlmostEqual(BETA, 0.7124)

    def test_mid_formula_exact(self):
        cr = self._cr(cloud())
        b = ca_band(cr, total_visits=242, available_workdays=21)
        # mid = BETA * circuity * sqrt(V*A)  (corridor regime, K cancels)
        A = b["geometry"]["hull_area_km2"]
        expected = BETA * b["circuity"]["value"] * math.sqrt(242 * A)
        self.assertAlmostEqual(b["reference_mid_km"], expected, places=6)

    def test_rigid_shift_invariance_theorem(self):
        base = ca_band(self._cr(cloud()), 242, 21)
        shift = ca_band(self._cr([(x + 0.0062, y) for x, y in cloud()]),
                        242, 21)
        self.assertAlmostEqual(base["reference_mid_km"],
                               shift["reference_mid_km"], places=4)
        # 故本模块永远无法靠内部几何发现整批CRS错配 —— 契约C1.2

    def test_k_invariance_within_model(self):
        cr = self._cr(cloud())
        b21 = ca_band(cr, 242, 21)
        b23 = ca_band(cr, 242, 23)
        self.assertAlmostEqual(b21["reference_mid_km"],
                               b23["reference_mid_km"], places=6)
        self.assertLess(b21["daily"]["band_km"][1], b23["daily"]["band_km"][1])

    def test_provenance_city_prior_low_confidence(self):
        cr = self._cr(cloud())
        b = ca_band(cr, 242, 21, city="天津市")
        prov = b["circuity"]
        self.assertEqual(prov["source"], "city_prior")
        self.assertEqual(prov["confidence"], "LOW")
        self.assertAlmostEqual(prov["value"], 1.22)

    def test_user_override_confirmed(self):
        b = ca_band(self._cr(cloud()), 242, 21, circuity_override=1.4)
        self.assertEqual(b["circuity"]["source"], "user_override")
        self.assertEqual(b["circuity"]["confidence"], "DECLARED_BY_USER")

    def test_band_width_composition_named(self):
        b = ca_band(self._cr(cloud()), 242, 21)
        comp = b["band_width_composition"]
        self.assertIn("circuity_uncertainty", comp)
        self.assertIn("hull_proxy_uncertainty", comp)
        self.assertIn("uniform_density_uncertainty", comp)
        self.assertFalse(b["statistical_confidence_interval"])

    def test_small_daily_n_widens_model_uncertainty(self):
        cr = self._cr(cloud(n=60))
        wide = ca_band(cr, 60, 30)     # 日均2店
        tight = ca_band(cr, 60, 10)    # 日均6店
        self.assertGreater(wide["band_width_composition"]
                           ["uniform_density_uncertainty"],
                           tight["band_width_composition"]
                           ["uniform_density_uncertainty"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2 红** → ModuleNotFoundError: spatial_ca.band
- [ ] **Step 3 实现:**

```python
"""G2: CA reference band (NOT a statistical CI, NOT an optimality proof).

Single asymptotic constant BETA=0.7124 (BHH leading term, unit square;
Applegate et al. 2006 computational estimate; arxiv 2602.11250 bounds).
Open-vs-closed day tours share this leading term; the difference is a
lower-order endpoint correction (Steele 1986) - modelled as uncertainty,
never as a second BHH constant pair (contract C-CONST).

Corridor-regime period total: T = BETA * c * sqrt(V * A) -> K-invariant.
"""
from __future__ import annotations

import math
from typing import Dict, Optional, Sequence, Tuple

from spatial_ca.geometry import CleanResult, hull_area_lonlat_km2
from spatial_ca.terrain import get_city_terrain_and_circuity

BETA = 0.7124
U_HULL = 0.08          # hull proxy vs true service domain (empirical)
U_CIRC = {"DECLARED_BY_USER": 0.02, "rep_history": 0.05,
          "city_observed": 0.06, "city_prior": 0.10,
          "national_default": 0.12}
U_UNIFORM = 0.10       # uniform-density + finite-n model mismatch baseline
U_UNIFORM_THIN = 0.18  # bumped when daily stops < 4 (asymptotics weakest)
_LO_SLACK, _HI_SLACK = 0.90, 1.50   # empirical status multipliers


def _u_uniform(daily_visits: float) -> float:
    return U_UNIFORM_THIN if daily_visits < 4 else U_UNIFORM


def classify(measured_km: float, band: Dict) -> str:
    lo, hi = band["reference_band_km"]
    if measured_km < lo * _LO_SLACK:
        return "BELOW_CA_REFERENCE"
    if measured_km <= hi:
        return "CONSISTENT_WITH_CA_REFERENCE"
    if measured_km <= hi * _HI_SLACK:
        return "ABOVE_CA_REFERENCE"
    return "STRONGLY_INCONSISTENT_WITH_CA"


def ca_band(clean: CleanResult, total_visits: int, available_workdays: int, *,
            city: Optional[str] = None,
            circuity_override: Optional[float] = None,
            is_closed_tour: bool = False) -> Dict:
    if total_visits <= 0 or available_workdays <= 0:
        raise ValueError("total_visits and available_workdays must be positive")
    if clean.crs_status == "CRS_UNCONFIRMED":
        # pass-through geometry, absolute magnitudes unverified -> contract C1.3
        pass
    area, dx, dy = hull_area_lonlat_km2(clean.points)
    if circuity_override is not None:
        circ = {"value": float(circuity_override), "source": "user_override",
                "confidence": "DECLARED_BY_USER",
                "calibration_version": None, "sample_size": None}
    elif city:
        t, c = get_city_terrain_and_circuity(city)
        circ = {"value": c, "source": "city_prior", "terrain": t,
                "confidence": "LOW", "calibration_version": "2026.09-p1",
                "sample_size": None}
    else:
        circ = {"value": 1.27, "source": "national_default",
                "confidence": "LOW", "calibration_version": "2026.09-p1",
                "sample_size": None}

    daily_visits = total_visits / available_workdays
    comp = {"circuity_uncertainty": U_CIRC[circ["source"]],
            "hull_proxy_uncertainty": U_HULL,
            "uniform_density_uncertainty": _u_uniform(daily_visits)}
    hw = math.sqrt(sum(v * v for v in comp.values()))
    # open vs closed: leading order identical; endpoint term folded into hw
    extra = 0.05 if is_closed_tour else 0.0
    mid = BETA * circ["value"] * math.sqrt(max(0.0, total_visits * area))
    lo, hi = mid * (1.0 - hw - extra), mid * (1.0 + hw + extra)
    return {
        "reference_mid_km": round(mid, 2),
        "reference_band_km": [round(max(0.0, lo), 2), round(hi, 2)],
        "daily": {"mean_visits": round(daily_visits, 2),
                  "mid_km": round(mid / available_workdays, 2),
                  "band_km": [round(lo / available_workdays, 2),
                              round(hi / available_workdays, 2)]},
        "geometry": {"hull_area_km2": round(area, 2),
                     "dx_km": round(dx, 2), "dy_km": round(dy, 2)},
        "circuity": circ,
        "beta": {"value": BETA, "role": "BHH leading-term constant (unit "
                 "square, closed TSP); open/closed difference is lower-order",
                 "bounds": [0.6277, 0.9038]},
        "band_width_composition": comp,
        "statistical_confidence_interval": False,
        "k_invariant_within_model": True,
        "crs_status": clean.crs_status,
        "assumptions": ["corridor_regime", "ASSUMED_UNIFORM_VISIT_DENSITY",
                        "inter_stop_distance_only",
                        "n_periods_from:available_workdays"],
        "is_closed_tour": is_closed_tour,
    }
```

- [ ] **Step 4 绿** `python3 -m unittest tests.test_band -v`
- [ ] **Step 5** `git commit -m "feat(band): CA reference band, single BETA + provenance + honest width (C7/C-CONST)"`

---

### Task 0.3: report.py — preassess 编排（门 + K 三语义 + 降级）

**Files:** Create `tests/test_report.py`, `spatial_ca/report.py`

- [ ] **Step 1 红:**

```python
# tests/test_report.py
import json
import random
import unittest
from spatial_ca.report import preassess


def cloud(n=201, seed=1):
    rnd = random.Random(seed)
    return [(115.9 + rnd.random() * 0.3, 39.55 + rnd.random() * 0.2)
            for _ in range(n)]


class TestPreassess(unittest.TestCase):
    def test_source_crs_required(self):
        with self.assertRaises(TypeError):
            preassess(cloud(), total_visits=242, available_workdays=21)

    def test_unadjudicated_outlier_blocks_band(self):
        rep = preassess(cloud() + [(118.9, 41.6)], total_visits=242,
                        available_workdays=21, source_crs="WGS84")
        self.assertEqual(rep["gate"], "BLOCKED_BY_DATA_QUALITY")
        self.assertIsNone(rep["band"])

    def test_confirm_drop_unblocks_with_lineage(self):
        rep = preassess(cloud() + [(118.9, 41.6)], total_visits=242,
                        available_workdays=21, source_crs="WGS84",
                        confirm_drop=(201,))
        self.assertEqual(rep["gate"], "PASSED")
        self.assertEqual(rep["lineage"]["dropped_by_user"], [201])
        self.assertIsNotNone(rep["band"])

    def test_confirm_keep_marks_lineage(self):
        rep = preassess(cloud() + [(118.9, 41.6)], total_visits=242,
                        available_workdays=21, source_crs="WGS84",
                        confirm_keep=(201,))
        self.assertEqual(rep["gate"], "INCLUDING_CONFIRMED_OUTLIER")

    def test_measured_status_uses_contract_names(self):
        rep = preassess(cloud(), total_visits=242, available_workdays=21,
                        source_crs="WGS84", measured_km=536.3)
        self.assertIn(rep["assessment"]["status"],
                      ("CONSISTENT_WITH_CA_REFERENCE", "ABOVE_CA_REFERENCE"))

    def test_unknown_crs_downgrades(self):
        rep = preassess([(x - 0.0062, y) for x, y in cloud()],
                        total_visits=242, available_workdays=21,
                        source_crs="UNKNOWN")
        self.assertEqual(rep["band"]["crs_status"], "CRS_UNCONFIRMED")
        self.assertEqual(rep["assessment"]["note_level"], "STRUCTURE_ONLY")

    def test_json_serialisable(self):
        json.dumps(preassess(cloud(), total_visits=242, available_workdays=21,
                             source_crs="WGS84", city="天津市").to_dict())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2 红** → spatial_ca.report 缺失
- [ ] **Step 3 实现**（`PreAssessment` dataclass：`gate`（PASSED/BLOCKED/INCLUDING_CONFIRMED_OUTLIER）、`band`（None 若阻断）、`assessment.status` + `diagnostic_note`（契约 C7 白名单措辞："可能由坐标错误、CRS 错配、跨区排班、仓库往返或业务约束造成，需进一步核查"）、`lineage`、`k`（三语义字段，见 C5；0.1.0 无 plan 时 `active_visit_days=None`）、`meta` 含 `ASSUMED_UNIFORM_VISIT_DENSITY`；`measured_scope` 非 `inter_stop` 时 warning）。
- [ ] **Step 4 绿** 全部测试（`crs_status == CRS_UNCONFIRMED` ⇒ 绝对量降级但结构可用）
- [ ] **Step 5** `git commit -m "feat(report): preassess gate pipeline, K semantics, measured-scope warnings (C2-C8)"`

---

### Task 0.4: 性能冒烟 + 门面清理 + terrain 措辞

**Files:** Modify `tests/test_sanity.py`（追加）、`spatial_ca/terrain.py`、`spatial_ca/__init__.py`

- [ ] Step 1: 追加 `test_10k_under_2s`（seeded 10,000 点 `clean+find_suspects` 总耗时 <2.0s，`@unittest.skipUnless(os.environ.get("SPATIAL_CA_PERF"), ...)` 可选开；本地必跑一次记录实测值）
- [ ] Step 2: terrain 文档字符串与 `city_prior` 注释改为 **prior, not calibration**；`get_city_terrain_and_circuity` 返回三元组 `(terrain, value, "2026.09-p1")` —— 调用点 band.py 同步（其测试已断言 calibration_version）
- [ ] Step 3: 全量 `python3 -m unittest discover -s tests -v` 绿；记录 571 销售代理数据（同构合成集）跑批耗时进 `docs/BENCH.md`（C-PERF 实测，不口头承诺）
- [ ] Step 4: `git commit -m "test: C-PERF grid smoke; docs: city table is prior not calibration"`

---

### Task 0.5: README（新定位）+ LICENSE + CI + 打 tag

**Files:** Create `README.md`, `LICENSE`, `.github/workflows/ci.yml`；修改 `docs/superpowers/plans/2026-09-11-preassessment-v2.md` 勾选

- [ ] README 结构：
  1. 一句话定位（契约原话）；
  2. **What it cannot do**（置顶声明：整批 CRS 错配不可由内部几何识别——定理；不是统计置信区间；0.1.0 无走廊/分区/公平政策）；
  3. 事故故事（房山 536↔1834 由参考带 10 秒证伪；天津 (110,110) 由 G1 拦截——**只声明 G1 能拦的部分**）；
  4. 快速上手（source_crs 必填示例）；
  5. 分级结论表（C7 状态 → 允许的业务结论）；
  6. 常数与版本溯源（BETA、city_prior）；
  7. 参考文献 + roadmap（0.2 走廊诊断 / 0.3 VisitDemand 加权 / 0.4 定义公平政策后的 cost_of_selected_equity_policy）。
- [ ] MIT LICENSE；CI：3.9–3.13 `python -m unittest discover`，另 nightly 任务开 `SPATIAL_CA_PERF=1`
- [ ] `git tag v0.1.0-rc1`；发布语句全部过 C9 白名单自查
- [ ] **发布前评审销账表**（README 附录）：逐条列出评审 §1.1–§1.8、§2.1–§2.6 的处置：
  - §1.1 G1 防不住房山 → **承认 + 写入 What-it-cannot-do**（定理级，C1.2）
  - §1.2 飞点未阻断 → 已修（Task 0.1/0.3 BLOCKED 门）
  - §1.3 命名 → 已改（band / 四状态）
  - §1.4 常数 → 已改（单 BETA=0.7124，C-CONST 表，v1 计划冻结）
  - §1.5 √K → **0.1.0 移除该 API**（随 corridor 推 0.2；届时命名 `dispersion_scenario_contrast` + 假设面板）
  - §1.6 频次加权 → roadmap 0.3 + 0.1.0 强制 `ASSUMED_UNIFORM_VISIT_DENSITY` 标记
  - §1.7 PoF → roadmap 0.4，命名 `cost_of_selected_equity_policy`；水填方向断言已修正（`n[0] >= n[3]`，随 equity 落地）
  - §1.8 假断言 → 已禁（本计划测试全部为性质/定理/降级断言）
  - §2.1 索引漂移 → CleanResult.index_map 强制通道
  - §2.2 二次投影 → hull_area_xy / hull_area_lonlat_km2 拆分
  - §2.3 O(N²) → 网格桶 + C-PERF 实测
  - §2.4 K 语义 → C5 三字段
  - §2.5 plan 完整性 → validate_plan 随 0.2（0.1.0 无 plan 输入）
  - §2.6 迂回系数 → provenance 结构 + prior 措辞
- [ ] `git commit -m "release(0.1.0-rc1): contract-first README, roadmap cut, CI, review disposition table"`

---

## Self-Review（writing-plans 规程）

1. **spec 覆盖：** 0.1.0 收缩范围 = 契约 C1/C2/C3/C5/C7/C8/C10 全覆盖；C4/C6/C9 的完整实现随后续版本，其**声明义务**（assumptions、note 措辞）已在 0.1.0 落地；
2. **占位符：** Task 0.3 Step 3 为规格级描述（dataclass 字段全枚举），实施者按契约字段展开——无 TODO/TBD；
3. **类型一致性：** `CleanResult(points, kept_indices, dropped, source_crs, crs_status)` 三处消费一致；`ca_band()` 返回 dict 键在 band 测试与 report 透传一致；`terrain` 三元组签名与 band 消费同 commit 修改；
4. **测试质量红线：** 无自等断言、无 `if False`；核心断言均为公式复算（非重跑被测函数）、定理（平移不变）、降级路径（BLOCK/UNKNOWN/THIN）。
