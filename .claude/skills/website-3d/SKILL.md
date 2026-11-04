---
name: website-3d
description: Use when working on the marketing site's scroll-driven 3D scene in website/nextjs — the single React Three Fiber Canvas, the zero-rerender scrollStore pattern, the 6 scenes, CameraRig, and the 700vh scroll layout. Read before adding scenes or scroll behavior.
---

# Website 3D Scene (React Three Fiber, scroll-driven)

The marketing site (`app/(site)/page.tsx`) is a **700vh scroll container** with one fixed `<Canvas>` and 6 scenes the camera flies through.

## Zero-rerender scroll pattern (critical)
- `scrollStore.ts` is a **plain module singleton** mutated by the `window.scroll` handler: `scrollStore.progress` (0→1), `scrollStore.raw` (px).
- R3F reads it **inside `useFrame`** — never via React state. **Do not add `useState`/`useEffect` in the hot path**; it causes re-renders and jank.

## Architecture
- Single `<Canvas>`: `components/Scene/MainScene.tsx` (lighting, Stars, SolarField, Drone, CameraRig, Bloom).
- `SceneController.tsx` (inside Canvas) maps `progress` → per-scene `[0,1]` for the 6 scenes; fades components in/out. No re-renders.
- `CameraRig.tsx` — `CatmullRomCurve3` path (6 waypoints), scroll → camera position, FOV breathing.
- Scenes: `SolarField` + `Drone` (1), `ThermalScan` (2), `DetectionBoxes` (3), `DroneFleet` (4), `HologramPanel` (5), `CTAEffect` (6).
- HTML overlays (outside Canvas): `components/UI/*` + `LeftPanel.tsx` (translated by scroll, no RAF/state).

## Scroll layout zones (`app/(site)/page.tsx`)
| Zone | Range | Layout |
|------|-------|--------|
| Hero | 0–100vh | full-width canvas |
| Split | 100–500vh | 40% left panel / 60% canvas (4 sections) |
| CTA | 500–700vh | full-width canvas |
Mobile ≤900px: single column, no split.

## Gotchas
- One Canvas for all scenes — never teardown/remount between scenes; toggle visibility in `SceneController`.
- `SolarField` is instanced (396 panels, 1 draw call) — keep it instanced.
- Animate compositor-friendly props; keep the `useFrame` loop allocation-free.
- `DynamicMainScene.tsx` / `DynamicCursor.tsx` are `ssr:false` wrappers — keep R3F out of SSR.
