# Interface: fusion and ROI engines (Workstream 3)

Pure Python, no DB or network. Code: `backend/solardoctor/fusion/`, `backend/solardoctor/roi/`.
Method and formulas: `docs/solardoctor/ROI_METHOD.md`.

## `solardoctor.roi`

```python
TARIFF_PRESETS = {"utility_ppa": 2.6, "c_and_i": 6.5, "residential": 8.0}   # Rs/kWh, editable user assumptions
ForecastHour(hours_ahead: float, precip_probability_pct: float | None = None, temperature_c: float | None = None)
RoiSettings(tariff_inr_per_kwh=6.5, tariff_preset="c_and_i", module_count=0, cleaning_cost_per_module_inr=0.0,
            water_l_per_module=0.0, water_cost_inr_per_l=0.0, labour_cost_inr=0.0, soiling_rate_per_day=None,
            rain_prob_threshold_pct=60.0, rain_window_h=72.0, calendar_interval_days=15.0, max_payback_days=30.0)
RoiSettings.from_preset(preset: str, **kw) -> RoiSettings        # ValueError on negative / NaN fields
evaluate(expected_kwh_day, deficit_fraction, settings, forecast=(), soiling_rate_per_day=None) -> RoiResult
cleaning_cost(settings) -> float
water_per_clean(settings) -> float
payback_days(cost, inr_per_day) -> float | None                    # None = never pays back
optimal_interval_days(cost, rate_per_day, clean_value_inr_per_day) -> float | None   # T*
rain_outlook(forecast, threshold_pct, window_h) -> (wait: bool, peak_pct | None, hours_ahead | None)
```

`RoiResult`: `decision` ("CLEAN NOW" | "WAIT"), `reason`, `expected_kwh_day`, `deficit_fraction`, `recoverable_kwh_day`,
`inr_per_day`, `clean_value_inr_per_day`, `cleaning_cost_inr`, `water_l_per_clean`, `payback_days` (null = never),
`payback_label`, `never_pays_back`, `rain_wait`, `rain_peak_probability_pct`, `rain_peak_hours_ahead`,
`optimal_interval_days`, `optimal_interval_note`, `water_saved_l_per_year` (signed), `assumptions` (dict with
`label: "user assumption (editable)"` plus every input used). `None` marks a quantity that is undefined or whose input
was missing. Invalid *inputs* to `evaluate` (None/NaN expected energy or deficit) never raise: WAIT with "ROI inputs missing:
configure expected energy/costs" and `incomplete = true`. A total cleaning cost of 0 (nothing configured) gives WAIT
"Cleaning cost not configured", also `incomplete`. `RoiResult` also has `soiling_rate_per_day` and `soiling_rate_source`
(e.g. "pvlib_kimber assumed default"; T* is a heuristic on that rate). Invalid *settings* raise `ValueError`.

## `solardoctor.fusion`

```python
TelemetryEvidence(status="ok", usable_clear_hours=None, deficit_severity=None, pi_median=None, deviation_percent=None,
                  expected_kwh_day=None, attributable_deficit_fraction=None, soiling_loss_rate_per_day=None)
PhotoEvidence(predicted_class: str, confidence: float | None, is_ood=False, needs_field_check=False,
              field_check_reason=None, model_version=None)
FusionSettings(roi: RoiSettings, conf_threshold=0.6, recheck_days=7, melt_temp_c=2.0, melt_window_h=48.0)
fuse(telemetry, photo, settings, *, forecast: Iterable[ForecastHour] = ()) -> FusionVerdict
load_rules() -> tuple[dict, ...]       # rules.yaml, loaded once, sorted by precedence
FusionVerdict(verdict, action, confidence, reason, severity: Severity, rule_id, telemetry_state, photo_state, roi: RoiResult | None)
```

Actions: `CLEAN NOW`, `WAIT`, `CLEAR IF SAFE`, `FIELD CHECK`, `REPLACE / WARRANTY CLAIM`, `NEEDS FIELD CHECK`,
`RE-CHECK NEXT CLEAR DAY`, `NO ACTION`. Severity: `CRITICAL | HIGH | MEDIUM | LOW` (DESIGN.md scale).

### Precedence (first match wins; `rules.yaml`)

1. Unclear photo: OOD, `needs_field_check`, confidence missing or `< conf_threshold` (exactly 0.6 passes), unknown class,
   or no photo. Wins over everything. 2. Inconclusive telemetry. 3-8 the six class rows from the spec table.
Three fallback rows (no deficit + clean / snow / electrical damage) cover combinations the spec table omits; they are
marked as fallbacks in the YAML (`healthy`, `snow_no_loss`, `latent_electrical`).

### Telemetry states

- `inconclusive`: telemetry None, `status != "ok"`, `usable_clear_hours <= 0`, or `usable_clear_hours` unknown with no alert.
- `deficit`: `deficit_severity` is WARNING or CRITICAL. INFO (peer hint only) counts as no deficit.
- `no_deficit`: otherwise.

### Severity (our judgement)

Hardware fault: always CRITICAL. Soiling with CLEAN NOW: HIGH, escalated to CRITICAL when the physics alert is CRITICAL;
soiling with WAIT: LOW, never escalated (escalation applies only when action is not WAIT). Electrical suspected: HIGH
(CRITICAL if physics CRITICAL). Latent damage: HIGH. Snow loss: MEDIUM.
Unclear photo: MEDIUM. Early soiling, inconclusive, healthy: LOW. Rationale: a CRITICAL verdict auto-creates a work
order, so a routine clean should only reach CRITICAL when the measured loss itself is critical.

### Other rules

- Soiling row: action comes from `roi.evaluate(...)`, using `telemetry.expected_kwh_day`,
  `telemetry.attributable_deficit_fraction`, `telemetry.soiling_loss_rate_per_day` and `forecast`.
- Snow row: WAIT if any forecast hour within `melt_window_h` has `temperature_c >= melt_temp_c`; otherwise CLEAR IF SAFE.
- `confidence` = calibrated photo confidence; 0.0 for Inconclusive and Unclear photo.
- `FusionVerdict.roi_incomplete` is true when the soiling row's ROI inputs or cleaning cost were missing (action WAIT,
  no saving computed). `TelemetryEvidence.soiling_rate_source` is passed through to `RoiResult.soiling_rate_source`.

## Adapter mapping

Physics (`physics-deficit.md`) to `TelemetryEvidence`:

| Field | Source |
|---|---|
| `status` | scan/performance `status` (`ok`, `no_telemetry`, `baseline_unsupported_for_trackers`) |
| `usable_clear_hours` | `qc.plant.usable` |
| `deficit_severity` | open `plant_alerts` row (`alert_type="deficit"`) `severity` |
| `pi_median` | event `pi_median` |
| `deviation_percent` | alert/event `deviation_percent` |
| `expected_kwh_day` | physics event `expected_kw_mean` x the plant's clear/daylight hours per day (from the physics event's `clear_hours` per day, else the plant setting); for the scope being cleaned |
| `attributable_deficit_fraction` | `1 - pi_median` of the scope being cleaned (plant or string); never scaled by module share |
| `soiling_rate_source` | `soiling.method` + `label`, e.g. "rdtools_srr measured", "pvlib_kimber modelled (assumed default)" |
| `soiling_loss_rate_per_day` | `soiling.soiling_loss_rate_per_day` (fraction/day, positive = loss) |

Vision (`vision-predict.md`) `PredictResult` to `PhotoEvidence`: `predicted_class`, `confidence`, `is_ood`,
`needs_field_check`, `field_check_reason`, `model_version` map one to one (same names and units).
`ForecastHour`: Open-Meteo hourly `precipitation_probability` (%) and `temperature_2m` (C); `hours_ahead` = hour index
minus the current hour. `RoiSettings` comes from the plant settings (DESIGN.md 8.4); `module_count` is that of the
scope being cleaned and `expected_kwh_day` must be for the same scope.
