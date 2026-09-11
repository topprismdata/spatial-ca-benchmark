"""spatial-ca-benchmark: mapless scale-benchmark & pre-assessment for
single-rep visit planning. Evidence before trust.

Facade uses PEP 562 lazy exports so the package imports cleanly while
submodules land milestone by milestone (0.1.0 = contract + gate + band).
"""

from __future__ import annotations

import importlib
from typing import Any

__version__ = "0.3.0rc1"

_EXPORTS = {
    # geometry (0.1.0)
    "clean_coordinates": "spatial_ca.geometry",
    "CleanResult": "spatial_ca.geometry",
    "gcj02_to_wgs84": "spatial_ca.geometry",
    "bd09_to_wgs84": "spatial_ca.geometry",
    "hull_area_xy": "spatial_ca.geometry",
    "hull_area_lonlat_km2": "spatial_ca.geometry",
    "project_km": "spatial_ca.geometry",
    # terrain (0.1.0)
    "CIRCUITY_PRESETS": "spatial_ca.terrain",
    "get_city_terrain_and_circuity": "spatial_ca.terrain",
    # sanity gate (0.1.0)
    "find_suspects": "spatial_ca.sanity",
    "adjudicate": "spatial_ca.sanity",
    # band (0.1.0)
    "BETA": "spatial_ca.band",
    "ca_band": "spatial_ca.band",
    "classify": "spatial_ca.band",
    # report (0.1.0)
    "preassess": "spatial_ca.report",
    "PreAssessment": "spatial_ca.report",
    # deferred roadmap (0.2/0.3/0.4) - ImportError carries roadmap guidance
    "reference_corridors": "spatial_ca.corridor",
    "diagnose_plan": "spatial_ca.corridor",
    "dispersion_scenario_contrast": "spatial_ca.corridor",
    "cost_of_selected_equity_policy": "spatial_ca.equity",
}

__all__ = ["__version__", *_EXPORTS]


def __getattr__(name: str) -> Any:  # PEP 562
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    try:
        mod = importlib.import_module(target)
    except ImportError as exc:  # not shipped in this milestone
        raise ImportError(
            f"{name} lives in {target!r}, which is not available yet "
            f"(deferred by the 0.1.0 scope cut).") from exc
    return getattr(mod, name)


def __dir__():
    return sorted(__all__)
