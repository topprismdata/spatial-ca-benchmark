"""Geometry primitives: CRS declaration, index-preserving cleaning, hulls.

Design contracts (MEASUREMENT_CONTRACT.md items 1, 2, 6; review M0 items):
- The caller MUST declare ``source_crs``; the framework never guesses a CRS
  label and can NEVER detect a whole-batch GCJ/WGS mislabel from internal
  geometry alone (rigid shifts leave pairwise structure invariant).
- Cleaning is index-preserving: every kept point carries its original row
  index so business plans (store_id / row references) never silently drift.
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

# CRS identifiers (contract item 1)
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
_A = 6378245.0
_EE = 0.00669342162296594323
_XPI = math.pi * 3000.0 / 180.0


def _out_of_china(lng: float, lat: float) -> bool:
    return not (CN_BBOX[0] <= lng <= CN_BBOX[2] and CN_BBOX[1] <= lat <= CN_BBOX[3])


def _transform_lat(lng: float, lat: float) -> float:
    ret = (-100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat
           + 0.1 * lng * lat + 0.2 * math.sqrt(abs(lng)))
    ret += (20.0 * math.sin(6.0 * lng * math.pi)
            + 20.0 * math.sin(2.0 * lng * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * math.pi)
            + 40.0 * math.sin(lat / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * math.pi)
            + 320.0 * math.sin(lat * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lng(lng: float, lat: float) -> float:
    ret = (300.0 + lng + 2.0 * lat + 0.1 * lng * lng
           + 0.1 * lng * lat + 0.1 * math.sqrt(abs(lng)))
    ret += (20.0 * math.sin(6.0 * lng * math.pi)
            + 20.0 * math.sin(2.0 * lng * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lng * math.pi)
            + 40.0 * math.sin(lng / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lng / 12.0 * math.pi)
            + 300.0 * math.sin(lng / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def gcj02_to_wgs84(lng: float, lat: float) -> Point:
    """Closed-form one-step de-bias. Points outside China pass through."""
    if _out_of_china(lng, lat):
        return lng, lat
    d_lat = _transform_lat(lng - 105.0, lat - 35.0)
    d_lng = _transform_lng(lng - 105.0, lat - 35.0)
    rad_lat = lat / 180.0 * math.pi
    magic = math.sin(rad_lat)
    magic = 1 - _EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    d_lat = (d_lat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrt_magic) * math.pi)
    d_lng = (d_lng * 180.0) / (_A / sqrt_magic * math.cos(rad_lat) * math.pi)
    return lng - d_lng, lat - d_lat


def bd09_to_gcj02(lng: float, lat: float) -> Point:
    x = abs(lng - 0.0065)
    y = abs(lat - 0.006)
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * _XPI)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * _XPI)
    return z * math.cos(theta), z * math.sin(theta)


def bd09_to_wgs84(lng: float, lat: float) -> Point:
    gl, ga = bd09_to_gcj02(lng, lat)
    return gcj02_to_wgs84(gl, ga)


# ---------------------------------------------------------------------------
# index-preserving cleaning
# ---------------------------------------------------------------------------
@dataclass
class CleanResult:
    """Kept points in WGS-84 (or raw when CRS unknown) + full lineage."""
    points: List[Point]
    kept_indices: List[int]                     # original row index of each kept pt
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
    """Validate + (optionally) datum-transform, never losing indices.

    - ``source_crs`` must be one of WGS84/GCJ02/BD09/UNKNOWN.
    - UNKNOWN: NO conversion is performed and the result is tagged
      ``CRS_UNCONFIRMED``; downstream reference bands must downgrade their
      conclusions and the caller owns the label risk (contract item 1).
    - Raises ValueError only when nothing survives validation.
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
                elif not (bbox[0] <= lng <= bbox[2] and bbox[1] <= lat <= bbox[3]):
                    bad = "outside_bbox"
        if bad is not None:
            dropped.append({"index": i, "reason": bad,
                            "lng": lng, "lat": lat})
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
# hulls: two functions, two coordinate semantics
# ---------------------------------------------------------------------------
def _hull_from_xy(pts_km: Sequence[XY]) -> float:
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


def hull_area_xy(pts_km: Sequence[XY]) -> Tuple[float, float, float]:
    """Area/dx/dy in km for ALREADY-PROJECTED points. No re-projection."""
    if not pts_km:
        return 0.0, 0.0, 0.0
    xs = [p[0] for p in pts_km]
    ys = [p[1] for p in pts_km]
    return _hull_from_xy(pts_km), max(xs) - min(xs), max(ys) - min(ys)


def project_km(coords_wgs84: Sequence[Point]) -> Tuple[List[XY], float, float,
                                                       float, float]:
    """Local equirectangular frame around the point set's min corner.

    Returns (xy_km, min_lng, min_lat, kx, ky). The frame (origin + km/deg
    scales) MUST be carried alongside the projected points; feeding xy back
    into lonlat APIs is forbidden by contract.
    """
    lngs = [p[0] for p in coords_wgs84]
    lats = [p[1] for p in coords_wgs84]
    min_lng, min_lat = min(lngs), min(lats)
    mean_lat = sum(lats) / len(lats)
    kx, ky = _kx(mean_lat), _KY
    xy = [((p[0] - min_lng) * kx, (p[1] - min_lat) * ky) for p in coords_wgs84]
    return xy, min_lng, min_lat, kx, ky


def hull_area_lonlat_km2(coords_wgs84: Sequence[Point]) -> Tuple[float, float, float]:
    """Area/dx/dy in km from WGS-84 degree points (projects internally)."""
    if not coords_wgs84:
        return 0.0, 0.0, 0.0
    xy, _, _, _, _ = project_km(coords_wgs84)
    return hull_area_xy(xy)
