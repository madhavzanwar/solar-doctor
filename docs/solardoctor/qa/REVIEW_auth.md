# QA review: feat/auth-seed (3cdfe65) vs 8814dae

Reviewer: sd-qa. Checkout: detached worktree /tmp/claude-0/qa-auth (branch is already checked out in another worktree). No source modified; a scratch probe test was used and deleted.

## Verdict: NO-SIGN-OFF (1 major scoping hole, 1 major logout gap; no blockers)

## 1. Test counts
- tests/backend now: 652 passed, 9 failed, 1 skipped (662 total). Baseline: 632 passed, 10 failed (642 total).
- +20 = the new tests/backend/test_auth_tokens.py (20 passed, confirmed in isolation). Pass count >= 632 and the failing set shrank (the 9 failures are a strict subset of the baseline 10, all weight-dependent). OK.
- test_model_info::test_describe_weights_real_checkpoint_is_yolo11 changed from FAIL to SKIP. Not caused by this branch (test_model_info.py is untouched). It carries `skipif(not REAL_WEIGHTS.exists())`. The baseline run had the Git LFS pointer file at ml/thermal/checkpoints/best.pt, so it existed and failed to parse. Commit 8814dae/DECISIONS.md #6 stripped the pointer, so the file is absent and the skip guard fires. This is environmental. Note that the real-checkpoint test is now silent until `make weights` runs; the CI gate should assert it is not skipped once weights exist.
- The 1 skipped test is exactly that one.

## 2. test_auth_users.py::test_session_token_is_stored_hashed
Diff: row count 1 -> 2 (access + refresh row), and `len==64 and token not in hash` now applies to every row, plus a new assertion that sha256(token) is among the stored hashes and that refresh_token is not a substring of any hash. Judgement: NOT weakened. The count change follows from the design (refresh stored in user_sessions); the checks are strictly stronger. Minor process note: edit made by the author in sd-qa-owned tests/ (see section 8).

## 3. Refresh / logout (verified by probe)
- Rotation: refresh returns a new pair, old refresh -> 401 on replay, new one still live (200). Row delete is the atomic gate (`deleted != 1` -> None), so concurrent double-use yields one winner. OK.
- Expiry: expired row is deleted and returns None (-> 401); disabled user -> 401. Covered by tests.
- Type confusion: refresh used as Bearer or ?api_key= -> 401 (domain-separated hash "refresh:"); access token posted as refresh_token -> 401. OK.
- Garbage / non-string refresh_token -> 401; non-JSON body -> 422 (minor, fine).
- MINOR: no reuse detection. A replayed (stolen) old refresh token returns 401 but the legitimate descendant chain is not revoked. Acceptable for now; document it.
- MAJOR (logout): POST /auth/logout with only the Bearer revokes the access session but NOT the paired refresh token. Repro: login, logout with Authorization header only, then POST /api/v1/auth/refresh with the refresh_token -> 200 (new valid pair). The SolarPulse frontend logout() (frontend/src/lib/api.ts:~380) never calls the server and does not send the refresh token at all, so for that client, server-side sign-out never happens and the 7-day refresh token stays live. Suggested fix: link the pair (e.g. store a shared family id or revoke all `refresh:` rows of the user on bearer logout), and have the frontend call logout with refresh_token. File: backend/solardoctor/api/routers/auth.py:142-157, core/auth.py (create_token_pair / revoke_refresh_token).
- Logout is public in users mode (needed for refresh-only sign-out); with no credentials it returns 204 without effect. OK.

## 4. Technician scoping
- MAJOR: scoping applied to one endpoint only (GET /parks/{id}/work-orders, work_orders.py:148-150). Technician with project membership can still read every fault in the park, including other technicians' assignee, notes and counts. Repro (scratch probe): technician t@ in project p1; fault 1 assigned to t@, fault 4 assigned to someone@else.test, same park. `GET /parks/PARK_A/faults` -> 200, total 2, lists both faults with assignee fields. `GET /faults/4/comments` -> 200, `/faults/4/photos` -> 200 (not assigned to them). Fault comments/photos/ensure_fault_visible check only project visibility (api/routers/faults.py:69-73, 161-208, 298-352; api/support/scope.py). The brief says technicians see only assigned work orders; faults ARE the work orders, so this is a bypass of the stated rule. Fix: in faults list filter by assignee for technicians and make ensure_fault_visible (comments/photos GET) require fault.assignee == principal.email for technicians. This file is outside the author's apparent scope (faults.py) so route to sd-backend/lead.
- Widening via query params on the covered endpoint is closed: `assignee=someone@else.test` and `assignee=` (empty) both still return only the technician's own row. Technician with no email gets "\0" (matches nothing). Cross-project park -> 403/404 (test covered).
- Technician is read-only: POST /missions, PATCH /faults, GET /users all 403 (rank technician 1 < operator 2). Note this means a technician cannot update status of their own work order; confirm that is intended.
- Assignee matching is by email string equality with free-text assignee (case-insensitive); an operator typo silently hides the order. Minor, document.

## 5. Register
- Role is always viewer, project_ids empty. Body fields role/project_ids/is_admin ignored (pydantic ignores extras): probe with `{"role":"admin","project_ids":[1],"is_admin":true}` -> 201 role viewer, project_ids []. No escalation.
- Rate limit: 10 attempts per IP per 15 min counting every attempt; tested in suite. Keyed on request.client.host, so behind a reverse proxy all clients share one bucket unless proxy headers are handled (pre-existing pattern, minor). In-memory, per process.
- Password policy: length 10-256 only (5 chars -> 400, 300 chars -> 400); "aaaaaaaaaa" and "1234567890" accepted. MINOR: no complexity/common-password check. MINOR contract mismatch: SolarPulse RegisterForm has minLength=8 (RegisterForm.tsx:132,148), backend demands 10, so an 8-9 char password passes the browser and returns 400 with a string detail (the form shows it; works but surprising). Documented in API_AUTH.md? Not verified; worth stating there.
- Duplicate email (case-insensitive) -> 409: account enumeration, inherent to open signup; minor.
- MINOR/policy: registration defaults ON (SOLARDOCTOR_ALLOW_REGISTRATION default "1") in users mode. Harmless-ish since a viewer has zero project scope, but the lead should confirm default for production.

## 6. Prefixed / unprefixed public paths
Public list is matched on strip_api_prefix(path), so /auth/{login,token,register,refresh,logout} work at both `/x` and `/api/v1/x` (probe: token 200 on both, register 400 validation, refresh 401, i.e. reached the handler unauthenticated). Trailing slash `/api/v1/auth/login/` -> 401 (fails closed). Only one prefix level stripped. /auth/me is not public (requires session). Bad bearer on public path is ignored (no 401), fine. OK.

## 7. /auth/token vs frontend
Frontend (LoginForm.tsx:25-44, RegisterForm.tsx:62-72) posts `application/x-www-form-urlencoded` with `username`=email, `password`, reads `access_token`, `refresh_token`; refresh posts JSON `{refresh_token}` and reads `access_token`/`refresh_token` (api.ts:24-41); register posts JSON `{username,email,password,full_name}`, expects ok status. Backend matches all of it: form parsed manually (no python-multipart dependency), username -> email, JSON body to /auth/token -> 401 (not 422), responses include token/access_token/refresh_token/token_type/expires_*. OK. The frontend never calls /auth/me or /auth/logout.

## 8. Diff outside the author's owned files
Changed paths: backend/solardoctor/{api/routers/{auth,work_orders}.py, api/schemas/{__init__,auth}.py, api/support/principal.py, core/auth.py, db/models.py}, docs/solardoctor/{API_AUTH,SEED_PLAN}.md, tests/backend/{test_auth_tokens,test_auth_users}.py.
- tests/ is sd-qa-owned; the author edited an existing test and added a test file. Content reviewed above and acceptable, but lead should confirm that was authorised.
- work_orders.py and db/models.py/core/auth.py are shared backend files; no physics/vision/frontend/ml files touched. No migration added; role column is String(16) with no CHECK, "technician" fits. THIRD_PARTY_NOTICES not affected (no copied code observed; the contract was re-implemented, SolarPulseAI is MIT anyway).
- SEED_PLAN.md is a plan only; no seed code in the diff despite the branch name.

## Summary table
| # | Severity | Item | Location |
|---|---|---|---|
| 1 | major | Technician can list all faults/assignees and read other faults' comments/photos | api/routers/faults.py:69-73,161-208,298-352; api/support/scope.py |
| 2 | major | Bearer-only logout leaves refresh token usable (refresh -> 200) | api/routers/auth.py:142-157; core/auth.py create_token_pair |
| 3 | minor | No refresh reuse detection / family revocation | core/auth.py rotate_refresh_token |
| 4 | minor | Password policy length-only; frontend minLength 8 vs backend 10 | core/auth.py MIN_PASSWORD_LEN; RegisterForm.tsx:132 |
| 5 | minor | Register limiter keyed on socket IP (proxy), in-memory; registration default on | core/auth.py, routers/auth.py:97 |
| 6 | minor | Real-checkpoint test now skipped; ensure CI asserts it runs once weights exist | tests/backend/test_model_info.py:107 |
| 7 | minor | Author edited sd-qa-owned tests/ | tests/backend/test_auth_users.py, test_auth_tokens.py |

Re-review after #1 and #2 are fixed (with tests that assert a technician cannot read another's fault via /faults list, comments and photos, and that refresh fails after bearer-only logout).
