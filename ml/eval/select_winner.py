#!/usr/bin/env python3
"""Pick the winning bake-off candidate from evaluate.py-style metrics JSONs.

Usage:
    python3 -m ml.eval.select_winner \
        --baseline ml/eval/results/baseline/metrics.json \
        --candidate yolo11x=ml/eval/results/yolo11x/metrics.json \
        --candidate rtdetr-x=ml/eval/results/rtdetr-x/metrics.json \
        --candidate codetr=ml/eval/results/codetr/metrics.json \
        --report-dir ml/eval/results

Weights CRITICAL-severity classes (per ml.src.utils.SEVERITY_MAP) more heavily
than the flat mAP@0.5, since those drive real remediation priority.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ml.src.utils import SEVERITY_MAP

CRITICAL_CLASSES = {cls for cls, sev in SEVERITY_MAP.items() if sev == "CRITICAL"}


def _load(path: str) -> dict:
    with open(path) as fh:
        return json.load(fh)


def score_candidate(metrics: dict, critical_weight: float = 2.0) -> float:
    """Weighted score: overall mAP50 plus extra weight on CRITICAL-class AP50."""
    score = metrics.get("map50", 0.0)
    for cls, per_class in metrics.get("per_class", {}).items():
        if cls in CRITICAL_CLASSES:
            score += (critical_weight - 1.0) * per_class.get("ap50", 0.0) / max(len(CRITICAL_CLASSES), 1)
    return score


def select_winner(
    baseline_path: str,
    candidate_paths: dict[str, str],
    critical_weight: float = 2.0,
    report_dir: Path | str = "ml/eval/results",
) -> dict:
    """Rank candidates by weighted score, pick a winner, persist the report."""
    baseline = _load(baseline_path)
    baseline_score = score_candidate(baseline, critical_weight)

    ranking = []
    for name, path in candidate_paths.items():
        metrics = _load(path)
        ranking.append({
            "name": name,
            "path": path,
            "score": score_candidate(metrics, critical_weight),
            "map50": metrics.get("map50", 0.0),
        })
    ranking.sort(key=lambda r: r["score"], reverse=True)

    winner = ranking[0]["name"] if ranking else None
    result = {
        "baseline_score": baseline_score,
        "ranking": ranking,
        "winner": winner,
        "winner_metrics_path": ranking[0]["path"] if ranking else None,
    }

    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "selection_report.json").write_text(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", action="append", required=True, help="name=path, repeatable")
    parser.add_argument("--report-dir", default="ml/eval/results")
    parser.add_argument("--critical-weight", type=float, default=2.0)
    args = parser.parse_args()

    candidate_paths = dict(c.split("=", 1) for c in args.candidate)
    result = select_winner(args.baseline, candidate_paths, args.critical_weight, args.report_dir)

    print(f"Baseline score: {result['baseline_score']:.4f}")
    print("\nRanking:")
    for r in result["ranking"]:
        print(f"  {r['name']:<12} score={r['score']:.4f}  mAP50={r['map50']:.4f}")
    print(f"\nWinner: {result['winner']}")


if __name__ == "__main__":
    main()
