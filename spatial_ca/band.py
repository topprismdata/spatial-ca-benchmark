"""v2.1 CA estimator: regime-routed closed-form route-length model.

Two literature-standard model forms, one frozen constant BETA = 0.7124
# v0.3.0 boundary term (Daganzo partition-model lineage): recursive-bisection
# districting adds a perimeter-like term kappa*sqrt(K*A) to the BHH interior.
# kappa frozen from synthetic validation v1 (fit square+rect4x1 Part A,
# 100% holdout coverage on disk+Lshape+asymptotics+K-invariance sets):
# docs/superpowers/plans/2026-09-11-synthetic-validation-design.md
KAPPA_BOUNDARY = 0.9531
(BHH leading term; Applegate et al. 2006; analytic bounds [0.6277, 0.9038]
are background, NOT band inputs):

- sparse_partitioned (f = V/N <= 2.0, monthly-plan corridor regime):
      monthly = c * (BETA * sqrt(V * A) + KAPPA_BOUNDARY * sqrt(K * A))
      interior BHH term + districting-boundary perimeter term (v0.3.0,
      frozen from pre-registered synthetic validation v1: kappa=0.9531,
      fit on square+rect4x1, 100% holdout coverage on disk/L-shape/
      asymptotic/K-invariance sets; Fangshan cross-check 0.906-0.962).
- dense_revisit (f >= 3.0, weekly-contract regime): Steele/BvNW dilution
  evaluated on the UNIFORM normalized field (max smoothing scale) gives
      monthly = BETA * c * sqrt(V * A * K)
  which is an UPPER ANCHOR: K daily sets thinning a territory they revisit
  cannot be shorter than uniform-scatter dilution over the hull; compact
  districts land below it. The nonuniform Stieltjes integral variant was
  retracted (dimensional bug + cell degeneracy, spec §11.2).
- 2.0 < f < 3.0: UNRELIABLE_TRANSITION - sparse value reported with
  transition_flag + regime_margin (dense/sparse ratio; the two forms differ
  by sqrt(K)*r, smoothing would be fudge, spec §3.3).

Accuracy ceiling (spec §11, literature + Guangzhou matrix): point-to-point
estimation on real road networks is 21-32% MAPE (PRC 2011; Figliozzi 2007);
the frozen dilution model measures 22.5% MAPE / 7-of-10 within [0.60,1.40]
on 10 weekly-contract lines. model_form_uncertainty carries this honestly.
Never a statistical confidence interval, never an optimality proof.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from spatial_ca.geometry import (CleanResult, CRS_UNCONFIRMED, Point,
                                 hull_area_lonlat_km2, project_km)
from spatial_ca.terrain import get_city_terrain_and_circuity

BETA = 0.7124
# v0.3.0 boundary term (Daganzo partition-model lineage): recursive-bisection
# districting adds a perimeter-like term kappa*sqrt(K*A) to the BHH interior.
# kappa frozen from synthetic validation v1 (fit square+rect4x1 Part A,
# 100% holdout coverage on disk+Lshape+asymptotics+K-invariance sets):
# docs/superpowers/plans/2026-09-11-synthetic-validation-design.md
KAPPA_BOUNDARY = 0.9531
BETA_BOUNDS = [0.6277, 0.9038]
ENVELOPE_VERSION = "v1"
# (lo, hi) multipliers on mid, by circuity provenance - policy, not stats
ENVELOPES = {
    "user_override": (0.88, 1.12),
    "rep_history": (0.85, 1.18),
    "city_observed": (0.82, 1.20),
    "city_prior": (0.75, 1.30),
    "national_default": (0.75, 1.30),
}
# dense regime: ONE-SIDED upper-anchor envelope; hi = 1.40 keeps the
# measured Guangzhou max legit ratio, lo = 0.25 only catches impossible
# undercounts (compact districts legitimately sit far below the anchor)
DENSE_ENVELOPE = (0.25, 1.40)
SPARSE_F, DENSE_F = 2.0, 3.0
MODEL_FORM = {
    "sparse_partitioned": "corridor_BHH_interior_plus_boundary",
    "dense_revisit": "dilution_uniform_field_upper_anchor",
    "UNRELIABLE_TRANSITION": "corridor_BHH_interior_plus_boundary",
}
MODEL_FORM_UNCERTAINTY = {"sparse_partitioned": 0.20,
                          "dense_revisit": 0.25,
                          "UNRELIABLE_TRANSITION": 0.35}
THIN_DAILY_VISITS = 4.0
# v0.3.0 input-side applicability flag (Beijing fresh-holdout, spec §5.6):
# stores whose NN scale sqrt(A_hull/n) < HOP_DENSE_LAMBDA_KM sit in ultra-dense
# urban territory where convex-hull uniformity and c~1.2-1.3 prioms break down
# (measured c_hop 1.9-3.1, coverage 4/10); regional lines (lambda >= 0.6 km)
# validated 7/8 with median ratio 1.010.
HOP_DENSE_LAMBDA_KM = 0.6
MIN_CELL_KM = 0.05
_LO_SLACK, _HI_SLACK = 0.90, 1.50    # status thresholds, version v1


def _provenance(city: Optional[str], override: Optional[float]) -> Dict:
    if override is not None:
        return {"value": float(override), "source": "user_override",
                "confidence": "DECLARED_BY_USER",
                "calibration_version": None, "sample_size": None}
    if city:
        t, c = get_city_terrain_and_circuity(city)
        return {"value": c, "source": "city_prior", "terrain": t,
                "confidence": "LOW", "calibration_version": "2026.09-p1",
                "sample_size": None}
    return {"value": 1.27, "source": "national_default",
            "confidence": "LOW", "calibration_version": "2026.09-p1",
            "sample_size": None}


def ca_band(clean: CleanResult, total_visits: int, available_workdays: int, *,
            visit_weights: Optional[Sequence[float]] = None,
            city: Optional[str] = None,
            circuity_override: Optional[float] = None,
            is_closed_tour: bool = False,
            including_confirmed_outlier: bool = False) -> Dict:
    if total_visits <= 0 or available_workdays <= 0:
        raise ValueError("total_visits and available_workdays must be positive")
    if clean.crs_status == CRS_UNCONFIRMED:
        raise ValueError("CRS_UNCONFIRMED: absolute-km model blocked (C1.3); "
                         "preassess() routes to structural diagnostics")
    pts = clean.points
    n = len(pts)
    area, dx, dy = hull_area_lonlat_km2(pts)
    circ = _provenance(city, circuity_override)

    uniform_assumed = visit_weights is None
    if uniform_assumed:
        weights: List[float] = [total_visits / n] * n
    else:
        if len(visit_weights) != n:
            raise ValueError("visit_weights length must equal cleaned point "
                             "count (remap via clean.index_map first)")
        weights = [float(w) for w in visit_weights]
        if sum(weights) <= 0:
            raise ValueError("visit_weights sum must be positive")

    hop_lambda = math.sqrt(area / max(1, n))
    f_revisit = total_visits / max(1, n)
    if f_revisit <= SPARSE_F:
        regime = "sparse_partitioned"
    elif f_revisit >= DENSE_F:
        regime = "dense_revisit"
    else:
        regime = "UNRELIABLE_TRANSITION"

    # sparse/transition: BHH interior + boundary term (v0.3.0)
    sparse_mid = circ["value"] * (
        BETA * math.sqrt(max(0.0, total_visits * area))
        + KAPPA_BOUNDARY * math.sqrt(max(0.0, available_workdays * area)))
    boundary_km = circ["value"] * KAPPA_BOUNDARY * math.sqrt(
        max(0.0, available_workdays * area))
    # dense upper anchor: uniform-field Steele dilution, deliberately NOT
    # coupled to the boundary term (synthetic Part B: 100% anchor coverage
    # as-is; coupling would let it fall below compact-district truths)
    dense_mid = BETA * circ["value"] * math.sqrt(
        max(0.0, total_visits * area * available_workdays))
    mid = dense_mid if regime == "dense_revisit" else sparse_mid
    cell_rule = None

    if regime == "dense_revisit":
        lo_mult, hi_mult = DENSE_ENVELOPE
    else:
        lo_mult, hi_mult = ENVELOPES[circ["source"]]
        daily_visits = total_visits / available_workdays
        if daily_visits < THIN_DAILY_VISITS:
            lo_mult -= 0.07
            hi_mult += 0.15
    if is_closed_tour:
        hi_mult += 0.05

    lo, hi = mid * lo_mult, mid * hi_mult
    margin = (round(dense_mid / sparse_mid, 3)
              if regime == "UNRELIABLE_TRANSITION" and sparse_mid > 0 else None)
    daily_visits = total_visits / available_workdays

    return {
        "daily_km": round(mid / available_workdays, 2),
        "monthly_km": round(mid, 2),
        "reference_mid_km": round(mid, 2),
        "reference_band_km": [round(lo, 2), round(hi, 2)],
        "daily": {"mean_visits": round(daily_visits, 2),
                  "mid_km": round(mid / available_workdays, 2),
                  "band_km": [round(lo / available_workdays, 2),
                              round(hi / available_workdays, 2)]},
        "regime": regime,
        "visits_per_store": round(f_revisit, 2),
        "transition_flag": regime == "UNRELIABLE_TRANSITION",
        "regime_margin": margin,
        "boundary_term_km": round(boundary_km, 2) if regime != "dense_revisit" else None,
        "model_form": MODEL_FORM[regime],
        "model_form_uncertainty": MODEL_FORM_UNCERTAINTY[regime],
        "anchor": ("upper" if regime == "dense_revisit" else "central"),
        "band_method": f"heuristic_policy_envelope_{ENVELOPE_VERSION}",
        "envelope_version": ENVELOPE_VERSION,
        "envelope_multipliers": [round(lo_mult, 3), round(hi_mult, 3)],
        "statistical_confidence_interval": False,
        "geometry": {"hull_area_km2": round(area, 2),
                     "dx_km": round(dx, 2), "dy_km": round(dy, 2)},
        "circuity": circ,
        "beta": {"point_estimate": BETA,
                 "published_mathematical_bounds": BETA_BOUNDS,
                 "bounds_used_in_operational_band": False,
                 "source": "BHH1959/Applegate2006",
                 "confidence": "uniform-asymptotic; transfer error "
                               "unquantified (see model_form_uncertainty)"},
        "crs_status": clean.crs_status,
        "degenerate_geometry": area <= 0.0 or area < 1e-4 * max(1e-9, dx * dy),
        "small_sample_warning": daily_visits < THIN_DAILY_VISITS,
        "hop_lambda_km": round(hop_lambda, 3),
        "ultra_dense_urban_warning": hop_lambda < HOP_DENSE_LAMBDA_KM,
        "including_confirmed_outlier": including_confirmed_outlier,
        "is_closed_tour": is_closed_tour,
        "assumptions": [f"regime:{regime}"]
        + (["ASSUMED_UNIFORM_VISIT_DENSITY"] if uniform_assumed else [])
        + ["inter_stop_distance_only", "K_from:available_workdays"]
        + (["ULTRA_DENSE_URBAN territory: treat as lower bound only; "
            "c_hop measured 1.9-3.1 on Beijing holdout, prior c understates"]
           if hop_lambda < HOP_DENSE_LAMBDA_KM else []),
    }


def classify(measured_km: float, band: Dict) -> str:
    if band.get("degenerate_geometry"):
        return "NOT_ASSESSED_DEGENERATE_GEOMETRY"
    lo, hi = band["reference_band_km"]
    if measured_km < lo * _LO_SLACK:
        return "BELOW_CA_REFERENCE"
    if measured_km <= hi:
        return "CONSISTENT_WITH_CA_REFERENCE"
    if measured_km <= hi * _HI_SLACK:
        return "ABOVE_CA_REFERENCE"
    return "STRONGLY_INCONSISTENT_WITH_CA"
