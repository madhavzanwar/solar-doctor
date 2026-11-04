"""
select_winner.py tests — run with:
    PYTHONSAFEPATH=1 python3 tests/test_select_winner.py
"""
from __future__ import annotations
import sys
import os
import json
import tempfile

import platform
import uuid

_HERE = os.path.abspath(os.path.dirname(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
sys.path = [_ROOT] + [p for p in sys.path if os.path.abspath(p) != _ROOT]

from pathlib import Path

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
_results: list[tuple[str, bool, str]] = []


def test(name: str):
    def decorator(fn):
        try:
            fn()
            _results.append((name, True, ""))
            print(f"  [{PASS}] {name}")
        except Exception as exc:
            _results.append((name, False, str(exc)))
            print(f"  [{FAIL}] {name}: {exc}")
        return fn
    return decorator


from ml.eval.select_winner import score_candidate, select_winner

_FAKE_METRICS = {
    "map50": 0.5,
    "per_class": {
        "string":         {"ap50": 0.4},   # CRITICAL
        "bypass-diode":   {"ap50": 0.4},   # CRITICAL
        "hot-spot-high":  {"ap50": 0.4},   # CRITICAL
        "cell":           {"ap50": 0.8},   # MEDIUM
    },
}


@test("score_candidate weights CRITICAL classes higher than default weight 1")
def _():
    unweighted = score_candidate(_FAKE_METRICS, critical_weight=1.0)
    weighted = score_candidate(_FAKE_METRICS, critical_weight=2.0)
    assert weighted > unweighted


@test("score_candidate is deterministic")
def _():
    a = score_candidate(_FAKE_METRICS)
    b = score_candidate(_FAKE_METRICS)
    assert a == b


@test("select_winner picks the candidate with the highest weighted score")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        baseline = {"map50": 0.3, "per_class": {"string": {"ap50": 0.2}}}
        weak = {"map50": 0.35, "per_class": {"string": {"ap50": 0.25}}}
        strong = {"map50": 0.6, "per_class": {"string": {"ap50": 0.55}}}

        (tmp / "baseline.json").write_text(json.dumps(baseline))
        (tmp / "weak.json").write_text(json.dumps(weak))
        (tmp / "strong.json").write_text(json.dumps(strong))

        result = select_winner(
            baseline_path=str(tmp / "baseline.json"),
            candidate_paths={"weak": str(tmp / "weak.json"), "strong": str(tmp / "strong.json")},
            report_dir=tmp,
        )
        assert result["winner"] == "strong"
        assert (tmp / "selection_report.json").exists()


@test("select_winner ranking is sorted best-first")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        baseline = {"map50": 0.3, "per_class": {}}
        a = {"map50": 0.4, "per_class": {}}
        b = {"map50": 0.7, "per_class": {}}
        (tmp / "baseline.json").write_text(json.dumps(baseline))
        (tmp / "a.json").write_text(json.dumps(a))
        (tmp / "b.json").write_text(json.dumps(b))

        result = select_winner(
            baseline_path=str(tmp / "baseline.json"),
            candidate_paths={"a": str(tmp / "a.json"), "b": str(tmp / "b.json")},
            report_dir=tmp,
        )
        assert result["ranking"][0]["name"] == "b"
        assert result["ranking"][1]["name"] == "a"


print("\n" + "═" * 65)
passed = sum(1 for _, ok, _ in _results if ok)
failed = sum(1 for _, ok, _ in _results if not ok)
print(f"  Results: {passed} passed, {failed} failed  ({len(_results)} total)")
if failed:
    for name, ok, err in _results:
        if not ok:
            print(f"    - {name}: {err}")
sys.exit(0 if failed == 0 else 1)
