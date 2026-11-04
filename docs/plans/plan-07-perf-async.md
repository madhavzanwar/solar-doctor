# Plan 07 — Performance & Async Hardening
**Priority:** P2 | **Effort:** Small
**Goal:** Fix sync-in-async anti-patterns and add basic resource limits to the API.

---

## Problems

### 1. Blocking DB calls in async endpoints

Several `@app.post` / `@app.get` endpoints declared `async def` but call synchronous SQLAlchemy operations directly on the event loop. This blocks the entire server during DB I/O.

**Pattern to find:**
```python
@app.get("/park/{park_id}")  # async def
async def get_park_summary(park_id: str):
    with get_session() as session:
        park = session.query(Park).filter_by(...)  # BLOCKING
```

**Fix:** Either:
- Convert these endpoints to `def` (not `async def`) — FastAPI runs sync endpoints in a thread pool automatically, which is correct.
- Or use `asyncio.to_thread()` for the DB call inside async endpoints.

The simplest fix is **convert to `def`** for any endpoint that only does DB I/O and no actual async work.

**Scan for affected endpoints:**
```bash
grep -n "^async def " platform/api/app.py | head -30
```
Most endpoints that fetch from DB should be plain `def`.

### 2. Batch job blocks the event loop during ZIP extraction

`_safe_extract_zip()` is called inside `_run_batch_job()` which runs in `BackgroundTasks`. This is fine since BackgroundTasks runs in a separate thread — but the ZIP extraction has no timeout. A malicious or corrupt ZIP can hang indefinitely.

**Fix:**
```python
import signal

def _safe_extract_zip_with_timeout(zf, extract_dir, timeout_s=300):
    """Raise TimeoutError if extraction takes longer than timeout_s."""
    def _handler(signum, frame):
        raise TimeoutError("ZIP extraction timed out")
    old = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(timeout_s)
    try:
        _safe_extract_zip(zf, extract_dir)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)
```

Note: `signal.SIGALRM` is Unix-only. On Windows, use `concurrent.futures.ThreadPoolExecutor` with `future.result(timeout=300)` instead.

### 3. No request-level timeout middleware

Long-running requests (e.g., a huge single-image inference) can stall clients indefinitely.

**Fix:** Add a timeout middleware:

```python
import asyncio
from fastapi import Request, Response

TIMEOUT_SECONDS = 120

@app.middleware("http")
async def timeout_middleware(request: Request, call_next):
    try:
        return await asyncio.wait_for(call_next(request), timeout=TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        return Response("Request timeout", status_code=504)
```

Place this AFTER the auth middleware in app.py.

### 4. SQLite WAL mode

For the local SQLite DB, enable WAL (Write-Ahead Logging) to allow concurrent readers:

```python
# platform/db/session.py
from sqlalchemy import event

engine = create_engine(DATABASE_URL, ...)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, _):
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()
```

This prevents "database is locked" errors when the API and background job write simultaneously.

---

## Steps

1. Scan `app.py` for `async def` endpoints that only do sync DB work → convert to `def`.
2. Add ZIP extraction timeout (`_safe_extract_zip_with_timeout`).
3. Add `timeout_middleware` to `app.py`.
4. Add WAL pragma to `db/session.py`.

---

## Done When

- [ ] No `async def` endpoint blocks the event loop with sync DB calls
- [ ] ZIP extraction has a 5-minute timeout
- [ ] Request timeout middleware responds 504 after 120s
- [ ] SQLite WAL mode enabled in session.py
- [ ] `python3 -m pytest tests/backend/ -ra` still passes
