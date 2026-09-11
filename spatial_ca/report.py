"""preassess(): the governance pipeline. State machine fixed by V2.1;
this module adds no policy of its own.

Gates: PASSED / PASSED_WITH_INVALID_ROWS_DROPPED /
INCLUDING_CONFIRMED_OUTLIER / BLOCKED_BY_DATA_QUALITY /
STRUCTURE_ONLY (C1.3: no absolute-km band on unconfirmed CRS).
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
            lo, hi = self.band["reference_band_km"]
            out.append(f"- CA reference band: **{self.band['reference_mid_km']}"
                       f" km**, envelope [{lo}, {hi}] km "
                       f"({self.band['band_method']}, not a statistical CI)")
        else:
            out.append(f"- band: none ({self.assessment['status']})")
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


def preassess(coords: Sequence[Point], *, total_visits: int,
              available_workdays: int, source_crs: str,
              city: Optional[str] = None,
              circuity_override: Optional[float] = None,
              is_closed_tour: bool = False,
              confirm_drop: Sequence[int] = (),
              confirm_keep: Sequence[int] = (),
              measured_km: Optional[float] = None,
              measured_scope: str = "inter_stop") -> PreAssessment:
    if measured_scope not in MEASURED_SCOPES:
        raise ValueError(f"measured_scope must be one of {MEASURED_SCOPES}")
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
                                "unlock the absolute-km reference band"})

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

    band = ca_band(effective, total_visits=total_visits,
                   available_workdays=available_workdays, city=city,
                   circuity_override=circuity_override,
                   is_closed_tour=is_closed_tour,
                   including_confirmed_outlier=bool(kept))

    # Dense-revisit refusal is INDEPENDENT of measured_km: the band itself
    # is structurally wrong here (Guangzhou holdout: 0/10 in-band, f=4.2-4.6,
    # underestimation ~2-3x), so it must never leak into the report at all.
    if band["regime"] == "dense_revisit":
        assessment = {"status": "NOT_ASSESSED_DENSE_VISIT_REGIME",
                      "visits_per_store": band["visits_per_store"],
                      "note": "stores revisited >2.5x per period: the month "
                              "re-sweeps districts; single-hull CA would "
                              "underestimate ~2-3x (Guangzhou holdout). "
                              "Awaiting district decomposition (0.2)."}
        return PreAssessment(gate="REFUSED_" + gate, lineage=lineage, k=k,
                             band=None,
                             structural=_structural(effective, suspects,
                                                    frame_relative=False),
                             assessment=assessment,
                             meta={"band_method": None,
                                   "envelope_version": None,
                                   "crs_status": clean.crs_status,
                                   "city": city,
                                   "circuity": band["circuity"]})

    if measured_km is None:
        assessment: Dict = {"status": "REFERENCE_ONLY"}
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
                "measured includes stems/round-trip; band models "
                "inter-stop distance only - compare with care")
    return PreAssessment(gate=gate, lineage=lineage, k=k, band=band,
                         structural=_structural(effective, suspects,
                                                frame_relative=False),
                         assessment=assessment,
                         meta={"band_method": (band or {}).get("band_method"),
                               "envelope_version": (band or {})
                               .get("envelope_version"),
                               "crs_status": clean.crs_status,
                               "city": city,
                               "circuity": (band or {}).get("circuity")})
