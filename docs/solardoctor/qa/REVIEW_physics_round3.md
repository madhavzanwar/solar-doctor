# sd-qa round 3: feat/physics-port @ 8737c56

Verdict: SIGN-OFF (no blocking findings; 4 low/minor notes).

## Verified
- F1: `pytest -k api_key_not_logged` alone: 2 passed. Whole test_review_fixes.py: 31 passed. Full tests/backend: 694 passed,
  9 failed, 1 skipped; the 9 failures are the weights-dependent set and are identical on base 8814dae (632 pass / 9 fail / 1 skip).
- F1 standalone repro, logging.basicConfig(DEBUG) with httpx/httpcore/urllib3/solardoctor/asyncio forced to DEBUG, before and after
  client construction: MockTransport 401/200/ReadTimeout/ConnectError, plus a real local HTTP server (real httpcore DEBUG traffic,
  401 and 200) and a refused connection, key with special chars (`aB+c/d=SECRETKEY9`): the key, its URL-encoded form and any
  substring never appear in logs or exception text. httpx INFO line shows `key=***`.
- F2 rules all hold (API + direct DB rows): age limit 24 h (30 s inside -> 200, 1 s outside -> 422), env override works, 5 % floor,
  mixing request/telemetry -> 422 (also with allow_simulated=true and one value), SIMULATED refused unless allow_simulated
  (case-insensitive), telemetry_ts/source returned, in telemetry_evidence and persisted (SQLite and PG), 422 persists nothing.
  tz-naive stored timestamps (fresh -> 200, 30 h old -> 422), IST-aware ts OK, expected>0 with actual NULL -> 422, NULL source
  treated as real (acceptable), ac_kw NULL impossible (NOT NULL, IntegrityError).
- Migration 0011 (edited, unreleased): upgrade / downgrade 0010 / upgrade on SQLite and real PostgreSQL 16: OK, schema identical
  after re-upgrade, telemetry_ts is timestamptz like created_at; ORM vs migration: no column or nullability differences;
  alembic autogenerate compare_metadata -> 0 diffs on both. Single head 0011. PG end-to-end diagnose with SIMULATED row ok.
- Test-fixture change SIMULATED -> USER: only the `source=` literal and a comment changed; every assertion in that test is
  unchanged, and the SIMULATED path gets new dedicated tests. Not weakened. golden_cases.py (vs 7f6b87f and 69c732d): only adds
  the new additive response fields (telemetry_ts, telemetry_source, earlier financial_assumption) to the keys dropped before
  comparing; golden JSON byte-unchanged, so all SolarPulse-derived values are still compared.
- F4/F5: skip 0..1,000,000 ok, 1,000,001 / 99999999999999999999 / negative / non-int -> 422; limit 0/501 -> 422; capacity and
  inverter capacity: 1e7 ok, 1e7+1 / 1e308 / NaN / 0 / negative / null -> 422; diagnosis powers: negative, >1e8, NaN, 1e308 -> 422.
- Trial merge: claude/practical-dirac-fddnwu already contains feat/physics-port (85448cc, ancestor check true) and feat/auth-seed;
  "Already up to date". Full tests/backend on that tree: 734 passed, 9 failed (same weights set), 1 skipped; single alembic head
  0011. (Branch has since advanced to d367e34; I tested 85448cc.)

## Findings (none blocking)
- LOW-1: future-dated telemetry (ts +30 days) is accepted by the fallback (only a lower age bound). Suggest `ts <= now + small skew`.
- LOW-2: SOLARDOCTOR_DIAGNOSIS_MAX_TELEMETRY_AGE_H=nan or inf -> unhandled ValueError/OverflowError -> 500 (operator misconfig;
  "abc" falls back safely, negative/0 -> 422). Reject non-finite values.
- LOW-3: plant with ac_kw=0 (only reachable by direct DB edit; API enforces gt=0) makes the floor 0, so a 0/0 night row is
  accepted and produces a persisted 0-loss "diagnosis". Guard `floor = max(floor, tiny)` or require expected > 0.
- LOW-4: explicit request expected=0, actual=0 yields a persisted diagnosis (200). Arguably user input; consider requiring expected > 0.
- Carried: F3 (frontend DiagnosisModal hard-codes `$` and shows "$0.00/day" for no-tariff plants) remains a note to sd-frontend.

Scratch edge tests were in the throwaway worktree only; worktrees removed, no branch touched.

SIGN-OFF
