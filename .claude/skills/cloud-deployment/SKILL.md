---
name: cloud-deployment
description: Use when deploying or debugging the live stack — Vercel (website + /platform), Hugging Face Spaces (FastAPI backend), and Supabase (Postgres). Read before pushing to production, changing env/secrets, or touching the Dockerfile.
---

# Cloud Deployment (Vercel + HF Spaces + Supabase)

Live stack: **Vercel** serves `axalonsystems.com` (+ `/platform`) → **HF Space** runs the FastAPI backend → **Supabase Postgres** stores data. All free-tier.

## Frontend — Vercel
- Production project: **`axalon-systems`** (rootDir `website/nextjs`), GitHub-integrated.
- **Deploy by `git push origin main`** → auto-build. Do **NOT** run `vercel --prod` from the repo root — it uploads the whole repo incl. `ml/Datasets` (~529 MB) and aborts ("Upload aborted").
- Env: `NEXT_PUBLIC_AXALON_API_URL` = the HF backend URL. It's a `NEXT_PUBLIC_` var → **baked at build time**, so set it *before* the build and redeploy after changing it.
- Verify: `vercel ls axalon-systems` (newest = Ready), then `curl -I https://axalonsystems.com/platform`.

## Backend — Hugging Face Space (`parakh20/axalon-api`, Docker)
- The Space has its **own file snapshot** (the `Dockerfile` does `COPY . .`). **A `git push` does NOT update it.** Update each changed backend file with:
  ```python
  from huggingface_hub import HfApi
  HfApi().upload_file(path_or_fileobj=…, path_in_repo=…, repo_id='parakh20/axalon-api', repo_type='space', token=…)
  ```
  Uploading a file triggers a rebuild.
- Config: var `PORT=7860`; secrets `AXALON_API_KEY` (Bearer password), `AXALON_DB_URL` (Supabase). Changing a secret restarts the Space.
- Dockerfile gotcha: a multi-source `COPY a b ./` flattens basenames — copy `ml/requirements.txt` with its own `COPY` line or `pip install -r ml/requirements.txt` fails. `psycopg2-binary` must be installed for Postgres.
- Tooling: `huggingface_hub` + `pg8000` in `~/.cloudtools/bin` (run from `/tmp` with `PYTHONSAFEPATH=1`). HF write token rotates per session.

## Database — Supabase
- `AXALON_DB_URL` (secret on the Space):
  `postgresql+psycopg2://postgres.<ref>:<PW with @→%40>@aws-1-ap-south-1.pooler.supabase.com:5432/postgres`
- Use the **session pooler** host (IPv4). Schema applied to alembic `0004`.

## Verify end-to-end
```bash
# health
curl https://parakh20-axalon-api.hf.space/health        # → {"status":"ok","db":"ok"}
# persistence round-trip: POST /missions (Bearer <key>) → confirm row in Supabase → DELETE
```

## Gotchas
- Backend `RUNTIME_ERROR` after a DB change → read the Space **run** logs (`/api/spaces/<repo>/logs/run`); usually a dialect/connection issue (see `database`).
- HF free Spaces sleep on idle (cold starts) — that's why the mission planner computes client-side.
- Full runbook: `docs/DEPLOYMENT.md` (`docs/DEPLOY_ORACLE.md` and `deploy/azure/` are historical, not live); project memory `cloud-deploy-progress` + `platform-remote-deployment`.
