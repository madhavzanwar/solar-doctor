# SolarDoctor — DESIGN.md

> **What this is:** the design system for SolarDoctor. It reverse-engineers the UI of **SolarPulseAI**
> (https://github.com/anugrahpatil-creator/SolarPulseAI, MIT, frontend at commit `0f99a1c`, 2026-10-17), which we
> clone **pixel-for-pixel**, and then extends it with the screens SolarDoctor needs (photo inspection, explainability,
> ROI, work orders, map).
>
> **Source of truth, in order:** (1) this file, (2) the reference screenshots in `./reference/`, (3) the original
> source files listed in §12. If they disagree, this file wins — it records deliberate changes.
>
> **How the reference screenshots were made:** the SolarPulseAI frontend was built and run locally (Next 15.5,
> React 19, Tailwind 4) with every `/api/v1/*` call mocked by Playwright. Two substitutions were needed in the
> sandbox: Google Fonts were loaded from `@fontsource` (same families: Syne + Source Sans 3), and the Unsplash hero
> photo was replaced by a gradient because the image CDN was unreachable. Data in the screenshots is fake.
> The Bhadla chart looks flat only because the mock data was scaled for a 120 kW plant.

---

## 1. Design character

**"Field instrument, printed on survey paper."** Calm, technical, editorial. It reads like an engineer's logbook,
not a SaaS template:

- **Paper** background with a faint **48 px survey grid**; white panels sit on it like sheets of paper.
- One heavy brand colour: **Field green** (`#1a3a2a`) — sidebar, primary buttons, active states.
- One warm accent: **Sun ochre** (`#c9852a`) — eyebrows, nav indices, live values, "actual output" lines.
- **Square corners** (2 px radius everywhere). No shadows. Separation comes from **1 px hairlines** (`#c5cdc5`).
- **Uppercase, tracked micro-labels** (0.68–0.75 rem, letter-spacing 0.08–0.16 em) above every number.
- **Numbered navigation** (`01 Overview`, `02 Plants`…) and numbered feature lists — the "instrument panel" signature.
- Numbers are big and set in the **display face**; units are small and muted beside them.
- Motion is minimal: rise-in on the landing hero, a pulsing status dot, 150 ms colour transitions.

Keep this character. Every new SolarDoctor screen must look like it shipped with the original.

---

## 2. Colour tokens

### 2.1 Clone-exact tokens (from `src/app/globals.css` `:root`)

| Token | Hex | Use |
|---|---|---|
| `--paper` | `#f0f2ef` | App/page background, topbar (at 92% opacity + 8 px blur) |
| `--ink` | `#141814` | Primary text |
| `--muted` | `#5c665c` | Secondary text, labels, axis text |
| `--line` | `#c5cdc5` | All borders, dividers, grid lines, chart gridlines |
| `--field` | `#1a3a2a` | Brand green: sidebar, primary buttons, active tab underline, "forecast" series |
| `--field-hover` | `#234a36` | Hover of field surfaces |
| `--sun` | `#c9852a` | Accent: eyebrows, nav indices, avatar, irradiance, "actual" series, warnings |
| `--panel` | `#ffffff` | Cards, inputs, tables, KPI strip |
| `--danger` | `#9b2c2c` | Critical, errors, destructive |

Derived (from `dashboard.css`): `--dash-accent-dim rgba(26,58,42,.08)`, `--dash-warning-dim rgba(201,133,42,.12)`,
`--dash-danger-dim rgba(155,44,44,.10)`, overlay `rgba(20,24,20,.45)`, modal scrim `rgba(20,24,20,.5)`,
table row hover `rgba(26,58,42,.03)`, muted badge `rgba(20,24,20,.06)`.
Sidebar text: `#f4f7f4` (100%), 72% for inactive items, 55% for role text; sidebar dividers `rgba(255,255,255,.12)`.
Landing hero scrim: `rgba(10,22,16,.72)`. Footer text: `#e8efe8` / `#c5d2c5`.

### 2.2 SolarDoctor additions (new tokens — add to `:root` and `@theme inline`)

All chosen to sit inside the paper / field / sun palette (muted, earthy, print-like; no neon).

**Severity scale** (alerts, work-order priority, deficit level). Always pair colour with a text label.

| Token | Hex | Label | Dim background |
|---|---|---|---|
| `--sev-critical` | `#9b2c2c` | CRITICAL | `rgba(155,44,44,.10)` |
| `--sev-high` | `#b45309` | HIGH | `rgba(180,83,9,.11)` |
| `--sev-medium` | `#c9852a` | MEDIUM (= sun) | `rgba(201,133,42,.12)` |
| `--sev-low` | `#5b6b7a` | LOW / MONITOR | `rgba(91,107,122,.10)` |
| `--sev-resolved` | `#1a3a2a` | RESOLVED (= field) | `rgba(26,58,42,.08)` |

**Defect classes** (the 6-class photo classifier). Used for chips, legend dots, bar charts. Never reuse these
for severity.

| Class | Token | Hex | Meaning / default action |
|---|---|---|---|
| Clean | `--cls-clean` | `#2f6b4f` | No action |
| Dusty | `--cls-dusty` | `#a8792f` | Clean (reversible) |
| Bird-drop | `--cls-bird` | `#6b6f4a` | Spot-clean (reversible, hotspot risk) |
| Snow-covered | `--cls-snow` | `#4f7f9e` | Wait / clear (reversible) |
| Electrical-damage | `--cls-electrical` | `#9b2c2c` | Field check + IV / thermal (irreversible) |
| Physical-damage | `--cls-physical` | `#6a4c7d` | Replace / warranty claim (irreversible) |

**Explainability (XAI) overlay** — a **separate** perceptual colormap so a heatmap is never read as "critical".
Use **viridis** for Grad-CAM (`#440154 → #31688e → #35b779 → #fde725`) at 45% default opacity, and for LIME draw
superpixel **outlines** in `--sun` with the positive-evidence fill `rgba(201,133,42,.35)`; negative evidence
(optional) `rgba(91,107,122,.30)`.

**Charts:** expected/clear-sky = `--field` solid 2 px; base/physics = `#718096` dashed `5 3`; actual = `--sun`
2 px with dots; deficit ribbon = `--sev-critical` at 14% fill between expected and actual; confidence band = `--line`
at 40%; P10/P90 = sun/field thin lines; gridlines `--line` dashed `2 3`.

**Dark mode:** the original has none. Do **not** invent one for v1. (If added later: paper → `#101411`,
panel → `#161c18`, line → `#2a332c`, ink → `#e8efe8`, field stays as accent `#3f7a5c`.)

---

## 3. Typography

### 3.1 Clone-exact
- Display: **Syne** 600/700/800 (`--font-display`) — logo, H1/H2, KPI values, plant names, nav indices.
- Text: **Source Sans 3** 400/500/600/700 (`--font-sans`) — everything else.
- Loaded via `next/font/google` in `src/app/layout.tsx` as CSS variables on `<body>`.

### 3.2 SolarDoctor upgrade (approved by owner: "better and aesthetic fonts")
Keep the *roles* identical; swap the faces for a more refined, more legible set:

| Role | Font | Weights | Why |
|---|---|---|---|
| Display (`--font-display`) | **Bricolage Grotesque** (Google Fonts, variable, optical size) | 600, 700, 800 | Same quirky-grotesque attitude as Syne but far more legible in KPI numbers and long names; optical sizing makes 72 px heroes and 18 px card titles both look intentional. |
| Text (`--font-sans`) | **Geist** (Vercel, Google Fonts / `geist` npm) | 400, 500, 600, 700 | Crisp, neutral UI face with excellent small-size rendering for tables and 11 px tracked labels. |
| Numeric / data (`--font-mono`, new) | **Geist Mono** | 400, 500, 600 | Tabular digits for kWh, ₹, %, timestamps, IDs, confidence scores. Use `font-variant-numeric: tabular-nums`. |
| Editorial accent (landing only, optional) | **Instrument Serif** italic | 400 | One or two emphasised words in hero/section headings, e.g. "Find the *silent* loss." Never in the app. |

Load all with `next/font/google` (`Bricolage_Grotesque`, `Geist`, `Geist_Mono`, `Instrument_Serif`),
`display: "swap"`, Latin subset, and expose them as the same CSS variables so no component changes.
If the owner wants the exact original look, set `NEXT_PUBLIC_FONT_MODE=clone` → Syne + Source Sans 3 (keep both code paths).

### 3.3 Type scale (rem, at 16 px root)

| Style | Font | Size / line-height | Weight | Tracking | Where |
|---|---|---|---|---|---|
| Hero H1 | display | 3rem → 3.75 (sm) → 4.5 (md) / 0.95 | 800 | -0.025em (`tracking-tight`) | Landing hero |
| Section H2 | display | 1.875 → 2.25 (sm) | 700 | tight | Landing sections |
| Page title (`.dash-section-title`) | display | 1.65 (1.4 under 768 px) / 1.15 | 700 | -0.02em | Dashboard pages |
| Card heading (e.g. "Your plants") | display | 1.15–1.25 | 700 | -0.02em | In-page section |
| KPI value (`.dash-kpi-value`) | display (mono for SolarDoctor ₹/kWh) | 1.75 / 1.05 | 700 | -0.02em | KPI strip |
| Body | sans | 0.95–1.125 / 1.5–1.6 | 400 | 0 | Paragraphs |
| Eyebrow (`.dash-eyebrow`) | sans | 0.75 | 600 | 0.14em, UPPERCASE, muted | Above page titles |
| Card title (`.dash-card-title`) | sans | 0.72 | 600 | 0.12em, UPPERCASE, muted | Top of every card |
| KPI label | sans | 0.70 | 600 | 0.10em, UPPERCASE | KPI strip |
| Table header | sans | 0.68 | 600 | 0.08em, UPPERCASE, muted | Tables |
| Badge | sans | 0.65–0.68 | 700 | 0.06–0.08em, UPPERCASE | Severity/status |
| Landing eyebrow | display | 0.875 | 600 | 0.18em, UPPERCASE, sun | Hero kicker |

---

## 4. Surfaces, spacing, shape, motion

- **Background grid** (`.site-grid`): inline SVG data-URI, 48×48 px, 1 px `#c5cdc5` stroke on top/left edges,
  over `--paper`. Used on landing feature section, auth pages and the entire dashboard root.
- **Radius:** `2px` on everything (buttons, inputs, cards, badges, avatar, modal). Status dots: 1 px radius
  (square-ish). Spinner is the only circle.
- **Borders:** 1 px `--line`. Active nav item: 2 px left border `--sun`. Advisory: 3 px left border `--sun`.
  Active tab: 2 px bottom border `--field`.
- **Shadows:** none. (Optional for SolarDoctor modals only: `0 24px 48px -24px rgba(20,24,20,.35)`.)
- **Spacing rhythm:** 0.15 / 0.35 / 0.45 / 0.65 / 0.85 / 1 / 1.15 / 1.25 / 1.5 / 1.75 rem. Card padding
  `1.25rem 1.35rem`. Grid gaps `1.15rem` (layouts), `0.85rem` (plant cards). Section bottom margins `1.5rem`.
- **Content width:** dashboard content max `1120px`, padding `1.75rem 2rem 3.5rem`. Landing `max-w-6xl`
  (72 rem) with `px-5 sm:px-8`.
- **Motion** (`globals.css`): `rise` 0.7 s ease-out (translateY 18 px → 0, fade) with 0.12 s stagger
  (`.animate-rise`, `-delay-1..3`); `reveal-line` 0.9 s (sun rule under hero title); `pulse-dot` 2.4 s infinite
  (status dot); hover transitions 0.15 s; sidebar slide 0.25 s. Respect `prefers-reduced-motion` (SolarDoctor must add
  this media query — the original lacks it).

---

## 5. App shell (dashboard)

```
┌──────────────┬───────────────────────────────────────────────────────────┐
│ OPERATIONS   │ topbar 52px · paper 92% + blur · right: user email        │
│ SolarDoctor  ├───────────────────────────────────────────────────────────┤
│──────────────│  EYEBROW                                                  │
│ 01 Overview  │  Page title (display 1.65rem)                [Primary CTA]│
│ 02 Plants    │  Sub copy (muted)                                         │
│ 03 …         │  ┌ KPI strip: 4 cells, hairline dividers ───────────────┐ │
│              │  └──────────────────────────────────────────────────────┘ │
│              │  ┌ card (2fr) ───────────────┐ ┌ card (240px) ─────────┐  │
│              │  └───────────────────────────┘ └───────────────────────┘  │
│──────────────│  max-width 1120px, 48px survey grid behind                │
│ [P] user     │                                                           │
│ [Sign out]   │                                                           │
└──────────────┴───────────────────────────────────────────────────────────┘
 sidebar 220px fixed, field green
```

- **Sidebar** `.dash-sidebar`: 220 px, fixed, full height, `--field` bg. Header: eyebrow "OPERATIONS" (0.68 rem,
  sun, tracked) over logo text (display 1.05 rem 700). Nav items: index (display 0.75 rem, sun, 1.5 rem wide) +
  label 0.9 rem/500; hover bg `rgba(255,255,255,.06)`; active bg `rgba(255,255,255,.08)`, weight 600, 2 px sun left
  border. Footer: 32 px square sun avatar with initial (ink text), name (0.82 rem/600), role (0.72 rem, 55%),
  full-width ghost "Sign out" (border `rgba(255,255,255,.22)`).
- **Topbar** `.dash-topbar`: sticky, 52 px, `rgba(240,242,239,.92)` + `backdrop-filter: blur(8px)`, bottom hairline.
  Left: hamburger (mobile only). Right: user email (0.82 rem muted, ellipsis at 200 px).
  *SolarDoctor addition:* plant switcher (select styled as `.dash-input`, 220 px) and a global date-range control
  (Today / 7d / 30d / Custom) on the left of the right cluster; a bell with open-alert count badge.
- **Responsive:** ≤960 px — KPI strip 2×2, all split/two-col/one-third grids collapse to 1 column. ≤768 px — sidebar
  becomes an off-canvas drawer (translateX(-100%)), overlay `rgba(20,24,20,.45)`, close ✕ button, content padding
  `1.25rem 1rem 2.5rem`, title 1.4 rem, forms single column. ≤480 px — KPI strip single column.

### SolarDoctor navigation (keep the numbered style)

| # | Label | Route | Notes |
|---|---|---|---|
| 01 | Overview | `/dashboard` | Fleet KPIs, deficit chart, recent alerts, plants (clone + new KPIs) |
| 02 | Plants | `/dashboard/plants` | Clone exactly; detail adds Strings, Inspections, ROI tabs |
| 03 | Performance | `/dashboard/performance` | Expected (clear-sky/PVWatts) vs actual, deficit, soiling ratio — evolves "Forecasts" |
| 04 | Inspections | `/dashboard/inspections` | Photo upload → diagnosis → explainability (new) |
| 05 | Alerts | `/dashboard/alerts` | Clone exactly (+ "Inspect" action that opens upload pre-linked to the alert) |
| 06 | Work orders | `/dashboard/work-orders` | List + board, detail drawer (new) |
| 07 | ROI | `/dashboard/roi` | Clean / Wait / Field-check decisions in ₹ (new) |
| 08 | Map | `/dashboard/map` | Plant/string/panel map (Leaflet, ported from Axalon) |
| 09 | Reports | `/dashboard/reports` | PDF / Excel / GeoJSON exports |
| — | Settings | `/dashboard/settings` | Tariffs, cleaning cost, thresholds, users |

---

## 6. Components (clone-exact specs; class names from `dashboard.css`)

| Component | Class(es) | Spec |
|---|---|---|
| Page header | `.dash-page-header`, `.dash-page-header-row`, `.dash-eyebrow`, `.dash-section-title`, `.dash-page-sub` | Max 40 rem; row variant puts a primary CTA on the right (`justify-between`, wraps). Optional breadcrumb `.dash-breadcrumb` above ("Plants / PCCoE Rooftop"). |
| Card | `.dash-card`, `.dash-card-title`, `.dash-card-title-meta` | White, 1 px line, 2 px radius, padding 1.25/1.35 rem. Title row: tracked uppercase label left, meta (0.82 rem, field, 600) or a `.dash-badge` right. |
| KPI strip | `.dash-kpi-grid`, `.dash-kpi`, `-label`, `-value`, `-unit`, `-sub`, modifiers `-accent`/`-warning`/`-danger`/`-sun` | ONE bordered white bar, 4 equal cells separated by vertical hairlines (not 4 separate cards). Value 1.75 rem display 700; unit 0.85 rem muted sans beside it; sub-line 0.78 rem muted. |
| Plant card | `.dash-plant-grid`, `.dash-plant-card`, `-name`, `-loc`, `-stats`, `-stat-label`, `-stat-value`, `.dash-status-dot`, `.dash-status-active/inactive` | Grid `repeat(auto-fill,minmax(260px,1fr))`, gap 0.85 rem; hover border → field. Name in display with a 7 px square status dot (field = active, line = inactive). Three stat pairs: tiny uppercase label over 0.95 rem/600 value. |
| Stat rows | `.dash-stat-row`, `-label`, `-value` | Key-value list with hairline separators (weather card, config). Value right-aligned 0.88 rem/600; irradiance/UV values coloured sun. |
| Weather | `.dash-weather-temp`, `.dash-weather-meta` | Temperature in display 1.65 rem sun; condition + place muted below. "MOCK" muted badge when data is simulated. |
| Alert row | `.dash-alert-list`, `.dash-alert-row`, `.dash-alert-badge.{CRITICAL,WARNING,INFO}`, `.dash-alert-msg`, `.dash-alert-time`, `.dash-alert-actions`, `.dash-alert-resolve-btn` | Grid: badge · message (+ meta line "Plant #2 · UNDERPERFORMANCE · −14.2% shortfall · 79 / 92 kW") · time · actions; hairline between rows; buttons are tiny ghost (0.74 rem) that turn field on hover. |
| Table | `.dash-table-wrap`, `.dash-table`, `td.nowrap` | Min-width 640 px with horizontal scroll; header 0.68 rem uppercase muted; cells 0.85 rem, padding 0.75/0.85; row hover tint; numeric columns right-aligned + tabular. |
| Buttons | `.btn-primary`, `.btn-ghost` (landing); `.dash-btn` + `-primary`/`-ghost`/`-sm` (app) | Field fill / ghost hairline; 600 weight; 2 px radius; disabled 55% opacity. |
| Tabs | `.dash-tabs`, `.dash-tab.active` | Text tabs on a bottom hairline; active = field text + 2 px field underline. |
| Filter chips | `.dash-chip-row`, `.dash-chip.active` | "Open 2 · All 3 · Resolved 1": active chip filled field with white text; count inline. |
| Toolbar | `.dash-toolbar`, `.dash-toolbar-spacer` | White bar with inline labelled selects ("Plant", "Horizon", "Interval") and a right-aligned primary "Refresh". |
| Badges | `.dash-badge` + `.dash-badge-red/orange/green/muted` | 0.68 rem, 700, uppercase, tinted bg + coloured text. |
| Advisory | `.dash-advisory`, `-title`, `-body` | White box with 3 px sun left border: "Dispatch advisory — Keep 12 kW BESS headroom…" Use for every AI recommendation. |
| Forms | `.dash-form-grid`, `.dash-field(.full)`, `.dash-input`, `select.dash-input` | 2-column grid; labels 0.75 rem uppercase muted; inputs white, focus border field. Landing/auth inputs use `.input-field`. |
| States | `.dash-loading` + `.dash-spinner`, `.dash-empty`, `.dash-error` | Centered muted text, 22 px ring spinner (line + field top); error = danger-dim box. Every data card needs all three. |
| Live chip / popover | `.online-adapter-chip`, `.online-adapter-popover*` | Sun-tinted pill "● Live adjust −6.0% · DAMPING ▾" that opens a popover with metrics. Reuse the pattern for "Model status" and "Data freshness". |
| Modal | `DiagnosisModal.tsx` (inline styles) | Scrim `rgba(20,24,20,.5)`, panel max 720 px, white, 2 px radius, 90 vh scroll. Urgency colour bar; technician steps numbered; badges for category/confidence. |
| Charts | `ForecastActualChart.tsx`, `ProbabilisticBandChart.tsx` | Hand-written SVG (no chart lib): viewBox width 860, padding `{top 20, right 24, bottom 40, left 56}`, dashed gridlines, kW axis labels, legend with checkboxes to toggle series, hover crosshair + tooltip, area gradients. Min width 420 px with horizontal scroll. |

---

## 7. Page anatomy (clone these exactly, then extend)

Reference images: `reference/desk-*.webp` (1440 px) and `reference/mob-*.webp` (390 px).

1. **Landing `/`** (`desk-landing`, `mob-landing`) — absolute transparent header (logo left; Features, How it works,
   Log in, Register/Dashboard right). Full-viewport hero: photo + `rgba(10,22,16,.72)` scrim, content bottom-left:
   sun eyebrow with pulsing square dot "OPERATIONAL PROTOTYPE", giant display title, 112 px sun rule, lead paragraph
   (white 88%), primary + ghost CTA. Then **Features** on survey grid: eyebrow, H2, intro, numbered list `01–04`
   with hairline separators (index column 5 rem). Then **How it works** on white: vertical timeline with square
   numbered markers on a left hairline (5 steps). Footer: field green, logo + blurb left, links right.
2. **Auth `/login`, `/register`** (`desk-login`, `desk-register`) — survey grid, logo top-left, centred 28 rem
   column: display H1, muted sub, labelled inputs, full-width primary button, status/alert messages, cross-link.
3. **Overview `/dashboard`** (`desk-overview`, `mob-overview`) — header; KPI strip (Active plants `2/3`, Total
   capacity in sun, Open alerts in danger, Forecast records); split row: Yield forecast card (plant select, live chip,
   "Forecast detail →" ghost, chart) + Current weather card (240 px); Recent alerts card; "Your plants" heading with
   "Add plant" primary + plant grid.
4. **Plants `/dashboard/plants`** + **New plant** (`desk-plants`, `desk-plant-new`) — grid of plant cards; form
   with 2-column fields (name, location, lat/long, timezone, capacity, inverter capacity, module count).
5. **Plant detail `/dashboard/plants/[id]`** (`desk-plant-detail`, `mob-plant-detail`) — breadcrumb, eyebrow
   "PLANT DETAIL", name with status dot, location · timezone, "Run forecast" primary; KPI strip (DC capacity, Inverter
   cap, Predicted yield, Open alerts); chart card + live weather card; Configuration (stat grid) + Alerts cards.
6. **Forecasts `/dashboard/forecasts`** (`desk-forecasts`) — header with live chip; tabs (Probabilistic & ramp ·
   Online learning · Point history); toolbar; KPI strip (Ramp risk HIGH, Peak ramp, Mean uncertainty, BESS reserve);
   advisory; uncertainty ribbon chart; "Interval schedule" table with risk badges and a "High & critical only"
   checkbox.
7. **Alerts `/dashboard/alerts`** (`desk-alerts`) — tabs (Alert log (n open) · Fault sandbox); chip filters
   (Open/All/Resolved); alert list with "Diagnose" + "Resolve"; DiagnosisModal.

---

## 8. New SolarDoctor screens (designed in the same language)

### 8.1 Inspections `/dashboard/inspections` and `/dashboard/inspections/[id]`
- **List:** KPI strip (Inspections this month · Reversible issues · Irreversible issues · Avg confidence) + table
  (thumbnail 48 px square, plant/string, predicted class chip, confidence bar, severity badge, linked alert, date,
  status).
- **New inspection (upload):** dashed 1 px `--line` dropzone on white (min 220 px tall), "Drop a panel photo or
  browse" (accepts JPG/PNG/HEIC, ≤ 15 MB, multiple). Optional selects: Plant, String, Linked alert. Camera capture on
  mobile (`capture="environment"`). Show per-file progress rows.
- **Result / detail:** two-column `dash-one-third`:
  - Left (2fr): **Evidence viewer** — the photo with overlay toggles as text tabs: `Original · LIME · Grad-CAM ·
    Side-by-side`; opacity slider (0–100, default 45) for heatmaps; "Press and hold to see original"; LIME shows the
    top-k superpixels outlined in sun with a k selector (3/5/8). Caption under the image: "Highlighted regions drove
    the *Dusty* prediction."
  - Right (1fr): **Diagnosis card** — class chip (class colour), confidence as display number "92%" with a
    10-segment bar, top-3 probabilities list, "Reversible / Irreversible" badge, **recommended action**
    (Clean · Spot-clean · Wait · Field check · Replace) in an advisory box, and a **"Needs field check"** state when
    confidence < 0.6 or the image fails the "is this a solar panel?" check (show the OOD reason).
  - Below: **Cross-check with performance** card — the deficit at the time of the photo (chart snippet of expected
    vs actual for that string ±3 days) and a verdict line: "Telemetry agrees: −11.8% under clear sky since 21 Oct" or
    "Telemetry disagrees: no deficit — likely cosmetic." This is SolarDoctor's signature component.
  - Footer actions: primary "Create work order", ghost "Mark as false positive", ghost "Download evidence PDF".

### 8.2 Performance `/dashboard/performance`
- Toolbar: Plant · String/Inverter · Range · Baseline (`Clear-sky (Ineichen)` / `PVWatts from NASA POWER` /
  `Hybrid ML`).
- KPI strip: Performance ratio · Energy deficit (kWh) · Soiling ratio (RdTools SRR) · Recoverable ₹ / month.
- Main chart: expected vs actual with **deficit ribbon** shaded `--sev-critical` 14%, clear-sky periods marked by a
  thin sun strip along the x-axis, rain events as small blue ticks, cleaning events as field flags.
- Secondary: string peer-comparison table (each string's normalised yield vs plant median, sparkline column,
  deficit badge), and a soiling-ratio line chart with cleaning/rain markers.

### 8.3 Work orders `/dashboard/work-orders`
- Toggle (text tabs): `List · Board`. Board columns = Open · Assigned · In progress · Resolved (· Stale), hairline
  column separators, cards are `.dash-card` with priority badge, title, plant/string, due date, assignee initial
  square (sun), class chip, ₹ at stake (mono).
- Detail = right drawer (420 px, white, left hairline): status stepper, priority, assignee, SLA due, linked alert +
  inspection (thumbnails), technician steps checklist, before/after photo slots, comments, and **"Verify fix"** which
  shows yield recovery after the job (expected vs actual 3 days before vs after).

### 8.4 ROI `/dashboard/roi`
- Settings strip (inline form): tariff ₹/kWh (presets: Utility PPA ₹2.6 · C&I ₹6.5 · Residential ₹8), cleaning cost
  per MW or per module, water per clean (L/module), labour hours.
- Decision table per string: recoverable kWh/day, ₹/day, days-to-payback of a clean, decision chip **CLEAN NOW**
  (field) / **WAIT** (low) / **FIELD CHECK** (high) / **REPLACE** (critical), reason text.
- Summary advisory: "Cleaning strings S-04 and S-07 recovers ≈ ₹1,240/week; skip S-02 (rain forecast in 2 days)."
- Water saved vs calendar cleaning counter (display number, litres).

### 8.5 Map `/dashboard/map`
- Leaflet map, muted tile style (CARTO Positron or Esri World Imagery toggle), plant pins as squares; zoom to
  string/panel grid (ported from Axalon `ParkMapGrid`/`AnomalyMap`), panels coloured by worst open issue severity,
  side drawer on click. Legend in a white card bottom-left.

### 8.6 Reports `/dashboard/reports`
- Table of generated reports (type, plant, period, created, size) + "Generate report" form (PDF / Excel / GeoJSON).

---

## 9. Imagery and iconography

- **Photos:** self-host in `frontend/public/images/` (never hotlink). Use real, licensed solar photography
  (Unsplash or Pexels licence), each recorded in `docs/IMAGE_CREDITS.md` with author + URL. Needed set:
  hero (wide utility array at golden hour — the original uses Unsplash photo `1509391366360-2e959784a276`),
  rooftop array (Indian rooftop if available), close-up of a dusty panel, technician cleaning panels, drone over an
  array. Treat all photos with the same scrim (`rgba(10,22,16,.72)`) or a subtle green-tinted duotone so they share
  one mood. Export AVIF/WebP, `next/image` with `sizes`.
- **Do not** put Kaggle dataset images on public marketing pages (dataset licence is "Unknown").
- **Illustrations:** simple line drawings in `--field` 1.5 px stroke (panel grid, sun, drone, droplet) for empty
  states; one per empty state.
- **Icons:** the original uses text glyphs (☰ ✕ → ▾). SolarDoctor may add **lucide-react** at `size=16`,
  `strokeWidth=1.75`, colour `currentColor`, only where they add meaning (upload, camera, map pin, download, bell,
  check, alert-triangle). Never decorative icon soup.
- **Logo:** wordmark only, display face: "Solar**Doctor**" with "Doctor" in sun on dark surfaces and field on paper.
  Optional mark: a 12 px square sun with a 1 px field cross (a panel cell). Favicon from the mark.

---

## 10. Content and voice

- Plain, operational, precise. Numbers first, then meaning: "−14.2% vs clear sky · 3 h · string S-04".
- Always show **units** (kW, kWh, ₹, %, W/m², °C) and **data provenance** badges: `MOCK`, `NASA POWER`,
  `PVDAQ`, `LIVE`, `MODEL v1.3`.
- AI output is always framed as a recommendation with confidence and a "why" (evidence) — never as a fact.
- Indian formatting for currency: `₹1,24,500` (use `Intl.NumberFormat('en-IN', {style:'currency',currency:'INR'})`).
  Dates `4 Nov 2026, 11:30` in the plant's timezone.

---

## 11. Accessibility and quality bar

- WCAG 2.2 AA contrast. Measured: `--sun` (#c9852a) on white is 3.06:1 → large text (≥ 24 px, or ≥ 18.7 px bold)
  and accents only; for small sun text on white/paper use `#9a6118` (5.13:1, add as `--sun-ink`). Sun on field
  green is 4.08:1 — fine for the 0.68–0.75 rem *bold uppercase* sidebar labels only if bumped to ≥ 14 px bold; otherwise
  use `#e0a24a`. Muted `#5c665c` passes on paper (5.31:1) and white (5.98:1).
- Visible focus ring: `outline: 2px solid var(--field); outline-offset: 2px` on all interactive elements.
- All severity/class colours paired with text. Charts have a text summary and an accessible data table toggle.
- Keyboard: sidebar, tabs, chips, dropzone, modal (focus trap + Esc), drawer.
- Mobile at 390 px: no horizontal page scroll except inside `.dash-table-wrap` and charts.
- Every data component ships with loading, empty and error states (see §6 "States").

---

## 12. Implementation map (copy these files first, then extend)

| Original file (SolarPulseAI `frontend/`) | Destination in solar-doctor `frontend/` | Action |
|---|---|---|
| `src/app/globals.css` | same | Copy verbatim, then append SolarDoctor tokens (§2.2), `--font-mono`, reduced-motion rule, focus ring, `--sun-ink`. |
| `src/app/dashboard/dashboard.css` | same | Copy verbatim; add new component classes in a separate `solardoctor.css` imported after it (do not edit originals so diffs stay reviewable). |
| `src/app/layout.tsx` | same | Swap fonts per §3.2 behind `FONT_MODE`. Update metadata to SolarDoctor. |
| `src/app/page.tsx`, `src/components/landing/*` | same | Copy; rewrite copy for SolarDoctor (detect → diagnose → explain → act); swap hero photo. |
| `src/app/(auth)/*`, `src/components/auth/*` | same | Copy; point to SolarDoctor auth endpoints. |
| `src/app/dashboard/DashboardShell.tsx`, `layout.tsx` | same | Copy; replace `navItems` with §5 nav; add topbar plant switcher + bell. |
| `src/app/dashboard/page.tsx`, `plants/**`, `alerts/page.tsx`, `forecasts/page.tsx` | same (forecasts → `performance/`) | Copy, re-wire to SolarDoctor API. |
| `src/components/forecast/*`, `src/components/diagnosis/DiagnosisModal.tsx` | same | Copy; extend chart with deficit ribbon + markers. |
| `src/lib/api.ts` | `src/lib/api/*` | Replace with a typed client generated from the backend OpenAPI schema (`openapi-typescript`). |

Licence: SolarPulseAI is MIT — keep its copyright notice in `THIRD_PARTY_NOTICES.md`.

---

## 13. Do / Don't

**Do:** hairlines, square corners, tracked micro-labels, numbered nav, big display numbers, one sun accent per
view, survey grid behind the app, advisories for AI recommendations, provenance badges.

**Don't:** rounded-2xl cards, drop shadows, gradients on UI chrome, purple/blue "AI" palettes, emoji, glassmorphism,
more than one accent colour per card, chart libraries with their default styling, icons without labels, red heatmaps
that collide with severity colours.
