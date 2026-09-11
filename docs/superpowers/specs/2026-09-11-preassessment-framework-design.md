# spatial-ca-benchmark：单销售事前判断框架 设计文档

> 状态：**数学与测量契约待验证（M0 返工中）** —— 评审裁定：`√K 恒等式、理论区间命名、PoF 定义、G1 防房山事故的能力、开闭环 BHH 常数` 五项过度确定结论暂缓，待 `docs/MEASUREMENT_CONTRACT.md` 条目逐条闭环后再定稿。定稿历史见文末《修订记录》。
> 日期：2026-09-11
> 仓库：`/Users/ghb/spatial-ca-benchmark`（独立 GitHub 项目，与 visit-scheduling-optimizer 母仓解耦）

---

## 1. 背景

本项目孵化自快消外勤两阶段排历优化（visit-scheduling-optimizer）的三起实战事故。三起事故的共同点：**错误或缺失的判断全部发生在"跑算法之前"，而当时没有任何不依赖地图、不依赖求解器的独立防线**。

### 1.1 事故一：坐标系混用导致整个底座失真 4 倍（房山）

北京房山线排历时，距离矩阵构建代码把 Excel 中的 GCJ-02（火星坐标）直接投影到 WGS-84 OSM 路网上。600~700 米的系统性平移在郊区把店铺吸附到封闭高速对侧与隔离带断头路，最短路径被迫绕行 2~50 倍：

- 真实人类计划月里程：**~536 km**（OSM 正确对齐后）
- 污染矩阵下算出的"基线"：**1,834 km**（虚高 3.4 倍）
- ALNS 在这个废底座上"优化"到 1,833 km 还自鸣得意——**算法永远发现不了底座坏了，它只会顺着坏数据优化**。

排查耗时多轮，直到用凸包面积 + BHH 闭式推出"这个销售这个月应该跑 460~530 km"，才在 10 秒内证伪了 1,834 km。**这个"10 秒证伪"的能力就是本项目的原型。**

### 1.2 事故二：占位坐标炸弹（天津）

全国 572 名销售批量体检中发现：天津某销售的客户"大胡同天津菜"坐标录为 `(110.0, 110.0)`——纬度 110° 越过北极点，是采集端失败时的手敲占位值。它让该员工月里程虚报为 **15,946 km**（真实约 87 km），并一度污染了全城市聚合统计。规则拦截（bbox 校验）+ 几何拦截（kNN 离群飞点标记）可以在毫秒级自动抓出这类点。

### 1.3 事故三：业务方质疑"手工计划怎么可能是最优"，无法回答

排历汇报中反复出现的问题：

- 优化后 -13.04%（广州）/-5.88%（房山）——**压降空间还有多少？谁给的保证？**
- 手工原计划与基线 A 几乎打平——**是人工已近最优，还是算法没跑够？**
- 业务问"平衡性差怎么办""多给一个工作日能省多少"——**每个问题都要求重跑一遍求解器，没人等得起。**

这三类问题需要一个**事前（判断计划好坏）+ 事前（预判杠杆效果）**的闭式基准层，独立于任何求解器存在。

### 1.4 GitHub 生态勘察（差异化确认）

| 检索方向 | 现状 | 空白 |
|---|---|---|
| Daganzo CA / BHH 工具库 | 仅 9 个零散学术脚本（≤1⭐），无打包发布的 Python 库 | **"CA 置信区间 + 数据体检"完全无人做** |
| p-median / 区划 | `pysal/spopt`(380⭐，geopandas/scipy 全家桶)、`territorium`(23⭐，启发式) | 无零依赖、无单决策者事前评估形态 |
| workload equity / PoF 落地 | Bertsimas PoF 只有理论文献 | **PoF 的可计算实现是空白** |
| route corridor | 全部是公路/管线选线语义 | 调度走廊（日动线紧凑性）语义无人做 |

结论：以"**单销售 × 免地图 × 闭式 × 事前**"四要素组合定位，全球无直接竞品，且实现成本（纯 stdlib 数学）与价值（省掉错误底座上的所有算力浪费）严重不对称——值得做。

---

## 2. 目标与非目标

**决策单元公理（用户裁定，不可动摇）：永远是"一个销售、一个计划周期"。不做跨销售分区。**

### 2.1 目标

| 编号 | 能力 | 定义 | 输出示例 |
|---|---|---|---|
| G1 | 数据体检 | 坐标炸弹 / 非法经纬度 / 孤立飞点拦截与定位 | `2 suspects: [110,110]@idx87, far_outlier 41km@idx12` |
| G2 | CA 理论区间 | 该销售该周期"应该"跑多少 km：开/闭环 BHH 常数切换 + 城市地貌自适应迂回系数 + 狭长形状修正 | `interval=[457.8, 519.1] km, mid=488.5` |
| G3 | 走廊诊断 | 日走廊公平份额（面积 `A/K`、等效半径 `r=√(A_sub/π)`）；对已有逐日计划算 ρ_area/ρ_r 逐日红绿灯；量化"走廊 vs 无走廊散巡"的 √K 倍差价 | `day07 ρ_area=3.4 超载跨区, 处方 n∝1/A` |
| G4 | 双轴平衡 | **店数均匀度**与**里程均匀度**两组指标（Gini/CV/极差/max-min），各自的**效率-平衡 Pareto 端点与 PoF**（Bertsimas 定义，闭式解，无需 MILP） | `Pof_visits=0.4%, Pof_km=6.1%` |
| G5 | 杠杆敏感性 | 周期天数 K、日负载 n、迂回系数 c、走廊宽度 [lo,hi] 的闭式偏导 + what-if 对照表 | `K:21→23 ⇒ 日区间 -5%, 半径 -4.5%, 总量 ±0` |

### 2.2 非目标（明确拒绝，防 scope 膨胀）

- ❌ 跨销售/跨车队 territory 分区（用户裁定）
- ❌ 实际路网距离计算（不调地图 API、不装 OSRM/OSMnx）
- ❌ VRP/TSP 求解器（框架的产物是标尺，不是解）
- ❌ p-median 精确 MILP 求解（其"K 中心"思想以**纯几何质心投影**形态保留在 G3 中：无约束时最优日走廊就是紧凑半径 ≤ r 的圆形动线，任何计划用"分配到最近日质心"即可投影成参考走廊做对比诊断——闭式、零依赖、够用）
- ❌ 运行时第三方依赖（含 numpy；连测试都用 stdlib `unittest`）

### 2.3 成功判据

1. 房山金样例：`preassess()` 对 536.30 km 人类计划判 `REASONABLE`、对 1,834 km 污染矩阵判 `SEVERELY_INFLATED`（复现事故证伪，偏差率与 §1.1 数字一致）；
2. 天津金样例：`(110.0, 110.0)` 在 G1 被拦截，剔除后该销售从 `15946 km` 修正到 ~87 km 且判定翻转 `SEVERELY→REASONABLE`；
3. √K 恒等式性质测试通过：同一点集 `corridor_free_total / corridor_total == √K`（闭式验证，±1e-9）；
4. 全国 571 销售可在 <60s 内完成全量体检（stdlib 纯 Python，单机单线程）；
5. `pip install spatial-ca-benchmark && spatial-ca --help` 一次成功。

---

## 3. 方案比选（已呈用户，取 A）

| 方案 | 描述 | 裁决 |
|---|---|---|
| **A 分层纯解析库** | 每个能力域一个模块，全闭式，零依赖；p-median 思想以质心投影诊断形态保留 | ✅ **采纳**。契合"独立发布"目标；模块边界=测试边界；无双路径依赖 |
| B 单文件巨石 | 全部塞进一个 benchmark.py | ❌ 5 个能力域挤一个文件，违背单一职责，演进即腐化 |
| C A + 可选 scipy/pulp 精确层 | 给 PoF 端点加 MILP 对照 | ❌ 破坏零依赖卖点；PoF 两端点本就是闭式最优（见 §5.4），MILP 不增加信息量 |

---

## 4. 架构与模块设计

```text
spatial_ca/                     运行时零第三方依赖（仅 stdlib: math, csv, json, dataclasses, bisect）
├── __init__.py     公开 API 门面：preassess, estimate_spatial_benchmark, SpatialBenchmark,
│                   evaluate_measurement, find_suspects, CIRCUITY_PRESETS, get_city_terrain_and_circuity
├── geometry.py    [已完成] clean_coordinates(bbox过滤+GCJ02→WGS84闭式转换),
│                   compute_convex_hull_area_km2(单调链凸包+鞋带公式), project_km(等距圆柱投影)
├── terrain.py     [已完成] 4 级地貌预设 + 108 城中文名→(地貌, 迂回系数)分类器
├── sanity.py      [G1] find_suspects(coords, bbox, nn_factor): 非法点 + kNN 离群飞点(≥8×中位NN距离);
│                   suspect_report() → dict。与 clean_coordinates 的关系：sanity 报告，clean 执行剔除
├── daganzo.py     [G2] SpatialBenchmark dataclass: 月级/日级区间+evaluate 状态阶梯;
│                   estimate_spatial_benchmark(coords, visits, days, *, tour, terrain|city|circuity)
├── corridor.py    [G3] CorridorPlan: A_sub, r_eff, n∝1/A 处方;
│                   diagnose_plan(plan: {day: [store_idx]}, stores): 逐日 ρ_area/ρ_r/紧凑度评级;
│                   corridor_value(visits, area, K): 返回 √K 倍散巡差价
├── balance.py     [G4] gini, cv, spread_ratio; pof_endpoints(areas, visits, capacity_range):
│                   efficient 端点(凹性⇒容量盒顶点⇒贪心闭式) + equal 端点(水填二分);
│                   tradeoff_scan(..., taus): τ∈[0,1] 两端点分配凸组合逐点闭式估值
├── sensitivity.py [G5] deltas(benchmark, K=?, n=?, c=?, corridor?): 解析偏导 + what-if 行
├── report.py      PreAssessment 聚合对象: 五个 section + to_dict()/to_markdown()/summary();
│                   preassess(...) = G1→G2→G3→G4→G5 编排,缺件自动降级
└── cli.py         `spatial-ca preassess --csv plan.csv --lng lng --lat lat --days 21 [--visits-col f --city-col c --plan-day-col d --measured-km km]`
                   `spatial-ca cities`（列地貌分类表）; argparse 子命令, 输出 markdown 或 --json
```

### 4.1 模块依赖方向（严格单向，禁止回边）

```text
cli/report → sensitivity/balance/corridor/daganzo/sanity → terrain → geometry
```

### 4.2 缺件降级矩阵（输入决定输出深度）

| 输入 | G1 | G2 | G3 | G4 | G5 |
|---|---|---|---|---|---|
| 仅 coords | ✅ | ✅ | 处方(r, n∝1/A) | 理论均匀解 | ✅ |
| + plan(逐日分配) | ✅ | ✅ | ✅ 逐日诊断 | ✅ 实测双轴 | ✅ |
| + measured_km | ✅ | ✅ evaluate | ✅ | ✅ | ✅ |
| 无 coords 合法点 | 全部 → `ValueError("all coordinates filtered")`，report 中给清洗统计 | | | | |

### 4.3 错误处理契约

- 点数 <3：区间退化为 `(0, span)` 并附 `warning="degenerate_geometry"`（不抛异常——体检报告里"店太少测不了"本身是结论）；
- 走廊不可行（`V < K·lo` 或 `V > K·hi`）：G3 返回 `feasible=False + infeasibility` 字段——**这本身是最重要的事前发现之一，不是错误**；
- 城市名不在 108 城表：静默回退 `suburban_mix 1.27` 并在 report.metadata 记 `terrain_fallback`。

---

## 5. 核心数学（公理层）

### 5.1 CA 主公式

$$d_{\text{day}}=k\,c\,f_{\text{shape}}\sqrt{A_{\text{sub}}\,\bar n},\qquad A_{\text{sub}}=\frac{A_{\text{hull}}}{K},\ \bar n=\frac{V}{K}$$

- BHH 常数：开链 $k\in[0.712,0.730]$，闭环 $k\in[0.750,0.765]$（自检一）；
- 迂回系数：`urban_plain_grid 1.22 / suburban_mix 1.27 / waterway_delta 1.29 / mountainous_rugged 1.35`（自检三，OSM 实测标定）；
- 形状修正：$f=1+\max(0,(e-1)\times0.08)$，上限 1.15（自检二，Figliozzi 边界效应简化）。

### 5.2 走廊 √K 恒等式（本项目最重要的结构性洞察）

走廊制：$T_{\text{corridor}}=K\cdot kc\sqrt{\tfrac AK\cdot\tfrac VK}=kc\sqrt{A\,V}$ —— **与 K 无关**。
无走廊随机散落：$T_{\text{free}}=kc\sqrt{A\,V\,K}$。
$$\boxed{\;T_{\text{free}}/T_{\text{corridor}}=\sqrt K\;}$$

实证：房山 K=21 → √K=4.58；实测"散点上限 2,158 km vs 走廊中枢 494 km = 4.36×"吻合。
**推论（修正敏感性设计）**：K 的杠杆不作用于总里程，只作用于①日区间宽度 ②走廊半径 $r\propto1/\sqrt K$ ③平衡可达性。多给一天 = 每天更轻松、月总量不变——这句话值一次汇报。

### 5.3 走廊诊断量

- 公平份额面积 $A_{\text{sub}}$、等效半径 $r=\sqrt{A_{\text{sub}}/\pi}$；
- 逐日：$\rho_{\text{area}}(d)=A_{\text{hull}}(\text{day}_d)/A_{\text{sub}}$（>2 亮红：跨板块）、$\rho_r(d)=\text{diam}(\text{day}_d)/(2r)$（>1.5 亮红：过长走廊必折返）；
- 里程均衡处方（G4 输出给 G3）：等日里程 ⇒ $n_k\propto1/A_k$（走廊越肥，装店越少）。

### 5.4 PoF 闭式端点（Bertsimas 定义落在 CA 代价上）

对"里程均匀"轴，容量盒 $n_k\in[lo,hi]$（无走廊则 $[0,hi]$）：

- **efficient 端点**：$\min\sum_k\sqrt{A_k n_k}$，被最小化目标关于 $n$ **凹** ⇒ 最优在盒约束多面体顶点 ⇒ 贪心闭式：按 $A_k$ 升序填到 $hi$，留一个分数位；
- **equal 端点**：$d_k\equiv\bar d$ 水填——$n_k(\bar d)=\mathrm{clip}\!\big((\bar d/kc)^2/A_k,\,lo,\,hi\big)$ 对 $\bar d$ 单调，二分 60 步命中 $\sum n_k=V$；
- 中间点：$n(\tau)=(1-\tau)n^{\text{eff}}+\tau n^{\text{eq}}$ 逐点代入闭式代价（端点精确、中段是可行路径上的诚实估值——文档如实标注，不冒称 Pareto 最优前沿）；
- $$\text{PoF}=\big(T_{\text{eq}}-T_{\text{eff}}\big)/T_{\text{eff}}\ \ge 0$$（性质测试断言非负 + 单调）。
- 店数轴 PoF 同理，代价函数换成 $n_k$ 的方差/极差，端点退化为均匀整数分配（组合数极小可穷举精确解）。

---

## 6. 数据流

```text
CSV/coords ─→ sanity.find_suspects ─→(suspects表)
          └─→ geometry.clean_coordinates ─→ 合法WGS84点
                 ├─→ daganzo.estimate ─→ 月/日区间 + evaluate(measured?)
                 ├─→ corridor: 处方(r, n∝1/A) + diagnose(plan?) ─→ 逐日红绿灯
                 ├─→ balance: pof_endpoints(areas?, V, corridor) + metrics(plan?)
                 └─→ sensitivity.deltas(bench, knobs)
report.PreAssessment(全部) ─→ to_markdown()/to_dict()/json
```

## 7. 测试策略（stdlib unittest，零依赖）

| 层 | 内容 |
|---|---|
| 单元 | 凸包面积已知方块=解析值；GCJ 转换与 eviltransform 参考值差 <1m；gini/cv 性质；水填二分收敛 |
| 性质 | √K 恒等式；PoF≥0 且随 τ 单调；开链区间<闭环；clean 幂等；坐标全非法抛 ValueError |
| 金样例 | 房山 201 店（区间 vs 479/536/504/1834 四态判定）；天津 (110,110) 拦截前后翻转 |
| 集成 | CLI 子进程冒烟：--csv 真实脱敏样例 → markdown 非空 + --json 可解析 |

## 8. 发布物与仓库布局

```text
spatial-ca-benchmark/
├── README.md            背景故事(两事故)+快速上手+公式摘要+两案例验证表
├── LICENSE              MIT
├── pyproject.toml       [已完成] 零依赖, console script spatial-ca
├── spatial_ca/          §4 清单
├── tests/               §7 清单
├── docs/
│   ├── DERIVATION.md    §5 完整推导 + 参考文献(BHH59/Daganzo84/FS06/Ballou02/Bertsimas11/MinMaxVSS)
│   └── CASE_STUDIES.md  房山/天津/571人批量 三份实录(脱敏聚合表)
├── examples/            quick_start.py · detect_dirty_gps.py · balance_pof.py
└── .github/workflows/ci.yml  python -m unittest discover (3.9-3.13 矩阵)
```

## 9. 风险与边界（诚实声明）

1. **CA 是均匀密度近似**：山区/单走廊狭长城市（如沿河谷 100km 长条）区间会偏乐观——用 ρ_r 与 elongation 上限对冲，README 明示适用域；
2. **中段 τ 路径非严格 Pareto**（凹性顶点定理只保证端点精确）：文档标注，不冒称；
3. **108 城地貌表**是经验标定不是理论值：随 case study 公布标定方法，欢迎 PR 扩表——这是社区钩子不是缺陷；
4. visit 母仓的 `core/spatial_continuous_approx.py` 与 `core/city_terrain_classifier.py` 在本仓成熟后**反向引用**（母仓改为依赖本包的 shim），避免双源漂移——列入后续独立迁移任务，不在本期范围。

## 10. 术语表

| 术语 | 含义 |
|---|---|
| CA | Continuous Approximation（Daganzo 连续近似） |
| BHH | Beardwood-Halton-Hammersley 定理及常数 |
| 走廊 | 单销售单日拜访动线的紧凑地理片区（继承母项目业务概念），非公路选线 corridor |
| PoF | Price of Fairness：强制公平相对效率最优的总代价涨幅 |
| ρ_area / ρ_r | 某日凸包面积 / 日直径 ÷ 走廊公平份额 / 公平半径 |
| 水填 | water-filling：对单调函数二分找均衡点 |

---

## 修订记录

| 版本 | 日期 | 内容 |
|---|---|---|
| v1 | 2026-09-11 | 初稿（G1-G5 全量、"理论区间/√K 差价/PoF 闭式"表述），用户批准 commit `34a31dc` |
| v1.1 | 2026-09-11 | **外部评审否决 5 项过度确定结论**：① G1 抓不到整批 CRS 错配（定理级：刚性平移内部几何不变）；② 飞点未阻断 G2（凸包 ×10 复现）；③ "理论区间"命名过强 → `ca_reference_band`；④ 两对"BHH 开闭环常数"缺乏文献（主项同 β，开环差为低阶项）；⑤ √K 是强假设场景比值非可实现差价。另抓出：水填断言方向反、自等断言假测试、索引漂移、投影二次套娃、O(N²) 与复杂度声明矛盾、K 语义混乱、city 系数"标定"言过其实 |
| v1.2 | 2026-09-11 | M0 返工：落 `docs/MEASUREMENT_CONTRACT.md`（C1-C10 + 常数考证 + 性能契约）；geometry 重写（CRS 声明必填、索引保持清洗、凸包双函数拆分）；`__init__` 惰性导出；状态回退"待验证"；0.1.0 范围收缩至 契约门+体检+参考带；走廊/需求加权/公平政策分别推至 0.2/0.3/0.4 |
| v1.3 | 2026-09-11 | **二轮评审 6 阻断 + 4 修正 → 计划 V2.1**：K 测试方向修正（日带随 K 递减 + T=Kd 性质断言）；0.1.0 NN 回退精确暴力（可证明停止网格推 0.2）；带宽改显式版本化政策带 `heuristic_policy_envelope_v1`（废除平方和伪统计）；UNKNOWN CRS 全面阻断绝对 km（band=None，仅 structural_diagnostics）；PreAssessment 统一 dataclass 属性访问；report 状态机完整实现（gate 五态含 PASSED_WITH_INVALID_ROWS_DROPPED）；BETA 拆 point_estimate/published_bounds/operational_inputs 三字段；性能门槛基线相对化改名 synthetic throughput |
