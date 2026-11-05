"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { alertsApi, plantsApi, type Alert, type Plant } from "@/lib/api";
import { useScope, type RangeKey } from "./scope";

const RANGES: { key: RangeKey; label: string }[] = [
  { key: "today", label: "Today" },
  { key: "7d", label: "7d" },
  { key: "30d", label: "30d" },
  { key: "custom", label: "Custom" },
];

/** Plant switcher, date range and notification bell for the dashboard topbar (DESIGN.md §5). */
export function TopbarControls() {
  const scope = useScope();
  const [plants, setPlants] = useState<Plant[]>([]);
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [open, setOpen] = useState(false);
  const bellRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    plantsApi
      .list()
      .then((p) => !cancelled && setPlants(p))
      .catch(() => undefined);
    alertsApi
      .list(undefined, 50)
      .then((a) => !cancelled && setAlerts(a))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onDown = (e: MouseEvent) => {
      if (bellRef.current && !bellRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  const openAlerts = (alerts ?? []).filter((a) => !a.is_resolved);
  const validPlant = plants.some((p) => p.id === scope.plantId) ? String(scope.plantId) : "";

  return (
    <div className="sd-topbar-controls">
      <label className="sd-visually-hidden" htmlFor="sd-plant-switcher">
        Plant
      </label>
      <select
        id="sd-plant-switcher"
        className="dash-input sd-plant-switcher"
        value={validPlant}
        disabled={plants.length === 0}
        onChange={(e) => scope.setPlantId(e.target.value ? Number(e.target.value) : null)}
      >
        <option value="">{plants.length === 0 ? "No plants" : "All plants"}</option>
        {plants.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>

      <div className="sd-range" role="group" aria-label="Date range">
        {RANGES.map((r) => (
          <button
            key={r.key}
            type="button"
            className={`sd-range-btn${scope.range === r.key ? " active" : ""}`}
            aria-pressed={scope.range === r.key}
            onClick={() => scope.setRange(r.key)}
          >
            {r.label}
          </button>
        ))}
      </div>
      {scope.range === "custom" && (
        <div className="sd-range-custom">
          <label className="sd-visually-hidden" htmlFor="sd-range-from">
            From date
          </label>
          <input
            id="sd-range-from"
            type="date"
            className="dash-input"
            value={scope.from}
            max={scope.to || undefined}
            onChange={(e) => scope.setCustom(e.target.value, scope.to)}
          />
          <label className="sd-visually-hidden" htmlFor="sd-range-to">
            To date
          </label>
          <input
            id="sd-range-to"
            type="date"
            className="dash-input"
            value={scope.to}
            min={scope.from || undefined}
            onChange={(e) => scope.setCustom(scope.from, e.target.value)}
          />
        </div>
      )}

      <div className="sd-bell" ref={bellRef}>
        <button
          type="button"
          className="sd-bell-btn"
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-label={openAlerts.length ? `Notifications, ${openAlerts.length} open alerts` : "Notifications"}
          onClick={() => setOpen((v) => !v)}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
            <path d="M6 9a6 6 0 0 1 12 0c0 6 2.5 7.5 2.5 7.5h-17S6 15 6 9zM10 20a2 2 0 0 0 4 0" />
          </svg>
          {openAlerts.length > 0 && <span className="sd-bell-count">{openAlerts.length}</span>}
        </button>
        {open && (
          <div className="sd-bell-pop" role="dialog" aria-label="Notifications">
            <div className="dash-card-title">Notifications</div>
            {openAlerts.length === 0 ? (
              <p className="sd-bell-empty">No notifications. Open alerts will appear here.</p>
            ) : (
              <ul className="sd-bell-list">
                {openAlerts.slice(0, 5).map((a) => (
                  <li key={a.id}>
                    <span className={`dash-alert-badge ${a.severity}`}>{a.severity}</span>
                    <span>{a.message}</span>
                  </li>
                ))}
              </ul>
            )}
            <Link href="/dashboard/alerts" className="dash-btn dash-btn-ghost dash-btn-sm" onClick={() => setOpen(false)}>
              {openAlerts.length > 5 ? `View all ${openAlerts.length} alerts` : "Open alerts"}
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
