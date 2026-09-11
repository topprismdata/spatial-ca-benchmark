"""G2: CA reference band (NOT a statistical CI, NOT an optimality proof).

Single asymptotic constant BETA = 0.7124 (BHH leading term; Applegate et
al. 2006 computational estimate; published analytic bounds [0.6277, 0.9038]
are background, NOT band inputs - reviewer ruling). Open/closed day tours
share the same leading term; the difference is a lower-order endpoint
correction (Steele 1986), represented as POLICY WIDTH, never a second
constant. Corridor-regime period total T = BETA*c*sqrt(V*A) is K-invariant.

Band = mid x explicit versioned multipliers keyed by circuity provenance
("heuristic_policy_envelope_v1"). After held-out calibration (P10/P90 by
daily-n/terrain/shape strata, contract C10) a later release may rename it
empirically_calibrated_reference_band.
"""
from __future__ import annotations

import math
from typing import Dict, Optional

from spatial_ca.geometry import (CleanResult, CRS_UNCONFIRMED,
                                 hull_area_lonlat_km2)
from spatial_ca.terrain import get_city_terrain_and_circuity

BETA = 0.7124
BETA_BOUNDS = [0.6277, 0.9038]
ENVELOPE_VERSION = "v1"
# (lo_multiplier, hi_multiplier) by circuity provenance - policy, not stats
ENVELOPES = {
    "user_override": (0.88, 1.12),
    "rep_history": (0.85, 1.18),
    "city_observed": (0.82, 1.20),
    "city_prior": (0.75, 1.30),
    "national_default": (0.75, 1.30),
}
THIN_DAILY_VISITS = 4.0
THIN_WIDEN_LO = 0.07            # subtracted from lo mult (band widens down)
THIN_WIDEN_HI = 0.15            # added to hi mult
CLOSED_HI_EXTRA = 0.05          # endpoint/stem correction as policy widening
_LO_SLACK, _HI_SLACK = 0.90, 1.50    # status thresholds (version v1)


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
            city: Optional[str] = None,
            circuity_override: Optional[float] = None,
            is_closed_tour: bool = False,
            including_confirmed_outlier: bool = False) -> Dict:
    if total_visits <= 0 or available_workdays <= 0:
        raise ValueError("total_visits and available_workdays must be positive")
    if clean.crs_status == CRS_UNCONFIRMED:
        raise ValueError("CRS_UNCONFIRMED: absolute-km band blocked (C1.3); "
                         "preassess() routes to structural diagnostics")
    area, dx, dy = hull_area_lonlat_km2(clean.points)
    circ = _provenance(city, circuity_override)
    daily_visits = total_visits / available_workdays
    lo_mult, hi_mult = ENVELOPES[circ["source"]]
    thin = daily_visits < THIN_DAILY_VISITS
    if thin:
        lo_mult -= THIN_WIDEN_LO
        hi_mult += THIN_WIDEN_HI
    if is_closed_tour:
        hi_mult += CLOSED_HI_EXTRA
    mid = BETA * circ["value"] * math.sqrt(max(0.0, total_visits * area))
    lo, hi = mid * lo_mult, mid * hi_mult
    return {
        "reference_mid_km": round(mid, 2),
        "reference_band_km": [round(lo, 2), round(hi, 2)],
        "band_method": f"heuristic_policy_envelope_{ENVELOPE_VERSION}",
        "envelope_version": ENVELOPE_VERSION,
        "envelope_multipliers": [round(lo_mult, 3), round(hi_mult, 3)],
        "statistical_confidence_interval": False,
        "daily": {"mean_visits": round(daily_visits, 2),
                  "mid_km": round(mid / available_workdays, 2),
                  "band_km": [round(lo / available_workdays, 2),
                              round(hi / available_workdays, 2)]},
        "geometry": {"hull_area_km2": round(area, 2),
                     "dx_km": round(dx, 2), "dy_km": round(dy, 2)},
        "circuity": circ,
        "beta": {"point_estimate": BETA,
                 "published_mathematical_bounds": BETA_BOUNDS,
                 "bounds_used_in_operational_band": False,
                 "role": "BHH leading-term constant (unit square, closed "
                         "TSP); open/closed delta is lower-order, folded "
                         "into policy width"},
        "k_invariant_within_model": True,
        "crs_status": clean.crs_status,
        "degenerate_geometry": area <= 0.0,  # <3 pts/collinear -> band=[0,0];
        # report maps this to NOT_ASSESSED_DEGENERATE_GEOMETRY (V2.1 review)
        "small_sample_warning": thin,
        "including_confirmed_outlier": including_confirmed_outlier,
        "is_closed_tour": is_closed_tour,
        "assumptions": ["corridor_regime", "ASSUMED_UNIFORM_VISIT_DENSITY",
                        "inter_stop_distance_only",
                        "K_from:available_workdays"],
    }


def classify(measured_km: float, band: Dict) -> str:
    lo, hi = band["reference_band_km"]
    if measured_km < lo * _LO_SLACK:
        return "BELOW_CA_REFERENCE"
    if measured_km <= hi:
        return "CONSISTENT_WITH_CA_REFERENCE"
    if measured_km <= hi * _HI_SLACK:
        return "ABOVE_CA_REFERENCE"
    return "STRONGLY_INCONSISTENT_WITH_CA"
