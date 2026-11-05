# QA review: feat/physics-port (7f6b87f) vs base 8814dae

Verdict: NO-SIGN-OFF (2 major findings must be fixed first; everything else is minor).

## Evidence summary
1. Counts: tests/backend = 663 passed, 9 failed, 1 skipped (baseline 632 pass / 10 fail). +31 passes = exactly the 31 new tests in tests/backend/physics. The 9 failures are the baseline weight-dependent set; the 10th (test_model_info real checkpoint) is skipped in this sandbox, which is unrelated to this branch. `git diff --name-status 8814dae` shows no existing test modified or deleted (only tests/backend/physics/* added). Merged with feat/auth-seed: 703 passed, same 9 failures.
2. Golden tests are genuine. sp_original.py copies the real SolarPulseAI sources into a temp package and golden tests compare ported output against both the live original and captured JSON, with identical inputs. They are not tautological. Sanity tests assert what they claim: Pune equinox noon GHI in 900-1100, night power exactly 0, AC <= rating over a year with 2.5x oversizing (max == 100), hot cells < cool, soiling linear, GHI=0 gives 0 power.
3. Alembic 0011: SQLite upgrade/downgrade/upgrade passes (test plus ORM-vs-migration column parity). I also ran 0001->0010->0011->downgrade->head->downgrade->0011 on real PostgreSQL 16 (no Timescale): clean. FK plants.park_id->parks.id (SET NULL), unique uq_plants_park_id, index ix_telemetry_plant_ts (plant_id, ts) confirmed. The Timescale branch was NOT run: the extension is not installed here and docker has no daemon. I did run its two ALTERs (drop telemetry_pkey, add PRIMARY KEY (id, ts)) on plain PG: valid. create_hypertable(... migrate_data => TRUE) in the same transaction as CREATE EXTENSION is syntactically fine but unverified.
4. Single alembic head (0011); no other versions added.
5. Attribution: every ported file has an MIT header; files without one (solar.py, registry.py, deps.py, schemas/__init__.py, empty ml/forecast __init__.py) are new or empty. THIRD_PARTY_NOTICES entry exists. Minor: it says destination is `backend/solardoctor/physics/schemas.py` but it is the package `physics/schemas/`, and it does not list the ml/forecast `README`/artifacts. No code from no-licence repos found.
6. Schemas vs SolarPulse originals: diff shows additive-only changes (Plant: park_id, altitude_m, tilt, azimuth, module_wp, temp_coeff, tariff_inr_kwh, source; Diagnosis: currency; Scada: extra optional fields). I generated live responses for every SolarPulse TS interface in frontend/src/lib/api.ts (Plant, PlantConfig, ForecastRecord, ForecastSummary, ProbabilisticForecast*, RampRiskSummary, OnlineAdapterStatus, Diagnosis, Taxonomy, WeatherData/Point, Alert) and compared keys: no missing required fields, extras only. Routes match the original, incl. `horizon_minutes` query and `PATCH /alerts/{id}/resolve`. Differences that do not affect the cloned frontend: `POST /plants/seed` absent (frontend never calls it; 405); WebSocket moved from `/ws/scada/{id}` to `/api/v1/ws/scada/{id}` (frontend does not use it); the SolarPulse `/auth/*` router is not ported (auth branch owns it; api.ts calls `/api/v1/auth/refresh`, so frontend login depends on the auth branch response shapes, which I did not review).
7. app.py: 3 additive hunks (import, 6 router entries, ws_router include); session.py: 1 line. `git merge-tree` against feat/auth-seed and feat/frontend-clone: both clean, no conflicts. Merged tree has single head and suite is green.
8. Sync conversion: no `async`/`await`/asyncpg in physics/, ml/forecast or the 5 sync routers; the only async code is the WebSocket handler, which offloads DB work with run_in_threadpool and closes sessions in finally. get_db closes sessions. No blocking calls in async routes.
9. Honesty: mock weather carries source="mock" and "(Simulated)" condition text, is never cached, and forecast_service refuses mock as irradiance input (and ML models require real NWP). Probabilistic model_name is `physics_scenario_simulated`. Telemetry/alerts carry a `source` column.

## Auth probe results (users mode, real TestClient)
- HTTP: unauthenticated 401; viewer GET 200, viewer POST 403 (router policy works).
- WebSocket: unauthenticated 4401; bad token 4401; unknown plant when authenticated 4004; unknown plant when unauthenticated 4401 (no plant-existence oracle); viewer and operator (header or ?token=) connect. Fine for read-only stream. Note: no per-project scoping (see m3).

## Findings

### MAJOR
M1. API key leaked into logs. `backend/solardoctor/physics/weather_service.py:304` logs the raw exception; httpx HTTPStatusError text contains the full URL including `key=`. Repro: set SOLARDOCTOR_WEATHER_API_KEY=SUPERSECRETKEY, call `get_current_weather(18.5,73.8, transport=httpx.MockTransport(lambda r: httpx.Response(401)))`; log line: `Client error '401 Unauthorized' for url 'https://api.weatherapi.com/v1/forecast.json?key=SUPERSECRETKEY&q=...'`. Fix: log `type(exc).__name__` and status code only, or redact `key=`.
M2. Fabricated diagnosis when no telemetry is supplied. `physics/diagnosis_service.py:439-440` substitutes `capacity*0.75` expected and `exp*0.65` actual, then `api/routers/diagnosis.py:22-40` persists the result. Repro (fresh plant, no tariff): `POST /api/v1/diagnosis/diagnose {"plant_id":1}` -> 200, DC_STRING_FAULT, confidence 84, estimated_loss_kw 31.5, financial_impact_per_day 13.86 USD, stored in `diagnoses`. This is invented data presented as a diagnosis, violating the never-invent rule. Fix: 422 (or a clearly labelled `insufficient_data` result, not persisted) when expected/actual cannot be derived from request or latest telemetry.

### MINOR
m1. Timezone not validated: `POST /plants` with `timezone="Mars/Phobos"` -> 201; `PUT` likewise 200 (schemas/plant.py). Validate with `zoneinfo.ZoneInfo`. Also `name` of 5000 chars accepted (column is String(256); fine on SQLite, a 500 on PostgreSQL); add max_length on name/location/etc.
m2. `GET /plants?limit=-1` and `limit=100000000` unvalidated (plants.py list_plants, SQLite treats -1 as unlimited); add `Query(ge=0/1, le=...)`. Same pattern in other list routes worth checking.
m3. No tenancy: plants are not tied to projects; any viewer in users mode sees all plants/telemetry regardless of project_ids. Acceptable only if documented; Park<->Plant link is optional.
m4. `POST /scada/readings/batch` has no size cap (schemas/scada.py:54) and `_trigger_online_adapter_update` (scada_service.py:52-78) runs 2 queries plus a persisted adapter update per row, plus per-row refresh after commit: N+1 and a cheap DoS for operator role. Cap list length (e.g. 1000) and batch the lookups.
m5. Currency fallback: for plants without tariff, diagnosis uses SolarPulse's $0.08/kWh and reports `currency="USD"` (labelled, so not dishonest), but for Indian plants it should rather return null/unknown financial impact than a US-dollar assumption. The assumption is not flagged as an assumption in the response.
m6. Concurrent create of a second plant for the same park can hit the unique constraint after the `_check_park` pre-check, producing a 500 rather than 409 (no IntegrityError handling; grep finds none).
m7. WebSocket accepts credentials in the query string (`?token=`, `?api_key=`); these end up in server/proxy access logs. Header is also supported; consider documenting or restricting.
m8. Migration 0011 Timescale branch untested (no extension/daemon available). Also downgrade does not remove the extension (intended) but a downgrade of a hypertable with PK (id, ts) was not exercised.
m9. THIRD_PARTY_NOTICES destination column inaccurate (see item 5); BASELINE doc count of 10 failures is now 9 failed + 1 skipped in this sandbox (environmental).

### Not found
No leftover async DB code, no SSRF (weather URLs fixed to api.weatherapi.com / power.larc.nasa.gov, coordinates come from stored plant), no secrets in git, no weakened tests, no licence violations.

## SIGN-OFF status: NO-SIGN-OFF
Re-review needed after M1 and M2 are fixed (small, localised changes); minors can be logged in BUILD_LOG.md.
