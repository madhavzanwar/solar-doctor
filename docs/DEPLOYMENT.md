# Deployment Runbook — Axalon Inspection Platform

## Production (live path)

```
Browser ──▶ Vercel project `axalon-systems`          (axalonsystems.com, incl. /platform)
              │  NEXT_PUBLIC_AXALON_API_URL (baked at build time)
              ▼
            Hugging Face Space `parakh20/axalon-api`  (Docker, app_port 7860, FastAPI)
              │  AXALON_DB_URL
              ▼
            Postgres (Supabase)  — must be durable, see "Database" below
```

Earlier deployment targets are no longer used. The Azure VM + Azure PostgreSQL deployment
(`deploy/azure/`) went down when the subscription was disabled. The Oracle Cloud plan
(`docs/DEPLOY_ORACLE.md`) never became the live path. Both are kept only for history.

### Frontend — Vercel `axalon-systems`

- The project is linked to the GitHub repo. Its production branch is `main` and its
  root directory is `website/nextjs`.
- **To deploy, push to `main`.** Vercel builds and publishes the site automatically.
- Do not run `vercel --prod` from the repo root. It uploads the whole repository, including
  datasets and weights, and the upload aborts.
- Environment variables (Vercel → Project → Settings → Environment Variables):
  - `NEXT_PUBLIC_AXALON_API_URL` is the Space URL (`https://parakh20-axalon-api.hf.space`).
    Vercel bakes `NEXT_PUBLIC_*` values into the build, so after changing one you must
    redeploy `main`.
  - `NEXT_PUBLIC_AXALON_API_KEY` is needed only when the API key is enabled (see "Auth").
- To verify, run `vercel ls axalon-systems` (the newest deployment should show Ready), then
  `curl -I https://axalonsystems.com/platform`.

### Backend — Hugging Face Space `parakh20/axalon-api`

- The Space is a Docker Space built from the repo-root `Dockerfile`. Its README front
  matter sets `sdk: docker` and `app_port: 7860`. The Space variable `PORT=7860` tells the
  container's uvicorn to listen on that port.
- **The Space keeps its own copy of the files.** The Dockerfile runs `COPY . .` against the
  Space repo, not GitHub, so pushing to `main` does **not** update the backend. Upload each
  changed backend file to the Space (for example with
  `huggingface_hub.HfApi().upload_file(..., repo_id="parakh20/axalon-api", repo_type="space")`).
  Every upload commit triggers a rebuild.
- **Upload `drone/` together with `platform/` and `ml/`.** `pyproject.toml` lists the
  `drone`, `drone.relay`, `drone.common` and `drone.agent` packages explicitly. If
  `drone/` is missing from the Space, the Dockerfile's `pip install -e .` fails with
  `package directory 'drone' does not exist` and the build breaks.
- Upload the model weights as well (`ml/checkpoints/best.pt`, 109 MB). Once the Space is up,
  confirm it serves the weights you expect. `GET /health` reads `model` and
  `model_info.sha256` from the file inside the container, and the result should match
  `sha256sum ml/checkpoints/best.pt` locally (first 12 hex characters).
- To verify:
  ```bash
  curl https://parakh20-axalon-api.hf.space/health
  # → {"status":"ok","db":"ok","model":"YOLO11x","model_info":{...,"sha256":"…"}, ...}
  ```
  `"db":"error"` means the API started but cannot reach `AXALON_DB_URL`. For crashes, read
  the Space run logs.
- Free Spaces go to sleep when idle, so the first request after a sleep is a cold start.
- An HF token can upload files and change secrets, both of which restart the Space. It may
  not be allowed to call `restart_space` directly.

#### Space variables vs secrets

Space settings have two lists: **Variables** (public, visible to anyone who can see the Space)
and **Secrets** (hidden). Rules:

- Store each name in **exactly one** list. If the same name is both a variable and a secret,
  the Space fails to start with
  `CONFIG_ERROR: Collision on variables and secrets names`. To fix it, delete the duplicate.
  When moving a value from a variable to a secret, add the secret and delete the variable
  in the same change.
- Store credentials as **secrets**: `AXALON_DB_URL` (it contains the DB password),
  `AXALON_API_KEY`, `SUPABASE_SERVICE_KEY`, and `AXALON_TRACK_PASSWORD`.
- Non-sensitive settings can be **variables**: `PORT=7860`, `SUPABASE_URL`,
  `AXALON_TRACK_BUCKET`, `AXALON_CORS_ORIGINS`, and `AXALON_RESULTS_TTL_HOURS`.
- Changing a variable or secret restarts the Space.

#### Database

- **`AXALON_DB_URL` must point at a durable Postgres database.** The Space's filesystem is
  wiped on every rebuild, restart, and wake from sleep. A SQLite URL such as
  `sqlite:////tmp/axalon.db` lets the API start, but parks, inspections, and jobs are
  **lost** at the next restart. Treat SQLite on the Space as a temporary stopgap only.
- Supabase format (use the **session pooler** host, which supports IPv4; URL-encode `@` in
  the password as `%40`):
  `postgresql+psycopg2://postgres.<project-ref>:<password>@aws-1-ap-south-1.pooler.supabase.com:5432/postgres`
- The image installs `psycopg2-binary` from `requirements_platform.txt`. Apply the schema
  with Alembic (see `.github/workflows/db-migrate.yml` and `alembic/`).
- `/track` file uploads persist in Supabase Storage when `SUPABASE_URL` and
  `SUPABASE_SERVICE_KEY` are set. Without them, uploads go to local disk and disappear
  like the SQLite data does.

#### Auth

The API key has to be set on both sides at once. On the Space, add the secret
`AXALON_API_KEY`. On Vercel, set `NEXT_PUBLIC_AXALON_API_KEY` to the same value, then
redeploy `main`. If only the Space has the key, every UI call returns 401 and the unlock
dialog appears. If only Vercel has it, the key does nothing. As of 2026-09-12, production
runs **without** a key (neither side is set).

## Local Docker Deployment

Prerequisites: `ml/checkpoints/best.pt` present (Git LFS), Docker Engine 24+ with Compose v2,
ports `3000` and `8000` free.

```bash
python3 scripts/make_sample_mission.py
cd tests/fixtures && zip -rq sample_mission.zip sample_mission/ && cd -

# Optional: populate History, Park Map, and Diff with demo data.
python3 scripts/seed_demo_data.py

# Optional: require API-key auth.
export AXALON_API_KEY=your-secret-key

docker compose build
docker compose up -d
```

Open `http://localhost:3000/platform`.

Docker stores SQLite and generated reports in the `axalon_data` volume. Batch job state is
kept in the `jobs` table, so `/status/{job_id}` still works after the API container restarts.

```bash
docker compose restart api
docker compose down
docker compose down -v  # also deletes the persisted DB volume
```

## Environment Variables

| Variable | Service | Default | Description |
|---|---|---|---|
| `PORT` | API | `8000` | uvicorn listen port. Set to `7860` on the HF Space |
| `AXALON_DB_URL` | API | repo-root SQLite; `sqlite:////app/data/axalon.db` in Docker | SQLAlchemy database URL. Production must use durable Postgres |
| `AXALON_API_KEY` | API | empty | When set, every endpoint except `/health` requires this Bearer key |
| `AXALON_AUTH_MODE` | API | unset | `off` (keyless) \| `apikey` (shared `AXALON_API_KEY`) \| `users` (accounts). Unset = `apikey` if `AXALON_API_KEY` is set, else `off`. Unknown values fail closed to `users` |
| `AXALON_BOOTSTRAP_ADMIN_EMAIL` | API | empty | Users mode: creates this admin on startup when no users exist |
| `AXALON_BOOTSTRAP_ADMIN_PASSWORD` | API | empty | Users mode: bootstrap admin password (10+ chars). Remove after first boot |
| `AXALON_SESSION_TTL_HOURS` | API | `12` | Users mode: login session lifetime |
| `AXALON_CORS_ORIGINS` | API | localhost + `axalonsystems.com` | Comma-separated list of allowed origins (replaces the defaults) |
| `AXALON_OUTPUT_DIR` | API | `output` (`/app/data/output` in Docker) | Generated reports and job artifacts |
| `AXALON_RESULTS_TTL_HOURS` | API | `0` (off) | Delete job results older than this many hours |
| `AXALON_TRACK_PASSWORD` | API | empty | Password for the `/track` workspace (`POST /track/login`). Login returns 503 until it is set. Never put it in a `NEXT_PUBLIC_*` var |
| `SUPABASE_URL` | API | empty | Supabase project URL. Enables durable Supabase Storage for `/track` files |
| `SUPABASE_SERVICE_KEY` | API | empty | Supabase service-role key. Server-side only |
| `AXALON_TRACK_BUCKET` | API | `track-files` | Supabase Storage bucket for `/track` uploads |
| `AXALON_USE_ENGINE` | API | empty | `true` loads a TensorRT `best.engine` next to `best.pt` when one exists |
| `AXALON_ALERT_MIN_SEVERITY` | API | `CRITICAL` | Lowest fault severity (`CRITICAL`\|`HIGH`\|`MEDIUM`\|`LOW`) that triggers an alert when an inspection job completes. Invalid values fall back to `CRITICAL` |
| `AXALON_ALERT_WEBHOOK_URL` | API | empty | Webhook alert channel: POSTs JSON (park, job/inspection id, per-severity counts, top faults, link). Includes a `text` field, so a Slack incoming-webhook URL works as-is. 8 s timeout, one retry. Treat as a secret |
| `AXALON_SMTP_HOST` | API | empty | SMTP server for email alerts. Email is enabled when this, `AXALON_ALERT_EMAIL_FROM` and `AXALON_ALERT_EMAIL_TO` are all set |
| `AXALON_SMTP_PORT` | API | `587` | SMTP port |
| `AXALON_SMTP_USER` | API | empty | SMTP login user (login skipped when empty) |
| `AXALON_SMTP_PASSWORD` | API | empty | SMTP login password. Secret |
| `AXALON_SMTP_STARTTLS` | API | `true` | Upgrade the SMTP connection with STARTTLS; set `false` only for a local relay |
| `AXALON_ALERT_EMAIL_FROM` | API | empty | Sender address for alert emails |
| `AXALON_ALERT_EMAIL_TO` | API | empty | Comma-separated recipient addresses for alert emails |
| `AXALON_PUBLIC_BASE_URL` | API | empty | Public console origin (e.g. `https://axalonsystems.com`); when set, alerts link to `<base>/platform?job=<id>` |
| `AXALON_NODEODM_URL` | API | empty | Base URL of a NodeODM server (e.g. `http://nodeodm:3000`). Enables in-platform orthomosaic generation; when unset the feature is disabled and `/health` reports `capabilities.odm.configured: false` |
| `AXALON_NODEODM_TOKEN` | API | empty | Optional NodeODM access token (NodeODM started with `--token`). Sent as the `token` query parameter; server-side only |
| `SENTRY_DSN` | API | empty | Enables Sentry error monitoring and tracing. Query-string credentials (`api_key`, `token`, `share`) are masked and frame locals are not sent. Treat as a secret |
| `SENTRY_ENVIRONMENT` | API | `production` | Sentry environment tag |
| `SENTRY_TRACES_SAMPLE_RATE` | API | `0.1` | Fraction of requests traced (1.0 exhausts the free quota quickly) |
| `SENTRY_PROFILE_SAMPLE_RATE` | API | `0` | Fraction of traced sessions profiled |
| `SENTRY_SEND_PII` | API | `false` | `true` also sends client IPs and request bodies |
| `NEXT_PUBLIC_AXALON_API_URL` | Next.js | `http://localhost:8000` | API base URL used by the browser (build-time) |
| `NEXT_PUBLIC_AXALON_API_KEY` | Next.js | empty | Bearer key sent by the UI. Must match `AXALON_API_KEY` |

When `AXALON_API_KEY` is set, `/health` stays public and every other endpoint requires
`Authorization: Bearer <key>`. The platform UI shows an unlock dialog after a `401` and
keeps the key in `sessionStorage`.

## Orthomosaic Generation (NodeODM)

The Park Map's **Generate orthomosaic** button stitches drone images into a GeoTIFF on an
[OpenDroneMap NodeODM](https://github.com/OpenDroneMap/NodeODM) server, then registers the result
exactly like a manually uploaded ortho (tiles and fault overlays work unchanged).

Run NodeODM next to the API:

```bash
# NodeODM listens on 3000 inside the container; publish it on 3001 locally so it
# does not collide with the Next.js UI on 3000.
docker run -d --name nodeodm -p 3001:3000 opendronemap/nodeodm
export AXALON_NODEODM_URL=http://localhost:3001
# Optional: docker run ... opendronemap/nodeodm --token s3cret  and
# export AXALON_NODEODM_TOKEN=s3cret
```

On a dedicated host the stock command is `docker run -p 3000:3000 opendronemap/nodeodm`. Keep
NodeODM on a private network — only the API talks to it.

Input and behaviour:

- Operators upload a ZIP (≤ 2 GB, same limits as batch uploads) or reuse the images of an existing
  inspection job. One camera per ortho: `rgb/` is preferred, `thermal/` is used when it is the only
  set, and flat folders are split by `_T`/`_V` style names.
- At least 5 images must carry GPS EXIF, otherwise the job fails before anything is sent to NodeODM.
- Default task options: `fast-orthophoto` on (solar parks are planar), `orthophoto-resolution` 2 cm/px,
  `dsm` off, `skip-3dmodel`, `auto-boundary`.
- Jobs are ordinary `jobs` rows (`odm-…`). Status is polled every 15 s; cancelling removes the NodeODM
  task. After an API restart, jobs already on NodeODM resume polling; jobs interrupted before
  submission are marked failed and must be restarted. Resumption assumes a single API worker process.

Hardware expectations (NodeODM, fast-orthophoto):

| Images (20 MP) | RAM | CPU | Disk (scratch) | Typical time |
|---|---|---|---|---|
| ≤ 200 | 8 GB | 4 cores | 20 GB | 10–30 min |
| 200–1,000 | 16–32 GB | 8 cores | 50–100 GB | 1–3 h |
| 1,000–3,000 | 64 GB+ | 16 cores | 200 GB+ | several hours |

Full (non-fast) reconstructions need roughly 2× the RAM and time. Radiometric 640×512 thermal
frames stitch poorly on their own — fly RGB alongside thermal and generate the ortho from RGB. NodeODM
does not run on the free Hugging Face Space; point `AXALON_NODEODM_URL` at a separate VM.

Alerts are best-effort: they are sent after the job's success is committed, every failure is caught and logged (`Alerts for job …: webhook=sent, email=failed`), and a broken channel never fails an inspection. Use **Settings → Send test alert** (`POST /alerts/test`) to verify delivery.

## Model Weights In CI

The e2e GitHub Actions job needs `ml/checkpoints/best.pt` for real inference. The weights are
tracked in Git LFS, so run `git lfs pull` before the e2e job. If the weights are unavailable,
CI creates a zero-byte placeholder and runs the Playwright flow with `PLAYWRIGHT_CI=1`. In that
mode a failed batch counts as an acceptable end state for the UI smoke test.

## Auth

`AXALON_API_KEY` alone gives shared-key auth: every endpoint except `/health` needs
`Authorization: Bearer <key>`, and the console shows an unlock dialog after a `401`.

### User accounts (`AXALON_AUTH_MODE=users`)

- Roles: `admin` (everything, incl. users, projects, settings, agents), `operator` (inspections, faults, missions, orthos, inventory, share links for their projects), `viewer` (read-only).
- Non-admins only see parks — and their inspections, faults, missions, orthos, analytics — in projects they are members of. Parks without a project are admin-only. Out-of-scope ids return `404`.
- `POST /auth/login {email, password}` returns an opaque session token (stored SHA-256-hashed server-side); send it as `Authorization: Bearer <token>`. `POST /auth/logout`, `GET /auth/me`, public `GET /auth/mode`.
- Admin: `/users` CRUD (role, disabled, password reset, `project_ids`). Disabling a user or resetting their password ends their sessions.
- Share links: `POST /share-links {project_id, label, expires_in_days}` returns the token once; `?share=<token>` on any request (or `/platform?share=<token>` in the browser) gives read-only access to that project until it expires or is revoked (`DELETE /share-links/{id}`).
- Login is throttled in-process: 5 failures per email and 20 per client IP per 15 minutes.
- First boot: set the two `AXALON_BOOTSTRAP_ADMIN_*` vars, sign in, create real accounts in Settings → Users & sharing, then remove the bootstrap vars.
- Known limitation: a non-admin cannot start the first inspection of a brand-new park (it would be created without a project); an admin runs it or assigns the park first.
