# QA re-review round 3: feat/auth-seed @ ab55350 vs 8814dae

Reviewer: sd-qa. Detached throwaway worktree (removed). Own probe scripts only; no source or branch modified.

## Verdict: SIGN-OFF (no blocker, no major; two informational notes)

## Suites
- tests/backend: 672 passed, 9 failed, 1 skipped. The 9 failures are the same weight-dependent set as rounds 1 and 2 (subset of baseline 10); skip is the real-checkpoint test (weights absent). Pass count above baseline 632.
- tests/test_api.py test_db.py test_imports.py test_orchestrator.py: 25 passed.

## A) Token namespace separation: FIXED (own repro, production PBKDF2)
Login, then on /auth/me, both as `Authorization: Bearer` and `?api_key=`:
- `family:<fid>`, `refresh:<rt>`, raw refresh token, bare fid, `FAMILY:<fid>`, `family: <fid>`, access token with a char appended, access token without `.fid`: all 401.
- Genuine access token: 200. Leaked access token whose row is expired: 401, and `family:<fid>` 401 too (no 7-day extension).
- POST /auth/refresh with the access token, the bare fid, or `family:<fid>` as refresh_token: all 401; legit refresh: 200.
- Why it holds: preimages of marker/refresh rows contain ':' (or a 16-char head before the dot), which the access shape `[A-Za-z0-9_-]{20,}(\.[0-9a-f]{16})?` rejects; refresh raw token also fails the hash lookup. Note the gate is a shape check, not a separate table/kind column; it is sufficient today, but any future token format containing ':' or a prefix change must keep the marker preimages outside the access alphabet (suggest a comment-level invariant, already present in code).
- Backward compatibility (pre-change `token_urlsafe(32)` 43-char tokens, no `.fid`): 200. Also 200: token_urlsafe(16/24/48/64) (22-86 chars), 64-char and 32-char hex, `sd_`-prefixed 46 chars, new `<rand>.<fid>` tokens, form-login (/auth/token) tokens, admin (bootstrap-style create_user admin) login tokens. A `=`-padded string is rejected (never produced by the code). Surrounding whitespace is stripped by the header parser and still authenticates (benign). Share-link tokens use resolve_share_link (own table, no regex) and the share-token fallback is reached after resolve_session returns None; apikey and off modes do not call resolve_session. Share/apikey/auth suites pass.
- Only risk: a pre-change DB session shorter than 20 chars would be rejected; the old code only ever issued 43-char tokens, so none exist.

## B) Registration timing: FIXED (production 600,000 iterations, 30 interleaved runs each, TestClient)
| path | median | min | max | stdev |
|---|---|---|---|---|
| register fresh | 115.4 ms | 111.4 | 146.3 | 7.3 |
| register duplicate | 113.8 ms | 110.6 | 138.6 | 6.4 |
| login known email, wrong password | 115.2 ms | 109.6 | 160.3 | 8.9 |
| login unknown email | 114.7 ms | 109.6 | 133.5 | 5.3 |
Differences (<2 ms) are inside noise. Other channels: login 401 body identical for known/unknown (`Invalid email or password`); limiter returns 401x5 then 429 for both a known and an unknown email (identical sequence). The dummy hash is cached per iteration count, so only the very first unknown-email login costs an extra hash (warm-up, not per-request). Residual (accepted, documented trade-off): a duplicate signup gets "registered" with no signal to the owner (no email verification), and the 10/IP limiter keys on socket IP.

## C) Valid-image upload asserts 201: FIXED
test_technician_can_work_own_fault now uploads a real PNG built with PIL and asserts 201 and that it is listed. My probe: real PNG -> 201 on both `/faults/N/photos` and `/api/v1/faults/N/photos`; fake 40-byte PNG -> 415 (the old assertion would have passed on it, the new one would not).

## D) Anonymous logout with a guessed fid: FIXED
With a fresh login, I sent anonymous logouts with: no credentials, `Bearer <junk>.<fid>`, `Bearer family:<fid>`, `Bearer <fid>`, refresh token used as bearer, body `{<fid>.zzzz}`, `{<fid>.<43 random>}`, `{refresh:<rt>}`, `{<access token>}`. All 204, and afterwards the real refresh token still refreshed (200). Revocation now needs a live session row (access) or a live refresh row, so it requires proof of a real credential.

## E) Technician write allowlist: FIXED
`fullmatch` with `[0-9]+` and `(?:comments|photos)`. Probes as technician (PATCH/POST/DELETE): `/faults/N/` 307 (redirect target re-checked), `/faults/Nx` 403, Arabic-Indic digit path 403, `/faults/N;x` 403, `//faults/N` 404, `/api/v1/api/v1/faults/N` 404, `/faults/N/photos/1` DELETE 403. Informational: `/faults/N%0A` (and `%0a`) is treated as `/faults/N` (the prefix stripper normalises it; the route also parses it as N), so the PATCH reaches the own-fault handler. Not a bypass: another technician's fault with the same suffix is 404, and `assignee` or `status: open` on own fault via that path remain 403, DELETE 403. No test covers `%0A`; consider adding one to pin the intent.

## Round-1 regression check
- Bearer-only logout kills refresh family: logout 204 then refresh 401 (still true, also covered by tests). Rotated descendants and reuse detection covered by passing tests.
- Technician scoping: other/unassigned fault GET comments/photos and PATCH -> 404 each; own fault allowed writes (status in_progress/resolved, notes, comment with forced author, photo) work; assignee/priority/due_date/status open|assigned -> 403. `/work-orders` probe path returned 404 in my probe (route prefix differs; covered by the suite's work-order test which passes).
- No test weakened: the round-3 test commit only adds tests and strengthens the PNG assertion.

## Findings, severity ranked
| # | Sev | Finding |
|---|---|---|
| 1 | info | Allowlist: trailing `%0A` normalises to the allowed route; harmless, add a pinning test |
| 2 | info | Namespace separation is by token-shape gate, not a typed column; fine now, invariant must be preserved if token formats change |
| 3 | info | Carry-overs: no email verification on signup, limiter keyed on socket IP, complexity policy minimal, frontend minLength 8 vs backend 10, real-checkpoint test skips until `make weights` |

## SIGN-OFF: YES. All round-2 items A-E verified fixed with independent repros; no regressions from round 1.
