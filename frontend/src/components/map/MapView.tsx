"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { alertsApi, plantsApi, type Alert, type GridPanel, type ParkGrid, type Plant } from "@/lib/api";
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
];

export default function MapView() {
  const [plants, setPlants] = useState<Plant[] | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
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
    Promise.all([plantsApi.list(), alertsApi.list(undefined, 200).catch(() => [] as Alert[])]).then(
      ([p, a]) => {
        if (!live) return;
        setPlants(p);
        setAlerts(a);
      },
      (err: unknown) => live && setError(err instanceof Error ? err.message : "Failed to load plants."),
    );
    return () => {
      live = false;
    };
  }, [attempt]);

  const pins = useMemo(() => plantPins(plants ?? [], alerts), [plants, alerts]);
  const selected = pins.find((p) => p.plant.id === selectedId) ?? null;
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
            onClose={() => {
              setSelectedId(null);
              setGrid(null);
              setPanelId(null);
            }}
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
