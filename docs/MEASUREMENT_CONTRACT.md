# 测量与证据契约 (Measurement & Evidence Contract)

> 版本: 0.1 (M0) · 2026-09-11
> 本契约是 spec 与 plan 之间的强制中间层：**任何结论若不能被本契约的条目背书，不得出现在输出、README 或 API 名称中。**
> 原则：**Evidence before Trust**（证据先于断言）。

---

## C1 坐标系：谁声明、谁验证、谁担责

1. 坐标系由**数据提供方声明**（API 必填参数 `source_crs ∈ {WGS84, GCJ02, BD09, UNKNOWN}`），框架不猜、不默认危险值。
2. **框架的不可知边界（定理级）**：整批刚性平移（GCJ↔WGS 系统性偏差 ~600m）不改变任何点对距离、凸包面积、形状比与内部几何——**仅凭点集内部几何，不存在任何算法能识别整批 CRS 标签错误**（房山事故因此不是 G1 能"检测"的对象，只能被外部证据证伪）。
3. `UNKNOWN` 时：不做任何转换，输出 `crs_status = CRS_UNCONFIRMED`，参考带结论降级为"几何结构分析（米级绝对位置未确认）"。
4. 外部验证通道（非本包内置，写入 docs）：抽查若干已知门店用地图 App 反查偏移方向；有历史实测里程序列时做比例一致性检验。
5. 每条输出携带 `crs_status` 与 `lineage`（dropped 索引、转换类型、版本）。

## C2 点的语义：门店还是拜访事件

- 输入点默认语义 = **唯一门店**；`required_visits` 为门店属性（频次），不允许把同一门店按拜访次数重复投点（重复点会摧毁凸包与最近邻统计）。
- 0.1.0 仅接受 `coords + total_visits`，此时隐含假设 **ASSUMED_UNIFORM_VISIT_DENSITY** 必须出现在输出 meta 中。
- 0.3.0 引入 `VisitDemand(store_id, coordinate, required_visits, eligible_days)` 后，密度按带权空间分布积分，废除均匀假设。

## C3 里程语义： measured_total_km 必须声明口径

调用方提供实测里程时必须声明是否包含：仓库/家出发腿（stem）、店间距离、午休折返、日终返程。参考带默认建模**纯店间开链巡访**；口径不齐时先对齐再比较，报告输出 `measured_scope` 字段供审计。

## C4 开链/闭环的业务定义

- 开链 = 当日首店起点、末店终点，无固定归位（外勤访销常态）。
- 闭环 = 必须回到仓库/家（配送车队常态）。
- **常数依据见 C-CONST（附录）**：开环与闭环共享同一渐近主项 β，差为低阶端部项；不得用两对"BHH 常数"冒充主项差异。

## C5 K 的语义：三种天数必须区分

| 字段 | 含义 | 用于 |
|---|---|---|
| `calendar_period_days` | 周期总天数 | 报告叙事 |
| `available_workdays` | 可工作天数 | CA 参考带的 K |
| `active_visit_days` | 实际有计划的天数 | 逐日诊断的分母 |

三者不相等时（请假、空白日）输出显式差值，禁止 `k_eff = len(plan)` 式静默吞日。

## C6 频次空间分布

见 C2。均匀频次假设下的任何偏差结论必须挂 `ASSUMED_UNIFORM_VISIT_DENSITY` 标记；加权模式落地前，不得对"高频店集中城区"类场景给出定量压降承诺。

## C7 结论分级：定理 / 模型推断 / 经验阈值

| 级别 | 内容 | 允许措辞 |
|---|---|---|
| **定理** | BHH 渐近式；刚性平移几何不变性；凸包面积对非凸服务域的下界性；等里程 $n\propto1/A$（闭包内精确） | "精确""不变""必然" |
| **模型推断** | CA 参考带本身；√K 型情景对照；Pareto 端点结构 | "在均匀密度+分区假设下""理想化对照" |
| **经验阈值** | circuity 1.22/1.27/1.29/1.35（city_prior，置信度 LOW）；状态阶梯 0.85/1.05/1.35；形状修正斜率 0.08 与帽 1.15 | "先验""待留出集标定" |

**统一改名（强制）**：`theoretical_interval → ca_reference_band`；"理论上下界"→"参考带下沿/上沿"；状态四件套 `BELOW_CA_REFERENCE / CONSISTENT_WITH_CA_REFERENCE / ABOVE_CA_REFERENCE / STRONGLY_INCONSISTENT_WITH_CA`；`sqrt_k_premium → dispersion_scenario_contrast`（比值字段 `idealized_upper_contrast_ratio`，必须随附全部前提假设）；PoF 输出名 `cost_of_selected_equity_policy`。
诊断措辞禁令：不得仅凭 CA 把高里程归因为"排班分组差"，只允许写"可能由坐标错误、CRS 错配、跨区排班、仓库往返或业务约束造成，需进一步核查"。

## C8 质量门（Gate）：G1 不过，G2 必须 fail-closed

| G1 结果 | gate / G2 行为 |
|---|---|
| 非法点（null/nan/bbox 外） | 排除 + lineage 记录；若曾发生则 gate=`PASSED_WITH_INVALID_ROWS_DROPPED`（不得静默显示 PASSED） |
| `far_outlier` **未经用户裁决** | gate=`BLOCKED_BY_DATA_QUALITY`，`band=None`，`status=NOT_ASSESSED_DATA_QUALITY_BLOCKED` |
| 用户确认排除（`confirm_drop=[...]`） | 干净集计算；lineage 保留 `dropped_by_user` 与影响量 |
| 用户确认保留（`confirm_keep=[...]`） | 计算 + gate=`INCLUDING_CONFIRMED_OUTLIER`，band 内 `including_confirmed_outlier=True` |
| `source_crs=UNKNOWN` | gate=`STRUCTURE_ONLY`；**绝对 km 全阻断**：`band=None`、`status=NOT_ASSESSED_CRS_UNCONFIRMED`；几何结果只进 `structural_diagnostics`（frame-relative），不得命名为 band |

禁止静默剔除，禁止发现飞点后照常输出，禁止在未确认 CRS 下给出任何 km 数值结论（非技术用户会忽略 note 直接看数字——fail closed 是唯一防线）。

## C9 状态 → 允许的业务结论（白名单）

- `CONSISTENT_WITH_CA_REFERENCE`：仅允许"未发现明显不可信输入/结果；如需改进须用路网+求解器实测"。**不得**声称"已近最优"。
- `ABOVE_CA_REFERENCE`：仅允许"值得路网级核查与重排评估"。**不得**给出可兑现节省额。
- `STRONGLY_INCONSISTENT_WITH_CA`：仅允许"高度疑似数据缺陷或口径错配，先查证据"。
- `BELOW_CA_REFERENCE`：仅允许"疑似漏访问/直线距离冒充/缺日，先查完整性"。
- `dispersion_scenario_contrast`：仅允许"结构性上限对照"。**不得**解读为可实现压降。

## C10 标定、留出与版本

- 参考带宽度成分：单一主常数 β（见附录）× 迂回系数不确定性（city_prior 层级 ±）× 模型失配乘子（经验值，公开标注为经验阈值，不冒称统计置信区间）。
- 迂回系数溯源结构（强制字段）：`{circuity, source: rep_history|city_observed|city_prior|national_default, calibration_version, sample_size, confidence}`；优先级按上列顺序。
- 留出协议：真实金样例（房山、广州 02–11 实测 OSM 矩阵对账）**不进公开仓库**；公开仓使用同构合成集 + `data_signature.json`（输入聚合统计指纹：点数/面积/跨度/实测带内判定），真实数据仅在私有环境按同一版本参数复跑，要求 4/4 状态判定一致。
- 任何标定变更必须 bump `calibration_version` 并在 CHANGELOG 留痕。

---

## 附录 C-CONST：常数考证（回应评审 §1.4）

| 数值 | 出处与语境 | 结论 |
|---|---|---|
| β = 0.7124（±0.001） | BHH (1959) 定理本体；数值由大规模 Monte-Carlo/Concorde 计算（Applegate et al., *The Traveling Salesman Problem*, 2006, §15 计算估计；Arlotto & Steele 2016 综述）。单位正方形均匀点集**闭环** TSP 渐近主项 | ✅ 0.1.0 唯一主常数 |
| 严格界 [0.6277, 0.9038] | Gaudio & Jaillet 等解析界 | 仅作 docs 背景 |
| 0.712–0.730 "开链常数对" | 我此前无文献锚定；开环相对闭环主项相同、缺边贡献为低阶项（O(n^{1/4}) 边界/端部修正，见 Steele 1986 次可加泛函理论） | ❌ 撤销：不再作为独立"BHH 常数" |
| 0.750–0.765 "闭环常数对" | 语境混入了 Daganzo CVRP 扇区几何系数（带 depot stem 的分区模型，非 BHH 本体） | ❌ 撤销：若未来引入 stem 项，单列 depot correction 模型并引用 Daganzo (1984) 公式 |
| 有限样本 n≈10–30/日 | "Review of Length Approximations for Tours with Few Stops" (2021) 指出纯 √n 律在小 n 有系统偏差 | ⚠️ 0.1.0 文档如实声明：参考带在日粒度 n<10 处最不可靠，标注而非精修 |

## 附录 C-PERF：性能契约（回应评审 §2.3）

- 离群检测使用 stdlib 空间哈希网格（桶边长=点集中位最近邻距离量级），期望 O(N)；最坏退化 O(N²) 时上限文档化。
- CI 性能冒烟门槛（宽松、防回归）：N=10,000 单销售 sanity+band < 2s；571 销售全国合计 < 60s（各销售点数 ≤2,000）。
- "全国 60s"必须**实测**写入 CI 产物，不得以复杂度口头保证。
