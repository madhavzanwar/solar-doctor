# QA round 2: feat/physics-port (69c732d) vs prior review (7f6b87f)

Verdict: NO-SIGN-OFF. One major (M1 only partly fixed: httpx's own logger still prints the key; the author's test
hides this by test-order), one medium (M2 stale/SIMULATED telemetry used silently). Everything else verified fixed.

## Evidence
- tests/backend on the branch: 684 passed, 9 failed (baseline weight-dependent set), 1 skipped. Trial merge into
  claude/practical-dirac-fddnwu (auth work): clean merge, 724 passed, same 9 failures, 1 skipped.
- Single alembic head (0011, down_revision 0010) on the merged tree. SQLite: upgrade head, downgrade 0010, upgrade head,
  downgrade base, upgrade head all rc=0.
- test_review_fixes.py run against OLD code (7f6b87f): 19 of 21 fail, 2 pass (retained-behaviour cases). Not vacuous.
  But see F1: the M1 tests pass only in the full suite.

## Findings (severity ranked)

### MAJOR
F1. M1 not fully closed: the API key still reaches logs through httpx's own logger. httpx logs every request at INFO:
`HTTP Request: GET https://api.weatherapi.com/v1/forecast.json?key=SUPERSECRETKEY&q=... "HTTP/1.1 401 Unauthorized"`
(also on 200). Any deployment with root/httpx logging at INFO (basicConfig, docker log drivers, Sentry breadcrumbs)
leaks the key on every weather call. The repo has no logging config, so default Python setup hides it, but it is one
config line away.
- The author's own tests `test_weather_api_key_not_logged[401|500]` FAIL when run alone
  (`pytest tests/backend/physics/test_review_fixes.py -k api_key_not_logged` -> 2 failed). They pass in the full suite only
  because an earlier alembic test runs `fileConfig`, which disables the existing `httpx` logger. Order-dependent test.
- The solardoctor code paths themselves are clean (see Verified). Fix: `logging.getLogger("httpx").setLevel(logging.WARNING)`
  (or a redacting Filter on httpx/httpcore) in weather_service, and have the `_iso` fixture re-enable the httpx logger
  like it does for solardoctor loggers so the test is order-independent.

### MEDIUM
F2. M2 core fixed, but the "latest telemetry row" fallback is silent about staleness and provenance.
`resolve_power_inputs` takes the newest row with both p_expected_kw and p_ac_kw: no age limit, no source check.
Repro: a 90-day-old `source="SIMULATED"` row (10 vs 90 kW) -> POST /diagnosis/diagnose {"plant_id":1} returns 200, 82 %
confidence "Inverter Thermal Derating", persisted; `telemetry_evidence` has no timestamp or source, so the result is
neither labelled SIMULATED nor stale. Also:
- Mixed inputs: request gives only expected_power_kw=100, latest row is a night row (0 kW) -> actual=0, 100 % deficit, 200
  (expected from request, actual from an unrelated timestamp).
- Latest row being night (0/0) gives a persisted "diagnosis" with 0 loss.
Suggest: max age (1-2 h), skip rows below an expected-power floor, reject mixing request and telemetry halves, and carry
`telemetry_ts` / `telemetry_source` into the response (label SIMULATED).

### MINOR
F3. m5: no-tariff behaviour is honest at the API (`currency="unset"`, `financial_impact_per_day=0.0`,
`financial_assumption` text, summary without a price), but 0.0 in a required float is still a number. The SolarPulse
frontend (/tmp/claude-0/sp/SolarPulseAI/frontend/src/lib/api.ts) types `financial_impact_per_day: number` and has no
`currency` field, so nothing breaks at type level and extra keys are ignored. However DiagnosisModal.tsx:141 hard-codes
`$${...toFixed(2)}/day`, so a no-tariff plant shows "$0.00/day" and an INR plant shows a dollar sign. Tell sd-frontend:
render "not estimated" when currency=="unset" and use the currency symbol.
F4. `skip` has no upper bound: GET /plants?skip=99999999999999999999 -> 500 (OverflowError, SQLite). Add `le`.
F5. Validation gaps: capacity_kw=1e308 accepted; negative expected/actual power accepted by /diagnosis/diagnose (and
persisted). Tested 13 hostile timezone strings (directories, traversal, NUL, empty, absolute): all 422, no 500.
F6. Auth-first websocket path accepts the socket before authenticating and waits up to 5 s; negligible, note only.
F7. `git diff 7f6b87f -- tests/backend/physics/golden_cases.py` changes 1 line; I did not find it weakening anything but it
is a test-data edit and deserves a glance.

## Verified fixed
- M1 (application code): with key set, 401, 500, ConnectError, ReadTimeout, ConnectTimeout and non-JSON 200 all produce
  `WeatherAPIError: WeatherAPI HTTP 401` / `request failed: ReadTimeout` only; no solardoctor log line, exception string
  or repr contained the key. Weather routes fall back to mock with no error body. forecast_service uses `redact()`.
  NASA POWER (`fetch_nasa_power_hourly`) uses no key; raw httpx errors carry only the public POWER URL; no route calls it.
  alert_worker/anomaly_service never touch weather or the key. Only httpx's own logger leaks (F1).
- M2: /diagnosis/diagnose with no telemetry (also only error code, or only one of the two powers) -> 422, diagnoses table
  empty, GET /diagnosis/plant/{id} == []. Alert diagnosis: no expected/actual -> 422; with values -> 200 using the alert's
  numbers; unknown alert -> 404. The 750 W/m2 / 32 C / 48 C fallbacks are removed. (See F2 for the telemetry fallback.)
- m4: cap 1000 enforced (1001 -> 422). Reworked ingest: for a 12-row sorted batch the adapter state (bias -10.58, scaling
  0.8526, 12 samples, checkpoint JSON) is identical to the old per-row code; with an active alert both leave the adapter
  untouched (gate preserved). A shuffled batch now gives the same state as the sorted one (old code was order dependent;
  an improvement). Checkpoint written once per plant. Unknown plant -> 404, nothing inserted.
- m6: duplicate park-link race -> 409 via IntegrityError handling (create and update).
- m7 websocket, apikey mode: none 4401, empty ?token= 4401, wrong/near-miss token (trailing space, case) 4401, header OK,
  subprotocol `solardoctor.bearer, k` OK (server echoes only `solardoctor.bearer`), bearer-only subprotocol 4401.
  Users mode (merged tree, real sessions): none 4401, junk 4401, header/query/api_key/subprotocol with a viewer token OK;
  junk subprotocol 4401; token before the marker 4401; `solardoctor.bearer, solardoctor.auth-first` 4401; auth-first with
  valid token OK; bad token / wrong type / JSON list / missing token -> 4401; auth message without offering auth-first -> 4401
  (no bypass); refresh_token as credential 4401; token after logout 4401; unknown plant 4401 unauthenticated vs 4004
  authenticated (no existence oracle). With SOLARDOCTOR_API_KEY empty the mode is off and sockets open: existing design.
- m1/m2 (prior numbering): timezone validated, name/location length bounded, list limit 1..500, skip >= 0.
- No test modified or deleted (test_review_fixes.py added).

## Required before SIGN-OFF
1. F1: silence/redact the httpx logger and make the M1 tests pass when run alone.
2. F2: age/source/mixing guard and provenance fields for telemetry-derived diagnosis (or label SIMULATED/stale).
Minors F3-F5 can go to BUILD_LOG.md; F3 needs a note to sd-frontend.
