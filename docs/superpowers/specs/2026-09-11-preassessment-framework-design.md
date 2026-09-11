# spatial-ca-benchmark 设计文档 v2.1（评审修订版）

> 状态：**评审后修订**（v2.0 经五人格并行评审判"密集分支验收路径不合理"，v2.1 按收敛意见修订；v1.x"参考带+拒答"叙事作废，见 §10）
> 上位契约：`docs/MEASUREMENT_CONTRACT.md`（措辞分级、溯源、留痕继续有效；C7-V2.2 拒答条款的取代见 §9 Contract Delta）

## 1. 背景

外勤片区管理需要一个**不依赖路网、不依赖求解器**的物理尺度基准：给定门店分布与拜访频次，"平均每天要跑多少公里"在几何上应是多少。用途：①片区工作量定标；②跨销售 workload 同尺比较；③上报里程数量级证伪（秒级）。推动案例：房山上报 1834 km（计划口径真值 536 km）需秒级证伪；广州 10 条周访线需同一模型出数。

## 2. 目标与输入面（v2.1 诚实化）

**核心产出 = 一个数**：`daily_km`（及 `monthly_km = daily_km × K`），闭式、纯几何、一次算出。

**输入面（完整列举，评审 RevCoh-M1 修订）**：
1. 门店坐标 + `source_crs ∈ {WGS84, GCJ02, BD09, UNKNOWN}` 声明；
2. 每店月访问次数（仅总数 V 时打 `ASSUMED_UNIFORM_VISIT_DENSITY` 标）；
3. `available_workdays = K`（契约 C5 绑定工作日，禁传日历日）；
4. **可选交互输入**：飞点裁决 `confirm_drop/confirm_keep`（契约 C8 强制，未裁决即阻断）；
5. **可选 c 覆盖**：用户抽样段距离（**即里程衍生物**，显式声明、`c_source` 留痕；**验收评估期禁用**，评审 RevAdv-5 防火墙）。

**不是输入**：每日分配、求解器结果。不做预测、不做训练、不做时间切分。真值只用于验收。

**次要产出**：卫生门（炸弹拦截留痕、CRS 阻断、退化提示）。措辞定位（RevScope 修订）：卫生门可一票否决 km 输出（C8 fail-closed），故在输出契约中是一等 gate 字段，但**不参与估计计算**。

## 3. 模型

β=0.7124（BHH 主项，provenance 携带 `beta_source=BHH1959/Applegate2006`、`beta_confidence="uniform-asymptotic, transfer error unquantified"`，评审 RevAdv-2）；c=城市先验（LOW 置信，验收冻结 c=1.29 并写入 §5 冻结文本）。

### 3.1 稀疏 regime（f=V/N ≤ 2.0）：日片区互斥
`monthly = β·c·√(V·A)`，`daily = monthly/K`。
表述纪律（RevCorr-M5）：**单点经验**（房山 f=1.2，V≈K² 巧合已自认），隐含**均匀分区假设**（日片区面积≈A/K 且互斥），未声明前不得称"已验证"。

### 3.2 密集 regime（f ≥ 3.0）：稀释连续统（**单一冻结规则**）
`monthly = β·c·√K·∫√m(x)dx`，`daily = monthly/K`。m = 月访问密度场（每 km² 访问数）。
**积分定义冻结**（RevCorr-C2/RevFeas-C2，全部实现细节入冻结文本）：
- 场表示：直方图网格，cell = **中位最近邻距 medNN**（唯一规则 R1；R2/R3 删除——仿真证 R2≈R3≈√(VA) 即已证伪的 M2 端元，三规则实为 3× 量值旋钮）；
- 积分域：门店凸包；跨界格按零面积稀释（格内质量/格面积）；
- 归一化：m 单位 = 访问数/km²；
- 退化声明：均匀场精确退化 √(VA)；合并格单调增 ∫√m（Jensen 凹性）；细网格极限→0；
- 成团失明声明（RevFeas-m8）：`ASSUMED_UNIFORM_VISIT_DENSITY` 下 ∫√m 对成团完全失明（成团性≈3× 杠杆），密集+均匀假设时输出措辞降级为"稀释参照"。

### 3.3 regime 边界政策（RevCorr-C1/RevAdv-3 修订）
f∈(2.0, 3.0) = **UNRELIABLE_TRANSITION**：两分支月总差 √K·r 倍（实测≈2.3–4.7×），不做平滑混合（M5 fudge 教训），但**必须**：
- 输出 `regime_margin = monthly_dense / monthly_sparse`（定义=两分支月总比，§4 契约字段）；
- transition 带内 `daily_km` 取稀疏分支值并挂 `transition_flag=True` + 措辞"regime 边界不可靠，数值仅供量级参考"；
- 预注册阈值敏感性检验：f∈[1.8,3.2] 扫描输出跳变幅度，随 v0.2.0 发布。

### 3.4 适用下限（RevCorr-M4）
密集分支要求 `V/K ≥ 10`（日稀释店数下限，BHH 连续统与小 n √ 律双重失效边界，契约 C-CONST）；不满足 → `SMALL_N_BELOW_FLOOR` 标 + 措辞降级。

## 4. 输出契约（v2.1 补字段）

```
EstimateResult:
  daily_km, monthly_km
  regime: sparse_partitioned | dense_dilution | UNRELIABLE_TRANSITION
  regime_margin            # 两分支月总比（边界治理字段，RevCorr-C1）
  transition_flag, small_n_floor_flag
  band: [lo, hi]           # 政策带；密集 regime 额外挂 model_form_uncertainty
                           # （模型形式散布 ~2×，经验乘子，非统计CI；RevCorr-M3）
  provenance: {beta, beta_source, beta_confidence, c, c_source, c_confidence,
               c_sample_size, cell_rule:"R1_medNN_frozen", calibration_version}
  assumptions: [...]
  hygiene: {gate, dropped_invalid, suspects, crs_status}   # 一等 gate，不参与计算
```
band.py 职责修订（RevScope-Minor）：**纯乘子外壳**，mid 来自 estimate.py；删除 band.py 内部点估计路径与 thin-widening（与密集主导误差源正交）；拒答分支从 report.py 移除（v2.1 起密集出数）。

## 5. 验收判据（v2.1 重写，预注册冻结 2026-09-11）

**冻结文本**：cell 规则 = R1(medNN)，c = 1.29（来源 terrain.py city_prior，LOW），验收期禁用 c 覆盖与 confirm 交互。

1. **单次冻结运行**（广州 10 线，baseA 口径）：如实报告命中率。**已知结果：7/10**（失败 08=2.37、11=2.01、10=1.34，全高估方向）。**该结果不触发任何规则更换**（RevFeas-C1/RevCoh-C1：换规则=事后选择=过拟合，与冻结日志纪律同罪）。
2. **v0.2.0 发布门 = SP 锚协议（log 判据乙）+ 新鲜留出集**：
   - 验收集 = **从未触碰的密集线**（新城市或新周期；广州 10 线已烧毁，只作 dev）；
   - P1: SP 可达优化里程 ∈ 政策带 ≥8/10；P2: 判别一致率（baseA/SP≥1.2 → ABOVE；≤1.05 → CONSISTENT）≥9/10；
   - 带符号偏差检验（RevAdv-4）：报告误差方向分布，|·| 不抹方向；
   - 不达标 → 如实发布失败报告，v0.2.0 不发，不放宽、不回填。
3. 房山回归：est ∈ 536/505 的 ±30%（口径=计划-on-OSM，见 §5.4）；1834 仍 STRONGLY_INCONSISTENT。
4. 天津回归：(110,110) 拦截且留痕。
5. **删除分层判据后门**（RevScope-Major/RevCoh-C1）：不存在"按线型分层 30%/8-of-10"选项。

### 5.4 真值口径表（RevCoh-M2 修订，预注册不允许留白）
| 名称 | 口径 | 用途 |
|---|---|---|
| baseA | 人类计划 + OSM 路网逐日最优排序 | 验收判据 1 的 true |
| 536/505 | 房山 baseA / SP 优化值（同口径） | 回归判据 3 |
| 1834 | 上报里程（污染输入） | 证伪用例 |
| SP | 求解器可达优化里程 | P1/P2 锚 |

## 6. 架构

```
spatial_ca/
  geometry.py   CRS 清洗/留痕/凸包/投影/最近邻（stdlib）
  density.py    月访问密度场 + ∫√m 冻结积分（新）
  estimate.py   daily_km/monthly_km 主入口 + regime 路由 + 边界政策（新）
  band.py       纯乘子外壳（mid 外源）+ 密集 model_form_uncertainty
  sanity.py     卫生门（一等 gate，不参与计算）
  report.py     EstimateResult 组装（拒答分支已移除）
  terrain.py    城市→c 先验
```

## 7. 非目标

不是优化器；不排路线/排班；不做统计置信区间；不做绝对性能承诺；不靠调宽带宽吞结构性错误；加权密度=0.3、公平政策代价=0.4（版本归属唯一表述，RevCoh-M3）。

## 8. 版本路线

- v0.1.0（已发布）：稀疏出数 + 密集拒答。**v0.2.0 起取代**（破坏性变更声明见 §9）。
- v0.2.0：本设计；发布门 = §5.2 新鲜留出 SP 锚协议全过。
- v0.3 / v0.4：加权密度 / 公平政策代价。

## 9. Contract Delta（RevScope-Major/RevCoh-M4 修订，显式作废清单）

| 契约条款 | v2.1 处置 |
|---|---|
| C7-V2.2 密集拒答（NOT_ASSESSED_DENSE_VISIT_REGIME, band=None） | **作废**，由 §3.2 密集出数 + §4 model_form_uncertainty 取代；CHANGELOG 留痕 |
| C7-V2.2 "district decomposition 为 0.2 正解" | **作废**（仿真证星期几片区模型 1/10，稀释连续统更符合实测）；0.2 改为稀释连续统 |
| C10 留出协议 | **延续并加严**：验收集必须新鲜（广州 10 线降级为 dev） |
| C2 0.3.0 VisitDemand | 不受影响 |
| C5 K 语义 | 升为 load-bearing（密集月总∝√K），§2 已绑定 available_workdays |
| C8 fail-closed | 不受影响（卫生门一等 gate） |

下游迁移：依赖 NOT_ASSESSED_* 状态的调用方在 v0.2.0 收到 `regime`+`model_form_uncertainty` 替代字段；CHANGELOG 标注破坏面。

## 10. 修订记录

| 版本 | 日期 | 内容 |
|---|---|---|
| v1.0–v1.4 | 2026-09-11 | 初版至广州留出证伪 |
| v2.0 | 2026-09-11 | 目标修正（核心产出=日均估计）；密集出数；拒答废除 |
| v2.1 | 2026-09-11 | **五人格评审修订**：R2/R3 删除（3× 旋钮/收敛已证伪端元）、积分定义冻结、边界 UNRELIABLE_TRANSITION+regime_margin 入契约、V/K≥10 下限、输入面诚实化（裁决/c 覆盖为声明输入）、验收重写（单次冻结运行如实报 7/10 + 新鲜留出 SP 锚门）、删除分层判据后门、真值口径表、band 纯外壳、Contract Delta 显式作废清单、β/c 溯源对称化 |
