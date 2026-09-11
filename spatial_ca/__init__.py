"""spatial-ca-benchmark: mapless asymptotic route-length pre-assessment.

Decision unit: ONE sales rep / ONE planning period.
Built on the Beardwood-Halton-Hammersley (BHH) theorem, Daganzo's continuous
approximation for (periodic) vehicle routing, and a Price-of-Fairness style
efficiency-equity trade-off analytics - all closed-form, zero runtime
third-party dependencies.

Public API surface: see __all__ below. Heavy lifting lives in submodules
(geometry / sanity / daganzo / corridor / balance / sensitivity / report).
"""

from spatial_ca.daganzo import (  # noqa: F401
    K_CLOSED,
    K_OPEN,
    SpatialBenchmark,
    estimate_spatial_benchmark,
)
from spatial_ca.geometry import (  # noqa: F401
    clean_coordinates,
    compute_convex_hull_area_km2,
    gcj02_to_wgs84,
    project_km,
)
from spatial_ca.sanity import find_suspects  # noqa: F401
from spatial_ca.terrain import (  # noqa: F401
    CIRCUITY_PRESETS,
    get_city_terrain_and_circuity,
)

try:  # report/corridor/balance land in later milestones; keep imports soft
    from spatial_ca.report import PreAssessment, preassess  # noqa: F401
except ImportError:  # pragma: no cover
    pass

__version__ = "0.1.0"

__all__ = [
    "K_OPEN",
    "K_CLOSED",
    "SpatialBenchmark",
    "estimate_spatial_benchmark",
    "find_suspects",
    "clean_coordinates",
    "gcj02_to_wgs84",
    "project_km",
    "compute_convex_hull_area_km2",
    "CIRCUITY_PRESETS",
    "get_city_terrain_and_circuity",
    "PreAssessment",
    "preassess",
    "__version__",
]
