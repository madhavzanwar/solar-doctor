"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { parksApi, type GridPanel, type ParkFaultsResponse, type ParkGrid } from "@/lib/api";
import { severityKey, type PlantPin } from "@/lib/map";
import { formatNumber } from "@/lib/performance";
import ParkMapGrid from "./ParkMapGrid";

export function SevBadge({ severity }: { severity: string | null | undefined }) {
  const key = severityKey(severity);
  if (!key || !severity) return <span className="dash-badge dash-badge-muted">CLEAN</span>;
  return (
    <span className="dash-badge" style={{ background: `var(--sev-${key}-dim)`, color: `var(--sev-${key})` }}>
      {severity.toUpperCase()}
    </span>
  );
}

/** Side drawer for a selected plant: open alerts, then (if the plant is linked to a park) the panel grid, panel detail and tracked faults. */
export default function PlantDrawer({
  pin,
  selectedPanelId,
  onSelectPanel,
  onGrid,
  alertsKnown = true,
  onClose,
}: {
  pin: PlantPin;
  selectedPanelId: string | null;
  onSelectPanel: (p: GridPanel | null) => void;
  onGrid: (g: ParkGrid | null) => void;
  alertsKnown?: boolean;
  onClose: () => void;
}) {
  const { plant, openAlerts, severity } = pin;
  const parkId = plant.park_id ?? null;
  const [grid, setGrid] = useState<ParkGrid | null>(null);
  const [faults, setFaults] = useState<ParkFaultsResponse | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");

  useEffect(() => {
    let live = true;
    setGrid(null);
    setFaults(null);
    onGrid(null);
    onSelectPanel(null);
    if (!parkId) {
      setState("idle");
      return;
    }
    setState("loading");
    Promise.all([parksApi.grid(parkId), parksApi.faults(parkId)]).then(
      ([g, f]) => {
        if (!live) return;
        setGrid(g);
        setFaults(f);
        onGrid(g);
        setState("idle");
      },
      () => live && setState("error"),
    );
    return () => {
      live = false;
    };
    // callbacks are stable setters from the parent
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parkId]);

  const panel = grid?.panels.find((p) => p.panel_id === selectedPanelId) ?? null;

  return (
    <aside className="dash-card sd-drawer" aria-label={`${plant.name} details`}>
      <div className="dash-card-title">
        <h2 ref={heading} tabIndex={-1} className="sd-drawer-title">{plant.name}</h2>
        <button type="button" className="dash-btn dash-btn-ghost dash-btn-sm" onClick={onClose} aria-label="Close plant details">Close</button>
      </div>
      <p className="dash-page-sub" style={{ marginBottom: "0.85rem" }}>{plant.location ?? "No location name"}</p>
      <div className="dash-stat-row"><span className="dash-stat-label">Capacity</span><span className="dash-stat-value">{formatNumber(plant.capacity_kw)} kW</span></div>
      <div className="dash-stat-row"><span className="dash-stat-label">Status</span><span className="dash-stat-value">{plant.is_active ? "Active" : "Inactive"}</span></div>
      <div className="dash-stat-row"><span className="dash-stat-label">Worst open issue</span><span className="dash-stat-value">{alertsKnown ? <SevBadge severity={severity} /> : <span className="dash-badge dash-badge-muted">UNKNOWN</span>}</span></div>

      <h3 className="sd-drawer-h">Open alerts ({openAlerts.length})</h3>
      {!alertsKnown ? (
        <p className="dash-page-sub">Alert status unavailable.</p>
      ) : openAlerts.length === 0 ? (
        <p className="dash-page-sub">No open alerts for this plant.</p>
      ) : (
        <ul className="sd-drawer-list">
          {openAlerts.map((a) => (
            <li key={a.id}><SevBadge severity={a.severity} /> <span>{a.message}</span></li>
          ))}
        </ul>
      )}

      <h3 className="sd-drawer-h">Panels</h3>
      {!parkId ? (
        <p className="dash-page-sub">This plant is not linked to a drone-inspected park, so there is no panel grid.</p>
      ) : state === "loading" ? (
        <p className="dash-page-sub" role="status">Loading panel grid…</p>
      ) : state === "error" ? (
        <div className="dash-error" role="alert">Could not load the panel grid for this plant.</div>
      ) : grid && grid.panels.length > 0 ? (
        <>
          <ParkMapGrid grid={grid} selectedPanelId={selectedPanelId} onSelect={onSelectPanel} />
          {panel ? (
            <div className="sd-panel-detail" aria-live="polite">
              <strong>Panel {panel.panel_id}</strong>
              <ul className="sd-drawer-list">
                {panel.detections.map((d, i) => (
                  <li key={i}><SevBadge severity={d.severity} /> <span>{d.class ?? "Unclassified"}{d.confidence != null ? ` · ${Math.round(d.confidence * 100)}%` : ""}</span></li>
                ))}
              </ul>
              {panel.gps && <p className="dash-page-sub">GPS {panel.gps.lat.toFixed(5)}, {panel.gps.lon.toFixed(5)}</p>}
            </div>
          ) : (
            <p className="dash-page-sub" style={{ marginTop: "0.5rem" }}>Select a panel to see its detections.</p>
          )}
        </>
      ) : (
        <p className="dash-page-sub">No panel detections yet for the latest inspection.</p>
      )}

      {parkId && faults && faults.faults.length > 0 && (
        <>
          <h3 className="sd-drawer-h">Tracked faults ({faults.total})</h3>
          <ul className="sd-drawer-list">
            {faults.faults.map((f) => (
              <li key={f.id}>
                <SevBadge severity={f.severity} /> <span>{f.panel_id ?? "Unknown panel"} · {f.status ?? "open"}{f.priority ? ` · ${f.priority}` : ""}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      <p style={{ marginTop: "1rem" }}><Link className="dash-link-inline" href={`/dashboard/plants/${plant.id}`}>Open plant page</Link></p>
    </aside>
  );
}
