"""Pure-geometry primitives: coordinate cleaning, GCJ-02 conversion, convex hull.

Zero third-party dependencies: everything here is stdlib math only.
"""

from __future__ import annotations

import math
from typing import Iterable, List, Optional, Sequence, Tuple

Point = Tuple[float, float]  # (lng, lat) in degrees

# Mainland-China bounding box used to reject impossible / placeholder coords.
_CN_LNG_RANGE = (73.0, 136.0)
_CN_LAT_RANGE = (3.0, 54.0)

_KY = 110.574  # km per degree latitude (WGS-84 meridional mean)


def _kx(mean_lat_deg: float) -> float:
    """km per degree longitude at a given latitude."""
    return 111.320 * math.cos(math.radians(mean_lat_deg))


# ---------------------------------------------------------------------------
# GCJ-02 ("Mars coordinates") -> WGS-84: public closed-form transform using
# the Krasovsky 1940 ellipsoid parameters.
# ---------------------------------------------------------------------------
_A = 6378245.0
_EE = 0.00669342162296594323


def _out_of_china(lng: float, lat: float) -> bool:
    return not (_CN_LNG_RANGE[0] <= lng <= _CN_LNG_RANGE[1]
                and _CN_LAT_RANGE[0] <= lat <= _CN_LAT_RANGE[1])


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
    """Convert one GCJ-02 point to WGS-84. Points outside China pass through."""
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


def clean_coordinates(
    coords: Iterable[Point],
    *,
    convert_gcj02: bool = True,
    bbox: Optional[Tuple[float, float, float, float]] = None,
) -> List[Point]:
    """Drop NaN/inf/out-of-range/placeholder points; optionally GCJ-02->WGS-84.

    ``bbox`` overrides the default mainland-China validity window
    ``(min_lng, min_lat, max_lng, max_lat)``.
    """
    lo_lng, lo_lat, hi_lng, hi_lat = bbox or (
        _CN_LNG_RANGE[0], _CN_LAT_RANGE[0], _CN_LNG_RANGE[1], _CN_LAT_RANGE[1])
    out: List[Point] = []
    for lng, lat in coords:
        if lng is None or lat is None:
            continue
        try:
            lng = float(lng)
            lat = float(lat)
        except (TypeError, ValueError):
            continue
        if math.isnan(lng) or math.isnan(lat) or math.isinf(lng) or math.isinf(lat):
            continue
        if not (lo_lng <= lng <= hi_lng and lo_lat <= lat <= hi_lat):
            continue
        out.append(gcj02_to_wgs84(lng, lat) if convert_gcj02 else (lng, lat))
    return out


def project_km(coords_wgs84: Sequence[Point]) -> Tuple[List[Point], float, float, float, float]:
    """Local equirectangular projection in km.

    Returns (points_km, min_lng, min_lat, kx, ky) so callers can reuse the
    same frame for multiple point sets (e.g. stores and centroids).
    """
    lngs = [p[0] for p in coords_wgs84]
    lats = [p[1] for p in coords_wgs84]
    min_lng, min_lat = min(lngs), min(lats)
    mean_lat = sum(lats) / len(lats)
    kx, ky = _kx(mean_lat), _KY
    pts = [((p[0] - min_lng) * kx, (p[1] - min_lat) * ky) for p in coords_wgs84]
    return pts, min_lng, min_lat, kx, ky


def compute_convex_hull_area_km2(
    coords_wgs84: Sequence[Point],
) -> Tuple[float, float, float]:
    """Return ``(hull_area_km2, dx_km, dy_km)`` for WGS-84 points.

    Local equirectangular projection (metre-accurate at district scale),
    Andrew's monotone-chain convex hull, shoelace area. Degenerate inputs
    (< 3 distinct points) yield ``(0.0, dx_km, dy_km)``.
    """
    if not coords_wgs84:
        return 0.0, 0.0, 0.0

    lngs = [p[0] for p in coords_wgs84]
    lats = [p[1] for p in coords_wgs84]
    min_lng, max_lng = min(lngs), max(lngs)
    min_lat, max_lat = min(lats), max(lats)
    mean_lat = sum(lats) / len(lats)

    kx = _kx(mean_lat)
    dx_km = (max_lng - min_lng) * kx
    dy_km = (max_lat - min_lat) * _KY

    if len(coords_wgs84) < 3:
        return 0.0, dx_km, dy_km

    pts = sorted({((p[0] - min_lng) * kx, (p[1] - min_lat) * _KY)
                  for p in coords_wgs84})
    if len(pts) <= 2:
        return 0.0, dx_km, dy_km

    def cross(o: Point, a: Point, b: Point) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: List[Point] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: List[Point] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]

    area_km2 = 0.5 * abs(sum(
        hull[i][0] * hull[(i + 1) % len(hull)][1]
        - hull[(i + 1) % len(hull)][0] * hull[i][1]
        for i in range(len(hull))
    ))
    return area_km2, dx_km, dy_km
