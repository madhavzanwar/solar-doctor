"use client";

import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { GridPanel } from "@/lib/api";
import { BASEMAPS, severityKey, type BasemapId, type PlantPin } from "@/lib/map";

// Plain Leaflet (BSD-2-Clause), driven imperatively: react-leaflet is Hippocratic-2.1, which our licence rule excludes.

// Square pins (DESIGN.md §8.5) as divIcons: no marker image assets to bundle.
function icon(kind: "plant" | "panel", sev: string | null, selected: boolean) {
  const key = sev === "UNKNOWN" ? "unknown" : (severityKey(sev) ?? "none");
  // Hit area (the icon box) is >= 24 px (WCAG 2.5.8); the visible square is smaller, see .sd-pin-plant/.sd-pin-panel.
  const size = kind === "plant" ? 28 : 24;
  return L.divIcon({
    className: "sd-pin-wrap",
    html: `<span class="sd-pin sd-pin-${kind} sd-pin-${key}${selected ? " sd-pin-selected" : ""}"></span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

export interface LeafletMapProps {
  pins: PlantPin[];
  panels: Array<GridPanel & { gps: { lat: number; lon: number } }>;
  selectedPlantId: number | null;
  selectedPanelId: string | null;
  basemap: BasemapId;
  onSelectPlant: (id: number) => void;
  onSelectPanel: (panel: GridPanel) => void;
  /** Bump `n` to move keyboard focus to a plant marker (used when the drawer closes). */
  focusPlant?: { id: number; n: number } | null;
  /** False when the alert request failed: pins render neutral grey instead of looking "clean". */
  alertsKnown?: boolean;
}

export default function LeafletMap({ pins, panels, selectedPlantId, selectedPanelId, basemap, onSelectPlant, onSelectPanel, focusPlant, alertsKnown = true }: LeafletMapProps) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const tiles = useRef<L.TileLayer | null>(null);
  const markers = useRef<L.LayerGroup | null>(null);
  const byId = useRef(new Map<string, { marker: L.Marker; kind: "plant" | "panel" }>());
  const cb = useRef({ onSelectPlant, onSelectPanel });
  cb.current = { onSelectPlant, onSelectPanel };

  useEffect(() => {
    const m = L.map(el.current!, { center: [22.5, 79], zoom: 4, scrollWheelZoom: true });
    map.current = m;
    markers.current = L.layerGroup().addTo(m);
    return () => {
      m.remove();
      map.current = tiles.current = markers.current = null;
    };
  }, []);

  useEffect(() => {
    const b = BASEMAPS[basemap];
    tiles.current?.remove();
    tiles.current = L.tileLayer(b.url, { attribution: b.attribution, maxZoom: b.maxZoom, maxNativeZoom: b.maxZoom }).addTo(map.current!);
  }, [basemap]);

  // Rebuild markers only when the data changes; selection just swaps icons (keeps focus on the marker).
  useEffect(() => {
    const g = markers.current!;
    g.clearLayers();
    byId.current.clear();
    const mk = (id: string, kind: "plant" | "panel", pos: [number, number], sev: string | null, title: string, alt: string, pick: () => void) => {
      const marker = L.marker(pos, { icon: icon(kind, sev, false), title, alt, keyboard: true }).addTo(g);
      marker.on("click", pick); // Leaflet turns Enter on a focused marker into a click
      byId.current.set(id, { marker, kind });
    };
    for (const { plant, severity, openAlerts } of pins) {
      mk(`plant:${plant.id}`, "plant", [plant.latitude, plant.longitude], alertsKnown ? severity : "UNKNOWN",
        `${plant.name}: ${severity ? `${openAlerts.length} open, worst ${severity}` : alertsKnown ? "no open alerts" : "alert status unavailable"}`, `Plant ${plant.name}`,
        () => cb.current.onSelectPlant(plant.id));
    }
    for (const p of panels) {
      mk(`panel:${p.panel_id}`, "panel", [p.gps.lat, p.gps.lon], p.worst_severity,
        `Panel ${p.panel_id}: ${p.detection_count} detection${p.detection_count === 1 ? "" : "s"}, worst ${p.worst_severity ?? "none"}`,
        `Panel ${p.panel_id}`, () => cb.current.onSelectPanel(p));
    }
  }, [pins, panels, alertsKnown]);

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

  useEffect(() => {
    if (focusPlant) byId.current.get(`plant:${focusPlant.id}`)?.marker.getElement()?.focus();
  }, [focusPlant]);

  // Re-fit only when the set of points changes, not on selection.
  const fit: Array<[number, number]> = panels.length ? panels.map((p) => [p.gps.lat, p.gps.lon]) : pins.map((p) => [p.plant.latitude, p.plant.longitude]);
  const fitKey = fit.map((p) => p.join(",")).join("|");
  useEffect(() => {
    const m = map.current;
    if (!m || fit.length === 0) return;
    if (fit.length === 1) m.setView(fit[0], 15);
    // Panel markers are metres apart: zoom in far enough that their 24 px hit areas do not overlap.
    else m.fitBounds(fit, { padding: [48, 48], maxZoom: panels.length ? 19 : 14 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey]);

  return <div ref={el} role="application" aria-label="Plant map" style={{ height: "100%", width: "100%" }} />;
}
