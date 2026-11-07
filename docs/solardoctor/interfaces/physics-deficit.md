# Physics deficit engine: interface for Workstream 3 (fusion / ROI / work orders)

Code: `backend/solardoctor/physics/`. Everything below matches the code on branch `feat/physics-deficit`.
Units: power kW, energy kWh, irradiance W/m2, temperature C, wind m/s, rain mm, PI (performance index =
actual / expected) dimensionless, `deviation_percent` = (expected - actual) / expected x 100 (positive = shortfall).
All timestamps are UTC.

## Python functions

| Function | Signature (short) | Returns |
|---|---|---|
| `deficit.scan_and_persist` | `(db, plant_id, start, end, baseline="pvwatts", now=None, nasa_fetch=..., openmeteo_fetch=...)` | `{status, qc_status, clock_offset_min, baseline, data_source, events: [DeficitEvent], alerts: [alert ids], qc, provenance}` for status `ok`; `qc_status` is `ok`, `time_offset_suspected` or `irradiance_unverified` (see Behaviour notes). Status `no_telemetry` and `baseline_unsupported_for_trackers` return only `{status, events: [], alerts: [], qc: {}, provenance: {}}`. Idempotent: one open alert per (plant, `deficit`, scope, inverter_id, string_id); a re-scan updates it. |
| `deficit.load_inputs` | `(db, plant, start, end, now=None, nasa_fetch=..., openmeteo_fetch=...)` | `(telemetry_df, weather_df, strings, inverters)` or `None` without telemetry |
| `deficit.performance` | `(plant, telemetry_df, weather, baseline="pvwatts", strings=(), inverters=())` | `Performance`: hourly PI per scope on QC-usable clear hours (`hourly[(scope, id)]` with `pi, actual_kw, expected_kw, n`), `qc`, `provenance`, `data_source` |
| `deficit.detect` | `(perf, plant)` | `list[DeficitEvent]` (scope, scope_id, name, severity, start, end, pi_median, expected_kw_mean, actual_kw_mean, deviation_percent, clear_hours, peer_z, evidence) |
| `deficit.peer_z` / `deficit.plant_hourly` | `(perf, min_hours)` / `(perf)` | per-string median PI + robust z / plant hourly frame (all hours) |
| `baseline.expected_power` | `(plant, weather, baseline="pvwatts"\|"clearsky"\|"hybrid")` | DataFrame `p_dc_kw, p_ac_kw, poa_global, cell_temp, solar_zenith`. 422 for trackers; 422 `hybrid_model_unavailable` when no trained artifact |
| `irradiance.resolve_weather` | `(plant, times, telemetry=None, db=None, now=None, nasa_fetch=..., openmeteo_fetch=...)` | DataFrame `ghi, poa, temp_air, wind_speed, precip_mm, ghi_clearsky, source` |
| `soiling_analytics.soiling_analysis` | `(plant, daily, rain_mm_hourly=None, reps=300)` | dict, see "Analytics result keys" |
| `soiling_analytics.degradation_analysis` | `(plant, daily)` | dict, see "Analytics result keys" |
| `soiling_analytics.latest` / `.save` | `(db, plant_id, kind)` / `(db, plant_id, kind, day, result)` | latest `plant_analytics` row as dict / idempotent upsert |
| `jobs.run_hourly` / `jobs.run_daily` | `(db, now=None, nasa_fetch=..., openmeteo_fetch=...)` | `{plant_id: status \| "error"}`. Hourly: scan of the last 24 h. Daily: rescan of 7 days + soiling + degradation (lookback 800 days). Active non-tracker plants only; a failing plant is logged and skipped. |

`daily` for the soiling functions: UTC-day index with `actual_kwh`, `expected_kwh` (QC-usable clear hours, so the ratio is a
PI), `insolation` (kWh/m2). Built by `jobs.daily_series`.

Jobs: `python -m solardoctor.physics.jobs hourly|daily`, or in the API with `SOLARDOCTOR_PHYSICS_JOBS=1` (default off; hourly
at each full hour, daily at 02:00 UTC). The repo has no generic scheduler (Axalon's jobs are FastAPI BackgroundTasks for
inspections), so this is a small asyncio loop in the API lifespan.

## Analytics result keys

Soiling (`soiling_analysis`; rates are fractions per day, positive = loss; ratios are 1 = clean; dates are ISO `YYYY-MM-DD`):
- always: `plant_id`, `days_with_data`, `status` (`ok` | `insufficient_data` | `unavailable`), `method` (`rdtools_srr` | `pvlib_kimber` | `none` | `unavailable`), `label` (`measured` | `modelled` | `none`); `reason` when status is not `ok`.
- `rdtools_srr` (>= 60 days): `soiling_ratio_p50`, `soiling_ratio_ci` [low, high], `soiling_loss_rate_per_day`, `soiling_loss_rate_ci_per_day` [low, high] (null with fewer than 2 valid intervals, then `note` says so), `soiling_loss_rate_pct_per_day` (percent per day), `cleaning_events` (dates of valid intervals after the first), `intervals` (valid soiling intervals), `ci_level_pct` (68.2), `note`.
- `pvlib_kimber` (rain data, < 60 days, or SRR found no interval; `note` says which): `soiling_ratio_p50`, `soiling_ratio_latest`, `soiling_loss_rate_per_day` and `_pct_per_day` (the assumed default, not a fit), `cleaning_events` (rain resets), `parameters` (cleaning_threshold mm, soiling_loss_rate, grace_period days, max_soiling), `days`, `note`.

Degradation (`degradation_analysis`): `plant_id`, `method` (`rdtools_yoy`), `label` (`measured`), `days_available`, `status` (`ok` | `insufficient_data`), `reason` (when insufficient, including sparse data with no year-over-year pairs); when `ok`: `rate_pct_per_year` (percent per year, negative = degrading) and `ci_pct_per_year` [low, high].
`plant_analytics` rows add `day` and `computed_at` on read (`soiling_analytics.latest`).

## Endpoints (`/api/v1`, viewer+ for GET, operator+ for POST/PUT)

All return 404 for an unknown plant/string and for one outside the caller's parks (a plant with no park is admin-only), and **422** `{"detail": {"status": "baseline_unsupported_for_trackers", "message": ...}}` for tracker
plants on every route except `PUT /performance/{plant_id}/thresholds`, which is a plain setting and works for trackers. Windows: default last 7 days, max 92 days, `start < end` (else 422). `baseline`: `clearsky|pvwatts|hybrid`, default `pvwatts`.

- `GET /performance/{plant_id}?start&end&baseline` -> `PerformanceResponse`: `status` (`ok` | `no_telemetry`), `data_source`,
  `series[]` (`ts, expected_kw, actual_kw, pi, clear, usable, source`), `events[]` (computed for the window, not persisted),
  `open_alerts[]` (persisted open deficit alerts), `soiling`, `degradation` (latest `plant_analytics` or null), `qc`, `provenance`.
- `POST /performance/{plant_id}/scan?start&end&baseline` -> `ScanResponse` (`status, qc_status, clock_offset_min, baseline, data_source, events, alert_ids, qc, provenance`); persists alerts.
- `PUT /performance/{plant_id}/thresholds` body `{"pi_warning": 0.95, "pi_critical": 0.90, "deficit_min_clear_hours": 3}`;
  needs `0 < pi_critical < pi_warning <= 1`, hours 1..24 -> same body plus `plant_id`.
- `GET /strings/{string_id}/peers?start&end` -> `{string_id, plant_id, status, normalised_yield, plant_median, peer_z, peers: [{string_id, name, normalised_yield, peer_z, clear_hours}]}`;
  `peer_z` is null with fewer than 4 comparable strings.
- Existing `GET /alerts`, `/alerts/{id}`, `/anomaly/{plant_id}` additionally return `scope, inverter_id, string_id, baseline, evidence` (parsed JSON); nothing removed.

Example shape (`GET /performance/1`, schematic: `<n>` stands for a number, no real values): `{"plant_id":1,"baseline":"pvwatts","status":"ok","data_source":"SIMULATED","series":[{"ts":"<utc>","expected_kw":<n>,"actual_kw":<n>,"pi":<n>,"clear":true,"usable":true,"source":"site_sensor"}],"events":[{"scope":"string","scope_id":<id>,"severity":"CRITICAL","pi_median":<n>,"peer_z":<n>,"clear_hours":<n>}],"open_alerts":[],"soiling":null,"degradation":null}`.

## Alert rows (`plant_alerts`, `alert_type = "deficit"`)

`scope` (`plant|inverter|string`), `inverter_id`, `string_id`, `baseline`, `expected_power_kw`, `actual_power_kw`,
`deviation_percent`, `severity`, `source` (= telemetry source), `is_resolved`, `message`, `evidence_json`.
`evidence_json` keys: `baseline, samples_used, data_source, qc, weather_provenance, cause_hint, pi_rolling_min, pi_series
{hours,min,median,max}, thresholds {pi_warning,pi_critical,min_clear_hours}, peer_z, window_start, window_end, pi_median, clear_hours`.

Severity: rolling median of hourly PI over `deficit_min_clear_hours` clear usable hours; `CRITICAL` if its lowest value is
< `pi_critical`, `WARNING` if < `pi_warning`; `INFO` only for a string with peer z <= -3 whose PI never went below `pi_warning`.
A plant-scope event means the strings are uniformly low (soiling, haze, curtailment class); a string event means one string
is an outlier among peers (drone target). One bad string does not raise a plant event.

Provenance (`source` per weather row): `site_sensor`, `nasa_power`, `openmeteo`, `clearsky_model`. With only `clearsky_model`
irradiance nothing can be verified as clear-sky, so no sample is usable and no alert is raised.
Telemetry `source`: `SIMULATED`, `PVDAQ`, `USER`.

## How WS3 should read it

- "Deficit >= threshold": open alert with `alert_type="deficit"` and `severity` in `WARNING|CRITICAL`; `INFO` is a peer hint only.
- "Cloudy / no QC data" (inconclusive, not healthy): `status == "no_telemetry"`, or `qc.plant.usable == 0` (scan/performance), or
  no `usable` hour in `series`. Absence of an alert in that case means nothing.
- Attributable deficit fraction: plant event `1 - pi_median` of plant energy (`deviation_percent / 100` is close but not identical: median of hourly ratios vs ratio of mean powers); string event
  `(1 - pi_median) x module_count / sum(module_count)` of plant energy.
- Soiling rate for ROI: `soiling.soiling_loss_rate_per_day` (fraction/day, positive = loss) with `soiling_loss_rate_ci_per_day`
  when `method == "rdtools_srr"` (`label: measured`, >= 60 days). `pvlib_kimber` (`label: modelled`) reports the assumed
  default rate and its parameters, not a fit. `status` `insufficient_data` / `unavailable` carries a `reason`.
  Degradation: `rate_pct_per_year` + CI, needs >= 2 years.
- Trackers: no baseline and no alerts; every route except `PUT thresholds` answers 422. `reference_9068.py` is a pvlib-gallery reference chain for tests only.

## What is SIMULATED

Seeded plants and the test generator (`tests/backend/physics/deficit_synth.py`) write `source="SIMULATED"`; alerts from them
carry `source="SIMULATED"` and `evidence.data_source="SIMULATED"`. Precision/recall in `docs/solardoctor/physics/DEFICIT_METRICS.md`
are measured on SIMULATED data only. Solar Data Tools is not installed, so with no irradiance-normalised energy the soiling
method is `unavailable`.

## Behaviour notes

- **Clock check:** the scan estimates the telemetry clock offset from site GHI vs the clear-sky curve (resolution one sampling step). At |offset| >= 30 min the scan returns `qc_status = "time_offset_suspected"`, `clock_offset_min`, and raises no events and writes no alerts. Otherwise `qc_status = "ok"`. It needs site GHI (> 50 % of rows) at <= 30 min sampling; otherwise `clock_offset_min` is null and the check is skipped.
- **Localisation:** every event carries `evidence.localisation`: `peer_compared`, `insufficient_peers` (strings present but fewer than 4 with enough clear hours: no string is singled out) or `no_string_data`.
- **Inverter-only telemetry:** with no plant meter and no strings, the plant series is the sum of the inverters, so a uniform deficit gives one plant event instead of one per inverter.
- **Alert lifecycle:** the detector never auto-resolves open deficit alerts (resolution and verify-fix belong to WS3). INFO rows (peer deficit below the alert threshold) are persisted with severity `INFO`. Idempotency (one open alert per scope and id) relies on a single writer (the jobs loop or the scan endpoint); there is no database unique constraint.
- **Unverified irradiance (rule for WS3):** a scan is `qc_status = "irradiance_unverified"` when fewer than 50 % of the QC-usable plant samples use site-sensor irradiance (the rest come from NASA POWER, Open-Meteo or the clear-sky model, whose error is shared by the whole plant). Then every plant- and inverter-scope event is capped at severity `INFO` (`evidence.capped_from` holds the computed severity, `evidence.irradiance_site_share` the share). String events keep their computed severity only when `evidence.localisation == "peer_compared"`, because comparing a string with its peers cancels the shared irradiance error. WS3 must therefore not turn an `INFO` plant/inverter event into a work order or a "clean now" call. The 50 % limit is fixed, not tuned. `time_offset_suspected` takes precedence when both apply. Deviation from the review brief: inverter-scope events are capped too, since no peer comparison exists for them.
- **Rain probability:** the Open-Meteo hourly request keeps `precipitation_probability` (and `precipitation`) next to the irradiance fields, so the weather frame can feed the ROI engine's rain-aware WAIT decision (a rain forecast makes cleaning now wasteful).
- **String-sum plant total:** with no plant meter, the plant series is the sum of the strings only at timestamps where strings holding at least 90 % of the module share report; otherwise NaN (a missing string would read as a deficit).
- **Access:** all `/performance` and `/strings/{id}/peers` routes are scoped to the caller's parks (404 outside them); reads viewer+, `POST scan` and `PUT thresholds` operator+ (technicians get 403).
