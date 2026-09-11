"""preassess(): the governance pipeline (spec v2.1 §3/§4).

Gates: PASSED / PASSED_WITH_INVALID_ROWS_DROPPED /
INCLUDING_CONFIRMED_OUTLIER / BLOCKED_BY_DATA_QUALITY /
STRUCTURE_ONLY (C1.3: no absolute-km band on unconfirmed CRS).

v2.1: dense-revisit regime is ASSESSED (dilution model, BvNW 1991; Guangzhou
matrix 22.5% MAPE = literature road-network ceiling), never refused;
degenerate geometry yields NOT_ASSESSED_DEGENERATE_GEOMETRY.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from spatial_ca.band import ca_band, classify
from spatial_ca.geometry import (CRS_UNCONFIRMED, CleanResult, Point,
                                 clean_coordinates, hull_area_lonlat_km2)
from spatial_ca.sanity import adjudicate, find_suspects

PASSED = "PASSED"
PASSED_WITH_INVALID_ROWS_DROPPED = "PASSED_WITH_INVALID_ROWS_DROPPED"
INCLUDING_CONFIRMED_OUTLIER = "INCLUDING_CONFIRMED_OUTLIER"
BLOCKED_BY_DATA_QUALITY = "BLOCKED_BY_DATA_QUALITY"
STRUCTURE_ONLY = "STRUCTURE_ONLY"

MEASURED_SCOPES = ("inter_stop", "with_stem_round_trip")


@dataclass
class PreAssessment:
    gate: str
    lineage: Dict
    k: Dict
    band: Optional[Dict]
    structural: Dict
    assessment: Dict
    meta: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {"gate": self.gate, "lineage": self.lineage, "k": self.k,
                "band": self.band, "structural": self.structural,
                "assessment": self.assessment, "meta": self.meta}

    def to_markdown(self) -> str:
        out = [f"# Spatial pre-assessment — gate: **{self.gate}**", ""]
        ln = self.lineage
        out.append(f"- lineage: invalid_dropped={ln['dropped_invalid']} "
                   f"user_dropped={ln['dropped_by_user']} "
                   f"kept_outliers={ln['kept_confirmed_outlier']} "
                   f"crs={ln['crs_status']}")
        out.append(f"- K: available_workdays={self.k['available_workdays']} "
                   f"active_visit_days={self.k['active_visit_days']}")
        if self.band is not None:
            b = self.band
            lo, hi = b["reference_band_km"]
            out.append(f"- estimate: **{b['daily_km']} km/day**, "
                       f"{b['monthly_km']} km/month "
                       f"(regime={b['regime']}, model={b['model_form']})")
            out.append(f"- reference band: [{lo}, {hi}] km "
                       f"({b['band_method']}, not a statistical CI; "
                       f"model_form_uncertainty=±{b['model_form_uncertainty']:.0%})")
            if b.get("regime_margin") is not None:
                out.append(f"- regime_margin (dense/sparse): x{b['regime_margin']} "
                           f"(UNRELIABLE_TRANSITION: regime boundary, both "
                           f"forms reported, no smoothing)")
        else:
            out.append(f"- estimate: none ({self.assessment['status']})")
        out.append(f"- assessment: {self.assessment['status']}")
        if self.assessment.get("diagnostic_note"):
            out.append(f"  - {self.assessment['diagnostic_note']}")
        return "\n".join(out)


def _structural(clean: CleanResult, suspects: List[Dict], *,
                frame_relative: bool) -> Dict:
    area, dx, dy = hull_area_lonlat_km2(clean.points)
    return {"frame_relative": frame_relative,
            "n_points": len(clean.points),
            "hull_area_km2": round(area, 2),
            "span_km": [round(dx, 2), round(dy, 2)],
            "suspects": suspects}


def _rebuilt_clean(base: CleanResult, adj: Dict) -> CleanResult:
    return CleanResult(points=adj["points"],
                       kept_indices=adj["original_indices"],
                       dropped=base.dropped,
                       source_crs=base.source_crs,
                       crs_status=base.crs_status)


def _remap_weights(visit_weights: Sequence[float],
                   kept_indices: Sequence[int]) -> List[float]:
    """Map weights given in ORIGINAL row order onto cleaned points.

    visit_weights[i] refers to original row i; invalid rows keep no slot, so
    the estimator consumes weights in kept_indices order. Length must equal
    the original input length (rows dropped by bbox still hold a weight).
    """
    return [float(visit_weights[i]) for i in kept_indices]


def preassess(coords: Sequence[Point], *, total_visits: int,
              available_workdays: int, source_crs: str,
              visit_weights: Optional[Sequence[float]] = None,
              city: Optional[str] = None,
              circuity_override: Optional[float] = None,
              is_closed_tour: bool = False,
              confirm_drop: Sequence[int] = (),
              confirm_keep: Sequence[int] = (),
              measured_km: Optional[float] = None,
              measured_scope: str = "inter_stop") -> PreAssessment:
    if measured_scope not in MEASURED_SCOPES:
        raise ValueError(f"measured_scope must be one of {MEASURED_SCOPES}")
    if visit_weights is not None and len(visit_weights) != len(coords):
        raise ValueError("visit_weights length must equal coords length")
    clean = clean_coordinates(coords, source_crs=source_crs)
    suspects = find_suspects(clean)
    adj = adjudicate(clean, suspects, confirm_drop=confirm_drop,
                     confirm_keep=confirm_keep)
    dropped_invalid = [d["index"] for d in clean.dropped]
    lineage = {"dropped_invalid": dropped_invalid,
               "dropped_by_user": adj.get("dropped_by_user", []),
               "kept_confirmed_outlier": adj.get("kept_confirmed_outlier", []),
               "crs_status": clean.crs_status,
               "source_crs": source_crs}
    k = {"calendar_period_days": None,
         "available_workdays": available_workdays,
         "active_visit_days": None}

    # branch 1: unadjudicated fly-outliers block every absolute conclusion
    if adj["decision"] == "BLOCKED_BY_DATA_QUALITY":
        return PreAssessment(
            gate=BLOCKED_BY_DATA_QUALITY, lineage=lineage, k=k, band=None,
            structural=_structural(clean, suspects, frame_relative=True),
            assessment={"status": "NOT_ASSESSED_DATA_QUALITY_BLOCKED",
                        "unresolved_suspects": adj["unresolved"],
                        "note": "adjudicate every suspect (confirm_drop/"
                                "confirm_keep) before trusting any km"})

    # branch 2: CRS unconfirmed -> structure only, band blocked (C1.3)
    if clean.crs_status == CRS_UNCONFIRMED:
        return PreAssessment(
            gate=STRUCTURE_ONLY, lineage=lineage, k=k, band=None,
            structural=_structural(clean, suspects, frame_relative=True),
            assessment={"status": "NOT_ASSESSED_CRS_UNCONFIRMED",
                        "note": "declare source_crs (WGS84/GCJ02/BD09) to "
                                "unlock the absolute-km estimate"})

    effective = (_rebuilt_clean(clean, adj)
                 if (adj["dropped_by_user"] or adj["kept_confirmed_outlier"])
                 else clean)
    kept = adj["kept_confirmed_outlier"]
    if dropped_invalid:
        gate = PASSED_WITH_INVALID_ROWS_DROPPED
    elif kept:
        gate = INCLUDING_CONFIRMED_OUTLIER
    else:
        gate = PASSED

    w = (_remap_weights(visit_weights, list(clean.kept_indices))
         if visit_weights is not None else None)
    if w is not None and (adj["dropped_by_user"] or adj["kept_confirmed_outlier"]):
        # re-filter rebuilt rows through the same index list
        keep_orig = set(adj["original_indices"])
        pairs = [(o, wt) for o, wt in zip(clean.kept_indices, w)
                 if o in keep_orig]
        w = [wt for _, wt in pairs]

    band = ca_band(effective, total_visits=total_visits,
                   available_workdays=available_workdays,
                   visit_weights=w, city=city,
                   circuity_override=circuity_override,
                   is_closed_tour=is_closed_tour,
                   including_confirmed_outlier=bool(kept))

    if measured_km is None:
        assessment: Dict = {"status": ("NOT_ASSESSED_DEGENERATE_GEOMETRY"
                                       if band["degenerate_geometry"]
                                       else "REFERENCE_ONLY")}
    elif band["degenerate_geometry"]:
        assessment = {"status": "NOT_ASSESSED_DEGENERATE_GEOMETRY",
                      "note": "collinear/insufficient points: no "
                              "2D service area to benchmark"}
    else:
        assessment = {"status": classify(measured_km, band),
                      "measured_total_km": round(measured_km, 2),
                      "diagnostic_note": (
                          "possible causes: coordinate errors, CRS mismatch, "
                          "cross-district scheduling, depot stems or business "
                          "constraints - verify with road distances before "
                          "concluding"),
                      "note_level": "OPERATIONAL"}
        if measured_scope != "inter_stop":
            assessment["scope_caveat"] = (
                "measured includes stems/round-trip; model estimates "
                "inter-stop distance only - compare with care")
    return PreAssessment(gate=gate, lineage=lineage, k=k, band=band,
                         structural=_structural(effective, suspects,
                                                frame_relative=False),
                         assessment=assessment,
                         meta={"model_form": band["model_form"],
                               "band_method": band["band_method"],
                               "envelope_version": band["envelope_version"],
                               "crs_status": clean.crs_status,
                               "city": city,
                               "circuity": band["circuity"]})
