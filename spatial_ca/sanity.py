"""G1 quality gate: exact nearest-neighbour fly-outliers + user adjudication.

V2.1: 0.1.0 uses EXACT brute-force O(N^2) NN. Typical single rep = 100-500
stores where this is comfortably sub-second; correctness beats throughput
(reviewer ruling). A provable-stopping ring-expansion grid is deferred to
0.2 with an equivalence test against this implementation.

Contract: C1.2 (whole-batch rigid CRS shift is UNDETECTABLE from internal
geometry - a theorem - so this module does not claim otherwise), C8 (gate
fails closed until every suspect is adjudicated).
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence

from spatial_ca.geometry import CleanResult, project_km


def find_suspects(clean: CleanResult, *, nn_factor: float = 8.0,
                  min_kept: int = 8) -> List[Dict]:
    """Flag kept points whose EXACT NN distance >= nn_factor x median NN."""
    pts = clean.points
    n = len(pts)
    if n < max(min_kept, 4):
        return []
    xy = project_km(pts)[0]
    nn = [min(math.hypot(xy[i][0] - xy[j][0], xy[i][1] - xy[j][1])
              for j in range(n) if j != i) for i in range(n)]
    med = sorted(nn)[n // 2]
    if med <= 1e-6:
        return []
    return [{"original_index": clean.kept_indices[pos],
             "clean_position": pos, "reason": "far_outlier",
             "nn_km": round(nn[pos], 2),
             "lng": pts[pos][0], "lat": pts[pos][1]}
            for pos in range(n) if nn[pos] > nn_factor * med]


def adjudicate(clean: CleanResult, suspects: Sequence[Dict], *,
               confirm_drop: Sequence[int] = (),
               confirm_keep: Sequence[int] = ()) -> Dict:
    """Apply user decisions over ORIGINAL row indices; fail closed otherwise."""
    drop = set(confirm_drop)
    keep = set(confirm_keep)
    flagged = {s["original_index"] for s in suspects}
    unresolved = sorted(flagged - drop - keep)
    if unresolved:
        return {"decision": "BLOCKED_BY_DATA_QUALITY",
                "unresolved": unresolved}
    new_pts = []
    new_idx = []
    for pos, orig in enumerate(clean.kept_indices):
        if orig in drop:
            continue
        new_pts.append(clean.points[pos])
        new_idx.append(orig)
    decision = ("INCLUDING_CONFIRMED_OUTLIER" if (keep & flagged)
                else "CLEANED")
    return {"decision": decision,
            "points": new_pts,
            "original_indices": new_idx,
            "index_map": {o: i for i, o in enumerate(new_idx)},
            "dropped_by_user": sorted(drop & flagged),
            "kept_confirmed_outlier": sorted(keep & flagged)}
