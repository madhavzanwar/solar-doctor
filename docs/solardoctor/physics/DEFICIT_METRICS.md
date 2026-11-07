# Deficit detector: precision / recall on SIMULATED data

## Easy suite

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


## Hard suite

Report seeds 100..119 (20 seeds x 13 scenarios = 260 scans). SIMULATED; 2.5% multiplicative noise on every string, 1.5% on the GHI sensor. Detection thresholds are unchanged. The only new QC parameter is the clock-offset limit (30 min, fixed by design, not fitted), so no tuning seeds were used; seeds 100..119 were never used to choose a parameter.

Scenarios: control_hard (healthy), slow_soiling (plant loss 0 to 8 % over 14 days; an event starting before the true loss reaches 4 % is a premature false positive), just_under (one string -3 %, no WARNING+ expected; an INFO peer notice on it is not a false positive), partly_cloudy (4 days of broken clouds, GHI sensor 7 min behind the array), clipping_day (DC/AC 1.56, healthy), clipping_string (same plant, one string -10 %), gaps_and_stuck (NaN runs, GHI sensor and one string power channel flatlined, healthy), time_offset (healthy, timestamps +1 h), one_of_many (24 strings, one at -8 %), jitter (0-59 s timestamp jitter, one string -20 %), control_nasa / cloudy_nasa (no site GHI; hourly NASA-style GHI with 3 % to 33 % error, healthy; cloudy_nasa has a cloudy day), string_nasa (the same NASA-only irradiance, one string -10 %).

| Scenario | Counting | TP | FP | FN | Precision | Recall |
|---|---|---|---|---|---|---|
| control_hard | any severity | 0 | 0 | 0 | n/a (no positives) | n/a (no positives) |
| control_hard | WARNING+ | 0 | 0 | 0 | n/a (no positives) | n/a (no positives) |
| slow_soiling | any severity | 19 | 1 | 1 | 0.950 | 0.950 |
| slow_soiling | WARNING+ | 19 | 1 | 1 | 0.950 | 0.950 |
| just_under | any severity | 0 | 3 | 0 | 0.000 | n/a (no positives) |
| just_under | WARNING+ | 0 | 3 | 0 | 0.000 | n/a (no positives) |
| partly_cloudy | any severity | 0 | 7 | 0 | 0.000 | n/a (no positives) |
| partly_cloudy | WARNING+ | 0 | 7 | 0 | 0.000 | n/a (no positives) |
| clipping_day | any severity | 0 | 0 | 0 | n/a (no positives) | n/a (no positives) |
| clipping_day | WARNING+ | 0 | 0 | 0 | n/a (no positives) | n/a (no positives) |
| clipping_string | any severity | 20 | 0 | 0 | 1.000 | 1.000 |
| clipping_string | WARNING+ | 20 | 0 | 0 | 1.000 | 1.000 |
| gaps_and_stuck | any severity | 0 | 0 | 0 | n/a (no positives) | n/a (no positives) |
| gaps_and_stuck | WARNING+ | 0 | 0 | 0 | n/a (no positives) | n/a (no positives) |
| time_offset | any severity | 0 | 0 | 0 | n/a (no positives) | n/a (no positives) |
| time_offset | WARNING+ | 0 | 0 | 0 | n/a (no positives) | n/a (no positives) |
| one_of_many | any severity | 20 | 0 | 0 | 1.000 | 1.000 |
| one_of_many | WARNING+ | 20 | 0 | 0 | 1.000 | 1.000 |
| jitter | any severity | 20 | 0 | 0 | 1.000 | 1.000 |
| jitter | WARNING+ | 20 | 0 | 0 | 1.000 | 1.000 |
| control_nasa | any severity | 0 | 17 | 0 | 0.000 | n/a (no positives) |
| control_nasa | WARNING+ | 0 | 0 | 0 | n/a (no positives) | n/a (no positives) |
| cloudy_nasa | any severity | 0 | 16 | 0 | 0.000 | n/a (no positives) |
| cloudy_nasa | WARNING+ | 0 | 0 | 0 | n/a (no positives) | n/a (no positives) |
| string_nasa | any severity | 20 | 15 | 0 | 0.571 | 1.000 |
| string_nasa | WARNING+ | 20 | 0 | 0 | 1.000 | 1.000 |

### Pooled over the hard suite

| Counting | TP | FP | FN | Precision | Recall |
|---|---|---|---|---|---|
| any severity | 99 | 59 | 1 | 0.627 | 0.990 |
| WARNING+ | 99 | 11 | 1 | 0.900 | 0.990 |

### Before and after the irradiance-verification cap (WARNING+)

Before = the earlier run of this script (same 12 scenarios and seeds, no cap). After = this run. `string_nasa` (10 % string fault, NASA-only irradiance) was added with the cap and has no before value.

| Row | Before TP/FP/FN | Before precision | Before recall | After TP/FP/FN | After precision | After recall |
|---|---|---|---|---|---|---|
| control_nasa | 0/17/0 | 0.000 | n/a (no positives) | 0/0/0 | n/a (no positives) | n/a (no positives) |
| cloudy_nasa | 0/16/0 | 0.000 | n/a (no positives) | 0/0/0 | n/a (no positives) | n/a (no positives) |
| pooled (12 scenarios) | 79/44/1 | 0.642 | 0.988 | 79/11/1 | 0.878 | 0.988 |
| pooled without NASA-only scenarios | 79/11/1 | 0.878 | 0.988 | 79/11/1 | 0.878 | 0.988 |
| string_nasa (new) | n/a | n/a | n/a | 20/0/0 | 1.000 | 1.000 |

Pooled WARNING+ without the two NASA-only scenarios: TP 99, FP 11, FN 1, precision 0.900, recall 0.990.

### Other measurements

- just_under: INFO peer notice on the -3 % string in 6 of 20 runs (6 events).
- slow_soiling: plant event found in 20 of 20 runs; premature starts in 1; delay after the true 5 % crossing median -0.67 days (min -2.42, max 0.33; negative = before the crossing).
- time-offset QC flag rate (`qc_status = time_offset_suspected`): control_hard 0/20; slow_soiling 0/20; just_under 0/20; partly_cloudy 4/20; clipping_day 0/20; clipping_string 0/20; gaps_and_stuck 0/20; time_offset 20/20; one_of_many 0/20; jitter 0/20; control_nasa 0/20; cloudy_nasa 0/20; string_nasa 0/20.