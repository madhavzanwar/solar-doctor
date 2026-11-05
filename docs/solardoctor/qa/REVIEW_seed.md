# QA review: feat/seed (efce7d2, 3 commits on b07e7e4)

Reviewer: sd-qa. Detached worktree, shared venv, own runs (NASA POWER and OEDI S3 reachable). No source or branch modified.
Verdict: **NO-SIGN-OFF** (one HIGH defect in the PVDAQ importer, two MEDIUM, rest LOW). The simulated seed itself is sound.

## Findings (severity ranked)

### HIGH-1 PVDAQ timestamps are shifted by 1 h during DST (fixed UTC-7 assumption is wrong)
`backend/solardoctor/seed/pvdaq.py:78-79,98-99` (`_utc_offset_hours`, `read()`); docstring lines 14-17; wrong assumption encoded in `tests/backend/test_seed_pvdaq.py:36,70-74`.
The importer adds a fixed +7 h ("local standard time"). The 9068 files are on the **DST-observing local clock** (America/Denver).
Evidence from the downloaded file (file clock = `measured_on`):
- Pad-1 POA first/last >20 W/m2, midpoint: 2024-01-10 07:35-16:40 (12:07), 2024-12-10 07:50-16:05 (11:57); in June 2024-06-20 05:50-20:10 (13:00). pvlib solar noon at Kersey (-104.55 deg) is 11:57 UTC-7 (=18:57 UTC), so winter = MST and summer = MDT (UTC-6).
- Result: every June row lands 1 h late in UTC (local noon 13:00 MDT = 19:00 UTC, importer stores 20:00 UTC). Any expected-vs-actual comparison or daily rollup is biased; the whole `Mapped.meta_notes` text is misleading.
Repro: `PYTHONSAFEPATH=1 PYTHONPATH=backend:. SOLARDOCTOR_DB_URL=sqlite:///x.db python scripts/import_pvdaq.py` then compare the AC/POA diurnal peak in UTC with `pvlib.Location(40.3864,-104.5512).get_solarposition` noon.
Fix: `tz_localize("America/Denver", ambiguous=..., nonexistent=...)` (confirm per system, metadata only has `timezone_code: 7`), then `tz_convert("UTC")`; handle the fall-back duplicate hour; rewrite the fixture test with a June (DST) and a January case; fix docstring/notes.

### MEDIUM-1 `--reset` crashes once a seeded fault has any comment, photo or detection
`backend/solardoctor/seed/builder.py:66` (`delete(PanelFault)...`). SQLite FKs are ON (`db/session.py:32`); `fault_comments`, `fault_photos`, `detections` reference `panel_faults.id` with no cascade.
Repro (done): seed, `POST` a comment on fault 5 (technician work), `python scripts/seed.py --reset` -> `IntegrityError: FOREIGN KEY constraint failed` (DELETE FROM panel_faults ...), exit 1. The failure is safe (the transaction rolls back, nothing destroyed) but `--reset` is unusable after real use of the work-order flow. Also, plants/telemetry deletion is attempted first in the same transaction, so the error message is confusing. Fix: delete comments/photos/detections of those faults first (or skip faults that have children and say so), and add a test. Existing test `test_second_run_is_a_no_op_and_reset_rebuilds` never creates child rows.

### MEDIUM-2 Seeded telemetry is not usable by the diagnose/fusion path by default; windows can be ~2 months old
`backend/solardoctor/seed/irradiance.py:discover_window`, `physics/diagnosis_service.py:619-660`. NASA POWER GHI lags: my run on 2026-11-05 produced the window 2026-08-02..2026-08-31 (66 days stale). `diagnose` rejects telemetry older than 24 h and SIMULATED telemetry without `allow_simulated=true`, so "telemetry cross-check" in the demo returns 422 unless the demo passes both flags/an env override. Any "last 24 h / last 7 d" dashboard widget will be empty. This is documented partly (SEED_PLAN notes window lag) but the consequence for the diagnose demo is not. Recommend: document, or offer `--shift-to-now` clearly labelled (time-shifted irradiance), or set `SOLARDOCTOR_MAX_TELEMETRY_AGE_HOURS` in the demo env. Also PanelFault `first_seen_date` = `date.today()` (`builder.py:_ensure_faults`) while telemetry is Aug 2026: fault dated 2026-11-05 describing a deficit seen in August.

### LOW-1 Licence/attribution for PVDAQ and NASA POWER not recorded
`THIRD_PARTY_NOTICES.md` has no PVDAQ/NASA entry (SEED_PLAN admits it). Independently verified (data.openei.org/submissions/4568, JSON-LD + page): **"Photovoltaic Data Acquisition (PVDAQ) Public Datasets", NREL (Deline, Perry, Deceglie, Muller, Sekulic, Jordan), DOI 10.25984/1846021, licence CC BY 4.0** (https://creativecommons.org/licenses/by/4.0/); the dataset's listing includes the `pvdaq/2023-solar-data-prize/` prefix. Attribution (creator, title, DOI, licence link, "changes made: 5->15 min means, UTC conversion") is required before display. Caveat: I did not find a separate Solar Data Prize licence page; confirm with the lead that the prize prefix carries no extra terms. NASA POWER data: open data, acknowledgement requested; add a line. Nothing is displayed as PVDAQ in the UI yet, only `source="PVDAQ"` in the DB.

### LOW-2 PVDAQ plant row looks like a fixed-tilt plant
`pvdaq.py:132-133`: `tilt=0.0, azimuth=180` for a single-axis tracker, no tracker flag in the schema; any code applying the fixed-tilt baseline to plant 'PVDAQ 9068 SR_CO' (e.g. `/plants/{id}/expected`) will give a wrong baseline. `p_expected_kw` is correctly left NULL; recommend a guard in the physics routes.

### LOW-3 Smaller notes
- `pvdaq.py:104`: negative inverter AC (min -17 kW night standby) silently clipped to 0; POA negatives clipped. Note in `meta_notes`.
- `pvdaq.py:106`: 15-min mean accepted from 1 of 3 samples (no minimum-count); gap days (2024-06-08/09/10: 705 missing 5-min rows) are correctly dropped, not filled (7938 rows = 2646 x 3; expected 8640).
- `download_prize_files`: S3 anonymous signing disabled works (verified, 4 s, 17 MB cache). `dest / Path(key).name` is safe from traversal; `--system-id` is `int`; offline paths are user-supplied local files (no risk). `pick()` falls back to the shortest name when no file range covers the window, silently; the result then errors with "no rows", acceptable. Cache is never revalidated.
- Alert evidence on Bhadla uses cloudy-spell days: alert at 2026-08-20 (day 18) is outside the spell (days 15-17) but its 3-day sustain window (days 16,17,18) includes two spell days (PI deficit 5.2 % on both: real, soiling is multiplicative, not a false positive). Skipped low-POA days (<8 samples, e.g. Pavagada day 16) do not reset the sustain counter (`alerts.py:daily_series`/`_run_state_machine`): arguably should reset or be documented.
- `panel_faults` has no `source` column; labelling relies on `notes LIKE 'SIMULATED%'`, which the reset also uses (a user who edits a seeded fault's notes detaches it from reset, harmless).
- Parks (`PARK_*`) and project rows carry real-sounding names; project name/description say SIMULATED, parks do not (no column). Plants API carries `source`.
- `SOLARDOCTOR_SEED_*_PASSWORD` shorter than 10 chars gives an uncaught ValueError traceback from `create_user`.
- DB 5.0 MB, seed 9 s (with network, warm cache), PVDAQ 4 s + 17 MB cache. Fine.

## Verification log

### (1) Tests
- Full `tests/backend` on feat/seed: **754 passed, 9 failed, 1 skipped**. Main is 734 passed, 9 failed, 1 skipped, so exactly +20 tests (17 seed, 4 pvdaq minus accounting = new files only) and the same 9 weight-dependent failures (test_api_contract x6, test_park_grid_endpoint x2, test_pipeline_unit x1). No regression.
- Meaningfulness: telemetry and baseline share `physics.solar.expected_power`, so healthy PI = 1.0 is true by construction (stated in `simulate.py` docstring). The tests are not purely tautological because they recover **injected, independently specified** quantities from the DB: soiling slope (-0.003/day +- 0.0006), S-04 PI 0.85-0.90 vs peers 0.95-1.02, cloudy-spell PI equals neighbouring days, AC <= rating, night = 0, labelling, second run no-op, logins, technician fault visibility, production guard. Gaps: no test for reset with real/PVDAQ/user rows, no reset-with-comments test (MEDIUM-1), DST test absent (HIGH-1), no assertion that Forecast rows are labelled other than by model name, `test_everything_is_labelled_simulated` does not query every table.

### (2) Seed runs (temp SQLite)
- Run 1 (NASA POWER, window 2026-08-02..08-31): all 3 plants `irradiance=NASA_POWER`, 31 680 telemetry rows, 5 alerts, 9 s. Run 2: "exists" for all plants, users unchanged, **DB byte-identical** (cmp).
- `--offline`: `SYNTHETIC_CLEARSKY`, window ends yesterday, same structure and alert set; labelled "SYNTHETIC ... not measured data; network disabled (--offline)".
- Every table with a `source` column queried: `plants` 3/3, `telemetry` 31 680/31 680, `plant_alerts` 5/5, `weather_cache` 3/3 = SIMULATED. Tables without a source column: inverters (`vendor`=SIMULATED), forecasts (`model_name`=seed_physics_hindcast_SIMULATED), panel_faults (notes start SIMULATED), projects (name/description), strings, parks (unlabelled, see LOW-3). Users excluded.
- Irradiance provenance recorded per plant in `weather_cache(kind=seed_meta)` JSON (`irradiance_source`, note, window, seed) and `seed_manifest.json`. Nothing is presented as real. Caveat: fault `first_seen_date` is run date (MEDIUM-2).

### (3) Secrets / safety
- No hard-coded passwords in the diff (grep); generated with `secrets.token_urlsafe(15)` (20 chars), printed once to stdout, not in the manifest, DB (hash only) or logs. Existing users untouched on re-run.
- `SOLARDOCTOR_ENV=production python scripts/seed.py` -> rc 2, message, no DB created. `--force` path not exercised.
- `--reset` with a DB containing a PVDAQ plant (+telemetry), a `USER` plant (+telemetry, alert) and an unrelated fault in a seed park (notes "field-observed"): all preserved, users preserved, SIMULATED plants rebuilt with new ids. Only failure mode is MEDIUM-1. A same-named non-SIMULATED plant is skipped, not overwritten.

### (4) Independent recomputation (own scripts, pvlib PVWatts from stored POA/T_mod, 14 % losses, 0.96 inverter; POA also reproduced from stored GHI with Erbs + isotropic, ratio 1.000)
- S-04: per-string PI day 0-9 = 1.00 (all strings); from day 10 S-04 = 0.86 -> 0.824, healthy strings 0.98 -> 0.94 (soiling). S-04 / median(peers) = **0.871-0.879** for days 10-26 (deficit 12.1-12.9 %, injected 12.5 %); before day 10 = 0.996-1.004. Matches the alert (12.5 %, string_underperformance).
- Soiling: Bhadla plant deficit 0.1 % (day 0) -> 8.6 % (day 29), ~0.3 %/day; Pavagada 5.7 % at start, -0.2 % after cleaning day 6, back to 7.0 %; PCCoE (plant level incl. S-04) 1.7 % -> 4.1 % at day 10 (S-04 step) -> 7.8 %.
- Cloudy spell days 15-17: eligible POA ~285 vs ~650 W/m2 on clear days (Bhadla), deficit continues the soiling trend (4.6/5.2/5.2 %, no spike); no alert has a timestamp in the spell (alerts: Bhadla 08-20, PCCoE 08-14 [S-04] and 08-29, Pavagada 08-04 resolved 08-08 and 08-27). Alerts come from `anomaly_service.detect_and_persist_anomaly` (log lines "Anomaly alert created"), not hand-written.
- Dashboard view: PCCoE shows an open string_underperformance WARNING (12.5 %) plus plant-wide soiling 5.7 %; Pavagada one resolved + one open; Bhadla one open; all stale by ~66 days (MEDIUM-2).

### (5) PVDAQ
- Real run (June 2024, system 9068): 7938 rows, 4 s, 17.8 MB cached; second run row count identical (idempotent). Plant: 4738 kWdc, ac 3820 (2 x 1910), 40 320 x 117.5 W modules, gamma -0.0028 per C, lat 40.3864 lon -104.5512 (all from metadata, none invented).
- Magnitudes: peak plant AC 3790 kW = 99 % of 3820 kW AC; inverters max 1903/1904 kW vs 1910; June energy 960 MWh over 27.6 valid days = 203 kWh/kWdc (about 7.3 kWh/kWp/day), plausible for a CdTe tracker in Colorado in June. Units kW, W/m2 consistent.
- Timezone: wrong in summer (HIGH-1). Averaging 5 -> 15 min: left-labelled, correct bin alignment; NaN: gaps dropped, partial bins accepted (LOW-3). Regex `^inverter_(\d+)_ac_power` correctly excludes the `inverter_module_*` sub-module columns (no double counting).
- Licence: CC BY 4.0, DOI 10.25984/1846021 (LOW-1).

### (6) Technician scoping (own API run, AUTH_MODE=users)
- Seeded technician: PCCoE -> [S-04], Bhadla -> [R12-C7], Pavagada -> [] (unassigned fault hidden); comments on faults 1,2 = 200, fault 3 (unassigned) = 404, PATCH on it = 404. A fresh technician with no assignments sees [0,0,0]. No-token `/plants` and `/alerts` = 401. Technicians can read `/plants` and `/alerts` (documented in API_AUTH.md as project data).

### (7) Repo hygiene
- `data/cache/` is gitignored (`.gitignore:161`); diff contains 13 files, largest 324 lines; no data, DB or weights committed. `make seed` / `seed-pvdaq` targets present.

## Sign-off status
NO-SIGN-OFF until HIGH-1 is fixed with a DST-aware test; MEDIUM-1 and MEDIUM-2 fixed or explicitly accepted by the lead; LOW-1 notices entry added. The simulated seed (items 2-4, 6, 7) otherwise meets the brief.
