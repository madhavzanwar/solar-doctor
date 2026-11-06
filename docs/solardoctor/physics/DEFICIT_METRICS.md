# Deficit detector: precision / recall on SIMULATED data

All numbers below come from `scripts/eval_deficit_synthetic.py` on **SIMULATED** telemetry (`tests/backend/physics/deficit_synth.py`); they are not measurements of a real plant.

Setup: fixed-tilt 400 kWp / 360 kWac plant, 2 inverters, 8 equal strings, 15-minute data, 3 days, measured-style GHI and ambient temperature in telemetry, 1% multiplicative power noise, seeds 0..9 (10 seeds x 6 scenarios = 60 scans). Truth is generated with `solar.expected_power`; the detector uses the independent `baseline.expected_power` (pvwatts) chain, so a small model mismatch is included. Thresholds: WARNING PI < 0.95, CRITICAL PI < 0.90 on the rolling median of 3 clear hours; peer rule z <= -3.

A true positive is an event on exactly the injected scope (the right string, or the plant for soiling). Control and cloudy-day scans have no injected event, so any event there is a false positive. `any severity` counts INFO (peer deficit below the alert threshold) events; `WARNING+` counts only WARNING and CRITICAL.

## Pooled

| Counting | TP | FP | FN | Precision | Recall |
|---|---|---|---|---|---|
| any severity | 40 | 0 | 0 | 1.000 | 1.000 |
| WARNING+ only | 40 | 0 | 0 | 1.000 | 1.000 |

## Per scenario

| Scenario | Counting | TP | FP | FN | Precision | Recall |
|---|---|---|---|---|---|---|
| control | any severity | 0 | 0 | 0 | n/a (no positives) | n/a (no positives) |
| control | WARNING+ | 0 | 0 | 0 | n/a (no positives) | n/a (no positives) |
| string_5 | any severity | 10 | 0 | 0 | 1.000 | 1.000 |
| string_5 | WARNING+ | 10 | 0 | 0 | 1.000 | 1.000 |
| string_10 | any severity | 10 | 0 | 0 | 1.000 | 1.000 |
| string_10 | WARNING+ | 10 | 0 | 0 | 1.000 | 1.000 |
| string_20 | any severity | 10 | 0 | 0 | 1.000 | 1.000 |
| string_20 | WARNING+ | 10 | 0 | 0 | 1.000 | 1.000 |
| soiling_7 | any severity | 10 | 0 | 0 | 1.000 | 1.000 |
| soiling_7 | WARNING+ | 10 | 0 | 0 | 1.000 | 1.000 |
| cloudy | any severity | 0 | 0 | 0 | n/a (no positives) | n/a (no positives) |
| cloudy | WARNING+ | 0 | 0 | 0 | n/a (no positives) | n/a (no positives) |

## Severity and PI of the detected events

| Scenario | Events | Severity counts | Median PI (min..max over runs) | Rolling-median PI min (min..max) |
|---|---|---|---|---|
| control | 0 | - | - | - |
| string_5 | 10 | {'WARNING': 10} | 0.950 (0.947..0.952) | 0.941..0.947 |
| string_10 | 10 | {'CRITICAL': 10} | 0.900 (0.898..0.902) | 0.892..0.897 |
| string_20 | 10 | {'CRITICAL': 10} | 0.800 (0.798..0.801) | 0.792..0.797 |
| soiling_7 | 10 | {'WARNING': 10} | 0.929 (0.928..0.929) | 0.925..0.927 |
| cloudy | 0 | - | - | - |

## Notes

- 5 % case (string_5): 10 detections, severities {'WARNING': 10}; lowest rolling-median PI per run 0.941..0.947 against the 0.95 threshold (10 of 10 runs below it, 0 at or above it). The margin to the threshold is 0.003 PI at the closest run, so the severity is set by noise and baseline mismatch at that boundary.
- 10 % case (string_10): 10 detections, severities {'CRITICAL': 10}; lowest rolling-median PI per run 0.892..0.897 against the 0.90 threshold (10 of 10 runs below it, 0 at or above it). The margin to the threshold is 0.003 PI at the closest run, so the severity is set by noise and baseline mismatch at that boundary.
- Healthy PI is ~1.0 here because the generator and the baseline share the same underlying pvlib physics apart from small implementation differences; real plants add model error, sensor calibration drift and soiling baselines that this test does not exercise.
- Cloudy-day immunity relies on the clear-sky QC (pvanalytics `reno` on measured GHI); one cloudy day among three clear days is tested, not a fully overcast week.
