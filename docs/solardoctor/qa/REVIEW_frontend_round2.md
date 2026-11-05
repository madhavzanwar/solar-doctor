# sd-qa round 2: feat/frontend-clone (tip d52598d, code tip 67a07a9)

Reviewer: sd-qa. Method: detached worktree of the branch, `npm ci`, production `next build --turbopack && next start`
(NEXT_PUBLIC_API_URL=http://localhost:8000), real backend from a detached worktree of origin/main (7152816) with
`SOLARDOCTOR_AUTH_MODE=users`, seeded by `scripts/seed.py --offline --days 7` into a temp SQLite DB (3 plants, admin +
technician), Playwright chromium 1243. Nothing in source or any branch was modified; worktrees and servers removed.
Scratch scripts: /tmp/claude-0/qa2s/.

## Verdict: SIGN-OFF

No blockers and no majors. All three round-1 majors are fixed and verified in a real browser against a real backend.
Two minors and a few nits remain (below); none block merge.

## Round-1 findings: status

| Round 1 | Status | Evidence (own runs) |
|---|---|---|
| M1 expired token never refreshes | FIXED | see 1 |
| M2 /plants overflow at 390 | FIXED | see 2 |
| M3 chip invents healthy state | FIXED | see 3 |
| minor 1 cookie TZ / no renewal | FIXED | see 4 |
| minor 2 focus return | FIXED for the alert Diagnose flow; NOT fixed for the sandbox "Run diagnosis" button (new minor A) | see 6 |
| minor 3 role label | FIXED | Administrator (admin), Technician (technician) |
| minor 4 dead alert badge | FIXED (removed) | diff |
| minor 5 forecast 404 console noise | PARTLY: UI quiet, browser still logs its own 404 line | see 6 |
| minor 6 Secure flag | FIXED | see 4 |
| minor 7 no CSP | FIXED (with the 'unsafe-inline' trade-off) | see 5 |
| minor 9 build needs network | not addressed (documented only); build passed here | |
| minor 10 hero weight | FIXED | see 6 |

## 1. M1: token refresh (real browser, real backend)

Branch merge state: `f867746` (CORS outermost, "fix(api): make CORS the outermost middleware") is an ancestor of
the branch tip (merge commit 111ac47) and of origin/main. origin/main has since moved on (seed commits, tip 7152816),
which the branch does not yet contain. `git merge-tree` of origin/main with the branch is clean, and the new
origin/main commits touch no `frontend/` files. `tests/backend/test_cors_outermost.py` passes (2 passed).

401s are now readable in the browser (CORS headers present). Results of opening /dashboard/plants after tampering:

| Scenario | Result |
|---|---|
| A. access = `bogus.token`, valid refresh | 401 on /plants, one POST /auth/refresh (deduplicated across 4 parallel calls), 200, retried, plants load, refresh token rotated, cookie kept. No "Could not reach". |
| B. bogus access, bogus refresh | refresh 401, session cleared, redirected to /login |
| C. bogus access, no refresh token | redirected to /login with no refresh call |
| D. well-formed unknown access token + valid refresh | silent refresh, data loads |
| E. genuinely expired (DB `user_sessions.expires_at` in the past) | refresh rejected, redirected to /login (note the backend ties refresh to the same session row, so this also kills refresh) |
| F. backend stopped, valid session | stays on /dashboard/plants, tokens and cookie unchanged, "Could not reach the SolarDoctor API at http://localhost:8000" shown. Session preserved. |

Nit: in F the page also renders the empty state "No plants registered yet / Register your first plant" under the
error banner (`frontend/src/app/dashboard/plants/page.tsx`, `plants.length === 0` branch is not gated on `error`).
This is misleading, since the true state is "unknown". Round 1 asked for this to be gated; only the refresh part was done.

## 2. M2: 390px overflow with real data

Real backend, logged-in admin, 3 seeded plants then 13 plants (10 extra with 80-char names, 60-char unbroken
location suffix, capacity 9,999,999 kW, forecasts generated for plants 1 to 3). 17 routes (/, /login, /register, all
dashboard routes, plant 1, 2, 3) at 390, 360 and 320 px: `scrollWidth <= innerWidth` on all, 0 failures
(the previous failure was 861 vs 390). The branch's own `test:overflow` harness: 24 of 24 pass.
Not covered: very long real alert messages (backend only produced one real alert); the harness covers that with fixtures.

## 3. M3: OnlineAdapterChip

Dashboard with a plant that has forecasts but no observed samples: chip reads "Live adjust — No data yet", no
green "On track". Unit tests (chip.test.tsx, 3) pass. Not exercised live with samples > 0 (no data source for that in the seed).

## 4. Cookie lifetime and Secure (non-UTC)

Cookie `sd_session` TTL measured from the real login response (access TTL 12.00 h, refresh TTL 168.00 h):

| timezoneId | cookie TTL after login | after forced refresh (cookie pre-shrunk to 2 min) |
|---|---|---|
| UTC | 168.00 h | 168.00 h |
| Asia/Kolkata | 168.00 h | 168.00 h |
| America/Los_Angeles | 168.00 h | 168.00 h |
| Pacific/Auckland | 168.00 h | 168.00 h |

Identical in every zone (round 1: 6.5 h IST, 20 h LA). Design note: the cookie now lives as long as the refresh token
(7 days), not the 12 h access token, which is correct for a presence-only cookie that exists so a stale access token can
refresh. If the refresh token is revoked server-side, the cookie outlives it, and the client guard then sends the user
to /login (scenario B), so no dead end.
Secure: via a self-signed TLS proxy (https://localhost:3443) the cookie has `Secure=true, SameSite=Lax`, both at login
and after refresh; over http it is not Secure. Not HttpOnly (needs JS to set; no secret in it).

## 5. CSP and security headers (production build)

Headers present on page, redirect and static image responses: CSP, X-Content-Type-Options nosniff, X-Frame-Options DENY,
Referrer-Policy strict-origin-when-cross-origin, Permissions-Policy, HSTS (prod only). CSP:
`default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:;
font-src 'self' data:; connect-src 'self' http://localhost:8000; media-src 'self'; object-src 'none'; base-uri 'self';
form-action 'self'; frame-ancestors 'none'`.

- 16 routes (anonymous desktop, authenticated desktop, authenticated 390): console CSP messages 0,
  `securitypolicyviolation` events 0, failed requests 0.
- next/font self-hosted woff2 load (200 from `/_next/static/media/*.woff2`), `document.fonts` shows Geist and Bricolage
  Grotesque loaded. API calls to :8000 succeed under `connect-src`.
- Enforcement works: an injected `<script src=https://evil.example/x.js>`, a `fetch('https://evil.example/')` and an
  external `<img>` are all blocked and reported. An injected inline `<script>` runs (by design, see below).
- Trade-off 'unsafe-inline' in script-src: the page has 7 inline bootstrap scripts (Next flight data), so removing it
  today would break hydration. With it, CSP no longer stops injected inline script or inline event handlers, which is
  the XSS class that matters because tokens are in localStorage. What it does still stop: remote script hosts,
  exfiltration to other origins via fetch/img/form, framing, and plugin content. Mitigations present: React escaping and
  no `dangerouslySetInnerHTML`/`innerHTML`/`eval` in `src` (grep clean). I judge this acceptable for a prototype and the
  comment in `next.config.ts` states it honestly.
- Nonce feasibility: yes, feasible and the better end state. `middleware.ts` already exists; Next 15 applies a nonce to
  its own inline scripts when the request carries a `Content-Security-Policy` header with `'nonce-...'` (+
  `'strict-dynamic'`). Cost: every page must render dynamically (read `headers()` in the root layout), which gives up
  static prerendering/CDN caching for `/`, `/login`, `/register`, and the middleware matcher widens from
  `/dashboard/**` to all pages. Since the dashboard is client-rendered behind auth, the cost is mostly the landing page's
  TTFB. Recommend as a follow-up, not a merge blocker. Hash-based is not practical (flight payload differs per page).
- `connect-src` is computed in `next.config.ts` at build time from `NEXT_PUBLIC_API_URL` (also build-time), so a
  deployment that changes the API URL must rebuild. Worth a line in deploy docs.

## 6. Smaller items

- Focus return (alert Diagnose flow): Esc, close button, overlay click all return focus to the "Diagnose" button.
  Focus enters the dialog on open.
- Role label: "Administrator" for admin, "Technician" for technician (from `/auth/me`); blank until loaded.
- /forecast/{id}/summary 404 (plant with no forecasts): no UI error, but the browser itself still prints
  "Failed to load resource: 404" in the console on /dashboard/plants/4 (only a backend 200/empty would remove it). Only
  console entry across 13 authenticated routes. The branch's BUILD_LOG states this accurately.
- Hero via next/image: AVIF 61 KB at w=1920 q=40 (desktop), 8.2 KB at w=640 (390 px viewport). Visually inspected
  at 1440: acceptable, no visible banding. Source webp 201,990 B, avif 113,427 B.
- IMAGE_CREDITS.md vs files: 3 entries (hero-desert-array, array-aerial, technician-panel), 6 files in
  `public/images`, 1:1; `technician-cleaning` removed from both. Licence and author claims unverifiable by me
  (unsplash.com blocks the proxy), same caveat as round 1 for the lead. Doc says the hero is "under 200 KB": the webp is
  197 KiB / 202 kB, borderline wording. `array-aerial` and `technician-panel` are unused but still shipped in `public/`
  (technician-panel.webp is 486 KB; only costs if requested).

## 7. Reruns

- `npx tsc --noEmit` clean; `npm run lint` clean; `vitest run` 9 files, 58 tests pass (was 40).
- `next build --turbopack`: 16 routes, middleware 39.2 kB, First Load JS 124 to 135 kB.
- axe harness (`test:a11y`, fixtures, 15 routes x 2 viewports): 0 violations at all impact levels. My own axe run
  (wcag2a/2aa/21a/21aa) against the REAL backend with 13 plants, 7 routes x 1440/390: 0 violations.
- `test:overflow`: 24 of 24 pass.
- Visual harness (clone font mode, fixtures), ratios common region vs reported: landing 9.6% (10.0), mobile landing
  15.9% (16.1), login 0.1 (0.1), register 0.2 (0.2), overview 0.4 / 0.3 (0.4 / 0.3), plants 1.1 (1.0), plant-new 0.4
  (0.4), plant-detail 0.5 / 0.3 (0.4 / 0.3), alerts 0.4 (0.4), performance 0.4 (0.4). All within 0.1 percentage point
  of the report; landing differs from the reference only by the photo hero (as in round 1).
- Backend: `tests/backend/test_cors_outermost.py` 2 passed on origin/main. I did not rerun the full 632-test backend
  suite; the branch changes no backend source relative to its merge base.

## 8. Whole-branch diff

`git diff f867746..feat/frontend-clone` (merge base with the main it merged): 46 files, all under `frontend/` or
`docs/`; no backend, ml, scripts or tests/ changes. Deleted: `technician-cleaning.{avif,webp}` (intended).
- `globals.css` and `dashboard.css` byte-identical to SolarPulseAI (`cmp`, /tmp/claude-0/sp/SolarPulseAI/frontend/src/app).
- `frontend/openapi.json` regenerated: equals `app.openapi()` of origin/main (104 paths, schemas identical), and
  `schema.d.ts` is exactly what `openapi-typescript` produces from it. `api.types.pending.ts` shrank to the weather types.
- Visible-behaviour changes beyond the brief: none found. No reference to the study-only repos in the diff.
- Note: diffing the branch directly against current origin/main shows seed files as "deleted" only because the
  branch has not merged the latest main; a merge is clean.
- Licence: new devDependencies `@axe-core/playwright` and `axe-core` are MPL-2.0. Used unmodified as dev tools, nothing
  copied or bundled, so the copy-with-attribution rule is not triggered; I suggest the lead add a one-line mention to
  THIRD_PARTY_NOTICES for completeness.

## Findings, severity ranked (all non-blocking)

### MINOR A. Focus is not returned after the Fault sandbox "Run diagnosis" modal
- Repro: /dashboard/alerts, tab "Fault sandbox", focus "Run diagnosis", click, wait for the dialog, press Esc.
  `document.activeElement` is `BODY` (not the button).
- Cause: `frontend/src/app/dashboard/alerts/page.tsx` ~line 387 still uses `disabled={runningSandbox || !customPlantId}`,
  which drops focus to body while the request runs, so the modal records body as "previous". The Diagnose button was
  fixed with `aria-disabled`/`aria-busy`; this one was missed. Fix: same pattern (keep `!customPlantId` as true disabled
  only before click, use aria-disabled while running).
- Latent: `DiagnosisModal` effect depends on `[onClose]` and the alerts page passes an inline arrow, so any re-render of
  AlertsPage while the modal is open re-runs the effect (focus jumps to first control, "previous" becomes an element
  inside the dialog). I found no trigger today (state updates are batched with opening), so latent only. Wrap onClose in
  `useCallback` or hold it in a ref.

### MINOR B. Empty state shown under the "API unreachable" error
- Repro: log in, stop the backend, open /dashboard/plants. Banner "Could not reach the SolarDoctor API" plus
  "No plants registered yet. Register your first plant". Gate the empty state on `!error`.

### NIT 1. Browser console 404 on plants with no forecasts
- `GET /forecast/{id}/summary` 404 prints a console error on /dashboard/plants/{id}; UI is quiet. Needs a backend 200
  with empty body to be truly silent (sd-physics/sd-backend, optional).

### NIT 2. Operational notes
- `NEXT_PUBLIC_API_URL` must be set at build time and is baked into the CSP; document in deploy notes.
- Fonts still fetched from Google at build time (build needs network); unchanged from round 1.
- IMAGE_CREDITS licence/author claims still need a human to confirm; two unused photos ship in `public/`.

## Needs from others
- Lead: merge latest origin/main into the branch (clean) before merging; confirm Unsplash licences; optionally add the
  axe MPL-2.0 note to THIRD_PARTY_NOTICES; decide on nonce-based CSP as a follow-up task.
- sd-frontend (follow-up, not blocking): MINOR A and B, nonce CSP.
