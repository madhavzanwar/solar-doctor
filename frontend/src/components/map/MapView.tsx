"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { alertsApi, edgeApi, OPEN_ALERT_LIMIT, plantsApi, type Alert, type GridPanel, type ParkGrid, type Plant } from "@/lib/api";
import { BASEMAPS, panelsWithGps, plantPins, type BasemapId, type StringTelemetry } from "@/lib/map";
import { EmptyState, LoadingState } from "@/components/ui/states";
import PlantDrawer from "./PlantDrawer";
import StringInspectionDrawer from "./StringInspectionDrawer";

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
  ["Normal string", "var(--cls-clean)"],
  ["Derated string", "var(--cls-dusty)"],
  ["Unknown", "#8a948a"],
];

export default function MapView() {
  const [plants, setPlants] = useState<Plant[] | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [alertsOk, setAlertsOk] = useState(true);
  const [truncated, setTruncated] = useState<string[]>([]);
  const [focusPlant, setFocusPlant] = useState<{ id: number; n: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  // GIS Layer & Opacity State
  const [basemap, setBasemap] = useState<BasemapId>("positron");
  const [layerOpacity, setLayerOpacity] = useState(0.85);

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedString, setSelectedString] = useState<StringTelemetry | null>(null);
  const [edgeOverrides, setEdgeOverrides] = useState<Record<string, Partial<StringTelemetry>>>({});
  const [grid, setGrid] = useState<ParkGrid | null>(null);
  const [panelId, setPanelId] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  // Poll live string telemetry from IoT Edge subsystem when a plant is selected
  useEffect(() => {
    if (selectedId == null || !edgeApi?.strings) {
      setEdgeOverrides({});
      return;
    }
    let live = true;
    edgeApi.strings(selectedId).then(
      (records) => {
        if (!live || !Array.isArray(records)) return;
        const map: Record<string, Partial<StringTelemetry>> = {};
        for (const r of records) {
          const fullId = r.string_id.startsWith("INV-") ? r.string_id : `${r.inverter_id}-${r.string_id}`;
          map[fullId] = {
            plant_id: r.plant_id,
            inverter_id: r.inverter_id,
            string_id: r.string_id,
            global_string_id: fullId,
            power_kw: r.power_kw,
            voltage_v: r.voltage_v,
            current_a: r.current_a,
            shortfall_kw: r.shortfall_kw,
            status: r.status,
            defect_diagnosis: r.defect_diagnosis,
            loss_pct: r.loss_pct,
            temperature_c: r.temperature_c,
          };
        }
        setEdgeOverrides(map);
      },
      () => {
        // Graceful fallback to deterministic generator data
      }
    );
    return () => {
      live = false;
    };
  }, [selectedId]);

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
        setTruncated(
          p
            .filter((_, i) => {
              const r = res[i];
              return r.status === "fulfilled" && r.value.length >= OPEN_ALERT_LIMIT;
            })
            .map((pl) => pl.name)
        );
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
    if (selectedString != null) {
      setSelectedString(null);
      return;
    }
    if (selectedId != null) setFocusPlant({ id: selectedId, n: (focusPlant?.n ?? 0) + 1 });
    setSelectedId(null);
    setSelectedString(null);
    setGrid(null);
    setPanelId(null);
  };

  // Escape closes the active string inspection or plant drawer from anywhere on the page
  useEffect(() => {
    if (selectedId == null && selectedString == null) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, selectedString]);

  const panels = useMemo(() => (selected && grid ? panelsWithGps(grid.panels) : []), [selected, grid]);

  if (error) {
    return (
      <div className="dash-error" role="alert">
        {error}{" "}
        <button type="button" className="dash-btn dash-btn-ghost dash-btn-sm" onClick={() => setAttempt((n) => n + 1)}>
          Retry
        </button>
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
      <div className="dash-toolbar" style={{ marginBottom: "1rem", flexWrap: "wrap", gap: "0.75rem" }}>
        {/* Layer Switcher Controls */}
        <div role="group" aria-label="GIS Layer Selection" className="sd-range sd-basemap">
          {(Object.keys(BASEMAPS) as BasemapId[]).map((id) => (
            <button
              key={id}
              type="button"
              className={`sd-range-btn${basemap === id ? " active" : ""}`}
              aria-pressed={basemap === id}
              onClick={() => setBasemap(id)}
            >
              {BASEMAPS[id].label}
            </button>
          ))}
        </div>

        {/* Opacity Slider for High-Res Drone Ortho & Radiometric Thermal IR */}
        {(basemap === "drone_ortho" || basemap === "thermal_ir") && (
          <div className="sd-opacity-bar" style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}>
            <label htmlFor="toolbar-layer-opacity" style={{ fontSize: "0.75rem", color: "var(--muted)", margin: 0, whiteSpace: "nowrap" }}>
              Overlay Blend: <strong className="dash-mono" style={{ color: "var(--ink)" }}>{Math.round(layerOpacity * 100)}%</strong>
            </label>
            <input
              id="toolbar-layer-opacity"
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={layerOpacity}
              onChange={(e) => setLayerOpacity(parseFloat(e.target.value))}
              className="sd-opacity-slider"
              aria-label="Layer blending opacity slider"
            />
          </div>
        )}

        <span className="dash-page-sub" style={{ margin: 0, alignSelf: "center" }}>
          {pins.length} plant{pins.length === 1 ? "" : "s"} · Select any plant for drone orthomosaics & string telemetry
        </span>
      </div>

      {!alertsOk && (
        <div className="dash-advisory" role="status" style={{ marginBottom: "1rem" }}>
          <div className="dash-advisory-title">Alert status unavailable</div>
          <div className="dash-advisory-body">
            Open alerts could not be loaded for every plant, so pins are grey rather than coloured by severity.
          </div>
        </div>
      )}
      {truncated.length > 0 && (
        <div className="dash-advisory" role="status" style={{ marginBottom: "1rem" }}>
          <div className="dash-advisory-title">Showing the {OPEN_ALERT_LIMIT} most recent open alerts</div>
          <div className="dash-advisory-body">
            {truncated.join(", ")} may have more; the worst severity shown could be understated.
          </div>
        </div>
      )}

      <div className="sd-map-layout">
        <div className="sd-map-frame" data-testid="map-frame">
          <LeafletMap
            pins={pins}
            panels={panels}
            selectedPlantId={selectedId}
            selectedPanelId={panelId}
            selectedStringId={selectedString?.global_string_id}
            basemap={basemap}
            layerOpacity={layerOpacity}
            onSelectPlant={(id) => {
              setSelectedId(id);
              setSelectedString(null);
            }}
            onSelectPanel={(p: GridPanel) => setPanelId(p.panel_id)}
            onSelectString={setSelectedString}
            onBasemapChange={setBasemap}
            onOpacityChange={setLayerOpacity}
            focusPlant={focusPlant}
            alertsKnown={alertsOk}
            stringTelemetryOverrides={edgeOverrides}
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

        {/* Side Drawer: String Inspection takes precedence when a string is actively selected */}
        {selectedString ? (
          <StringInspectionDrawer
            stringData={selectedString}
            plantName={selected?.plant.name ?? "Solar Facility"}
            onClose={() => setSelectedString(null)}
          />
        ) : selected ? (
          <PlantDrawer
            key={selected.plant.id}
            pin={selected}
            selectedPanelId={panelId}
            onSelectPanel={(p) => setPanelId(p?.panel_id ?? null)}
            onGrid={setGrid}
            alertsKnown={alertsOk}
            onClose={close}
            onSelectString={setSelectedString}
          />
        ) : (
          <aside className="dash-card sd-drawer" aria-label="Plant details">
            <p className="dash-page-sub">Select a plant pin to inspect its gigawatt-scale inverter stations and drone strings.</p>
            <ul className="sd-drawer-list">
              {pins.map((p) => (
                <li key={p.plant.id}>
                  <button
                    type="button"
                    className="dash-btn dash-btn-ghost dash-btn-sm"
                    onClick={() => {
                      setSelectedId(p.plant.id);
                      setSelectedString(null);
                    }}
                  >
                    {p.plant.name}
                  </button>
                </li>
              ))}
            </ul>
          </aside>
        )}
      </div>
    </>
  );
}
