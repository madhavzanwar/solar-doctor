# SolarDoctor frontend

Next.js 15 / React 19 / Tailwind 4, no UI libraries. Derived from SolarPulseAI (MIT). `src/app/globals.css` and
`src/app/dashboard/dashboard.css` must stay byte-identical to upstream; additions go in `src/app/solardoctor.css`.

```bash
npm ci
npm run dev            # http://localhost:3000 (API at NEXT_PUBLIC_API_URL, default http://localhost:8000)
npm run lint && npm run typecheck && npm test && npm run build
```

`next build` fetches Google Fonts, so it needs network.

## Smoke test against a real API: `npm run test:smoke`

`tests/smoke/run.mjs` drives a real browser against a **built** frontend and a **live, seeded** API. Nothing is mocked.
It exits non-zero if any check fails (API down, wrong text, missing SIMULATED badge, console error, failed API call...).

| Env var | Meaning |
|---|---|
| `SMOKE_BASE_URL` | frontend origin, e.g. `http://localhost:3000` (`npm run build && npm run start`) |
| `SMOKE_API_URL` | API origin the frontend was built against, i.e. the value of `NEXT_PUBLIC_API_URL` at build time |
| `SMOKE_EMAIL`, `SMOKE_PASSWORD` | seeded admin (`admin@solardoctor.example` and `SOLARDOCTOR_SEED_ADMIN_PASSWORD`); if the API login answers 401 the account is registered first |
| `SMOKE_PLANT_NAMES` | optional, comma list; default `Bhadla Block C,PCCoE Rooftop,Pavagada Unit 4` |
| `CHROMIUM_PATH` | optional browser executable |

Checks: API health and login; `/`, `/login`, `/dashboard` (redirects to `/login` while logged out); login through the form;
`/dashboard`, `/dashboard/plants`, `/dashboard/plants/<first id>`, `/dashboard/alerts`, `/dashboard/performance` each return
HTTP 2xx with the expected `<h1>`; the plants table lists the three seeded plants, each with the `SIMULATED` badge and the
empty state is absent; zero console errors, zero uncaught page errors, zero failed API requests (4xx/5xx or network
failure; the only allowed answer is 404 from `/api/v1/forecast/<id>/summary`, "no forecasts yet"; a request aborted by
navigation after the server answered 2xx, as for the 204 logout, is not a failure); Sign out lands on `/login` and
`/dashboard` then redirects to `/login`.

```bash
SOLARDOCTOR_AUTH_MODE=users SOLARDOCTOR_DB_URL=sqlite:////tmp/smoke.db SOLARDOCTOR_SEED_ADMIN_PASSWORD=... \
  PYTHONPATH=backend:. python scripts/seed.py --offline
SOLARDOCTOR_AUTH_MODE=users SOLARDOCTOR_DB_URL=sqlite:////tmp/smoke.db uvicorn solardoctor.api.app:app --port 8000 &
cd frontend && NEXT_PUBLIC_API_URL=http://localhost:8000 npm run build && npm run start &
SMOKE_BASE_URL=http://localhost:3000 SMOKE_API_URL=http://localhost:8000 \
  SMOKE_EMAIL=admin@solardoctor.example SMOKE_PASSWORD=... npm run test:smoke
```

## Visual gate: `npm run test:visual`

Builds with `NEXT_PUBLIC_FONT_MODE=clone`, mocks the API with `tests/fixtures`, screenshots at 1440x900 and 390x844 and
compares with `docs/solardoctor/design/reference/*.webp` (pixelmatch, per-pixel threshold 0.1). Exits 1 on failure.
Thresholds are written in the script (`APP_MAX`, `LANDING_MAX`) and are not to be tuned after the fact:

- Dashboard and auth routes: full-canvas diff **<= 2.0 %** (a page-height mismatch counts as differing pixels), desktop
  and mobile wherever a reference exists.
- Landing (new photo and copy): **<= 3.0 %** with masks. Masking rule: the hero `<section>`, every img/picture/svg and
  every element directly containing text (+2 px) are painted flat grey in both images at the same coordinates; ratio =
  differing pixels / unmasked pixels of the region both images cover (height difference from new copy is not gated).
- No reference image, so screenshot-only (not gated): mobile login, register, plant-new, plants, alerts, performance.

Results: `docs/solardoctor/qa/visual/results.md`.

## Other checks

- `npm run test:a11y`: axe-core (WCAG A/AA) on 15 routes at desktop and mobile; must report 0 violations.
- `npm run test:overflow`: no horizontal page scroll at 390 px (and 1440 px) on every dashboard route.
- `npm run gen:api`: regenerate the typed client from `openapi.json`.
