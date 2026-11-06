"""Measure deficit-detector precision/recall on SIMULATED telemetry; writes docs/solardoctor/physics/DEFICIT_METRICS.md.

    PYTHONSAFEPATH=1 PYTHONPATH="backend;." python scripts/eval_deficit_synthetic.py [n_seeds]

Deterministic: seeds 0..n-1 (default 10). Generator: tests/backend/physics/deficit_synth.py.
"""
from __future__ import annotations

import collections
import statistics
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.backend.physics import deficit_synth as ds  # noqa: E402

OUT = ROOT / "docs" / "solardoctor" / "physics" / "DEFICIT_METRICS.md"


def _fmt(x: float) -> str:
    return "n/a (no positives)" if x != x else f"{x:.3f}"


def _row(name: str, s: dict) -> str:
    return f"| {name} | {s['tp']} | {s['fp']} | {s['fn']} | {_fmt(s['precision'])} | {_fmt(s['recall'])} |"


def main(n_seeds: int = 10) -> None:
    seeds = list(range(n_seeds))
    runs, pooled, per = ds.evaluate(seeds)
    lines = [
        "# Deficit detector: precision / recall on SIMULATED data", "",
        "All numbers below come from `scripts/eval_deficit_synthetic.py` on **SIMULATED** telemetry "
        "(`tests/backend/physics/deficit_synth.py`); they are not measurements of a real plant.", "",
        f"Setup: fixed-tilt 400 kWp / 360 kWac plant, 2 inverters, 8 equal strings, 15-minute data, 3 days, measured-style GHI and "
        f"ambient temperature in telemetry, {ds.NOISE:.0%} multiplicative power noise, seeds {seeds[0]}..{seeds[-1]} "
        f"({n_seeds} seeds x {len(ds.SCENARIOS)} scenarios = {len(runs)} scans). Truth is generated with `solar.expected_power`; "
        "the detector uses the independent `baseline.expected_power` (pvwatts) chain, so a small model mismatch is included. "
        "Thresholds: WARNING PI < 0.95, CRITICAL PI < 0.90 on the rolling median of 3 clear hours; peer rule z <= -3.", "",
        "A true positive is an event on exactly the injected scope (the right string, or the plant for soiling). "
        "Control and cloudy-day scans have no injected event, so any event there is a false positive. "
        "`any severity` counts INFO (peer deficit below the alert threshold) events; `WARNING+` counts only WARNING and CRITICAL.", "",
        "## Pooled", "", "| Counting | TP | FP | FN | Precision | Recall |", "|---|---|---|---|---|---|",
        _row("any severity", pooled["any_severity"]), _row("WARNING+ only", pooled["warning_or_critical"]), "",
        "## Per scenario", "", "| Scenario | Counting | TP | FP | FN | Precision | Recall |", "|---|---|---|---|---|---|---|"]
    for sc, s in per.items():
        lines.append(_row(f"{sc} | any", s["any_severity"]).replace("| any |", "| any severity |", 1) if False else
                     f"| {sc} | any severity" + _row("", s["any_severity"])[2:].rstrip())
        lines.append(f"| {sc} | WARNING+" + _row("", s["warning_or_critical"])[2:].rstrip())
    lines += ["", "## Severity and PI of the detected events", "",
              "| Scenario | Events | Severity counts | Median PI (min..max over runs) | Rolling-median PI min (min..max) |",
              "|---|---|---|---|---|"]
    for sc in ds.SCENARIOS:
        evs = [e for r in runs if r["scenario"] == sc for e in r["events"]]
        if not evs:
            lines.append(f"| {sc} | 0 | - | - | - |")
            continue
        pis = [e.pi_median for e in evs]
        lows = [e.evidence["pi_rolling_min"] for e in evs if e.evidence["pi_rolling_min"] is not None]
        sev = dict(collections.Counter(e.severity for e in evs))
        lines.append(f"| {sc} | {len(evs)} | {sev} | {statistics.median(pis):.3f} ({min(pis):.3f}..{max(pis):.3f}) | "
                     f"{min(lows):.3f}..{max(lows):.3f} |")
    s5 = [e for r in runs if r["scenario"] == "string_5" for e in r["events"]]
    near = sum(1 for e in s5 if e.evidence["pi_rolling_min"] is None)
    lines += ["", "## Notes", "",
              f"- The 5 % case sits right at the 0.95 WARNING threshold: of {len(s5)} detections, {near} were only INFO "
              "(rolling median never dropped below 0.95), the rest WARNING. Whether a 5 % loss becomes an alert depends on noise and the baseline mismatch; the peer rule still localises the string.",
              "- The 10 % case sits at the 0.90 CRITICAL boundary: severity is CRITICAL or WARNING depending on the run (see counts above), as the rule implies.",
              "- Healthy PI is ~1.0 here because the generator and the baseline share the same underlying pvlib physics apart from small implementation differences; real plants add model error, sensor calibration drift and soiling baselines that this test does not exercise.",
              "- Cloudy-day immunity relies on the clear-sky QC (pvanalytics `reno` on measured GHI); one cloudy day among three clear days is tested, not a fully overcast week.", ""]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
