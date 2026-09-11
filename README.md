# spatial-ca-benchmark

> **Before you call a road network or a solver, find out quickly which inputs and results are clearly not trustworthy.**

一句话定位：**调用路网与求解器之前，用数据契约与空间尺度基准快速发现明显不可信的输入和结果。**

`spatial-ca-benchmark` 是面向单销售访销排班的无地图（mapless）事前判断工具：输入门店坐标、月拜访量与工作天数，它基于 CA（Continuous Approximation，连续近似）渐近规律给出一个"月总里程参考带"，把实测里程对照参考带分级（`BELOW / CONSISTENT / ABOVE / STRONGLY_INCONSISTENT`），并用 fail-closed 质量门强制先处理坏数据、未确认的坐标系。stdlib only，Python ≥ 3.9，零第三方依赖。

---

## 1. What it cannot do（先读这个）

按证据契约（`docs/MEASUREMENT_CONTRACT.md`）逐条声明——以下限制是**定理或评审裁决**，不是暂时没做完：

1. **整批 CRS 错配在原理上不可由内部几何识别。** 刚性平移（GCJ02↔WGS84 约 600 m 级系统偏差）不改变任何点对距离、凸包面积与形状比——仅凭点集内部几何，**不存在**任何算法能发现整批坐标标签错误。这不是本包"还没做"，是定理（C1.2）。可执行声明：`tests/test_band.py::TestBand.test_rigid_shift_invariance_theorem`（平移前后全部内部量严格不变）。因此 `source_crs ∈ {WGS84, GCJ02, BD09, UNKNOWN}` 是**必填声明**，由数据提供方担责；`UNKNOWN` 时绝对 km 全部阻断。
2. **参考带是版本化启发政策带，不是统计置信区间。** `band_method = heuristic_policy_envelope_v1`：中位估计 × 一张显式乘法系数表。输出字段 `statistical_confidence_interval = False` 永远为真值。它也不是最优性证明——带内不等于"没问题"。
3. **0.1.0 没有的东西**：走廊诊断（`reference_corridors`）、公平政策代价（`cost_of_selected_equity_policy`）、需求加权（`VisitDemand`）。当前密度假设为 `ASSUMED_UNIFORM_VISIT_DENSITY`（均匀拜访密度），该假设随每份输出出现在 `band.assumptions` 中；加权模式落地前，不对"高频店集中城区"类场景做任何定量承诺。
4. **飞点检测是精确暴力 O(N²) 最近邻（`bruteforce_v1`）。** 适用域 = **单销售 ≤ 2,000 店**（典型 100–500 店亚秒级）。更大规模请等 0.2 的可证明停止网格版（将附与本实现的等价性测试）。本版**不做任何绝对规模性能承诺**——性能数据全部是 *synthetic throughput benchmark*（合成吞吐 ≠ 真实数据最坏分布），门槛为相对基线制。
5. **它不是优化器。** 不排路线、不分组、不排班，不承诺任何可兑现的节省额。高里程只输出诊断提示"可能由坐标错误、CRS 错配、跨区排班、仓库往返或业务约束造成，需进一步核查"——禁止凭 CA 把高里程归因为"排班分组差"。
6. **小日样本不可靠。** 参考带基于 √(V·A) 渐近律，在日粒度拜访数 n < 10 处有系统性偏差（2021 年综述结论）；此时输出 `small_sample_warning = True` 并加宽政策带，但可靠性下降本身只能标注、无法修复。

## 2. 事故故事（只讲可兑现的部分）

以下两个真实场景推动了本包的 fail-closed 设计。真实数据不进公开仓库（留出协议，见 §6）；下面用同构合成集复现，数字可当场验证。

**房山：1834 km 的月度计划。** 某区域月度拜访计划上报实测总里程 1834 km。清洗 201 个门店点、扫描飞点、建带、分类——整个流程亚秒级完成，得到 `STRONGLY_INCONSISTENT_WITH_CA`：1834 km 对着 **[243.79, 422.57] km** 的参考带（中位 325.05 km）根本放不进"口径差异"的解释框架。参考带没有说错在哪里，只说了"高度疑似数据缺陷或口径错配，先查证据"——后来查实是输入缺陷。这正是它该有的作用：**证伪只要几秒，解释要靠证据。**

**天津：藏在数据里的 (110, 110)。** 一个真实数据集混入一行 `(110.0, 110.0)`——经纬度字段填反/填错产生的越界非法点。G1 不会静默吞掉它：剔除会记录在 `lineage.dropped_invalid = [201]`，并且 gate 升格为 `PASSED_WITH_INVALID_ROWS_DROPPED`——报告明示"发生过剔除"，永远不会顶着 `PASSED` 的脸面装干净。未裁决的飞点更严格：整份报告 `gate = BLOCKED_BY_DATA_QUALITY`、`band = None`，一条 km 数值都不会给。

## 3. 快速上手

```bash
pip install .          # stdlib only, Python >= 3.9
python -m unittest discover -s tests   # 自检
```

以下示例的输出均为实跑结果（Python 3.10，2026-09-11）。

**① `source_crs` 必填，正常评估**（201 店，月拜访 242 次 / 21 个工作日，天津，实测 536.3 km）：

```python
import random
from spatial_ca import preassess

rnd = random.Random(20260911)
stores = [(115.9 + rnd.random() * 0.3, 39.55 + rnd.random() * 0.2)
          for _ in range(201)]

rep = preassess(stores, total_visits=242, available_workdays=21,
                source_crs="WGS84", city="天津市", measured_km=536.3)
print(rep.to_markdown())
```

```
# Spatial pre-assessment — gate: **PASSED**

- lineage: invalid_dropped=[] user_dropped=[] kept_outliers=[] crs=CONFIRMED_WGS84
- K: available_workdays=21 active_visit_days=None
- CA reference band: **312.25 km**, envelope [234.19, 405.93] km (heuristic_policy_envelope_v1, not a statistical CI)
- assessment: ABOVE_CA_REFERENCE
  - possible causes: coordinate errors, CRS mismatch, cross-district scheduling, depot stems or business constraints - verify with road distances before concluding
```

`ABOVE_CA_REFERENCE` 允许的唯一结论是"值得路网级核查与重排评估"——不许给出"能省 XX km"之类的可兑现节省额。

**② `UNKNOWN` CRS → 结构诊断，绝对 km 全阻断**（即使传了 `measured_km` 也不评估）：

```python
rep = preassess(stores, total_visits=242, available_workdays=21,
                source_crs="UNKNOWN", measured_km=536.3)
print(rep.gate)                   # STRUCTURE_ONLY
print(rep.band)                   # None —— 绝对 km 被阻断
print(rep.assessment["status"])   # NOT_ASSESSED_CRS_UNCONFIRMED
print(rep.structural["frame_relative"])   # True —— 只有框架相对量
```

**③ 非法行不静默**（混入 `(110.0, 110.0)`，bbox 外被剔除且明示）：

```python
rep = preassess(stores + [(110.0, 110.0)], total_visits=242,
                available_workdays=21, source_crs="WGS84", city="天津市")
print(rep.gate)                        # PASSED_WITH_INVALID_ROWS_DROPPED
print(rep.lineage["dropped_invalid"])  # [201]
```

**④ 飞点必须裁决**（远处 `(118.9, 41.6)`，最近邻 310.62 km，未裁决前一律阻断）：

```python
dirty = stores + [(118.9, 41.6)]
blocked = preassess(dirty, total_visits=242, available_workdays=21,
                    source_crs="WGS84", city="天津市")
print(blocked.gate)   # BLOCKED_BY_DATA_QUALITY
print(blocked.band)   # None —— 未裁决，不给任何 km

cleaned = preassess(dirty, total_visits=242, available_workdays=21,
                    source_crs="WGS84", city="天津市", confirm_drop=(201,))
print(cleaned.gate)                        # PASSED
print(cleaned.lineage["dropped_by_user"])  # [201] —— 裁决进 lineage
```

`confirm_keep=(201,)` 则计算照常、gate 升格为 `INCLUDING_CONFIRMED_OUTLIER`，且 `band.including_confirmed_outlier = True`。

## 4. gate × status 全表（五 gate / 八 status）

### 4.1 质量门（gate，C8：G1 不过，G2 必须 fail-closed）

| gate | band | 触发条件 |
|---|---|---|
| `PASSED` | 有 | 无剔除、无保留飞点 |
| `PASSED_WITH_INVALID_ROWS_DROPPED` | 有 | 系统剔除了非法行（null/nan/bbox 外），剔除在 `lineage.dropped_invalid` 明示 |
| `INCLUDING_CONFIRMED_OUTLIER` | 有（`including_confirmed_outlier=True`） | 用户 `confirm_keep` 保留飞点 |
| `BLOCKED_BY_DATA_QUALITY` | **None** | 存在未裁决飞点（`assessment.unresolved_suspects` 列出索引） |
| `STRUCTURE_ONLY` | **None** | `source_crs = UNKNOWN`；几何只进 `structural_diagnostics`（框架相对量） |

### 4.2 状态 → 允许的业务结论（白名单照抄 C9）

| status | 允许结论 | 禁止 |
|---|---|---|
| `CONSISTENT_WITH_CA_REFERENCE` | "未发现明显不可信输入/结果；如需改进须用路网+求解器实测" | 声称"已近最优" |
| `ABOVE_CA_REFERENCE` | "值得路网级核查与重排评估" | 给出可兑现节省额 |
| `STRONGLY_INCONSISTENT_WITH_CA` | "高度疑似数据缺陷或口径错配，先查证据" | 任何归因式结论 |
| `BELOW_CA_REFERENCE` | "疑似漏访问/直线距离冒充/缺日，先查完整性" | 表扬"优于基准" |
| `REFERENCE_ONLY` | 未提供 `measured_km`：仅参考带本身可参考 | 对任何实测值下结论 |
| `NOT_ASSESSED_DATA_QUALITY_BLOCKED` | 未评估；先裁决飞点 | 任何 km 级结论 |
| `NOT_ASSESSED_CRS_UNCONFIRMED` | 未评估；先声明 `source_crs` | 任何绝对 km 结论 |
| `NOT_ASSESSED_DEGENERATE_GEOMETRY` | 未评估；共线/点数不足，无 2D 服务域可比 | 任何带级结论 |

分类阶梯（实测 m 对带 [lo, hi]，系数为经验阈值、`v1` 版本、待留出集标定）：`m < 0.90·lo` → BELOW；`m ≤ hi` → CONSISTENT；`m ≤ 1.50·hi` → ABOVE；否则 STRONGLY。

**措辞分级（C7）**：定理级内容（BHH 渐近式、刚性平移不变性、凸包面积下界、闭包内 `n ∝ 1/A`）可用"精确/不变/必然"；CA 参考带、情景对照属模型推断，只能说"在均匀密度+分区假设下""理想化对照"；迂回系数 1.22/1.27/1.29/1.35 与状态阶梯系数属经验阈值，只能说"先验""待留出集标定"。0.2 的 `dispersion_scenario_contrast` 落地后也只允许解读为"结构性上限对照"，不得解读为可实现压降。

## 5. 常数与版本溯源

**β = 0.7124（±0.001）** — BHH (1959) 渐近式主项，数值取 Applegate et al. 2006（§15 计算估计；单位正方形均匀点集**闭环** TSP）。输出三字段，界与运营带显式分离：

```python
rep.band["beta"]
# {'point_estimate': 0.7124,
#  'published_mathematical_bounds': [0.6277, 0.9038],
#  'bounds_used_in_operational_band': False,
#  'role': 'BHH leading-term constant (unit square, closed TSP); ...'}
```

解析界 [0.6277, 0.9038]（Gaudio & Jaillet 等）仅作背景，**不进运营带**。开链/闭环共享同一渐近主项，差为低阶端部项（Steele 1986 次可加泛函）——体现为闭环 `hi +0.05` 的政策加宽，**不存在第二对"BHH 常数"**（此前的 0.712–0.730 / 0.750–0.765"常数对"已撤销，见契约 C-CONST）。

**政策带系数表（`heuristic_policy_envelope_v1`，显式乘法、按迂回系数溯源分级）：**

| circuity `source` | lo × | hi × | 附注 |
|---|---|---|---|
| `user_override` | 0.88 | 1.12 | 用户声明迂回系数（`DECLARED_BY_USER`） |
| `rep_history` | 0.85 | 1.18 | 实测历史里程 |
| `city_observed` | 0.82 | 1.20 | 该市实测路网矩阵 |
| `city_prior` | 0.75 | 1.30 | 城市先验（`confidence = LOW`） |
| `national_default` | 0.75 | 1.30 | 全国缺省 1.27 |

加宽规则：日均拜访 < 4（`small_sample_warning = True`）时 lo −0.07、hi +0.15；闭环 `hi +0.05`。状态阶梯系数（0.90 / 1.50）同为 `v1` 经验阈值。

**迂回系数先验（`city_prior`，confidence = LOW，待留出集标定）**：平坦棋盘格 1.22（成都/北京/西安…）、混合近郊 1.27（缺省）、水网三角洲 1.29（广州/杭州…）、山地起伏 1.35（重庆/贵阳/兰州…）。溯源结构含 `{value, source, terrain, confidence, calibration_version, sample_size}`；`calibration_version = 2026.09-p1`（任何标定变更必须 bump 版本并在 CHANGELOG 留痕）。

## 6. 留出验证计划（C10）

- **金样例不进公开仓库**：房山、广州 02–11 实测 OSM 矩阵对账等真实样本仅在私有留出环境按同版本参数复跑；公开仓使用同构合成集 + `data_signature.json`（点数/面积/跨度/实测带内判定的聚合指纹）。
- **当前状态**：所有带系数（β 之外）均为 `heuristic_policy_envelope_v1` 启发先验，未经过任何真实样本标定。
- **升版条件**：按日粒度 n / 地形 / 形状分层（strata），在留出集上取 P10/P90 分位数标定带宽；要求真实金样例 4/4 状态判定一致后，`band_method` 才允许改名 `empirically_calibrated_reference_band`，同时 bump `calibration_version` 并在 CHANGELOG 留痕。达不到 4/4 一致就维持启发带命名，不假装"已标定"。

## 7. Roadmap

| 版本 | 内容 | 门槛 |
|---|---|---|
| **0.2** | 可证明停止的网格加速 NN（ring-expansion + 网格边界下界）；紧凑度诊断（`reference_corridors` / `diagnose_plan`）；`dispersion_scenario_contrast`（原 `sqrt_k_premium`，比值字段 `idealized_upper_contrast_ratio`，随附全部前提假设） | 网格版**必须**携带与 0.1.0 暴力版（`bruteforce_v1`）的等价性测试；情景对照只允许"结构性上限对照"解读 |
| **0.3** | `VisitDemand(store_id, coordinate, required_visits, eligible_days)` 需求加权 | 废除 `ASSUMED_UNIFORM_VISIT_DENSITY` 均匀密度假设 |
| **0.4** | `cost_of_selected_equity_policy`（公平政策代价，整数化 + rounding gap 分析） | 水填方向断言 `n[0] >= n[3]` 已定稿 |

## 8. 参考文献

- Beardwood, Halton & Hammersley (1959). *The Shortest Path Through Many Points*. — BHH 渐近定理本体。
- Applegate, Bixby, Chvátal & Cook (2006). *The Traveling Salesman Problem: A Computational Study*. §15 — β = 0.7124 的数值估计。
- Gaudio & Jaillet — 单位正方形 TSP 常数的解析界 [0.6277, 0.9038]（背景资料，不进运营带）。
- Steele (1986). *An Epsilon Lemma for Subadditive Euclidean Functionals*. — 开/闭环差为低阶端部项的依据。
- Daganzo (1984). — CVRP 分区扇区几何（若未来引入 depot stem 项将单列 depot correction 模型并引用此式）。
- Newell (1980)；Ballou, Magazine & Rao (2002). — 路网迂回系数的经验锚点。
- *Review of Length Approximations for Tours with Few Stops* (2021). — 小 n（< 10）处 √n 律系统偏差，本包以 `small_sample_warning` 标注。

## 9. 禁语清单（本 README 及一切输出中不得出现）

- ~~"全球无竞品"~~ —— 无从考证，永不写。
- ~~"理论上下界"~~ —— 参考带只有"参考带下沿/上沿"（`ca_reference_band`）。
- ~~"√K 差价"~~ —— 只有 `dispersion_scenario_contrast`（理想化对照的结构性上限比值，0.2 落地）。
- ~~"闭式 PoF"~~ —— 只有 `cost_of_selected_equity_policy`（0.4 落地）。
- ~~"已近最优"~~ —— `CONSISTENT_WITH_CA_REFERENCE` 只允许 §4.2 白名单措辞。
- ~~绝对性能承诺~~ —— 只有 *synthetic throughput benchmark* + 相对基线门槛（`docs/BENCH.md`、`tests/perf_baseline.json`）。

## 附录：0.1.0 发布销账表（V2.1 两轮评审十项裁决 → 实现 + 测试）

| # | 裁决 | 实现位置 | 测试 |
|---|---|---|---|
| ① | K 断言方向修正（日带随 K 递减；`T = K·d`） | `spatial_ca/band.py` `ca_band().daily`（`mid/K`，周期总量 K 不变） | `tests/test_band.py::TestBand.test_k_invariance_and_daily_direction` |
| ② | 0.1.0 飞点检测用精确暴力 NN；可证明停止网格推 0.2 + 等价测试 | `spatial_ca/sanity.py` `find_suspects`（O(N²) 精确 NN） | `tests/test_sanity.py::TestSuspects.test_nn_distance_is_exact`；等价性测试随 0.2 |
| ③ | 带宽 = 显式版本化政策带（系数表，废除平方和伪统计） | `spatial_ca/band.py` `ENVELOPES` / `ENVELOPE_VERSION` | `tests/test_band.py::TestBand.test_policy_envelope_explicit` |
| ④ | `UNKNOWN` CRS fail-closed（band=None、绝对 km 阻断、仅结构诊断） | `spatial_ca/report.py` branch 2；`spatial_ca/band.py` `ca_band` 拒收 | `tests/test_report.py::TestPreassess.test_unknown_crs_blocks_absolute_km`；`tests/test_band.py::TestBand.test_unknown_crs_band_blocked` |
| ⑤ | `PreAssessment` 统一 dataclass 属性访问，禁 `__getitem__` 双接口 | `spatial_ca/report.py` `PreAssessment` | `tests/test_report.py` 全文件（断言全部属性访问；`test_json_serialisable` 覆盖 `to_dict`） |
| ⑥ | 状态机完整实现、治理逻辑零临场发挥 | `spatial_ca/report.py` `preassess`（显式 branch 1/2/3） | `tests/test_report.py::TestPreassess` 全套 |
| ⑦ | invalid 剔除不静默：专属 gate + `lineage.dropped_invalid` | `spatial_ca/report.py` gate 判定段 | `tests/test_report.py::TestPreassess.test_invalid_rows_earn_their_own_gate` |
| ⑧ | `adjudicate` 死代码/双跳 decision 清除 | `spatial_ca/sanity.py` `adjudicate`（单跳 decision） | `tests/test_sanity.py::TestAdjudication`（含 `test_unknown_drop_index_blocks`、`test_conflicting_adjudication_blocks`） |
| ⑨ | BETA 拆 `point_estimate / published_mathematical_bounds / bounds_used_in_operational_band=False` | `spatial_ca/band.py` `ca_band()["beta"]` | `tests/test_band.py::TestBand.test_beta_fields_separated` |
| ⑩ | 性能 = 基线相对门槛 + synthetic throughput 命名 | `tests/test_sanity.py::TestThroughput`、`tests/perf_baseline.json`、`docs/BENCH.md` | `tests/test_sanity.py::TestThroughput.test_national_synthetic_throughput`（`SPATIAL_CA_PERF=1`）；宽松冒烟 `test_500_stores_under_5s` |

另有增量守护：`degenerate_geometry`（比值阈值，非绝对面积）→ `NOT_ASSESSED_DEGENERATE_GEOMETRY` 映射（`tests/test_band.py::test_degenerate_flag_not_swallowed / test_degenerate_diagonal_collinear / test_thin_valley_is_not_degenerate`），系评审后补强，不在十项裁决编号内。
