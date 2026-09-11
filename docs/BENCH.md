# BENCH — synthetic throughput measurements (v0.1.0, M0)

> 契约依据: `docs/MEASUREMENT_CONTRACT.md` 附录 C-PERF。
> 本文一切数字为本机实测，**不是性能承诺**；门槛是基线相对制（`tests/perf_baseline.json`，退化 > 2x 判失败），不用固定秒数做跨环境绝对门槛。

## 环境

| 项 | 值 |
|---|---|
| 机器 | Apple M2（arm64, macOS, `nproc`=8 逻辑核） |
| Python | 3.12.0（系统 python3, stdlib only） |
| 实现 | `spatial_ca.sanity.find_suspects` — **精确暴力 O(N²) NN**，`mode=bruteforce_v1` |
| 数据 | `kind=synthetic`：`cloud(n, seed)` 均匀随机点 + 无离群注入 |

## 实测（2026-09-11）

| 场景 | 耗时 | 说明 |
|---|---|---|
| 500 点单次 `find_suspects` | 72–79 ms（3 次取值） | 对应 `test_500_stores_under_5s` 的 <5s 宽松冒烟——仅防算法级错写（如误写 O(N³)），**不是**性能上限声明 |
| 571 × 200 点全量（`SPATIAL_CA_PERF=1`） | 7.3 s（另测 7.1–8.5 s 波动带） | `test_national_synthetic_throughput`；写入 `tests/perf_baseline.json` = `{"national_571x200_s": 7.3, "mode": "bruteforce_v1", "kind": "synthetic"}` |

基线相对门已做双向验证：

- 绿向：重跑 7.07 s < 2.0 × 7.64 s → OK。
- 红向：人为把基线改为 1.0 s 后重跑 → `assertLess(total, 2.0 * prev)` FAIL（8.53 not less than 2.0），随后测试自动用新实测覆写基线，自愈回 7–8.5 s 区间。

## 边界声明（契约 C-PERF 附加项）

1. **合成吞吐 ≠ 真实数据最坏分布。** synthetic 均匀随机点云不包含真实门店数据可能出现的聚集/长链/重复坐标等最坏形态；真实分布最坏样本随私有留出环境补测，不在本版承诺范围。
2. `bruteforce_v1` 显式标注：本版复杂度即 O(N²)，README/BENCH 禁止口头宣称网格复杂度。可证明停止的网格加速属 0.2，须携带与本次暴力实现的等价性测试。
3. 单销售适用域（≤2,000 店）之外的规模行为未经测量，不做外推。

## 复现

```bash
# 常规（nightly 吞吐 skip）
python3 -m unittest tests.test_sanity -v

# nightly 合成吞吐（会读写 tests/perf_baseline.json）
SPATIAL_CA_PERF=1 python3 -m unittest tests.test_sanity.TestThroughput.test_national_synthetic_throughput -v
```
