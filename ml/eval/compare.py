#!/usr/bin/env python3
"""Compare two evaluation metrics JSONs and flag per-class regressions.

Usage:
    python3 -m ml.eval.compare baseline.json new.json

Prints a per-class AP50 delta table. Exits 1 if any CRITICAL class (sourced from
ml.src.utils.SEVERITY_MAP, the single source of truth for severity) regresses by
more than REGRESSION_THRESHOLD.
"""
from __future__ import annotations

import json
import sys

from ml.src.utils import SEVERITY_MAP

# Single source of truth — never hardcode the critical class list here.
CRITICAL_CLASSES = {cls for cls, sev in SEVERITY_MAP.items() if sev == "CRITICAL"}
REGRESSION_THRESHOLD = 0.05  # absolute AP50 drop that counts as a regression


def _load(path: str) -> dict:
    with open(path) as fh:
        return json.load(fh)


def compare(baseline_path: str, new_path: str) -> int:
    """Print a delta table; return 1 if a CRITICAL class regressed, else 0."""
    baseline = _load(baseline_path)
    new = _load(new_path)

    regressions = []
    print(f"{'Class':<25} {'Baseline AP50':>14} {'New AP50':>10} {'Delta':>9}")
    print("-" * 60)

    for cls in baseline.get("per_class", {}):
        b_ap = baseline["per_class"][cls].get("ap50", 0.0)
        n_ap = new.get("per_class", {}).get(cls, {}).get("ap50", 0.0)
        delta = n_ap - b_ap
        is_regression = delta < -REGRESSION_THRESHOLD
        flag = " !" if is_regression else ""
        critical = " [CRITICAL]" if cls in CRITICAL_CLASSES else ""
        print(f"{cls:<25} {b_ap:>14.4f} {n_ap:>10.4f} {delta:>+9.4f}{flag}{critical}")
        if is_regression and cls in CRITICAL_CLASSES:
            regressions.append(cls)

    print("-" * 60)
    b_map = baseline.get("map50", 0.0)
    n_map = new.get("map50", 0.0)
    print(f"{'mAP@0.5':<25} {b_map:>14.4f} {n_map:>10.4f} {n_map - b_map:>+9.4f}")

    if regressions:
        print(f"\nREGRESSION in CRITICAL classes: {sorted(regressions)}")
        return 1
    return 0


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: python3 -m ml.eval.compare <baseline.json> <new.json>", file=sys.stderr)
        return 2
    return compare(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    sys.exit(main())
