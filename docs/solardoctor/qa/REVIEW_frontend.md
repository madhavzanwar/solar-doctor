# sd-qa review: feat/frontend-clone (tip edb68be)

Reviewer: sd-qa (independent). Method: detached worktree of the branch, real backend from `main` (b07e7e4; `origin/main` does not exist locally) run with `SOLARDOCTOR_AUTH_MODE=users`, bootstrap admin, 5 plants and 5 days of telemetry created through the API, production `next start`, Playwright with chromium. No source or branch was modified.

## Verdict: NO-SIGN-OFF

No blockers. Two majors (one needs a backend fix) and one more major on honesty. The Phase D "390px no horizontal scroll" criterion fails on /dashboard/plants with real data.

## Findings, severity ranked

### MAJOR 1. Expired/invalid access token never refreshes in a real browser (backend CORS + frontend assumption)
- Repro: log in, set `localStorage.solardoctor_access_token = "bogus.token"`, open /dashboard/plants. The browser sends `GET /api/v1/plants`, gets no readable response, and the UI shows "Could not reach the SolarDoctor API..." (plus the empty state "No plants registered yet"). No `/auth/refresh` call is made and the user is not sent to /login.
- Cause: backend auth-middleware 401s carry no `Access-Control-Allow-Origin` (`curl -si -H 'Origin: http://localhost:3000' -H 'Authorization: Bearer bogus' :8000/api/v1/plants` shows no CORS headers). Browser turns it into a network error, so `apiFetch` (`frontend/src/lib/api/http.ts`, the `res.status === 401` branch) is dead code against the real API. The 12 h access TTL therefore ends in a broken dashboard until manual sign-out.
- Unit tests mock `fetch` with a 401 so they cannot see this.
- Fix owners: sd-backend (CORS must be the outermost middleware so 401/403/429 carry CORS headers). Frontend should also treat status 0 on an authenticated call with a stored refresh token as a refresh trigger, or at least not render the empty state below an error (`frontend/src/app/dashboard/plants/page.tsx:~60-70` shows both).

### MAJOR 2. /dashboard/plants overflows horizontally at 390px with real data
- Repro: admin, 390x844, open /dashboard/plants with at least one plant that has weather. `documentElement.scrollWidth` = 861 vs 390; the table is 928px wide, `TABLE.dash-table` has no scroll wrapper (`frontend/src/app/dashboard/plants/page.tsx:~76-125`, `className="nowrap"` cells). All other routes at 390 (including /, /login, /register, plant detail, alerts, performance, stubs) had no overflow.
- The visual and axe harnesses use fixtures and do not assert overflow, so they pass. Fix must go in `solardoctor.css` / a wrapper (dashboard.css is byte-locked).

### MAJOR 3. OnlineAdapterChip shows an invented status when there is no data
- Dashboard with a plant that has no forecasts: chip reads "Live adjust +0.0% ON TRACK" (green). `frontend/src/components/forecast/OnlineAdapterChip.tsx:~146-150` defaults `gamma=1.0`, `biasKw=0`, `samples=0`, `statusLabel="BASELINE_OPTIMAL"` when `status` is missing or the call failed. This presents a healthy state that was never measured. Should render "No data" / hidden.

### MINOR
1. **Cookie expiry computed from a naive timestamp.** `frontend/src/lib/api/auth.ts` `secondsUntil(expires_at)` uses `Date.parse` on `"2026-11-05T21:27:59.620538"` (no Z; backend is UTC). Measured `sd_session` TTL with a real 12 h token: UTC browser 12.0 h, Asia/Kolkata 6.5 h, America/Los_Angeles 20 h. In IST the middleware bounces a user with a still-valid token after 6.5 h. Use `expires_in` (present in the body, 43199) instead. The cookie is also never renewed after a refresh (`saveTokens` does not call `setSessionCookie`), so after 12 h the middleware redirects even if the refresh token (7 d) is good.
2. **Modal focus is not returned to the trigger in the real alert flow.** The Diagnose button is `disabled` during the request, which drops focus to `body`, so the modal records `body` as the previous element. After Esc: `document.activeElement` is `BODY` (DESIGN.md section 11 asks for return). Tab/Shift+Tab trap, initial focus in dialog and Esc-close all work.
3. **Hard-coded role label.** `frontend/src/app/dashboard/DashboardShell.tsx:84` shows "Plant operator" for every user (admin shown as "Plant operator"). Read the role from `/auth/me` or drop it.
4. **Alert SIMULATED badge is dead.** `AlertResponse` has no `source`; the DB column `plant_alerts.source` is `USER` by default. `Alert.source` in `api.types.ts:16` is a type-level assumption that nothing populates. Badges on plants, dashboard, plant detail and weather are correctly data-driven (see below), alerts are not.
5. **Console noise.** `GET /forecast/{id}/summary` returns 404 for a plant with no forecasts and logs a console error on plant detail (handled gracefully in UI). Expected-empty should ideally be 200/empty or be swallowed quietly.
6. **Cookie flags.** `sd_session` is set without `Secure` (`storage.ts` `setSessionCookie`); harmless today (no secret) but should add `Secure` when `location.protocol === "https:"`.
7. **No CSP / security headers** in `frontend/next.config.ts`; tokens in localStorage are therefore fully exposed to any XSS. React escaping and no `dangerouslySetInnerHTML` in app code mitigate; recommend a CSP (`default-src 'self'; connect-src 'self' <API>`; `img-src 'self' data:`) and documenting the localStorage trade-off.
8. **Backend text with `$`.** Diagnosis technician step 02 says "cleaning cost ($/kW)" while the UI is INR. Backend wording, report to sd-physics.
9. **Build needs network.** `next build` fetches Google fonts at build time. One build (a11y harness, run concurrently with a server) failed with "next/font/google queries have exactly one entry"; two retries passed, so it is flaky/network dependent. Offline CI/Docker builds will fail; consider documenting or vendoring fonts.
10. **Hero image weight.** `hero-desert-array.webp` is 580 KB at 2400 px (served through `next/image`; AVIF files exist but are not referenced by name). Lighthouse not run (not installed offline); not a blocker.
11. `npm audit`: moderate advisories in dev-only chains (vitest/eslint/minimatch); no runtime dependency flagged in the summary I saw.

## Checks and results

### 1. Clean build and diff vs upstream
- `npm ci`, `npm run lint` (clean), `npx tsc --noEmit` (clean), `vitest run` (5 files, 40 tests pass), `next build --turbopack` (18 pages, middleware 39 kB) all green.
- `cmp` against SolarPulseAI: `globals.css` identical; `dashboard.css` identical.
- Modified upstream files (all differ, intended rebrand/API/nav): `(auth)/layout.tsx`, `(auth)/login/page.tsx`, `(auth)/register/page.tsx`, `dashboard/DashboardShell.tsx`, `dashboard/alerts/page.tsx`, `dashboard/layout.tsx`, `dashboard/page.tsx`, `dashboard/plants/[id]/page.tsx`, `dashboard/plants/page.tsx`, `app/layout.tsx`, `app/page.tsx`, `components/auth/LoginForm.tsx`, `RegisterForm.tsx`, `components/diagnosis/DiagnosisModal.tsx`, `components/forecast/ProbabilisticBandChart.tsx`, `components/landing/{Features,Hero,HowItWorks,SiteFooter,SiteHeader}.tsx`; config: `package.json`, `next.config.ts` (images.remotePatterns removed, distDir env added), `tsconfig.json`, `eslint.config.mjs`. Upstream-only: `dashboard/forecasts/page.tsx` (moved to `/dashboard/performance`), `lib/api.ts` (replaced by `lib/api/*`). Added: `middleware.ts`, `solardoctor.css`, `lib/{auth-guard,money,password}.ts`, `lib/api/*`, `components/{Logo,ui,dashboard,forecast/ForecastActualChart,OnlineAdapterChip}`, stub routes, `public/images`. `ForecastActualChart.tsx` and `OnlineAdapterChip.tsx` differ from upstream by small additions (chip value/mode label).

### 2. Licence
- No reference to rithvik123 / VishnuBhaiya / mcomuniello / Apollo9 code, text or CSS in `frontend/src`, tests; only the study-only list in THIRD_PARTY_NOTICES.
- No external image URLs, no font CDN links in `src`/`tests` (only `https://evil.example` in a unit test). Fonts are self-hosted by `next/font/google` (woff2 served from `/_next/static/media`).
- `docs/IMAGE_CREDITS.md` lists all 4 photos; 8 files in `public/images` (avif+webp each) match the 4 entries, all 2400 px, no EXIF. Licence claim "Unsplash License": **unverifiable by me** (unsplash.com returns a bot-check 401 to curl through the proxy). Note `technician-cleaning` is credited "Florida Solar Fix (sponsored image)": still under the Unsplash licence but it is brand advertising imagery; the author should confirm. Only the hero is used; the other 3 are "reserved".
- THIRD_PARTY_NOTICES has the SolarPulseAI (MIT) frontend entry, fonts (OFL) and photo/credits pointer. Gap: notice does not state the MIT copyright text/licence file for the copied frontend files beyond the attribution line (acceptable per rule, flag for lead to confirm `LICENSE` of upstream is reproduced if required). Minor.

### 3. Auth (live)
- Middleware: presence-only `sd_session` cookie. Forgeable (anyone can set it), but the shell is client-rendered and carries no data: with a forged cookie and no token the client guard sent me to /login and made zero API calls; page HTML did not contain seeded plant names. API remains the authority (valid-token requests only). OK.
- Unauthenticated `/dashboard/**` all 307 to `/login?next=...` (checked all 14 routes).
- Open redirect: `next` values `//evil.example`, `https://evil.example`, `/\evil.example`, `javascript:alert(1)` all land on /dashboard; `/dashboard/alerts` honoured. OK.
- Register -> auto-login -> /dashboard works (name field is required). Login, bad-password message ("Invalid email or password.") correct. Logout: `POST /auth/logout` with Bearer + refresh_token; afterwards old access token -> 401 and the refresh token -> 401 (server revocation confirmed); localStorage and cookie cleared; /dashboard redirects. The logout fetch shows `net::ERR_ABORTED` in Playwright because of the immediate `location.href` navigation, but the server revoked.
- Refresh: single-flight `refreshOnce` promise dedupes; rotation saved via `saveTokens`. Not exercisable end to end because of MAJOR 1.
- Visiting /login while authenticated does not redirect to the dashboard (cosmetic).

### 4. Honesty
- Badges: plants list/dashboard/plant detail show SIMULATED for `source=simulated` plants and none for `source=real`; weather badge "MOCK" appears because the backend returned `source:"mock"` (no key). Driven by data.
- No fabricated numbers found in components; fixtures only under `tests/`. Stub pages (ROI, map, inspections, work-orders, reports) are explicit empty states. Exceptions: MAJOR 3, minor 3.
- Settings: no enabled control outside nav (script enumerated input/select/button), "Not connected" note and badges present.
- Bell: lists only real open alerts from `/alerts` (2 inserted rows shown, count correct); empty message otherwise.
- DiagnosisModal against live API: plant with tariff -> "₹2,475/day"; plant without tariff -> "Not estimated" with explanation; alert without power values -> 422 surfaced as a readable message ("Alert N has no expected/actual power to diagnose."), no modal.

### 5. Accessibility
- axe script rerun (fixtures, 15 routes x 1440/390): 0 violations at every impact level.
- Keyboard: first Tab is "Skip to content", Enter moves focus to `main#main` (hash `#main`); tab order follows nav in DOM order; focus outline 2px solid on all tested stops; modal: focus enters dialog, 25x Tab and 25x Shift+Tab stay inside, Esc closes (focus return fails, minor 2).
- 390px horizontal overflow: fails only on /dashboard/plants (MAJOR 2); no other route.

### 6. Visual (rerun, clone font mode, fixtures)
Reproduced the reported ratios: landing 10.0% desktop / 16.1% mobile; login 0.1%; register 0.2%; overview 0.4% / 0.3%; plants 1.0%; plant-new 0.4%; plant-detail 0.5% (report says 0.4%) / 0.3%; alerts 0.4%; performance 0.4%. Reference set has only 12 images, so mobile plants/alerts/login/register/performance/plant-new are unchecked. Landing differences, viewed against the reference: layout, section order, spacing and typography are the same; differences are the photo hero (replacing the dark gradient), copy, wordmark colouring, and the nav ("Log in / Register" vs "Dashboard / Sign out"). Judged photo/copy only. Caveat: all visual and axe runs use mocked API data, which is why MAJOR 2 was missed.

### 7. Lighthouse
Not run (no Lighthouse available offline). Only noted observable weight: hero 580 KB webp, first-load JS 122-134 kB per route.

## Needs from others
- sd-backend: CORS outermost so 401/403/429 are readable (MAJOR 1).
- sd-frontend: MAJOR 1 frontend handling, MAJOR 2, MAJOR 3, minors 1-3, 5-7.
- Lead: confirm Unsplash licences by a human (unverifiable here); decide on the sponsored image.

Environment notes: temporary worktrees removed; servers stopped; my scratch scripts are in /tmp/claude-0/qa-walk/.
