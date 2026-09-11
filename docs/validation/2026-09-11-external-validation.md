# CA Framework External Validation Report (2026-09-11)

## Datasets

| Source | Type | n | f | Result |
|---|---|---|---|---|
| Fangshan (房山) | Monthly plan, sparse | 201 | 1.20 | **PASS** ratio 1.08–1.15 |
| Guangzhou (广州) | Weekly contract, dense | 103–172 | 3.5–4.6 | **PASS** 9/10 anchor band |
| Amazon ALMRRC 2021 | Daily TSP | 33–80 | 1.0 | **FAIL** ratio 1.4–2.6 |

## Amazon ALMRRC (51 routes) — **NOT APPLICABLE DOMAIN**

- Source: 9,184 real delivery routes, AWS S3 public
- Sample: 51 routes across 13 stations (LA, Seattle, Boston, Chicago, Austin)
- Ground truth: OSRM road-network distance along driver's actual sequence

### Why this dataset cannot validate the framework

| Dimension | Framework target | Amazon ALMRRC | Match? |
|---|---|---|---|
| Domain | Field sales visit planning | Parcel delivery | **NO** |
| Temporal structure | Monthly plan, cross-day allocation | Daily independent TSP | **NO** |
| Optimization | Cross-day assignment + TSP | Per-day TSP only | **NO** |
| n (points) | ≥150 (territory coverage) | 33–80 (clustered) | **NO** |
| f (visits/store) | ~1.2 (sparse monthly) | 1.0 (single-day) | **NO** |
| Distance unit | Road-network km | travel_times = seconds | **NO** |

The framework predicts **optimized monthly total distance** for a territory
covered by ≥150 stores with cross-day allocation. Amazon data has none of
these properties. Using it for validation is a category error.

### Observed (for reference only)

| Metric | Value | Interpretation |
|---|---|---|
| ratio (actual/mid) median | 1.64 | BHH lower bound, expected for small-n clustered TSP |
| TSP-optimal/mid median | 1.66 | Sorting NOT the issue; hull inflation dominates |
| Actual/TSP gap | 1.09× | Driver sequence ≈ TSP-optimal (time windows dominate) |

These numbers are consistent with BHH theory at small n (hull inflation),
NOT a framework failure. The framework was never designed for this domain.

## Valid Validation Basis (domain-matched)

| Dataset | Domain | n | f | Result |
|---|---|---|---|---|
| Fangshan (房山) | Monthly visit plan, sparse | 201 | 1.20 | **PASS** ratio 1.08–1.15 |
| Guangzhou (广州) | Weekly contract, dense | 103–172 | 3.5–4.6 | **PASS** 9/10 anchor band |

Both use real OSM road-network distances, real visit frequencies, and
real monthly/weekly planning structure. These are the only valid
validation sources available.

## Framework Applicability Boundary (FINAL)

| Scenario | n | f | Domain | Applicable | Validated |
|---|---|---|---|---|---|
| Monthly sparse plan | ≥150 | ~1.2 | Visit planning | **YES** | Fangshan 1.08–1.15 |
| Weekly dense routes | ≥100 | 3–5 | Visit planning | **YES** (upper anchor) | Guangzhou 9/10 |
| Daily parcel TSP | <100 | 1.0 | Delivery | **NO** (wrong domain) | N/A |

## Recommendation

- Use framework for **visit planning** (monthly/weekly, n≥100, territory coverage)
- Do NOT use for **parcel delivery** or **daily TSP estimation**
- Open-source data for visit planning with real road distances is extremely
  rare (commercial sensitivity); Fangshan + Guangzhou remain the validation basis

## Pre-registered Synthetic Validation v1 (2026-09-12, 148 configs)

Design frozen before run: `docs/superpowers/plans/2026-09-11-synthetic-validation-design.md`.
Factors: 6 shapes (square/rect4x1/disk/L-shape/ring/gauss5) x n(100-1600) x
density d(0.15/1.0/4.0 km2/store, areas 15-6400 km2); K-invariance subtest;
dense anchor (f=3/4.3/6); asymptotics n->6400.

Ground truth: recursive-bisection districting + multi-start NN/2-opt/Or-opt
TSP (Held-Karp audit: mean gap 0.02%, max 0.75%), Euclidean, circuity=1.

### Harness incident ledger (honest, fixed BEFORE gates decided)
1. v1-run1: repeats omitted (single-cover truth vs beta*sqrt(V*A) prediction,
   V=1.2n) - semantic mismatch in harness, not model. Fixed (R1).
2. v1-run2: repeats scattered to random global days -> non-compact day sets,
   truth inflated +41.8% by cross-domain detours. Fixed (R2: boundary-strip
   repeats, matches observed Fangshan structure: 41 repeat stores clustered
   at shared borders).

### Results (frozen gates)
- **Part A original pure-BHH model: FAIL** - non-failing-shape coverage 58%
  (gate >= 80%), median ratio 1.24. Plateau decomposition (n=800,K=21,f=1.2):
  1.178 = finite-n BHH constant (1.106) x districting boundary term (1.086)
  x repeat-detour (0.98). Ring/gauss5 behaved as pre-declared (A_eff/A_hull
  0.36-0.45; underprediction direction after correction).
- **Two-term fix mid = c*(beta*sqrt(V*A) + kappa*sqrt(K*A)), kappa=0.9531**
  fitted ONLY on square+rect4x1 Part A:

| holdout set | n | median | coverage | orig model |
|---|---|---|---|---|
| disk+L-shape Part A | 30 | 0.999 | 100% | 60% |
| asymptotics n->6400 | 16 | 1.003 | 100% | 62% |
| K-invariance | 6 | 1.042 | 100% | 33% |
| Part A all non-failing | 60 | 1.000 | 100% | 58% |

- Part B dense anchor (unchanged): 100% coverage, median 0.595 -> PASS.
- Fangshan cross-check (real data, c=1.27, K=5): baseline-A ratio 1.147 ->
  **0.962**, SP 1.080 -> **0.906**; 1834 km still STRONGLY_INCONSISTENT.

### Verdict
Framework v0.3.0-rc1. Sparse branch: synthetically validated at scale with
fit/holdout discipline + one real cross-check; **fresh real-world holdout
still missing** (Guangzhou burned as dev; Fangshan burned as calibration;
Suzhou report lacks coordinates), hence rc not released. Dense anchor and
hygiene gates unaffected.
