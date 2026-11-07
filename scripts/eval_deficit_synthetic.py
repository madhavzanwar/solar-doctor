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
from tests.backend.physics import deficit_synth_hard as hs  # noqa: E402

OUT = ROOT / "docs" / "solardoctor" / "physics" / "DEFICIT_METRICS.md"


def _fmt(x: float) -> str:
    return "n/a (no positives)" if x != x else f"{x:.3f}"


def _row(name: str, s: dict) -> str:
    return f"| {name} | {s['tp']} | {s['fp']} | {s['fn']} | {_fmt(s['precision'])} | {_fmt(s['recall'])} |"


def _pr(tp: int, fp: int, fn: int) -> dict:
    return {"tp": tp, "fp": fp, "fn": fn, "precision": tp / (tp + fp) if tp + fp else float("nan"),
            "recall": tp / (tp + fn) if tp + fn else float("nan")}


# Measured earlier by this script (commit d4844bc, 12 scenarios, seeds 100..119) before plant/inverter events were capped
# at INFO under unverified irradiance. (TP, FP, FN), identical for "any severity" and "WARNING+".
BEFORE = {"control_nasa": (0, 17, 0), "cloudy_nasa": (0, 16, 0), "pooled (12 scenarios)": (79, 44, 1),
          "pooled without NASA-only scenarios": (79, 11, 1)}


def hard_block(seeds: list[int]) -> list[str]:
    """Hard suite (tests/backend/physics/deficit_synth_hard.py) on the report seeds; every number is measured here."""
    per = {sc: [] for sc in hs.SCENARIOS}
    flags = {sc: 0 for sc in hs.SCENARIOS}
    for sc in hs.SCENARIOS:
        for seed in seeds:
            res, truth, sids, _ = hs.run(sc, seed)
            per[sc].append(hs.judge(sc, res, truth, sids))
            flags[sc] += res.get("qc_status") == "time_offset_suspected"
    sums = lambda rows, mode: tuple(sum(r[mode][k] for r in rows) for k in ("tp", "fp", "fn"))
    out = ["", "## Hard suite", "",
           f"Report seeds {seeds[0]}..{seeds[-1]} ({len(seeds)} seeds x {len(hs.SCENARIOS)} scenarios = {len(seeds) * len(hs.SCENARIOS)} scans). "
           f"SIMULATED; {hs.NOISE_P:.1%} multiplicative noise on every string, {hs.NOISE_G:.1%} on the GHI sensor. "
           "Detection thresholds are unchanged. The only new QC parameter is the clock-offset limit (30 min, fixed by design, not fitted), "
           "so no tuning seeds were used; seeds 100..119 were never used to choose a parameter.", "",
           "Scenarios: control_hard (healthy), slow_soiling (plant loss 0 to 8 % over 14 days; an event starting before the true loss "
           "reaches 4 % is a premature false positive), just_under (one string -3 %, no WARNING+ expected; an INFO peer notice on it is not a false positive), "
           "partly_cloudy (4 days of broken clouds, GHI sensor 7 min behind the array), clipping_day (DC/AC 1.56, healthy), "
           "clipping_string (same plant, one string -10 %), gaps_and_stuck (NaN runs, GHI sensor and one string power channel flatlined, healthy), "
           "time_offset (healthy, timestamps +1 h), one_of_many (24 strings, one at -8 %), jitter (0-59 s timestamp jitter, one string -20 %), "
           "control_nasa / cloudy_nasa (no site GHI; hourly NASA-style GHI with 3 % to 33 % error, healthy; cloudy_nasa has a cloudy day), "
           "string_nasa (the same NASA-only irradiance, one string -10 %).", "",
           "| Scenario | Counting | TP | FP | FN | Precision | Recall |", "|---|---|---|---|---|---|---|"]
    for sc in hs.SCENARIOS:
        for label, mode in (("any severity", "any"), ("WARNING+", "warn")):
            out.append(f"| {sc} | {label} | " + " | ".join(str(v) for v in sums(per[sc], mode)) +
                       f" | {_fmt(_pr(*sums(per[sc], mode))['precision'])} | {_fmt(_pr(*sums(per[sc], mode))['recall'])} |")
    out += ["", "### Pooled over the hard suite", "", "| Counting | TP | FP | FN | Precision | Recall |", "|---|---|---|---|---|---|"]
    for label, mode in (("any severity", "any"), ("WARNING+", "warn")):
        t = tuple(sum(sums(per[sc], mode)[i] for sc in hs.SCENARIOS) for i in range(3))
        out.append(f"| {label} | {t[0]} | {t[1]} | {t[2]} | {_fmt(_pr(*t)['precision'])} | {_fmt(_pr(*t)['recall'])} |")
    nasa = ("control_nasa", "cloudy_nasa")
    t = tuple(sum(sums(per[sc], "warn")[i] for sc in hs.SCENARIOS if sc not in nasa) for i in range(3))
    old12 = [sc for sc in hs.SCENARIOS if sc != "string_nasa"]
    p12 = tuple(sum(sums(per[sc], "warn")[i] for sc in old12) for i in range(3))
    pn = tuple(sum(sums(per[sc], "warn")[i] for sc in old12 if sc not in ("control_nasa", "cloudy_nasa")) for i in range(3))
    after = {"control_nasa": sums(per["control_nasa"], "warn"), "cloudy_nasa": sums(per["cloudy_nasa"], "warn"),
             "pooled (12 scenarios)": p12, "pooled without NASA-only scenarios": pn}
    out += ["", "### Before and after the irradiance-verification cap (WARNING+)", "",
            "Before = the earlier run of this script (same 12 scenarios and seeds, no cap). After = this run. "
            "`string_nasa` (10 % string fault, NASA-only irradiance) was added with the cap and has no before value.", "",
            "| Row | Before TP/FP/FN | Before precision | Before recall | After TP/FP/FN | After precision | After recall |", "|---|---|---|---|---|---|---|"]
    for k, b in BEFORE.items():
        a = after[k]
        out.append(f"| {k} | {b[0]}/{b[1]}/{b[2]} | {_fmt(_pr(*b)['precision'])} | {_fmt(_pr(*b)['recall'])} | "
                   f"{a[0]}/{a[1]}/{a[2]} | {_fmt(_pr(*a)['precision'])} | {_fmt(_pr(*a)['recall'])} |")
    sn = sums(per["string_nasa"], "warn")
    out.append(f"| string_nasa (new) | n/a | n/a | n/a | {sn[0]}/{sn[1]}/{sn[2]} | {_fmt(_pr(*sn)['precision'])} | {_fmt(_pr(*sn)['recall'])} |")
    out += ["", f"Pooled WARNING+ without the two NASA-only scenarios: TP {t[0]}, FP {t[1]}, FN {t[2]}, precision {_fmt(_pr(*t)['precision'])}, recall {_fmt(_pr(*t)['recall'])}.", "",
            "### Other measurements", ""]
    notice = sum(r["notice"] for r in per["just_under"])
    out.append(f"- just_under: INFO peer notice on the -3 % string in {sum(1 for r in per['just_under'] if r['notice'])} of {len(seeds)} runs ({notice} events).")
    delays = [r["delay_days"] for r in per["slow_soiling"] if r["delay_days"] is not None]
    prem = sum(r["premature"] for r in per["slow_soiling"])
    out.append(f"- slow_soiling: plant event found in {len(delays)} of {len(seeds)} runs; premature starts in {prem}; delay after the true 5 % crossing "
               + (f"median {statistics.median(delays):.2f} days (min {min(delays):.2f}, max {max(delays):.2f}; negative = before the crossing)." if delays else "n/a."))
    out.append("- time-offset QC flag rate (`qc_status = time_offset_suspected`): " +
               "; ".join(f"{sc} {flags[sc]}/{len(seeds)}" for sc in hs.SCENARIOS) + ".")
    return out


def main(n_seeds: int = 10) -> None:
    seeds = list(range(n_seeds))
    runs, pooled, per = ds.evaluate(seeds)
    lines = [
        "# Deficit detector: precision / recall on SIMULATED data", "", "## Easy suite", "",
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
    lines += ["", "## Notes", ""]
    for sc, thr, label in (("string_5", 0.95, "5 %"), ("string_10", 0.90, "10 %")):
        evs = [e for r in runs if r["scenario"] == sc for e in r["events"]]
        sev = collections.Counter(e.severity for e in evs)
        lows = [e.evidence["pi_rolling_min"] for e in evs if e.evidence["pi_rolling_min"] is not None]
        span = f"{min(lows):.3f}..{max(lows):.3f}" if lows else "n/a"
        side = sum(1 for v in lows if v < thr)
        lines.append(f"- {label} case ({sc}): {len(evs)} detections, severities {dict(sev)}; lowest rolling-median PI per run "
                     f"{span} against the {thr:.2f} threshold ({side} of {len(lows)} runs below it, "
                     f"{len(lows) - side} at or above it). "
                     + ("The margin to the threshold is " + f"{min(abs(v - thr) for v in lows):.3f} PI at the closest run, "
                        "so the severity is set by noise and baseline mismatch at that boundary." if lows else ""))
    lines += [
              "- Healthy PI is ~1.0 here because the generator and the baseline share the same underlying pvlib physics apart from small implementation differences; real plants add model error, sensor calibration drift and soiling baselines that this test does not exercise.",
              "- Cloudy-day immunity relies on the clear-sky QC (pvanalytics `reno` on measured GHI); one cloudy day among three clear days is tested, not a fully overcast week.", ""]
    lines += hard_block(list(range(100, 120)))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
