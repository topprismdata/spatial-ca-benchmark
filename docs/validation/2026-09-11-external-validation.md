# CA Framework External Validation Report (2026-09-11)

## Datasets

| Source | Type | n | f | Result |
|---|---|---|---|---|
| Fangshan (房山) | Monthly plan, sparse | 201 | 1.20 | **PASS** ratio 1.08–1.15 |
| Guangzhou (广州) | Weekly contract, dense | 103–172 | 3.5–4.6 | **PASS** 9/10 anchor band |
| Amazon ALMRRC 2021 | Daily TSP | 33–80 | 1.0 | **FAIL** ratio 1.4–2.6 |

## Amazon ALMRRC Validation (51 routes, ≤80 stops)

- Source: 9,184 real delivery routes, AWS S3 public
- Sample: 51 routes across 13 stations (LA, Seattle, Boston, Chicago, Austin)
- Ground truth: OSRM road-network distance along driver's actual sequence
- Prediction: BHH sparse `β·c·√(n·A)`, c=city_prior

### Results

| Metric | Value |
|---|---|
| ratio (actual/mid) median | **1.64** |
| ratio mean ± std | 1.66 ± 0.28 |
| In band [0.75, 1.30]×mid | **2/51** |
| MAPE | 66% |
| Direction | ALL ABOVE (BHH is lower bound) |

### TSP-optimal comparison (22 routes, NN+2opt)

| Metric | Value |
|---|---|
| TSP/mid median | **1.66** |
| TSP MAPE | 72% |
| Actual/TSP gap | 1.09× |

**Conclusion**: Sorting is NOT the issue. Even TSP-optimal exceeds BHH by 66%.

## Root Cause: Convex Hull Inflation + Small n

BHH asymptotic assumes n→∞, uniform distribution. Amazon data violates both:
- n = 33–80 (far from asymptotic)
- Points clustered in residential blocks; hull includes parks/rivers/empty lots
- Hull area >> effective service area

Evidence: ratio negatively correlated with n (n=38 → 2.0; n=80 → 1.3).

## Framework Applicability Boundary (FINAL)

| Scenario | n | f | Applicable | Validated |
|---|---|---|---|---|
| Monthly sparse plan (Fangshan-style) | ≥150 | ~1.2 | **YES** | ratio 1.08–1.15 |
| Weekly dense routes (Guangzhou-style) | ≥100 | 3–5 | **YES** (upper anchor) | 9/10 in band |
| Daily TSP (Amazon-style) | <100 | 1.0 | **NO** | hull inflation, 66% under |

## Recommendation

- Use framework for **monthly/weekly planning** (n≥100, points cover territory)
- Do NOT use for **daily TSP estimation** (n<100, clustered points)
- If daily TSP estimation needed: use effective-area correction (α-hull or KDE bandwidth) instead of convex hull
