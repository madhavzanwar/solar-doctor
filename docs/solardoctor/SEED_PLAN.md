# Seed plan (`make seed`, `scripts/seed.py`, `scripts/import_pvdaq.py`)

Status: IMPLEMENTED on branch `feat/seed` (code in `backend/solardoctor/seed/`, CLIs `scripts/seed.py` and
`scripts/import_pvdaq.py`, tests `tests/backend/test_seed*.py`). The sections below are the original plan; the
"Implementation notes" section at the end records where the implementation deliberately differs.

## 1. Users
- 1 admin, 1 technician via `create_user` (idempotent: skip if the email exists). Emails/passwords come from
  `SOLARDOCTOR_SEED_ADMIN_EMAIL/PASSWORD` and `SOLARDOCTOR_SEED_TECH_EMAIL/PASSWORD`; when unset, generate random
  passwords and print them once. No default password is committed.
- The technician gets project membership for the seeded plants' projects, and seeded faults/work orders are
  assigned to the technician's email (that is how work-order scoping matches, see `API_AUTH.md`).

## 2. Plants (all `source="SIMULATED"`)
| Plant | Capacity | Location |
|---|---|---|
| Bhadla Block C | 50 MW | Bhadla, Rajasthan |
| PCCoE Rooftop | 120 kW | Pune, Maharashtra |
| Pavagada Unit 4 | 25 MW | Pavagada, Karnataka |

Latitude/longitude/tz (`Asia/Kolkata`), tilt, azimuth, module and inverter counts, temperature coefficient and tariff are
filled from the `plants` model fields and documented in the script with their basis (site coordinates from public
maps; tilt ~ latitude; azimuth 180). Anything not sourced is labelled an assumption in a comment.
Each plant is linked to an Axalon `Park` per the 1:1 link added by sd-physics.

## 3. Irradiance input
1. Fetch NASA POWER hourly (`ALLSKY_SFC_SW_DWN`, `ALLSKY_SFC_SW_DIFF`/`DNI` where available, `T2M`, `WS10M`) for the last
   30 complete days at each coordinate. Cache as CSV under `data/cache/nasa_power_<plant>_<start>_<end>.csv`
   (gitignored). Re-runs read the cache.
2. Offline fallback (network blocked or API error): pvlib clear-sky (Ineichen, Linke turbidity from pvlib's
   lookup) multiplied by a **synthetic cloud model**: a seeded AR(1) daily clearness index plus intra-day
   noise. Every row produced this way carries `irradiance_source="SYNTHETIC_CLEARSKY"`, the seed prints a
   warning, and the UI badge stays `SIMULATED`. The fallback is never described as measured data.

## 4. Telemetry generation (30 days, 15-min steps)
- pvlib `ModelChain`/PVWatts: transposition (Perez) to POA, cell temperature (SAPM/Faiman), DC to AC with
  inverter clipping at AC rating. Fixed RNG seed (`--seed`, default 42) for reproducibility.
- Add measurement noise (~1 % multiplicative) and nighttime zeros.
- Injected, labelled events (also written to a `seed_manifest.json` so tests can assert detection):
  - **Soiling ramps:** per-plant linear loss 0.1-0.3 %/day, reset by a "cleaning" or by a rain day (>2 mm).
  - **String fault (one plant):** one string at 0 current for a fixed window, visible as a deficit on one inverter/string.
  - **Cloudy spell:** 3 consecutive days of reduced clearness index (physics expected power still computed
    from the true irradiance, so this must NOT raise a loss alert; it is the false-positive control).
- All rows `source="SIMULATED"`.

## 5. Alerts and diagnoses
Run the physics module's own anomaly detector over the generated series (do not hand-write alerts): the soiling
ramps and the string fault should produce alerts with severity from the module; the cloudy spell should produce
none. Seed 1-2 resolved alerts for history. Each alert and diagnosis row also carries `source="SIMULATED"`.

## 6. `scripts/import_pvdaq.py`
- Uses `pvdaq_access` (https://github.com/NatLabRockies/pvdaq_access) to download PVDAQ system 9068 (used in
  pvlib's gallery) for a bounded date range; metadata (lat/lon, tilt, azimuth, capacity) from PVDAQ's system
  metadata, not invented.
- Creates a fourth plant with `source="PVDAQ"`, telemetry rows with `source="PVDAQ"`, cached under
  `data/cache/pvdaq_9068_*.csv`. Network failure: exit non-zero with a clear message; no fake fallback.
- Licence: check the dataset terms and add the attribution to `THIRD_PARTY_NOTICES.md` / the UI before shipping.

## 7. Behaviour and tests
- `make seed` is idempotent (`--reset` drops only rows with `source="SIMULATED"`; never touches PVDAQ or user data).
- Refuses to run when `SOLARDOCTOR_ENV=production` unless `--force`.
- Tests: second run adds no duplicates; all rows labelled; injected soiling slope recovered within tolerance;
  AC power never above the AC rating; zero at night; technician can log in and sees only its assigned work orders.

## 8. Implementation notes (as built)

Run: `make seed` (or `python scripts/seed.py [--reset] [--offline] [--end YYYY-MM-DD] [--seed N]`), `make seed-pvdaq`.

- **Window.** NASA POWER GHI lags real time by weeks/months. The seed probes the last 100 days at Bhadla and ends
  the 30-day window on the latest day with a complete 24 h GHI record (`discover_window`). So timestamps can be
  weeks to months older than "now"; `--end` pins the window. All plants share one window.
- **Irradiance.** `pvlib.iotools.get_nasa_power` hourly `ghi, temp_air, wind_speed`, cached as
  `data/cache/nasa_power_<plant>_<start>_<end>.csv` (gitignored). Hour averages become 15-min values by
  interpolating the clear-sky index. Fallback (`SYNTHETIC_CLEARSKY`: clear-sky x seeded AR(1) cloud model) on any
  fetch error, > 5 % GHI gaps or `--offline`. The source per plant is stored in `weather_cache`
  (`kind="seed_meta"`, `source="SIMULATED"`, JSON `irradiance_source`/`irradiance_note`) and in
  `data/cache/seed_manifest.json`. (`plants` has no metadata column; no schema change was made.)
- **Telemetry** is the repo's own `physics.solar.expected_power` evaluated on the true irradiance, times injected
  events, times 1 % noise. Healthy PI is therefore ~1.0 by construction: the seed tests the detection pipeline,
  not model accuracy. `p_expected_kw` holds the clean physics baseline (no soiling); `v`/`i` are left NULL.
  Plant-level rows have `inverter_id`/`string_id` NULL; PCCoE additionally has inverter-level and per-string rows.
- **Injected events** (see the manifest): soiling Bhadla 0.30 %/day, PCCoE 0.20 %/day, Pavagada 5.5 % at start
  then cleaned on day 6, 0.30 %/day after; PCCoE string S-04 -12.5 % DC from day 10; cloudy spell on days 15-17
  (GHI x 0.35, applied to the irradiance, so expected power sees it).
- **Alerts** (`seed/alerts.py`): daily PI on eligible hours (elevation > 15 deg, POA >= 250 W/m2, not clipped);
  3 consecutive days over the plant's soiling threshold (5 %) call `anomaly_service.detect_and_persist_anomaly`
  (types `soiling_loss`, `string_underperformance`); a day back under the threshold resolves the alert.
  The S-04 alert is measured against peers (median string), so soiling does not mask it. Thresholds are set
  temporarily (the module keeps them in process memory) and removed afterwards.
- **Forecast rows.** To make `/forecast/{id}/summary` return data the seed writes 2 days (192 rows, 15-min) of
  `forecasts` per plant: model `seed_physics_hindcast_SIMULATED` (clean physics baseline as "prediction",
  simulated telemetry as `actual_power_kw`). It is a hindcast, not a forecast. NOTE: `get_forecast_summary`
  divides the power sum by 60 (assumes 1-min spacing), so its `total_*_kwh` are 15x too small for this 15-min
  data. That is an sd-physics issue, not changed here.
- **Faults.** Three `panel_faults` (S-04 string CRITICAL, assigned to the technician; Bhadla hot-spot-low assigned;
  Pavagada bypass-diode unassigned), notes start with `SIMULATED`. The technician is a member of the seed
  project, so `/parks/{id}/faults` shows exactly the two assigned faults. No `diagnoses` rows are seeded.
- **Users.** `admin@solardoctor.example`, `technician@solardoctor.example` (override with
  `SOLARDOCTOR_SEED_ADMIN_EMAIL/PASSWORD`, `SOLARDOCTOR_SEED_TECH_EMAIL/PASSWORD`); unset passwords are generated and
  printed once. Existing users are never modified.
- **Idempotency.** Re-run = no changes (plants matched by name). `--reset` deletes SIMULATED plants, their
  telemetry/alerts/forecasts/inverters/strings, seed faults and `seed_meta`; users, PVDAQ plants and parks stay.
  `SOLARDOCTOR_ENV=production` refuses unless `--force`.
- **Size.** ~31.7k telemetry rows (2880 per plant + PCCoE inverter/string rows), SQLite ~5 MB.

### PVDAQ import (`scripts/import_pvdaq.py`)
- System 9068 (`SR_CO`, Kersey CO, 4738 kWdc, 2 x 1910 kWac, single-axis tracker, CdTe) is a **DOE 2023 Solar Data
  Prize** system. It is NOT under `pvdaq/csv/pvdata/system_id=9068` (what `pvdaq_access.downloadData` v0.1.2 reads,
  so that call silently downloads nothing); it lives at `s3://oedi-data-lake/pvdaq/2023-solar-data-prize/9068_OEDI/`.
  `downloadSolarPrizeData` would fetch every file (several GB), so the importer uses the same anonymous boto3 access
  but fetches only `*_ac_power_data*.csv`, `*_irradiance_data*.csv` and `*_system_metadata.json` (~18 MB for the
  2024-01..2025-04 slice), cached in `data/cache/pvdaq_9068/`. Only Solar Data Prize systems are supported.
- Command: `python scripts/import_pvdaq.py --system-id 9068 --start 2024-06-01 --end 2024-06-30` (or `make seed-pvdaq`).
  Offline: `--ac-csv ... --irr-csv ... --metadata ...`.
- Mapping and assumptions are in the module docstring of `backend/solardoctor/seed/pvdaq.py` (timestamps treated
  as UTC-7 local standard time, 5 -> 15 min means, plant AC = sum of inverter AC, no expected power for trackers).
- Dataset licence/attribution is NOT yet recorded in `THIRD_PARTY_NOTICES.md` (not verified; lead to decide).
- Tests use an artificial fixture (`FIXTURE_NOT_REAL_DATA`) with the real column layout; the real import was run
  once by hand against the live bucket.
