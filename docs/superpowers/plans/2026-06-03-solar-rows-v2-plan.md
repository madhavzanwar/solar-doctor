# Implementation Plan — Solar Row Mode v2

**Spec:** `docs/superpowers/specs/2026-06-03-solar-rows-v2-design.md`
**Goal:** Replace the wrong v1 solar mode. New flow: draw **area** (polygon) → set **Row Angle α / Drone Orientation / Gimbal Tilt** → **"Select solar rows"** click-mode → for each clicked row, a line at α clipped to the area, photo waypoints, serpentine-connected.
**All frontend** (`website/nextjs`). Ship via `git push origin main` (Vercel auto-deploys). Tests = `cd website/nextjs && npm test`; typecheck = `npx tsc --noEmit`.

> Session note: the repo's GateGuard hook fact-forces every Edit/Write + first Bash. Consider asking the user to disable `pre:edit-write:gateguard-fact-force` + `pre:bash:gateguard-fact-force` via `ECC_DISABLED_HOOKS` at session start.

## Phase 1 — Geometry (`lib/missionGeometry.ts`) + tests  ← do first, commit
1. `MissionParams`: add `rowAngleDeg?: number` (α, default 0) and `droneHeadingDeg?: number | 'auto'` (default 'auto'). (`gimbalPitchDeg` already exists.)
2. **Replace** `generateSolar`. New signature:
   ```ts
   export function generateSolar(area: LatLon[], rowCenters: LatLon[], params: MissionParams): Waypoint[]
   ```
   Algorithm (reuse existing `centroid`, `toXY`, `toLatLon`, `rotate`, `scanLineIntersections`, `withTravelHeadings`):
   - guard: `area.length < 3 || rowCenters.length < 1` → `[]`.
   - `origin = centroid(area)`; `aRad = (rowAngleDeg ?? 0) * Math.PI/180` (CCW-from-east tilt; α = angle with horizontal/east).
   - `rotArea = area.map(p => rotate(toXY(p, origin), -aRad))`.
   - For each row center: `rc = rotate(toXY(c, origin), -aRad)`; `xs = scanLineIntersections(rotArea, rc.y)`; if `xs.length < 2` skip; endpoints `{x:xs[0], y:rc.y}` & `{x:xs[xs.length-1], y:rc.y}`. Keep `{y: rc.y, e1, e2}`.
   - Sort rows ascending by `y`; serpentine: `dir` alternates `[e1,e2]` vs `[e2,e1]`; push to `surveyXY`.
   - `survey = surveyXY.map(p => toLatLon(rotate(p, aRad), origin))`.
   - Build `Waypoint[]`: first point = home (no separate home point — same as the v1 fix); set `alt = altitudeM`, `gimbalPitch = gimbalPitchDeg ?? -90`.
   - Headings: if `typeof droneHeadingDeg === 'number'` set every `heading = droneHeadingDeg`; else `withTravelHeadings(wps)`.
3. Tests `tests/unit/solarGimbal.test.ts` (extend): clipped endpoints lie within the area bbox; `rows×2` waypoints; α changes endpoint orientation; gimbal stamped; empty area/rows → `[]`.
4. **Commit** (`feat(plan): solar v2 geometry — clip row lines to area at row angle α`).

## Phase 2 — PlanTab wiring (`components/Platform/PlanTab.tsx`)
1. `DEFAULT_PARAMS`: add `rowAngleDeg: 0, droneHeadingDeg: 'auto'`.
2. State: `const [solarRows, setSolarRows] = useState<LatLon[]>([])`; `const [selectingRows, setSelectingRows] = useState(false)`.
3. `waypoints` memo solar branch → `base = (polygon && polygon.length >= 3 && solarRows.length >= 1) ? generateSolar(polygon, solarRows, params) : []` (remove the v1 `generateSolar([polygon[0],polygon[1]], polygon.slice(2), params)`). Add `solarRows` to deps.
4. `handleShapeDrawn` for solar: keep drawing the **area** as `polygon` (polygon tool). When the area is (re)drawn, optionally `setSolarRows([])`.
5. Pass to `PlanMap`: `solarRows`, `selectingRows`, `onSolarRowsChange={setSolarRows}`. Pass to `PlanSidebar`: `selectingRows`, `onToggleSelectRows={() => setSelectingRows(v=>!v)}`, `solarRowCount={solarRows.length}`, `onClearRows={() => setSolarRows([])}`.

## Phase 3 — PlanMap (`components/Platform/PlanMap.tsx`)
1. **Draw tool:** change so solar uses **polygon** (the area), not polyline:
   `const tool = missionType === 'corridor' ? 'polyline' : missionType === 'orbit' ? 'marker' : 'polygon'` (i.e. remove `|| missionType==='solar'`).
2. Props: add `solarRows?: LatLon[]`, `selectingRows?: boolean`, `onSolarRowsChange?: (rows: LatLon[]) => void`.
3. Refs/layer: `rowsLayerRef` (LayerGroup, created in init). `rowsRef = useRef<LatLon[]>([])` mirroring `solarRows`.
4. Click-mode effect (pattern = the Measure tool already in this file): when `selectingRows`, `map.on('click', onClick)` appends `{lat,lon}` to `rowsRef` and calls `onSolarRowsChange([...rowsRef.current])`; cleanup `map.off`. (Beware: leaflet-draw polygon drawing also uses clicks — only enable row-clicks when NOT actively drawing; acceptable to require the user to finish the area first.)
5. Render effect on `solarRows`: clear `rowsLayerRef`, draw a **blue dot** (`L.circleMarker(..., {radius:4,color:'#2563eb',fillOpacity:1})`) per row.
6. Keep the generated lines rendering via the existing `waypoints` path effect (no change).

## Phase 4 — PlanSidebar (`components/Platform/PlanSidebar.tsx`)
1. Props: `selectingRows: boolean`, `onToggleSelectRows: () => void`, `solarRowCount: number`, `onClearRows: () => void`.
2. Solar section (show when `missionType === 'solar'`): a **"Select solar rows"** toggle button (primary when active) + `{solarRowCount} rows · Clear`; sliders **Row Angle α** (0–180, `rowAngleDeg`), **Drone Orientation** (0–359 `droneHeadingDeg` + Auto toggle like α), **Gimbal Tilt** (reuse `gimbalPitchDeg`, 0=horizon).
3. Update the Mission hint for solar to: "Draw the area, set the row angle, then Select solar rows and click each row."
4. The grid-only "Panel row angle α" control stays for grid; solar uses its own Row Angle.

## Phase 5 — Verify + ship
1. `npm test` (extend solar tests green) + `npx tsc --noEmit` clean.
2. Commit + `git push origin main`; poll `vercel ls axalon-systems` to Ready; `curl -I https://axalonsystems.com/platform`.
3. Manual check: grid still works; solar = draw area → Select rows → click rows → path appears clipped at α; exports carry gimbal/heading.
4. Update memory `mission_planner_roadmap.md` (mark solar v2 shipped, supersedes v1).

## Files touched
`lib/missionGeometry.ts`, `tests/unit/solarGimbal.test.ts`, `components/Platform/PlanTab.tsx`, `components/Platform/PlanMap.tsx`, `components/Platform/PlanSidebar.tsx`.

## Reference for the next session
Live now: planner with grid/perimeter/corridor/orbit/solar(v1-wrong), α readout, gimbal slider, battery split, re-inspect, map tools, analytics Overview tab. Backend HF (pw `axalon1234`) + Supabase (GH Actions `db-migrate.yml` auto-applies migrations). See memories `mission_planner_roadmap`, `cloud_deploy_progress`.
