"""Geometry primitives: CRS declaration, index-preserving cleaning, hulls.

Design contracts (MEASUREMENT_CONTRACT.md items C1, C2, C6):
- The caller MUST declare ``source_crs``; the framework never guesses a CRS
  label and can NEVER detect a whole-batch GCJ/WGS mislabel from internal
  geometry alone (rigid shifts leave pairwise structure invariant - a
  theorem, not a limitation to be engineered away).
- Cleaning is index-preserving: every kept point carries its original row
  index so business plans (store_id / row references) never drift silently.
- Hull helpers are split by coordinate semantics: ``hull_area_xy`` takes
  projected km points, ``hull_area_lonlat_km2`` takes WGS-84 degrees.
  No function guesses which one it received.

Zero third-party dependencies (stdlib math only).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

Point = Tuple[float, float]
XY = Point  # projected kilometres, local frame

# Validity windows
CN_BBOX = (73.0, 3.0, 136.0, 54.0)        # mainland China (lng, lat)
GLOBAL_BBOX = (-180.0, -90.0, 180.0, 90.0)

# CRS identifiers (contract C1)
WGS84 = "WGS84"
GCJ02 = "GCJ02"
BD09 = "BD09"
UNKNOWN = "UNKNOWN"
VALID_CRS = (WGS84, GCJ02, BD09, UNKNOWN)

# CRS status outcomes (never silently merged)
CONFIRMED_WGS84 = "CONFIRMED_WGS84"
CONVERTED_FROM_GCJ02 = "CONVERTED_FROM_GCJ02"
CONVERTED_FROM_BD09 = "CONVERTED_FROM_BD09"
CRS_UNCONFIRMED = "CRS_UNCONFIRMED"

_KY = 110.574  # km per degree latitude (WGS-84 meridional mean)


def _kx(mean_lat_deg: float) -> float:
    return 111.320 * math.cos(math.radians(mean_lat_deg))


# ---------------------------------------------------------------------------
# datum transforms (public closed-form algorithms; Krasovsky 1940 params)
# ---------------------------------------------------------------------------
# WP03: 转换函数收敛到 coords-core v0.1.0 (唯一事实源)。
# 行为兼容说明: 本仓公开 API gcj02_to_wgs84 历史上是闭式一步 de-bias,
# 因此转发到 coords_core 的 closed_form 层 (位级一致), 迭代规范层见 coords_core。
from coords_core import (  # noqa: E402
    bd09_to_gcj02,
    bd09_to_wgs84,
    gcj02_to_wgs84_closed_form as gcj02_to_wgs84,
    out_of_china as _out_of_china,
)

# ---------------------------------------------------------------------------
# index-preserving cleaning
# ---------------------------------------------------------------------------
@dataclass
class CleanResult:
    """Kept points + full lineage. Never renumbers silently.

    ``points`` are the effective frame: WGS-84 when the source CRS was
    declared (and thus converted), raw input when CRS_UNCONFIRMED.
    """
    points: List[Point]
    kept_indices: List[int]                 # original row index of each kept pt
    dropped: List[Dict] = field(default_factory=list)
    source_crs: str = UNKNOWN
    crs_status: str = CRS_UNCONFIRMED

    @property
    def index_map(self) -> Dict[int, int]:
        """original_row -> clean_position (the ONLY legal way to map plans)."""
        return {orig: pos for pos, orig in enumerate(self.kept_indices)}


def clean_coordinates(coords: Sequence[Point], *,
                      source_crs: str = UNKNOWN,
                      bbox: Tuple[float, float, float, float] = CN_BBOX,
                      ) -> CleanResult:
    """Validate + (only when declared) datum-transform, never losing indices.

    UNKNOWN performs NO conversion and tags CRS_UNCONFIRMED: absolute km
    conclusions must be blocked downstream (contract C1.3).
    Raises ValueError only when nothing survives validation.
    """
    if source_crs not in VALID_CRS:
        raise ValueError(f"source_crs must be one of {VALID_CRS}")
    if source_crs == WGS84:
        status = CONFIRMED_WGS84
    elif source_crs == GCJ02:
        status = CONVERTED_FROM_GCJ02
    elif source_crs == BD09:
        status = CONVERTED_FROM_BD09
    else:
        status = CRS_UNCONFIRMED

    kept: List[Point] = []
    kept_idx: List[int] = []
    dropped: List[Dict] = []
    for i, pt in enumerate(coords):
        bad: Optional[str] = None
        lng = lat = None
        if pt is None or len(pt) != 2 or pt[0] is None or pt[1] is None:
            bad = "null"
        else:
            try:
                lng, lat = float(pt[0]), float(pt[1])
            except (TypeError, ValueError):
                bad = "non_numeric"
            else:
                if math.isnan(lng) or math.isnan(lat):
                    bad = "nan"
                elif _out_of_china(lng, lat):
                    # datum-agnostic sanity window: applies pre-conversion to
                    # GCJ02/BD09 inputs too (offsets are ~km, not degrees)
                    bad = "outside_bbox"
        if bad is not None:
            dropped.append({"index": i, "reason": bad, "lng": lng, "lat": lat})
            continue
        if status == CONVERTED_FROM_GCJ02:
            lng, lat = gcj02_to_wgs84(lng, lat)
        elif status == CONVERTED_FROM_BD09:
            lng, lat = bd09_to_wgs84(lng, lat)
        kept.append((lng, lat))
        kept_idx.append(i)

    if not kept:
        raise ValueError("all coordinates were dropped as invalid")
    return CleanResult(points=kept, kept_indices=kept_idx, dropped=dropped,
                       source_crs=source_crs, crs_status=status)


# ---------------------------------------------------------------------------
# hulls: two entry points, two coordinate semantics
# ---------------------------------------------------------------------------
def _hull_area_from_xy(pts_km: Sequence[XY]) -> float:
    pts = sorted({(round(p[0], 6), round(p[1], 6)) for p in pts_km})
    if len(pts) < 3:
        return 0.0

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: List[XY] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: List[XY] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    return 0.5 * abs(sum(
        hull[i][0] * hull[(i + 1) % len(hull)][1]
        - hull[(i + 1) % len(hull)][0] * hull[i][1]
        for i in range(len(hull))))


def project_km(coords_wgs84: Sequence[Point]) -> Tuple[List[XY], float, float,
                                                       float, float]:
    """Local equirectangular frame around the set's min corner.

    Returns (xy_km, min_lng, min_lat, kx, ky). Carry the frame alongside
    projected points; feeding xy back into lonlat APIs is forbidden (C2.2).
    """
    lngs = [p[0] for p in coords_wgs84]
    lats = [p[1] for p in coords_wgs84]
    min_lng, min_lat = min(lngs), min(lats)
    mean_lat = sum(lats) / len(lats)
    kx, ky = _kx(mean_lat), _KY
    xy = [((p[0] - min_lng) * kx, (p[1] - min_lat) * ky) for p in coords_wgs84]
    return xy, min_lng, min_lat, kx, ky


def hull_area_xy(pts_km: Sequence[XY]) -> Tuple[float, float, float]:
    """(area, dx, dy) in km for ALREADY-PROJECTED points. No re-projection."""
    if not pts_km:
        return 0.0, 0.0, 0.0
    xs = [p[0] for p in pts_km]
    ys = [p[1] for p in pts_km]
    return (_hull_area_from_xy(pts_km),
            max(xs) - min(xs), max(ys) - min(ys))


def hull_area_lonlat_km2(coords_wgs84: Sequence[Point]) -> Tuple[float, float, float]:
    """(area, dx, dy) in km from WGS-84 degree points (projects internally)."""
    if not coords_wgs84:
        return 0.0, 0.0, 0.0
    xy, _, _, _, _ = project_km(coords_wgs84)
    return hull_area_xy(xy)
