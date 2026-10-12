"""spatial-ca command line interface (v0.3.1).

Stdlib-only thin wrapper over preassess(). Reads store coordinates from CSV
or JSON and prints the PreAssessment as markdown or JSON.

Examples:
    spatial-ca preassess stores.csv --source-crs GCJ02 \
        --total-visits 1200 --available-workdays 22 --format markdown
    spatial-ca preassess stores.csv --source-crs WGS84 --total-visits 800 \
        --available-workdays 20 --confirm-drop 17 --confirm-keep 42
    spatial-ca version
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from typing import List, Tuple

from spatial_ca import __version__
from spatial_ca.report import MEASURED_SCOPES, preassess


def _load_coords_csv(path: str, lng_col: str, lat_col: str) -> List[Tuple[float, float]]:
    coords: List[Tuple[float, float]] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise SystemExit(f"empty CSV: {path}")
        names = reader.fieldnames
        if lng_col not in names or lat_col not in names:
            raise SystemExit(
                f"columns {lng_col!r}/{lat_col!r} not in {names}; "
                "use --lng-col/--lat-col to override")
        for row in reader:
            raw_lng, raw_lat = row[lng_col], row[lat_col]
            if raw_lng is None or raw_lat is None:
                coords.append((float("nan"), float("nan")))  # keep lineage index
                continue
            try:
                coords.append((float(raw_lng), float(raw_lat)))
            except ValueError:
                coords.append((float("nan"), float("nan")))
    return coords


def _load_coords_json(path: str) -> List[Tuple[float, float]]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return [(float(p[0]), float(p[1])) for p in data]


def _int_list(value: str) -> Tuple[int, ...]:
    return tuple(int(v) for v in value.split(",") if v.strip()) if value else ()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="spatial-ca",
        description="Mapless scale pre-assessment for single-rep visit planning.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_pre = sub.add_parser(
        "preassess", help="five-gate pre-assessment (spec v2.1)")
    p_pre.add_argument("coords", help="CSV or JSON file of [lng, lat] points")
    p_pre.add_argument("--source-crs", required=True,
                       choices=["WGS84", "GCJ02", "BD09", "UNKNOWN"],
                       help="declared CRS of the input (UNKNOWN -> STRUCTURE_ONLY)")
    p_pre.add_argument("--total-visits", type=int, required=True)
    p_pre.add_argument("--available-workdays", type=int, required=True)
    p_pre.add_argument("--city", default=None,
                       help="city name for terrain circuity prior")
    p_pre.add_argument("--measured-km", type=float, default=None)
    p_pre.add_argument("--measured-scope", default="inter_stop",
                       choices=list(MEASURED_SCOPES))
    p_pre.add_argument("--is-closed-tour", action="store_true")
    p_pre.add_argument("--confirm-drop", default="", help="comma-separated indexes")
    p_pre.add_argument("--confirm-keep", default="", help="comma-separated indexes")
    p_pre.add_argument("--lng-col", default="lng", help="CSV longitude column")
    p_pre.add_argument("--lat-col", default="lat", help="CSV latitude column")
    p_pre.add_argument("--format", default="markdown", choices=["markdown", "json"])

    sub.add_parser("version", help="print version")

    args = parser.parse_args(argv)

    if args.command == "version":
        print(f"spatial-ca {__version__}")
        return 0

    if args.coords.lower().endswith(".json"):
        coords = _load_coords_json(args.coords)
    else:
        coords = _load_coords_csv(args.coords, args.lng_col, args.lat_col)
    if not coords:
        raise SystemExit("no coordinates loaded")

    result = preassess(
        coords,
        total_visits=args.total_visits,
        available_workdays=args.available_workdays,
        source_crs=args.source_crs,
        city=args.city,
        is_closed_tour=args.is_closed_tour,
        confirm_drop=_int_list(args.confirm_drop),
        confirm_keep=_int_list(args.confirm_keep),
        measured_km=args.measured_km,
        measured_scope=args.measured_scope,
    )
    if args.format == "json":
        json.dump(result.to_dict(), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print(result.to_markdown())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
