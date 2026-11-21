"use client";

import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { GridPanel } from "@/lib/api";
import {
  BASEMAPS,
  generateParkStringPolygons,
  severityKey,
  STRING_HEALTH_COLORS,
  type BasemapId,
  type InverterStationProperties,
  type PlantPin,
  type StringStatus,
  type StringTelemetry,
} from "@/lib/map";

// Square pins (DESIGN.md §8.5) as divIcons: no marker image assets to bundle.
function icon(kind: "plant" | "panel", sev: string | null, selected: boolean) {
  const key = sev === "UNKNOWN" ? "unknown" : (severityKey(sev) ?? "none");
  const size = kind === "plant" ? 28 : 24;
  return L.divIcon({
    className: "sd-pin-wrap",
    html: `<span class="sd-pin sd-pin-${kind} sd-pin-${key}${selected ? " sd-pin-selected" : ""}"></span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function createStringPopupHtml(str: StringTelemetry): string {
  const statusClass = str.status.toLowerCase();
  const alertClass = str.shortfall_kw > 0 ? "sd-metric-alert" : "";
  const tempRow = str.temperature_c
    ? `<div class="sd-popup-metric"><span class="sd-metric-label">Thermal IR</span><span class="sd-metric-val">${str.temperature_c.toFixed(1)}°C</span></div>`
    : "";

  return `
    <div class="sd-string-popup" data-string-id="${str.global_string_id}">
      <div class="sd-popup-header">
        <strong class="sd-popup-title">${str.global_string_id}</strong>
        <span class="sd-status-badge sd-status-${statusClass}">${str.status}</span>
      </div>
      <div class="sd-popup-station">${str.station_name} · Inverter ${str.inverter_id}</div>

      <div class="sd-popup-grid">
        <div class="sd-popup-metric">
          <span class="sd-metric-label">Voltage</span>
          <span class="sd-metric-val">${str.voltage_v.toFixed(1)} V</span>
        </div>
        <div class="sd-popup-metric">
          <span class="sd-metric-label">Current</span>
          <span class="sd-metric-val">${str.current_a.toFixed(2)} A</span>
        </div>
        <div class="sd-popup-metric">
          <span class="sd-metric-label">Output Power</span>
          <span class="sd-metric-val">${str.power_kw.toFixed(2)} kW</span>
        </div>
        <div class="sd-popup-metric">
          <span class="sd-metric-label">Shortfall</span>
          <span class="sd-metric-val ${alertClass}">${str.shortfall_kw.toFixed(2)} kW</span>
        </div>
        <div class="sd-popup-metric">
          <span class="sd-metric-label">Loss %</span>
          <span class="sd-metric-val ${alertClass}">${str.loss_pct.toFixed(1)}%</span>
        </div>
        ${tempRow}
      </div>

      <div class="sd-popup-diagnosis">
        <span class="sd-diagnosis-label">Defect Diagnosis</span>
        <span class="sd-diagnosis-text">${str.defect_diagnosis}</span>
      </div>

      <a
        href="/dashboard/inspections?plant_id=${str.plant_id}&string_id=${encodeURIComponent(str.global_string_id)}"
        class="dash-btn dash-btn-primary dash-btn-sm sd-popup-btn"
      >
        Inspect String with AI &rarr;
      </a>
    </div>
  `;
}

export interface LeafletMapProps {
  pins: PlantPin[];
  panels: Array<GridPanel & { gps: { lat: number; lon: number } }>;
  selectedPlantId: number | null;
  selectedPanelId: string | null;
  selectedStringId?: string | null;
  basemap: BasemapId;
  layerOpacity?: number;
  onSelectPlant: (id: number) => void;
  onSelectPanel: (panel: GridPanel) => void;
  onSelectString?: (str: StringTelemetry | null) => void;
  onBasemapChange?: (id: BasemapId) => void;
  onOpacityChange?: (opacity: number) => void;
  /** Bump `n` to move keyboard focus to a plant marker (used when the drawer closes). */
  focusPlant?: { id: number; n: number } | null;
  /** False when the alert request failed: pins render neutral grey instead of looking "clean". */
  alertsKnown?: boolean;
  stringTelemetryOverrides?: Record<string, Partial<StringTelemetry>>;
}

export default function LeafletMap({
  pins,
  panels,
  selectedPlantId,
  selectedPanelId,
  selectedStringId,
  basemap,
  layerOpacity = 0.85,
  onSelectPlant,
  onSelectPanel,
  onSelectString,
  onBasemapChange,
  onOpacityChange,
  focusPlant,
  alertsKnown = true,
  stringTelemetryOverrides,
}: LeafletMapProps) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const baseTiles = useRef<L.TileLayer | null>(null);
  const overlayTiles = useRef<L.TileLayer | null>(null);
  const markers = useRef<L.LayerGroup | null>(null);
  const parkGeoJsonLayer = useRef<L.GeoJSON | null>(null);
  const byId = useRef<Map<string, { marker: L.Marker; kind: "plant" | "panel" }>>(new Map());

  const cb = useRef({ onSelectPlant, onSelectPanel, onSelectString });
  cb.current = { onSelectPlant, onSelectPanel, onSelectString };

  // Track map initialization
  const [mapReady, setMapReady] = useState(false);

  useEffect(() => {
    const m = L.map(el.current!, { center: [22.5, 79], zoom: 4, scrollWheelZoom: true });
    map.current = m;
    markers.current = L.layerGroup().addTo(m);
    setMapReady(true);

    return () => {
      m.remove();
      map.current = baseTiles.current = overlayTiles.current = markers.current = parkGeoJsonLayer.current = null;
    };
  }, []);

  // Update Base and Overlay Tile Layers according to Basemap and Opacity
  useEffect(() => {
    const m = map.current;
    if (!m) return;

    const config = BASEMAPS[basemap];

    // Determine base map configuration
    // For drone_ortho and thermal_ir overlays, use imagery as base underneath
    const baseConfig = config.isOverlay ? BASEMAPS.imagery : config;

    if (baseTiles.current) {
      baseTiles.current.remove();
    }
    baseTiles.current = L.tileLayer(baseConfig.url, {
      attribution: baseConfig.attribution,
      maxZoom: baseConfig.maxZoom,
      maxNativeZoom: baseConfig.maxZoom,
    }).addTo(m);

    // If active layer is an overlay (drone_ortho or thermal_ir), add overlay tile layer
    if (overlayTiles.current) {
      overlayTiles.current.remove();
      overlayTiles.current = null;
    }

    if (config.isOverlay) {
      const overlayLayer = L.tileLayer(config.url, {
        attribution: config.attribution,
        maxZoom: config.maxZoom,
        maxNativeZoom: config.maxNativeZoom ?? 18,
        className: config.filterClass ?? "",
        opacity: layerOpacity,
      }).addTo(m);
      overlayTiles.current = overlayLayer;
    }
  }, [basemap, mapReady]);

  // Real-time Opacity slider updates
  useEffect(() => {
    if (overlayTiles.current) {
      overlayTiles.current.setOpacity(layerOpacity);
    }
  }, [layerOpacity]);

  // Rebuild plant and panel markers
  useEffect(() => {
    const g = markers.current;
    if (!g) return;
    g.clearLayers();
    byId.current.clear();

    const mk = (
      id: string,
      kind: "plant" | "panel",
      pos: [number, number],
      sev: string | null,
      title: string,
      alt: string,
      pick: () => void
    ) => {
      const marker = L.marker(pos, { icon: icon(kind, sev, false), title, alt, keyboard: true }).addTo(g);
      marker.on("click", pick);
      byId.current.set(id, { marker, kind });
    };

    for (const { plant, severity, openAlerts } of pins) {
      mk(
        `plant:${plant.id}`,
        "plant",
        [plant.latitude, plant.longitude],
        alertsKnown ? severity : "UNKNOWN",
        `${plant.name}: ${severity ? `${openAlerts.length} open, worst ${severity}` : alertsKnown ? "no open alerts" : "alert status unavailable"}`,
        `Plant ${plant.name}`,
        () => cb.current.onSelectPlant(plant.id)
      );
    }
    for (const p of panels) {
      mk(
        `panel:${p.panel_id}`,
        "panel",
        [p.gps.lat, p.gps.lon],
        p.worst_severity,
        `Panel ${p.panel_id}: ${p.detection_count} detection${p.detection_count === 1 ? "" : "s"}, worst ${p.worst_severity ?? "none"}`,
        `Panel ${p.panel_id}`,
        () => cb.current.onSelectPanel(p)
      );
    }
  }, [pins, panels, alertsKnown, mapReady]);

  // Update selected marker styling
  useEffect(() => {
    const sevOf = (p: PlantPin) => (alertsKnown ? p.severity : "UNKNOWN");
    const all = [
      ...pins.map((p) => ({ id: `plant:${p.plant.id}`, sev: sevOf(p) })),
      ...panels.map((p) => ({ id: `panel:${p.panel_id}`, sev: p.worst_severity })),
    ];
    for (const { id, sev } of all) {
      const e = byId.current.get(id);
      if (e) e.marker.setIcon(icon(e.kind, sev, id === `plant:${selectedPlantId}` || id === `panel:${selectedPanelId}`));
    }
  }, [selectedPlantId, selectedPanelId, pins, panels, alertsKnown]);

  // Focus plant
  useEffect(() => {
    if (focusPlant) byId.current.get(`plant:${focusPlant.id}`)?.marker.getElement()?.focus();
  }, [focusPlant]);

  // Render Utility-scale Inverter Station and String GeoJSON Polygons
  useEffect(() => {
    const m = map.current;
    if (!m) return;

    if (parkGeoJsonLayer.current) {
      parkGeoJsonLayer.current.remove();
      parkGeoJsonLayer.current = null;
    }

    if (selectedPlantId == null) return;
    const selectedPin = pins.find((p) => p.plant.id === selectedPlantId);
    if (!selectedPin) return;

    const parkData = generateParkStringPolygons(selectedPin.plant, stringTelemetryOverrides);

    const gj = L.geoJSON(parkData as unknown as GeoJSON.GeoJsonObject, {
      style: (feature) => {
        if (!feature || !feature.properties) return {};
        if (feature.properties.type === "inverter_station") {
          const stProps = feature.properties as InverterStationProperties;
          const stColor = STRING_HEALTH_COLORS[stProps.status] || "#2f6b4f";
          return {
            color: stColor,
            weight: 1.5,
            dashArray: "4, 4",
            fillColor: stColor,
            fillOpacity: 0.05,
          };
        }
        if (feature.properties.type === "string") {
          const strProps = feature.properties as StringTelemetry;
          const isSel = selectedStringId === strProps.global_string_id;
          const hColor = STRING_HEALTH_COLORS[strProps.status] || "#2f6b4f";
          return {
            color: isSel ? "#ffffff" : strProps.status === "CRITICAL" ? "#5a1a1a" : strProps.status === "DERATED" ? "#5a3f15" : "#1a3d2c",
            weight: isSel ? 3 : 1.2,
            fillColor: hColor,
            fillOpacity: 0.88,
          };
        }
        return {};
      },
      onEachFeature: (feature, layer) => {
        if (feature.properties.type === "inverter_station") {
          const st = feature.properties as InverterStationProperties;
          layer.bindTooltip(
            `<strong>${st.station_name}</strong> (${st.inverter_id})<br/>Strings: ${st.total_strings} · ${st.power_kw} kW / ${st.capacity_kw} kW`,
            { sticky: true }
          );
        } else if (feature.properties.type === "string") {
          const str = feature.properties as StringTelemetry;
          layer.bindTooltip(
            `<strong>${str.global_string_id}</strong> · ${str.status} (${str.power_kw} kW)`,
            { sticky: true }
          );

          const popupHtml = createStringPopupHtml(str);
          layer.bindPopup(popupHtml, { maxWidth: 300, minWidth: 240 });

          layer.on("click", () => {
            cb.current.onSelectString?.(str);
          });
        }
      },
    }).addTo(m);

    parkGeoJsonLayer.current = gj;

    // Zoom into the park strings
    const bounds = gj.getBounds();
    if (bounds.isValid()) {
      m.fitBounds(bounds, { padding: [36, 36], maxZoom: 18 });
    }
  }, [selectedPlantId, selectedStringId, pins, stringTelemetryOverrides, mapReady]);

  // Re-fit bounds when pins change and no plant is selected
  const fit: Array<[number, number]> = panels.length
    ? panels.map((p) => [p.gps.lat, p.gps.lon])
    : pins.map((p) => [p.plant.latitude, p.plant.longitude]);
  const fitKey = fit.map((p) => p.join(",")).join("|");

  useEffect(() => {
    const m = map.current;
    if (!m || fit.length === 0 || selectedPlantId != null) return;
    if (fit.length === 1) m.setView(fit[0], 15);
    else m.fitBounds(fit, { padding: [48, 48], maxZoom: panels.length ? 19 : 14 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey, selectedPlantId]);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <div ref={el} role="application" aria-label="Plant map" style={{ height: "100%", width: "100%" }} />

      {/* On-Map HUD Controls for Layer Switcher & Opacity blending */}
      <div className="sd-map-hud" role="region" aria-label="GIS Layer Controls">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 className="sd-map-hud-title">GIS Layers</h3>
          <span className="dash-mono" style={{ fontSize: "0.68rem", color: "var(--muted)" }}>
            {basemap === "drone_ortho" ? "RTK Drone" : basemap === "thermal_ir" ? "FLIR IR" : "Base"}
          </span>
        </div>

        <div role="group" aria-label="Map layer selector" style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem" }}>
          {(Object.keys(BASEMAPS) as BasemapId[]).map((id) => (
            <button
              key={id}
              type="button"
              className={`dash-btn ${basemap === id ? "dash-btn-primary" : "dash-btn-ghost"} dash-btn-sm`}
              style={{ fontSize: "0.7rem", padding: "0.2rem 0.4rem", flex: "1 1 calc(50% - 0.25rem)" }}
              aria-pressed={basemap === id}
              onClick={() => onBasemapChange?.(id)}
            >
              {BASEMAPS[id].label}
            </button>
          ))}
        </div>

        {(basemap === "drone_ortho" || basemap === "thermal_ir") && (
          <div className="sd-opacity-bar" style={{ marginTop: "0.2rem" }}>
            <label htmlFor="leaflet-opacity-slider" style={{ fontSize: "0.72rem", color: "var(--muted)", margin: 0 }}>
              Blend: <strong className="dash-mono" style={{ color: "var(--ink)" }}>{Math.round(layerOpacity * 100)}%</strong>
            </label>
            <input
              id="leaflet-opacity-slider"
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={layerOpacity}
              onChange={(e) => onOpacityChange?.(parseFloat(e.target.value))}
              className="sd-opacity-slider"
              aria-label="Layer blending opacity slider"
            />
          </div>
        )}
      </div>
    </div>
  );
}
