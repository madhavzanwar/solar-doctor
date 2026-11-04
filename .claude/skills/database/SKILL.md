---
name: database
description: Use when touching SQLAlchemy models, sessions, or migrations in platform/db and alembic/ — including the SQLite (local) ↔ PostgreSQL (Supabase prod) dialect differences that have bitten this codebase.
---

# Database (SQLAlchemy + Alembic, SQLite ↔ Supabase Postgres)

Models and sessions live in `platform/db/`; migrations in `alembic/`. Local dev uses SQLite; production uses **Supabase Postgres** via `AXALON_DB_URL`.

## Models & sessions
- Models: `platform/db/models.py` (`Base`, e.g. `Mission`, parks, inspections, detections, panel_faults).
- Sessions: `get_session()` — always close in a `finally:` block.
- `platform/db/migrate.py` runs idempotent startup checks; its table/column existence checks MUST be dialect-agnostic (`inspect(engine).has_table(...)` / `inspect(engine).get_columns(...)`) — **not** SQLite-only `sqlite_master` / `PRAGMA`, which crash on Postgres.

## Local vs production
- **Local:** no `AXALON_DB_URL` → SQLite file. Conditional `connect_args` already handle the SQLite vs Postgres engine difference.
- **Production (Supabase):** set `AXALON_DB_URL` (a secret on the HF Space):
  ```
  postgresql+psycopg2://postgres.<ref>:<URL-ENCODED-PW>@aws-1-ap-south-1.pooler.supabase.com:5432/postgres
  ```
  Notes: use the **session pooler** host (IPv4); `@` in the password must be URL-encoded to `%40`; the driver `psycopg2-binary` must be in `requirements_platform.txt`.

## Migrations
- Apply with `PYTHONSAFEPATH=1 alembic upgrade head` (current head: `0004`).
- The Supabase schema is already applied — `alembic upgrade head` is a no-op there unless you wipe it.

## Gotchas (hard-won)
- Anything importing the package needs `PYTHONSAFEPATH=1` (the `platform/` shadow) or SQLAlchemy crashes on import.
- A wrong/missing `AXALON_DB_URL` (or a SQLite-only query) makes the backend boot-crash — check the Space runtime logs.
- After changing a backend DB file, re-upload it to the HF Space (`huggingface_hub.upload_file`), not just `git push` (see `cloud-deployment`).
