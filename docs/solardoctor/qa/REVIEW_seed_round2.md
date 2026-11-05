# QA round 2: feat/seed (tip 7321c12, merged with origin/main f867746)

Reviewer: sd-qa. Detached worktrees, shared venv, own repros (real PVDAQ 9068 and NASA POWER over the network). No source or branch modified; worktrees removed.
Verdict: **SIGN-OFF** (no HIGH or MEDIUM findings; LOW items listed).

## Findings (severity ranked)

### LOW-1 Default (unshifted) seed still mixes dates
Plain seed: window ends 2026-08-31, fault `first_seen_date` = 2026-08-31 but `due_date` = today+7/+14 (2026-11-12/19). With `--shift-to-now` it is consistent (first_seen 2026-11-04, due 11-12/11-19). In both modes `first_seen_date` is the window end, not the deficit onset (S-04 alert 2026-10-18 shifted / 08-14 plain; onset day 10). Cosmetic.

### LOW-2 PVDAQ "dropped" note counts the whole file, not the import window
A June and a January import both print "19 ambiguous/non-existent DST rows dropped"; all 19 are 2024-11-03 01:xx (12 AC + 7 irradiance rows) and are outside those windows. Misleading, harmless.

### LOW-3 GHI is not strictly <= clear-sky
GHI is k x clear-sky with k clipped at 1.15 (NASA values above the Ineichen model are kept). Vs the repo's own clear-sky: max ratio 1.150 (Pavagada), 1.115 shifted Bhadla; 92 of 1268 daytime steps > 1.0 at Bhadla (shifted), 31/1312 Pavagada; identical behaviour without the flag (138 and 68). Night GHI and AC are 0 in every case. Not caused by shifting; document or clip at 1.0.

### LOW-4 Shifted weather is seasonally mismatched
Aug (monsoon) cloud index and temperature are placed on Oct 6 to Nov 4 (+65 days; solar geometry is recomputed). Labelled (`NASA_POWER_TIME_SHIFTED`, note and `shift_days` in `weather_cache`, manifest, CLI), so honest, but PCCoE mean clearness is 0.15-0.67. Also Bhadla POA vs an independent Erbs+isotropic transposition is +3.7 % median (p95 +5.8 %) in Nov, vs +0.3 % in Aug: a transposition-model difference inside `physics/solar.py`, not seed code.

### LOW-5 Reset edge cases
- A user fault in a seed park whose notes START with "SIMULATED" is deleted by `--reset` (prefix match). A note that merely mentions SIMULATED later is preserved (tested). Acceptable, but the label is notes-based because `panel_faults` has no source column.
- Reset deletes comments/photos on seeded faults (technician work; blobs in the object store are orphaned) and sets `detections.fault_id` NULL on detections attached to them. Intended per code comment; the CLI does not warn.
- Failed password validation happens after parks and project are already committed (parks 3, users 0, plants 0); rerun is fine. Exit code 1, clean message, no traceback.
- Re-running without `--shift-to-now` on a shifted DB prints the freshly computed window start (2026-08-02) while the data on disk is shifted; the "ends" line uses the stored data. Cosmetic.

### LOW-6 Notices and deps
`boto3` is imported but not declared in any requirements file (message says `pip install pvdaq_access`, which pulls it). Notices are otherwise accurate (see 4).

## Verification

### (1) PVDAQ DST (real data)
- Import June 2024 (7935 rows) and January 2024 (8820 rows). Onset/offset midpoint of POA > 20 W/m2 minus pvlib solar noon at (40.3864, -104.5512) in UTC: **June median 0.0 min, January +3.0 min** (27 and 31 days). Power-weighted centroid: January -3 min (AC) / +4 (POA); June -39 / -35 min, caused by afternoon convective weather asymmetry (onset/offset is unaffected). Old fixed UTC-7 would put June at +60 min. Within ~20 min on the robust metric both seasons; the author's -7.5 min June figure was not reproduced exactly (different metric).
- 2024-03-10 spring forward: the file has no 02:xx hour; nothing invented, 0 dropped. Local midpoints Mar 8-12 in UTC: 19:15, 19:07, 19:00, 18:52 (continuous, no 1 h jump).
- 2024-11-03 fall back: file has one 01:xx hour (ambiguous). It is dropped (12 + 7 rows, reported), so 8 bins (2 h) are missing in UTC (07:00-08:45); nothing shifted. Midpoints Nov 1-4 in UTC 18:30, 18:37, 18:45, 18:52 (continuous).
- Idempotent: re-import of June gives identical row count, sum(p_ac) and sum(poa); overlapping import (06-15..07-10) leaves 10815 rows, 10815 distinct (ts, inverter) keys, one plant, two inverters.
- Tests in the branch cover DST both seasons, fall-back drop and 2-of-3 bins; they pass.

### (2) --reset
Seeded DB + PVDAQ plant (7935 rows) + USER plant + telemetry + comment, photo and detection on S-04 + user faults in a seed park (one noting "...the SIMULATED S-04 string" later in text) + a user detection/comment. `--reset` exits 0 (earlier crash fixed). Preserved: users 2, PVDAQ plant and rows, USER plant and row, the user fault with the late-mention note and its comment and detection, inspection. Removed/rebuilt: SIMULATED plants (ids 1-3 to 6-8), their strings/inverters/forecasts/alerts/telemetry (no orphans), seeded faults (recreated), the S-04 comment and photo; detection detached (fault_id NULL). Park names "(SIMULATED)".

### (3) --shift-to-now (network, 2026-11-05)
- Window 2026-10-06..2026-11-04 (+65 days), all plants `NASA_POWER_TIME_SHIFTED`; label in telemetry meta (`seed_meta`), report line, manifest. Plant/telemetry/alert rows keep `source=SIMULATED`.
- Night: 0 GHI rows and 0 AC rows at solar elevation < 0 (all plants). Expected power recomputed with independent PVWatts from stored POA/T_mod: max diff 0.009 kW. GHI vs clear-sky: LOW-3.
- S-04 / peers (daily, POA > 400): 0.99-1.01 until day 10, then 0.869-0.879 (injected 12.5 %), same as unshifted (0.872-0.879).
- Cloudy spell days 15-17 = 2026-10-21..23: daily clearness 0.32/0.28 etc.; no alert timestamps in the spell. Alerts (all from `anomaly_service`, "Anomaly alert created" logs): Bhadla 10-26; PCCoE string_underperformance 10-18 (12.5 %) and soiling 11-02; Pavagada 10-08 resolved 10-12 (cleaning day 6) and 10-31. Forecast rows 2026-11-03..04, faults 2026-11-04 / due 11-12, 11-19: consistent with window.
- Idempotency: shift run 1 vs run 2 DB byte-identical; plain run 1 vs 2 byte-identical; offline + flag: flag ignored, labelled, synthetic. Offline note "window already ends yesterday" ok.

### (4) THIRD_PARTY_NOTICES
PVDAQ: NREL authors, DOI 10.25984/1846021, CC BY 4.0 confirmed again on data.openei.org/submissions/4568 (licence URL in JSON-LD). Changes made listed accurately; the caveat that no separate Solar Data Prize licence page was reviewed is honest. NASA POWER: acknowledgement only, not overclaimed; says seeded rows are simulations. pvdaq_access: PyPI metadata BSD 3-Clause, "access pattern only, no code" consistent with the file. No overclaiming found.

### (5) Minors
Short password: clean `ERROR:` line, rc 1, no user/plant created (LOW-5). Clip counts reported (66 / 2882 June; 174 / 5094 January). 2-of-3: [1,2,3]->2.0, [4,nan,6]->5.0, [nan,nan,9]->NaN. Park names "<name> (SIMULATED)".

### (6) Suites
- feat/seed alone: 773 passed, 11 failed, 1 skipped. Failures: the 9 weight-dependent ones plus `physics/test_golden::test_matches_captured` and `physics/test_physics_sanity::test_alert_worker_flags_shortfall_against_pvlib_baseline`. Those two also fail on pristine origin/main in this shared venv, so they are environment-dependent here (the lead's main figure was 9 failures) and not a branch regression; worth the lead re-running them in the CI environment.
- Trial merge of feat/seed into origin/main f867746 (no new fetch commits): clean merge, no conflicts; full tests/backend 775 passed, 11 failed (same set), 1 skipped; ruff clean; `alembic heads` single head 0011.

## Sign-off
SIGN-OFF. HIGH-1, MEDIUM-1 and MEDIUM-2 from round 1 are fixed and verified with own repros; the licence entries are correct. Remaining items are LOW. Condition for the lead: confirm the two env-dependent failures (golden, alert worker) are green in CI on main.
