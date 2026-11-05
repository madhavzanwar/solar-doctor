# QA re-review round 2: feat/auth-seed @ f360286 vs 8814dae

Reviewer: sd-qa. Detached throwaway worktree (removed). Probe tests lived only in that worktree.

## Verdict: NO-SIGN-OFF (1 major new defect introduced by the fix, 1 major residual, rest minor)

## Suites
- tests/backend: 667 passed, 9 failed, 1 skipped. The 9 failures are the same weight-dependent set as round 1 (subset of the baseline 10). Pass count above baseline 632.
- tests/test_api.py test_db.py test_imports.py test_orchestrator.py: 25 passed.
- auth/share/apikey/scope/token subset: 160 passed.

## Round-1 findings
1. Bearer-only logout (FIXED, verified). Own probe: logout with access token only -> refresh 401; rotated descendant (login -> refresh -> bearer logout with the new access token) -> new refresh 401; second login of same user unaffected; replay of a rotated refresh revokes the whole family incl. the newest token, other family unaffected.
2. Technician scoping (FIXED for fault routes, verified; see below).

## NEW MAJOR A: access-token-derived credential outlives the access token (domain separation broken)
core/auth.py stores marker rows as sha256(b"family:"+fid) and refresh rows as sha256(b"refresh:"+token), in the same user_sessions table that resolve_session() looks up by sha256(bearer). Because the hash prefixes are plain strings, an attacker can present them as bearer tokens.
- The fid is the suffix of EVERY access token (`<random>.<fid>`), so anyone who sees an access token (proxy log, `?api_key=` URL, browser history) can send `Authorization: Bearer family:<fid>` and is authenticated as that user until the marker expires (refresh TTL, 7 days) instead of the 12 h access TTL. Repro: login, GET /auth/me with `Bearer family:<fid>` -> 200. It is cleared only when the real login logs out or the family is revoked.
- `Bearer refresh:<refresh_token>` also -> 200 on /auth/me (a refresh token usable as a 7-day non-rotating access token). This contradicts the round-1 "refresh as bearer -> 401" property, which only held for the raw token.
- Impact: session-lifetime extension for a leaked access token; weakens the rotation design. No privilege escalation (same user).
- Fix: store family markers and refresh rows in a way resolve_session cannot match, e.g. a distinct `kind` column or a keyed HMAC with different keys, or make resolve_session reject tokens that start with "family:"/"refresh:" and, better, hash markers with a server secret. Add a test: Bearer "family:<fid>" and "refresh:<rt>" -> 401.

## NEW MAJOR B: duplicate-register 409 -> 201 still enumerates via timing
Response body/status are now identical (verified, keys equal, email normalised the same, existing account password untouched, role never escalated). But the duplicate path skips PBKDF2 (600k iterations). Measured with production iteration count: duplicate ~7 ms vs fresh ~115 ms, repeatable (the one 160 ms duplicate sample was a cold first call). Anyone can distinguish registered emails; the 10/IP/15 min limiter only slows it. Fix: always run the hash (hash first, then check duplicate) or hash a dummy on the duplicate path. Also a UX note: a duplicate signup gets "registered" and never receives any signal (no email verification), accepted trade-off but document it.

## Technician scope (verified with own probes)
- Fault-embedding surface: only faults.py and work_orders.py reference PanelFault/assignee/notes (grep of backend/solardoctor). park summary/grid/recurring/diff, /parks, /analytics/overview, /projects, results, map: none emit assignee or fault rows (probe output contained no assignee text).
- Reads on an unassigned or other technician's fault: GET /faults/{id}/comments, /photos, /photos/{pid} -> 404 (also for non-existent id, so no existence oracle). GET /parks/PARK_A/faults hides others' rows and assignee, counts only own. work-orders (json/csv, `assignee=` override, status filter) never returns others' rows.
- Writes: PATCH status in_progress/resolved, notes, resolution_note, comment (author forced to own email), photo upload on own fault succeed. Assignee/priority/due_date/status open|assigned|etc -> 403; PATCH/comment/photo on other fault -> 404; DELETE photo, POST/PUT elsewhere, missions, inventory, settings, park PATCH -> 403.
- Photo upload really works: with a real 8x8 PNG made with PIL, POST /faults/{own}/photos -> 201, listed, GET returns the identical bytes, other fault -> 404, DELETE -> 403. The author's test uses a 40-byte fake PNG and asserts only "not 403/404", so it would also pass on a 415 (it does not prove success). MINOR: replace with a valid image and assert 201.
- Minor: PATCH body check validates the fields the technician sent, but a technician can set a fault to `resolved` and so make it vanish from their own list (assignee unchanged, still visible); fine.
- Minor: technician can read fault list `status` filter etc. only for own; ok.

## The changed existing tests (diff vs 8814dae)
Only test_auth_users.py::test_session_token_is_stored_hashed is a pre-existing test on 8814dae (count 1 -> 3: access, refresh, family marker; hash checks stricter than before, still asserts tokens not stored plain). Not weakened. The other three changes are in test_auth_tokens.py, a file added on this branch (so no base to weaken):
- duplicate register 409 -> 201: replaced, not dropped, with stronger checks (same status and key set as a fresh signup, existing password still works). Legit given the policy change, but see Major B.
- rotation test: ordering changed and reuse revocation asserted (stricter).
- technician read-only test: the PATCH-fault 403 expectation was replaced by 404 for an unassigned fault, and two other 403 cases (inventory POST, mission DELETE) added; blocked count 3 -> 4. Behaviour change by design, coverage not reduced.

## Token format and other modes
Access token is `<urlsafe random>.<16 hex>`; the response keeps Axalon keys (`token`, `expires_at`, `user`) plus the new ones. Opaque to clients; no test or client parses it. apikey, share-link and off modes unaffected (auth/share/apikey subset 160 passed). Share tokens are separate and not touched. Note: unauthenticated POST /auth/logout with a junk bearer `x.<fid>` revokes that family without a valid session (204) - requires knowing the fid, i.e. already holding an access/refresh token; low.

## access_policy allowlist path tricks (technician)
Tried, none yielded a forbidden write: trailing slash (307 redirect, target re-checked), `//faults/N`, `/api/v1//faults/N`, `/API/V1/faults/N`, `/api/v1/api/v1/faults/N` (404, single prefix strip), `%0A` suffix (regex `$` matches before newline but the route does not; 404), `;x` suffix (403), percent-encoded digit `/faults/%31` (resolves to the own fault, legitimate), `/faults/N/comments` with PATCH (405), PUT/POST on /faults/N (405), DELETE photo (403), `..` segments (405). The regex is anchored and method-specific, the handlers re-check ownership; no bypass found. Minor hardening: use `fullmatch` with `[0-9]+` (Python `\d` matches Unicode digits, though routing currently rejects them).

## Findings, severity ranked
| # | Sev | Finding | Where |
|---|---|---|---|
| A | major | `Bearer family:<fid>` / `Bearer refresh:<rt>` authenticate for up to 7 days; fid is exposed in every access token | core/auth.py _family_hash/_refresh_hash vs resolve_session |
| B | major | Duplicate register is still distinguishable by timing (7 ms vs 115 ms) | core/auth.py create_user / routers/auth.py register |
| C | minor | Photo-upload test uses a fake PNG and asserts only not 403/404; proves nothing about success | tests/backend/test_auth_tokens.py technician work test |
| D | minor | Anonymous logout with `x.<fid>` revokes a family (needs fid) | routers/auth.py logout |
| E | minor | Allowlist regex: use fullmatch and [0-9]+ | api/support/principal.py |
| F | minor | Carry-overs from round 1: no complexity policy beyond repeated-char/email-name, registration default on, limiter keyed on socket IP, frontend minLength 8 vs backend 10, real-checkpoint test skipped | various |

## SIGN-OFF: NO. Re-review after A and B are fixed with tests (bearer `family:`/`refresh:` -> 401; duplicate vs fresh register timing within noise at production iteration count).
