"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { alertsApi, OPEN_ALERT_LIMIT, plantsApi, type Alert, type GridPanel, type ParkGrid, type Plant } from "@/lib/api";
import { BASEMAPS, panelsWithGps, plantPins, type BasemapId } from "@/lib/map";
import { EmptyState, LoadingState } from "@/components/ui/states";
import PlantDrawer from "./PlantDrawer";

// Leaflet touches `window` at import time, so it must never render on the server.
const LeafletMap = dynamic(() => import("./LeafletMap"), {
  ssr: false,
  loading: () => <LoadingState label="Loading map…" rows={2} />,
});

const LEGEND: Array<[string, string]> = [
  ["CRITICAL", "var(--sev-critical)"],
  ["HIGH / WARNING", "var(--sev-high)"],
  ["MEDIUM", "var(--sev-medium)"],
  ["LOW / INFO", "var(--sev-low)"],
  ["No open issue", "var(--field)"],
  ["Unknown", "#8a948a"],
];

export default function MapView() {
  const [plants, setPlants] = useState<Plant[] | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [alertsOk, setAlertsOk] = useState(true);
  const [truncated, setTruncated] = useState<string[]>([]);
  const [focusPlant, setFocusPlant] = useState<{ id: number; n: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [basemap, setBasemap] = useState<BasemapId>("positron");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [grid, setGrid] = useState<ParkGrid | null>(null);
  const [panelId, setPanelId] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    setError(null);
    setPlants(null);
    plantsApi.list().then(
      async (p) => {
        // One request per plant for its *open* alerts, so a busy fleet is not silently cut off at a global cap.
        const res = await Promise.allSettled(p.map((pl) => alertsApi.listOpen(pl.id)));
        if (!live) return;
        setPlants(p);
        setAlerts([...new Map(res.flatMap((r) => (r.status === "fulfilled" ? r.value : [])).map((al) => [al.id, al])).values()]);
        setAlertsOk(res.every((r) => r.status === "fulfilled"));
        setTruncated(p.filter((_, i) => { const r = res[i]; return r.status === "fulfilled" && r.value.length >= OPEN_ALERT_LIMIT; }).map((pl) => pl.name));
      },
      (err: unknown) => live && setError(err instanceof Error ? err.message : "Failed to load plants."),
    );
    return () => {
      live = false;
    };
  }, [attempt]);

  const pins = useMemo(() => plantPins(plants ?? [], alerts), [plants, alerts]);
  const selected = pins.find((p) => p.plant.id === selectedId) ?? null;
  const close = () => {
    if (selectedId != null) setFocusPlant({ id: selectedId, n: (focusPlant?.n ?? 0) + 1 });
    setSelectedId(null);
    setGrid(null);
    setPanelId(null);
  };

  // Escape closes the drawer from anywhere on the page while it is open.
  useEffect(() => {
    if (selectedId == null) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const panels = useMemo(() => (selected && grid ? panelsWithGps(grid.panels) : []), [selected, grid]);

  if (error) {
    return (
      <div className="dash-error" role="alert">
        {error}{" "}
        <button type="button" className="dash-btn dash-btn-ghost dash-btn-sm" onClick={() => setAttempt((n) => n + 1)}>Retry</button>
      </div>
    );
  }
  if (plants === null) return <LoadingState label="Loading plants…" />;
  if (pins.length === 0) {
    return (
      <EmptyState icon="map" title="No mapped plants yet">
        Register a plant with coordinates to see it here. Panel-level faults appear once an inspection has been localised.
      </EmptyState>
    );
  }

  return (
    <>
      <div className="dash-toolbar" style={{ marginBottom: "1rem" }}>
        <div role="group" aria-label="Basemap" className="sd-range sd-basemap">
          {(Object.keys(BASEMAPS) as BasemapId[]).map((id) => (
            <button key={id} type="button" className={`sd-range-btn${basemap === id ? " active" : ""}`} aria-pressed={basemap === id} onClick={() => setBasemap(id)}>
              {BASEMAPS[id].label}
            </button>
          ))}
        </div>
        <span className="dash-page-sub" style={{ margin: 0 }}>{pins.length} plant{pins.length === 1 ? "" : "s"} · pins are coloured by the worst open alert</span>
      </div>

      {!alertsOk && (
        <div className="dash-advisory" role="status" style={{ marginBottom: "1rem" }}>
          <div className="dash-advisory-title">Alert status unavailable</div>
          <div className="dash-advisory-body">Open alerts could not be loaded for every plant, so pins are grey rather than coloured by severity.</div>
        </div>
      )}
      {truncated.length > 0 && (
        <div className="dash-advisory" role="status" style={{ marginBottom: "1rem" }}>
          <div className="dash-advisory-title">Showing the {OPEN_ALERT_LIMIT} most recent open alerts</div>
          <div className="dash-advisory-body">{truncated.join(", ")} may have more; the worst severity shown could be understated.</div>
        </div>
      )}
      <div className="sd-map-layout">
        <div className="sd-map-frame" data-testid="map-frame">
          <LeafletMap
            pins={pins}
            panels={panels}
            selectedPlantId={selectedId}
            selectedPanelId={panelId}
            basemap={basemap}
            onSelectPlant={setSelectedId}
            onSelectPanel={(p: GridPanel) => setPanelId(p.panel_id)}
            focusPlant={focusPlant}
            alertsKnown={alertsOk}
          />
          <div className="sd-legend dash-card" aria-label="Severity legend" role="group">
            {LEGEND.map(([label, color]) => (
              <span key={label} className="sd-legend-item">
                <span className="sd-swatch" style={{ background: color }} aria-hidden="true" />
                {label}
              </span>
            ))}
          </div>
        </div>

        {selected ? (
          <PlantDrawer
            key={selected.plant.id}
            pin={selected}
            selectedPanelId={panelId}
            onSelectPanel={(p) => setPanelId(p?.panel_id ?? null)}
            onGrid={setGrid}
            alertsKnown={alertsOk}
            onClose={close}
          />
        ) : (
          <aside className="dash-card sd-drawer" aria-label="Plant details">
            <p className="dash-page-sub">Select a plant pin to see its open alerts and panel grid.</p>
            <ul className="sd-drawer-list">
              {pins.map((p) => (
                <li key={p.plant.id}>
                  <button type="button" className="dash-btn dash-btn-ghost dash-btn-sm" onClick={() => setSelectedId(p.plant.id)}>{p.plant.name}</button>
                </li>
              ))}
            </ul>
          </aside>
        )}
      </div>
    </>
  );
}
