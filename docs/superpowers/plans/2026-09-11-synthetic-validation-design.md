# 合成验证设计 v1（预注册冻结 2026-09-11）

> 状态：**预注册**（运行前冻结；运行后只许如实报告，不许改判据换结果——与 §11 冻结日志纪律同罪）
> 文献锚点：[BHH] Beardwood-Halton-Hammersley 1959；[Daganzo] 1978/2005；[Steele] 1981 非均匀推广；[BvNW] Beardwood-Van Nesmith-Wertz 1991 稀释极限；[Figliozzi] 2010 簇结构两项式

## 1. 目标

在**假设可控**的合成世界上检验框架两条分支的几何律：
- 稀疏分支中心估计：`monthly = β·√(V·A)`（合成世界 circuity≡1.0，纯几何检验）
- 密集分支上锚：`anchor = β·√(V·A·K)`，单边带 [0.25, 1.40]×anchor

并**绘制失效边界**（哪些形状/密度结构违反假设、偏离多大），而非只确认成功。

## 2. 因子与水平（142 组）

### Part A 稀疏中心估计（90 组）
| 因子 | 水平 | 依据 |
|---|---|---|
| 形状 shape | square / rect4x1 / disk / Lshape / ring / gauss5(成团) | 凸包 vs 有效面积杠杆 |
### Part A 稀疏中心估计（96 组）
| 因子 | 水平 | 依据 |
|---|---|---|
| 形状 shape | square / rect4x1 / disk / Lshape / ring / gauss5(成团) | 凸包 vs 有效面积杠杆 |
| n | 100, 200, 400, 800, 1600 | BHH 渐近收敛 |
| 密度 d (km²/店) | 0.15 / 1.0 / 4.0 | 面积跨尺度 15–6400 km² |
固定 f=1.2, K=21。面积 = n×d 派生。

### Part A2 K-不变性（6 组）
shape ∈ {square, rect4x1} × n=200 × d=1.0 × K ∈ {4, 9, 21}。

### Part C 渐近收敛（16 组）
shape ∈ {square, disk} × n ∈ {50,100,200,400,800,1600,3200,6400}，K=21, f=1.2, d=1.0。
检验 ratio → 1（BHH 渐近）。

合计 90+6+36+16 = **148 组**。

## 3. Ground-truth 协议（冻结）

1. 点集按 shape/density 采样（seed=20260911+config_id，可复现）。
2. **片区分割**：递归几何二分（沿长轴平衡切分，K 片）——标准 districting 启发式；紧凑性由构造保证。
3. 每日路线 = 片区内**闭环 TSP**，Euclidean 距离。
   求解器：NN + 2opt + Or-opt。
   **求解器间隙审计**：30 个 n≤12 实例对 Held-Karp 精确解，报告平均/最大间隙；文献界 2opt 均匀 Euclidean ≤5%。
4. `monthly_true = Σ_d TSP_d`（inter-stop 口径，不含 depot stem——与框架 `measured_scope="inter_stop"` 对齐）。
5. 密集 ground truth：门店按递归二分划入 K 个 weekday 类（紧凑），每类每月访 f 次：
   `monthly_true = f · Σ_k TSP(class_k)`。

### 3.1 修订 R1（2026-09-12，结果评估前；v1 首跑发现 harness bug 后冻结）
原协议未指定**重复访问落在哪天**。首跑 (v1) 实现为"每店单覆盖"（true 对
`β√(V·A)`，V=1.2n），与公式语义不一致，属实验装置缺陷非模型缺陷。
冻结修正：稀疏分支的 (V−n) 次重复访问以**边界条带**形式落入兄弟片区：
每片区取其距分裂线最近的 (V−n)/K 家门店加入兄弟日集合——两日集合均
保持紧凑（相邻区域、不同工作日；对应房山实测结构：41 家重复店集中在
边界片区）。v2 首试"兄弟日任取全片区店"被否：深位店产生跨域绕路，
日集合失去紧凑性，属生成器缺陷非模型性质（真值虚增 41.8%）。
密集分支不变（每周同日类扫全片区，与周合同一致）。
判据与因子结构不变。

## 4. 预测与判据（冻结）

- 稀疏：`mid = β·√(V·A_hull)`，β=0.7124；ratio = monthly_true / mid。
  **验收**：Part A 中**非失效形状**（square/rect4x1/disk/Lshape）ratio 中位数 ∈ [0.90, 1.30]，带 [0.75,1.30] 覆盖率 ≥ 80%。
  ring/gauss5 为**预声明失效格**：只绘边界，不计验收。
- 密集：ratio_a = monthly_true / anchor。
  **验收**：覆盖率（[0.25,1.40]）≥ 90%；且中位数 ≤ 1.0（上锚方向正确）。
- Part C：ratio 对 log(n) 单调递减趋近 1；n=6400 时 ratio ∈ [0.95, 1.15]。

## 5. 统计分析计划（冻结）

- 主效应：按 shape / n / K / f 分组的 ratio 中位数 + IQR 表。
- 失效边界表：ring/gauss5 的 ratio 分布 + 凸包/有效面积比（A_hull/A_eff，A_eff=各片区凸包和）。
- 全部原始结果落 `output/synthetic_validation_v1.json`（可复现种子）。
- 任何判据未过 → 如实报告并定位根因，**不许调 β/带/判据**。

## 6. 运行与归档

- 脚本 `experiments/synthetic_validation.py`（本仓）。
- 结果写入验证报告 §Synthetic v1 + README 故事三补一段。
- commit 信息含 "pre-registered"。
