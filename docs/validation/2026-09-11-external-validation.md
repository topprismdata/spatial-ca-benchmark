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
