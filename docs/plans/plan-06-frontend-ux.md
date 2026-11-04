# Plan 06 — Frontend UX Improvements
**Priority:** P2 | **Effort:** Medium
**Goal:** Targeted improvements to the Next.js platform UI; no architectural changes.

---

## Current Platform UI

`/platform` has 10 tabs:
1. Operations — batch inspection upload
2. Inspect — single pair
3. History — past inspections table
4. Park Map — grid + fault heatmap
5. Diff — compare two inspections
6. Plan — mission planner (Leaflet map)
7. Overview — analytics dashboard
8. Live Ops — drone telemetry
9. Assets — projects/sites/missions
10. (Settings)

`/track` — password-gated workspace for notes, files, inventory

---

## Improvement Areas

### 1. Loading States — `Skeleton.tsx`

**Problem:** Several tabs show a blank white area while data loads. The `Skeleton.tsx` component exists but is inconsistently applied.

**Fix:** Audit every `fetch` call in Platform components. Where data is loading, render `<Skeleton rows={n} />` instead of nothing. Specifically:
- `HistoryTab.tsx` — table rows
- `OverviewTab.tsx` — stat cards
- `AssetsTab.tsx` — project list

### 2. Error Boundaries

**Problem:** If a fetch throws, the entire tab crashes (white screen).

**Fix:** Add a reusable `ErrorBanner` component:

```tsx
// components/Platform/ErrorBanner.tsx
export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="ax-error-banner">
      <span>{message}</span>
      {onRetry && <button onClick={onRetry}>Retry</button>}
    </div>
  )
}
```

Wrap the data-fetching area of each tab in a try/catch that renders `<ErrorBanner>` on failure.

### 3. Toast Notifications — Improve Visibility

**Problem:** The `Toast` component exists but success toasts disappear too quickly (2s) and error toasts don't stand out.

**Fix in `Toast.tsx`:**
- Success toasts: 3s duration
- Error toasts: 6s duration + red border
- Add `role="alert"` for accessibility

### 4. OverviewTab — Empty State

**Problem:** When there are no parks, `OverviewTab` shows nothing.

**Fix:** Add an empty state illustration and a CTA:

```tsx
if (parks.length === 0) {
  return (
    <div className="ax-empty-state">
      <p>No parks yet. Upload your first batch inspection to get started.</p>
      <button onClick={() => onTabChange('operations')}>Go to Operations</button>
    </div>
  )
}
```

### 5. PlanTab — Mission Save Confirmation

**Problem:** When saving a mission plan, there is no visible confirmation that the save succeeded.

**Fix:** Call `toast.success("Mission saved")` after a successful POST to `/missions`.

### 6. HistoryTab — Sortable Columns

**Problem:** The inspection history table is fixed-order (most recent first) with no way to sort.

**Fix:** Add client-side sort to `HistoryTab.tsx`:
- Columns: Date, Park, Faults (total), CRITICAL count
- Clicking a column header toggles ascending/descending
- Use `useState` for `{ column, direction }` sort state
- Filter via `.sort()` on the inspections array

### 7. Mobile Responsiveness — Platform Shell

**Problem:** The rail navigation + content area don't handle narrow viewports well.

**Fix:**
- Below 768px: hide rail labels, show icons only
- Below 480px: move rail to bottom (tab bar style)
- Add `aria-label` to all rail buttons

---

## Implementation Order

1. `ErrorBanner.tsx` — unblocks all tab fixes
2. Loading states (Skeleton) — apply to HistoryTab + OverviewTab + AssetsTab
3. Toast improvements
4. Empty state in OverviewTab
5. PlanTab save confirmation
6. HistoryTab sort
7. Mobile rail

---

## Done When

- [ ] No tab shows a blank white screen during loading or on error
- [ ] `ErrorBanner` component exists and is used by at least 3 tabs
- [ ] Toast durations updated (3s success, 6s error)
- [ ] OverviewTab has empty state
- [ ] HistoryTab columns are sortable
- [ ] Platform shell readable at 480px viewport width
