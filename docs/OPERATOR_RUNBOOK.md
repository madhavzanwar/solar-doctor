# Operator Runbook — Axalon Inspection Platform

The 10-minute walk through a real local inspection from zero.

## Prereqs

- `./run.sh setup` has completed once
- `ml/checkpoints/best.pt` exists (~22 MB)
- Optional: WeasyPrint system libs (for PDF reports). See `docs/INSTALLATION.md`.

## 1. Generate the sample mission

```bash
python3 scripts/make_sample_mission.py
cd tests/fixtures && zip -rq sample_mission.zip sample_mission/ && cd -
```

You should see `tests/fixtures/sample_mission.zip` (~1–5 MB).

## 2. Start the services

```bash
./run.sh all
```

In another terminal, verify:

```bash
curl -fsS http://localhost:8000/health
curl -fsS -o /dev/null -w '%{http_code}\n' http://localhost:3000/platform
```

Both should return `200`.

## 3. Open the platform UI

Open `http://localhost:3000/platform` in a browser.

## 4. Run a batch inspection

On the **Operations** tab:

1. Park ID: `SOLAR_PARK_DEMO`
2. Altitude: `42`
3. Choose file: `tests/fixtures/sample_mission.zip`
4. Click **Start batch**.
5. Wait for progress to reach 100% (~30–90 seconds depending on GPU/CPU).
6. The map below should show markers from the detected anomalies.

## 5. Download reports

Click each of the four report buttons. Files land in your default Downloads folder.

## 6. Inspect a single image

On the **Inspect** tab:

1. Choose file: `tests/fixtures/sample_mission/thermal/img_001.jpg`.
2. Submit. Annotated image + detection list appear.

## 7. Browse history

On the **History** tab:

1. Park dropdown should include `SOLAR_PARK_DEMO`.
2. Select it. You should see the inspection from step 4.

## 8. Tweak settings

On the **Settings** tab:

1. Change confidence to `0.30`.
2. Save.
3. Reload page — value persists.

## Demo mode

To populate the platform with realistic data without running a real batch job, use the demo seed script:

```bash
python3 scripts/seed_demo_data.py
```

This is idempotent — safe to re-run at any time. It will:

1. Drop and recreate the `SOLAR_PARK_DEMO` park with a 6×8 grid (48 panels, `R1-C1` through `R6-C8`).
2. Insert 3 inspection records timestamped today, today−15 days, and today−30 days, so the History chart shows a multi-point trend.
3. Insert synthetic `Detection` rows per inspection (~10% CRITICAL, 15% HIGH, 50% MEDIUM, 25% LOW, spread across ~20 panels). No YOLO run required.
4. Write GPS coordinates on a synthetic grid around 0°N 0°E so the AnomalyMap has spatially distributed markers.

On completion the script prints a summary:

```
Park: SOLAR_PARK_DEMO | Inspections: 3 | Detections: N
```

After seeding, the **History**, **Park Map**, and **Diff** tabs all show populated data immediately.

## CI

GitHub Actions runs two independent parallel jobs on every push and PR to `main`:

| Job | Command | What it covers |
|-----|---------|----------------|
| `backend-tests` | `pytest tests/backend/ -ra --strict-markers` | API contract, DB models, orchestrator, park-grid aggregator |
| `frontend-unit` | `cd website/nextjs && npm test` | `api.ts` client, Toast hook, all vitest unit tests |

Playwright e2e is **intentionally excluded** from CI — it requires live services (API + DB) and belongs in `scripts/test_all.sh` for local pre-push runs.

**Reading a failure:**

- Click the failing job in the GitHub Actions panel.
- Expand the failing step to see the full output.
- `backend-tests` failures are almost always import errors, DB schema mismatches, or broken endpoint contracts.
- `frontend-unit` failures are type errors, broken mocks, or component logic bugs.
- Fix the root cause locally, run `./scripts/test_all.sh` to confirm, then push.

## Troubleshooting

- **Any silent failure** is a bug. Every failure should produce a visible toast bottom-right of the screen. If it didn't, that's a Phase 1 regression — file it.
- **PDF download fails** — likely WeasyPrint libs missing. Install per `docs/INSTALLATION.md` or use JSON / Excel / GeoJSON instead.
- **No detections in the map** — the synthetic hotspots may not match the trained model distribution. Re-run `python scripts/make_sample_mission.py --seed 12345` to get a fresh batch.

## 9. Run the test suite (optional)

Phase 2 added an automated suite covering API contract, pipeline units, frontend units, and a Playwright end-to-end walk of all five tabs.

```bash
./scripts/test_all.sh
```

What it does:

- **Backend pytest** (`tests/backend/`) — every API endpoint + the orchestrator + the panel-grid aggregator.
- **Frontend vitest** (`website/nextjs/tests/unit/`) — the `api.ts` client + the Toast hook.
- **Frontend playwright** (`website/nextjs/tests/e2e/`) — drives a headless Chromium through every tab including a real batch run.

The script starts the platform services itself if they're not already up, and stops them after. Pass-through exit code: zero on success, non-zero on the first failing suite.

## Phase 4 additions

### API key auth

Set `AXALON_API_KEY` before starting services:

```bash
export AXALON_API_KEY=your-key
./run.sh all
```

The platform UI prompts for the key after a `401`. The key is stored in `sessionStorage` and clears when the browser session ends.

### Docker

See `docs/DEPLOYMENT.md` for the Docker runbook.

### Job state persistence

Batch job status now lives in SQLite. Completed and failed jobs remain visible through `/status/{job_id}` after an API restart. Jobs that were marked `running` during a restart are reset to `queued` on startup with a message noting that they were re-queued.
