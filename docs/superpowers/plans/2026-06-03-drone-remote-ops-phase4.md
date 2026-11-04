# Drone Remote Ops — Phase 4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the incrementally-grown Live Ops tab into a cohesive cockpit — a live Leaflet map with a heading-rotated drone marker and a breadcrumb trail, arranged with the telemetry HUD, command bar, and video into one intentional layout.

**Architecture:** Phases 1–3 left the map as a placeholder (`<p>` showing lat/lon) and stacked the HUD/commands/video ad hoc. Phase 4 adds a real `LiveMap` (reusing the mission planner's Leaflet dynamic-import pattern), a pure track buffer for the breadcrumb, and a deliberate cockpit grid layout + CSS. No backend changes.

**Tech Stack:** Next.js + Leaflet (reused from `PlanMap.tsx`) + `vitest`. No new deps, no Python.

**Spec:** `docs/superpowers/specs/2026-06-03-drone-remote-operations-design.md` (Phase 4: cockpit UI).
**Depends on:** Phases 1–3 plans implemented (`liveOps.ts`, `LiveOpsTab.tsx`, `VideoPanel.tsx`).

---

## Conventions
- Frontend tests: `cd website/nextjs && npx vitest run <file>`. Build: `npm run build`.
- Commit after every green step. Match `PlanMap.tsx` for Leaflet usage.

---

## Task 1: Pure breadcrumb track buffer

**Files:**
- Create: `website/nextjs/lib/track.ts`
- Test: `website/nextjs/tests/unit/track.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// website/nextjs/tests/unit/track.test.ts
import { describe, it, expect } from "vitest";
import { appendTrackPoint, type LatLon } from "@/lib/track";

describe("appendTrackPoint", () => {
  it("appends a point", () => {
    const t = appendTrackPoint([], { lat: 1, lon: 2 }, 100);
    expect(t).toEqual([{ lat: 1, lon: 2 }]);
  });

  it("caps the buffer at maxLen (drops oldest)", () => {
    let t: LatLon[] = [];
    for (let i = 0; i < 5; i++) t = appendTrackPoint(t, { lat: i, lon: 0 }, 3);
    expect(t.map((p) => p.lat)).toEqual([2, 3, 4]);
  });

  it("skips a near-duplicate consecutive point (<~0.5m)", () => {
    const t1 = appendTrackPoint([], { lat: 28.4, lon: 77.1 }, 100);
    const t2 = appendTrackPoint(t1, { lat: 28.4000001, lon: 77.1000001 }, 100);
    expect(t2.length).toBe(1); // negligible move ignored
  });

  it("keeps a meaningful move", () => {
    const t1 = appendTrackPoint([], { lat: 28.4, lon: 77.1 }, 100);
    const t2 = appendTrackPoint(t1, { lat: 28.401, lon: 77.1 }, 100);
    expect(t2.length).toBe(2);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd website/nextjs && npx vitest run tests/unit/track.test.ts`
Expected: FAIL — cannot resolve `@/lib/track`

- [ ] **Step 3: Write `website/nextjs/lib/track.ts`**

```ts
// website/nextjs/lib/track.ts
// Pure breadcrumb buffer for the live map. Immutable: returns a new array.
// Drops the oldest point past maxLen and skips negligible jitter so the polyline
// stays smooth and bounded.

export interface LatLon { lat: number; lon: number }

const MIN_MOVE_M = 0.5;

function metersBetween(a: LatLon, b: LatLon): number {
  const R = 6_371_000;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLon = ((b.lon - a.lon) * Math.PI) / 180;
  const lat1 = (a.lat * Math.PI) / 180;
  const lat2 = (b.lat * Math.PI) / 180;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function appendTrackPoint(
  track: LatLon[],
  point: LatLon,
  maxLen: number
): LatLon[] {
  const last = track[track.length - 1];
  if (last && metersBetween(last, point) < MIN_MOVE_M) return track;
  const next = [...track, point];
  return next.length > maxLen ? next.slice(next.length - maxLen) : next;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd website/nextjs && npx vitest run tests/unit/track.test.ts`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add website/nextjs/lib/track.ts website/nextjs/tests/unit/track.test.ts
git commit -m "feat(web): pure breadcrumb track buffer"
```

---

## Task 2: LiveMap component (drone marker + breadcrumb + follow)

**Files:**
- Create: `website/nextjs/components/Platform/LiveMap.tsx`

No unit test (Leaflet DOM); validated visually. **Read `website/nextjs/components/Platform/PlanMap.tsx` first** and copy its dynamic-import / `ssr:false` / Leaflet-icon setup exactly.

- [ ] **Step 1: Read the existing map pattern**

Read `PlanMap.tsx`: note how it imports Leaflet under a client-only wrapper, how it
sets up the default marker icon, and how it fits bounds.

- [ ] **Step 2: Create `LiveMap.tsx`**

```tsx
// website/nextjs/components/Platform/LiveMap.tsx
"use client";

import { useEffect, useRef } from "react";
import type { LatLon } from "@/lib/track";

// Leaflet is loaded client-side only (same approach as PlanMap.tsx).
interface Props {
  position: LatLon | null;
  headingDeg: number;
  track: LatLon[];
  follow?: boolean;
}

export default function LiveMap({ position, headingDeg, track, follow = true }: Props) {
  const mapRef = useRef<any>(null);
  const markerRef = useRef<any>(null);
  const lineRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // init map once
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const L = (await import("leaflet")).default;
      await import("leaflet/dist/leaflet.css");
      if (cancelled || !containerRef.current || mapRef.current) return;
      const map = L.map(containerRef.current).setView([20, 0], 2);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap",
        maxZoom: 19,
      }).addTo(map);
      mapRef.current = map;
    })();
    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  // update marker + breadcrumb on telemetry
  useEffect(() => {
    if (!mapRef.current || !position) return;
    (async () => {
      const L = (await import("leaflet")).default;
      const map = mapRef.current;
      const latlng: [number, number] = [position.lat, position.lon];

      // rotated drone marker via a divIcon (▲ rotated to heading)
      const icon = L.divIcon({
        className: "live-drone-marker",
        html: `<div style="transform:rotate(${headingDeg}deg)">▲</div>`,
        iconSize: [24, 24],
        iconAnchor: [12, 12],
      });
      if (!markerRef.current) {
        markerRef.current = L.marker(latlng, { icon }).addTo(map);
      } else {
        markerRef.current.setLatLng(latlng);
        markerRef.current.setIcon(icon);
      }

      const pts = track.map((p) => [p.lat, p.lon] as [number, number]);
      if (!lineRef.current) {
        lineRef.current = L.polyline(pts, { color: "#14b8a6", weight: 2 }).addTo(map);
      } else {
        lineRef.current.setLatLngs(pts);
      }

      if (follow) map.panTo(latlng, { animate: true });
      if (map.getZoom() < 15) map.setView(latlng, 17);
    })();
  }, [position, headingDeg, track, follow]);

  return <div ref={containerRef} className="live-map" />;
}
```

- [ ] **Step 3: Commit**

```bash
git add website/nextjs/components/Platform/LiveMap.tsx
git commit -m "feat(web): live map with heading-rotated drone marker + breadcrumb"
```

---

## Task 3: Integrate map + track into LiveOpsTab

**Files:**
- Modify: `website/nextjs/components/Platform/LiveOpsTab.tsx`

- [ ] **Step 1: Add a dynamic (ssr:false) import + track state**

At the top of `LiveOpsTab.tsx`:

```tsx
import dynamic from "next/dynamic";
import { appendTrackPoint, type LatLon } from "@/lib/track";

const LiveMap = dynamic(() => import("@/components/Platform/LiveMap"), { ssr: false });
const MAX_TRACK = 500;
```

Add track state and accumulate it from telemetry. Replace the `onTelemetry: setTelem`
handler with one that also appends to the track:

```tsx
  const [track, setTrack] = useState<LatLon[]>([]);
  // ...in connectLiveOps handlers:
      onTelemetry: (t) => {
        setTelem(t);
        setTrack((cur) => appendTrackPoint(cur, { lat: t.lat, lon: t.lon }, MAX_TRACK));
      },
```

- [ ] **Step 2: Replace the placeholder `<p className="liveops-pos">` with the map**

```tsx
      <LiveMap
        position={telem ? { lat: telem.lat, lon: telem.lon } : null}
        headingDeg={telem?.heading_deg ?? 0}
        track={track}
      />
```

- [ ] **Step 3: Verify build**

Run: `cd website/nextjs && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add website/nextjs/components/Platform/LiveOpsTab.tsx
git commit -m "feat(web): wire live map + breadcrumb into Live Ops tab"
```

---

## Task 4: Cockpit layout + CSS

**Files:**
- Modify: `website/nextjs/app/globals.css` (or the platform stylesheet the other tabs use — check where `.liveops-*` would live)
- Modify: `website/nextjs/components/Platform/LiveOpsTab.tsx` (apply the grid wrapper)

- [ ] **Step 1: Add cockpit styles**

Append to the platform stylesheet (use the existing design tokens — teal accent
`#14b8a6`, the same surface/border vars the other tabs use; inspect a sibling
component for the exact token names):

```css
/* Live Ops cockpit */
.liveops {
  display: grid;
  grid-template-columns: 1fr 360px;
  grid-template-rows: auto 1fr;
  grid-template-areas:
    "hud hud"
    "map side";
  gap: 12px;
  height: calc(100vh - 120px);
}
.liveops-hud {
  grid-area: hud;
  display: flex; flex-wrap: wrap; gap: 16px;
  padding: 10px 14px;
  background: var(--surface, #0f1720);
  border: 1px solid var(--border, #1f2a37);
  border-radius: 10px;
  font-variant-numeric: tabular-nums;
}
.live-map { grid-area: map; min-height: 320px; border-radius: 10px; overflow: hidden; }
.liveops-side {
  grid-area: side;
  display: flex; flex-direction: column; gap: 12px; overflow-y: auto;
}
.liveops-control, .liveops-commands { display: flex; flex-wrap: wrap; gap: 8px; }
.liveops-commands button:disabled { opacity: .4; cursor: not-allowed; }
.live-drone-marker { color: #14b8a6; font-size: 20px; line-height: 24px; text-align: center; }
.ack-ok { color: #34d399; } .ack-fail { color: #f87171; }
.video-panel-feed { width: 100%; border-radius: 8px; background: #000; aspect-ratio: 16/9; }

@media (max-width: 900px) {
  .liveops { grid-template-columns: 1fr; grid-template-areas: "hud" "map" "side"; height: auto; }
}
```

- [ ] **Step 2: Wrap the side controls in `LiveOpsTab.tsx`**

Group the control bar, command bar, ack line, and `VideoPanel` inside a
`<div className="liveops-side">…</div>` so the grid areas line up. The HUD stays
`.liveops-hud`; the map is `.live-map` (from `LiveMap`).

- [ ] **Step 3: Verify build + visual check**

Run: `cd website/nextjs && npm run build`
Then `npm run dev`, open `/platform` → Live Ops with relay+agent (SITL + test
pattern) running. Confirm: HUD across the top, map left, controls+video right;
mobile collapses to a single column. Resize to 375/768/1440 — no overflow.

- [ ] **Step 4: Commit**

```bash
git add website/nextjs/app/globals.css website/nextjs/components/Platform/LiveOpsTab.tsx
git commit -m "feat(web): cockpit grid layout + styling for Live Ops"
```

---

## Self-Review Notes (resolved)
- **Spec coverage (Phase 4):** real live map with heading marker + breadcrumb (Tasks 1–3),
  cohesive cockpit layout integrating HUD + commands + video (Task 4). Telemetry/command/video
  behavior is unchanged from Phases 1–3 — this phase is purely the cockpit surface. ✔
- **Reuse:** `LiveMap` follows the existing `PlanMap.tsx` Leaflet pattern (Task 2 Step 1 mandates
  reading it); track buffer is a new pure util, fully tested. ✔
- **Responsive:** grid collapses to single column ≤900px (matches the platform's mobile breakpoint
  noted in CLAUDE.md). ✔
- **No placeholders:** the only deliberately-unfixed value is the exact CSS token names, which the
  engineer is told to read from a sibling component. ✔
```
