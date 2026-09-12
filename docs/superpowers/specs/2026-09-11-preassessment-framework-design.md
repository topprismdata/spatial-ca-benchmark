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

### 3.1 稀疏 regime（f=V/N ≤ 2.0）：日片区互斥（v2.2 两项式）
`monthly = c·(β·√(V·A) + κ·√(K·A))`，`daily = monthly/K`。κ=0.9531（冻结）。
- 内部项 β√(V·A)：BHH；边界项 κ√(K·A)：K 个日片区的周长型修正（Daganzo 分区模型血统，Steele 边界项）。
- **来源**（预注册合成验证 v1，148 组，设计文档 `docs/superpowers/plans/2026-09-11-synthetic-validation-design.md`）：κ 仅在 square+rect4x1 Part A 拟合；留出 disk/Lshape（cov 100%）、渐近 n→6400（100%）、K-不变性（100%）；纯 BHH 公理被实验证伪（原模型 median ratio 1.24、cov 58%）。
- 平台分解（n=800, K=21, f=1.2）：ratio 1.178 = 有限-n BHH 常数 1.106 × 分区边界 1.086 × 重复增程 0.98。
- 表述纪律（RevCorr-M5）：单点经验（房山）已被合成大规模验证取代；但**新鲜真实留出仍缺**（§5.6），故 v0.3.0 为 rc。

### 3.2 密集 regime（f ≥ 3.0）：均匀场稀释**上锚**（v2.1b 定稿）
`monthly = β·c·√(V·A·K)`，`daily = monthly/K`。即 Steele/BvNW 稀释极限在**最大平滑尺度（均匀场）**下的取值：K 个日集合对同一领地的稀释重扫，其里程下界即"日集合在凸包内均匀散布"的 BHH 值。
**语义（load-bearing）**：这是**上锚**，不是中心估计。紧凑片区规划必然低于它（成团性杠杆只向下作用）；政策带因此**单边**：`[0.25·mid, 1.40·mid]`——下缘只拦"不可能的低值"（漏访/直线口径），上缘拦"超锚 40% 的结构可疑计划"。
**撤回**（v2.1b，2026-09-11）：v2.1 曾冻结"直方图网格 cell=medNN 的 ∫√m dx"（Stieltjes 变体）。实现回归暴露两处致命缺陷，**整条冻结作废**：
- 量纲错误：正确离散化是 `h·Σ√v_c`（非 `√h·Σ√v_c`）；medNN≈30m 下点质量场使 `h·Σ√w → 0`（细网格极限退化，§3.2 旧文本自己写过的"细网格极限→0"正是死刑判决）；
- 此前"22.5% MAPE / 7-10 入带"的达标数字出自带量纲 bug 的 `√h` 变体或逐线实测 c 通道（后者已被 §11.2 判弃）——**达标结论不成立，撤回**。
- 教训入 §6 事故簿：任何"冻结规则"在入库前必须过**量纲+极限**两道解析检查，数值达标不构成证据。

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
               c_sample_size, anchor:"upper|central", calibration_version}
  assumptions: [...]
  hygiene: {gate, dropped_invalid, suspects, crs_status}   # 一等 gate，不参与计算
```
band.py 职责修订（RevScope-Minor）：**纯乘子外壳**，mid 来自 estimate.py；删除 band.py 内部点估计路径与 thin-widening（与密集主导误差源正交）；拒答分支从 report.py 移除（v2.1 起密集出数）。

## 5. 验收判据（v2.1 重写，预注册冻结 2026-09-11）

**冻结文本**：密集 = 均匀场上锚（§3.2 v2.1b），c = 1.29（来源 terrain.py city_prior，LOW），验收期禁用 c 覆盖与 confirm 交互。

1. **单次冻结运行**（广州 10 线，baseA 口径，上锚语义）：锚带覆盖率 **9/10**（唯一越上缘者 08：baseA/锚=1.60，恰为已知结构最差的人类计划，SP 优化后 621 km 落带 1.23——锚正确分离了"结构可疑"与"优化后"）；SP 优化计划 **10/10** 落带。锚/真值平均偏差 35%（上锚单边语义的预期偏置，不作中心精度宣称）。
2. **v0.2.0 发布门 = SP 锚协议（log 判据乙）+ 新鲜留出集**：
   - 验收集 = **从未触碰的密集线**（新城市或新周期；广州 10 线已烧毁，只作 dev）；
   - P1: SP 可达优化里程 ∈ 政策带 ≥8/10；P2: 判别一致率（baseA/SP≥1.2 → ABOVE；≤1.05 → CONSISTENT）≥9/10；
   - 带符号偏差检验（RevAdv-4）：报告误差方向分布，|·| 不抹方向；
   - 不达标 → 如实发布失败报告，v0.2.0 不发，不放宽、不回填。
3. 房山回归：est ∈ 536/505 的 ±30%（口径=计划-on-OSM，见 §5.4）；1834 仍 STRONGLY_INCONSISTENT。
4. 天津回归：(110,110) 拦截且留痕。

### 5.6 v2.2 结果补记（如实，不回填）
- **v1 判据（纯 BHH）：FAIL**——非失效形状 cov 58% < 80%。根因 = 缺边界项，非排序/非形状。
- **v2 两项式：拟合内 cov 100%**（median 1.002）；房山交叉检验基线A 0.962 / SP 0.906（原 1.147/1.080）。
- **密集上锚不耦合边界项**：Part B 合成 cov 100%（median 0.595≤1.0），广州留出 9/10 不变（08 仍标记）。
- **发布门状态（v2.3 更新）**：北京新鲜留出到位（全部.xlsx，18 条月拜访线，GCJ02 与房山同源校验 0m，OSRM 实测月里程，NP9902504=烧毁房山线已剔除）：
  - 两项式 mid (c_prior=1.22)：**median 1.202，cov 11/18**；
  - 纯 BHH 对照：median 1.649，cov 3/18 → **边界项在新鲜真实数据上方向与量级双确认**（1.65→1.20）；
  - λ=√(A/n) 输入侧分层：**区域型 λ≥0.6km n=8 → median 1.010、cov 7/8（门达标 ≥80%）**；超密城市 λ<0.6km n=10 → median 1.700、cov 4/10（域外）；
  - c 实测两变体（c_pair 0.3-3km 窗 / c_hop 跳距尺度自适应窗）对超密线能把 ratio 拉回带内（6/10），但对区域线过冲（c_hop 1.8-2.3 使区域线 1/8）——**统一 c 替换不可行，先验+旗标是正解**；
  - v0.3.0 转正发布：λ<0.6km → `ultra_dense_urban_warning=True`（纯输入侧几何判定），措辞降级为下界；区域型月拜访 = 已验证域。
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
| v2.2 | 2026-09-12 | 预注册合成验证 148 组：纯 BHH 判据 FAIL（cov 58%）如实报；边界项 κ√(KA) 两项式拟合+留出全绿；房山 ratio 1.147→0.962；发布门补记（rc 状态，缺新鲜真实留出） |
| v2.1 | 2026-09-11 | **五人格评审修订**：R2/R3 删除（3× 旋钮/收敛已证伪端元）、积分定义冻结、边界 UNRELIABLE_TRANSITION+regime_margin 入契约、V/K≥10 下限、输入面诚实化（裁决/c 覆盖为声明输入）、验收重写（单次冻结运行如实报 7/10 + 新鲜留出 SP 锚门）、删除分层判据后门、真值口径表、band 纯外壳、Contract Delta 显式作废清单、β/c 溯源对称化 |

## 11. 理论精度天花板与广州验证矩阵（2026-09-11 终版，全部有据）

### 11.1 文献天花板（论文原文，非本仓实验）
- Figliozzi (2007), TR-B 41:572-584，六城 13.2 万条真实出行：**点到点距离估计 MAPE 22%-32%、R² .67-.71**；
- Figliozzi (2010), TR-B 44:498-509：两项式模型对模拟欧式数据 MAPE<5%（R² .974-.992），对实际车队数据误差显著放大；其精确形式依赖"簇数 m"作为显式输入；
- PRC (2011)：迂回系数按城市与距离带变化 1.02-1.38（城区汽车，均值概念），且城市间差异不可传递（NYC 2014 同法得 1.286-1.988）；
- Beardwood-Van Nesmith-Wertz (1991)：非均匀密度的正确渐近式 β∫√f dx（稀释极限，BHH 自认未证的推广）。
**结论：对真实路网+仅几何输入，±20-30% MAPE 是该理论的公开天花板。**

### 11.2 广州验证矩阵（本仓实测，冻结参数，零调参）
| 模型 | c | MAPE | ±30% 带 | 判定 |
|---|---|---|---|---|
| ~~稀释 βc√K·∫√m dx，cell=medNN（Stieltjes 变体）~~ | 1.29 先验 | ~~22.5%~~ | ~~7/10~~ | **撤回**：√h 量纲 bug + 点质量场细网格退化；达标数字无效 |
| 均匀场稀释上锚 βc√(V·A·K)，单边带 [0.25,1.40]×mid | 1.29 先验 | 35%（偏置，非中心误差） | baseA 9/10、SP 10/10 | **定稿**：上锚语义，08 被正确标记 |
| Figliozzi 两项式 k_m√(Am)+k_a√(An)（发表系数 1.1635/1.0），m=稀释网格触及数 | 实测 | 78.4% | 1/10 | **模型误用**：他的 k 配 Solomon 簇数定义，非触及格数；弃 |
| 随机点对中位 c 测量（0.15-3km 带） | — | 不可复现 | — | **测量法弃**：骑行微凸包被不可达/绕河尾污染（02 中位 c=4.48 vs p25=1.79）；文献 c 均基于实际驶过对 |

### 11.3 边界裁决（§11.1+§11.2 合取）
"广州 ≥8/10 入带" 与 "输入仅坐标+频次+K" 在公开文献框架内**不可兼得**：残余误差的唯一文献解药是簇结构输入（Figliozzi 2010 的 m），不在输入面内。框架据此定位：
1. **稀疏 regime（f≤2.5）**：主精度区（房山式月访片区），±30% 验收；
2. **密集 regime（f>2.5）**：输出**均匀场稀释上锚** + `model_form="dilution_uniform_field_upper_anchor"` + `anchor="upper"` + `model_form_uncertainty=0.25`，明示"紧凑片区必然低于锚；越上缘 40% 才是结构可疑信号"——**这是能力声明，不是失败**；
3. 任何"8/10 密集线 ±30%"的宣称若出现，视为违反本节（需簇结构输入才配得上）。
