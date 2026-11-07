"use client";

import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { GridPanel } from "@/lib/api";
import { BASEMAPS, severityKey, type BasemapId, type PlantPin } from "@/lib/map";

// Plain Leaflet (BSD-2-Clause), driven imperatively: react-leaflet is Hippocratic-2.1, which our licence rule excludes.

// Square pins (DESIGN.md §8.5) as divIcons: no marker image assets to bundle.
function icon(kind: "plant" | "panel", sev: string | null, selected: boolean) {
  const key = severityKey(sev) ?? "none";
  const size = kind === "plant" ? 22 : 12;
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
}

export default function LeafletMap({ pins, panels, selectedPlantId, selectedPanelId, basemap, onSelectPlant, onSelectPanel }: LeafletMapProps) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const tiles = useRef<L.TileLayer | null>(null);
  const markers = useRef<L.LayerGroup | null>(null);
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

  useEffect(() => {
    const g = markers.current!;
    g.clearLayers();
    const mk = (pos: [number, number], ic: L.DivIcon, title: string, alt: string, pick: () => void) => {
      const marker = L.marker(pos, { icon: ic, title, alt, keyboard: true }).addTo(g);
      marker.on("click", pick);
      // Leaflet makes markers focusable; Enter is the keyboard "click".
      marker.on("keypress", (e) => (e as L.LeafletKeyboardEvent).originalEvent.key === "Enter" && pick());
    };
    for (const { plant, severity, openAlerts } of pins) {
      mk([plant.latitude, plant.longitude], icon("plant", severity, plant.id === selectedPlantId),
        `${plant.name}: ${severity ? `${openAlerts.length} open, worst ${severity}` : "no open alerts"}`, `Plant ${plant.name}`,
        () => cb.current.onSelectPlant(plant.id));
    }
    for (const p of panels) {
      mk([p.gps.lat, p.gps.lon], icon("panel", p.worst_severity, p.panel_id === selectedPanelId),
        `Panel ${p.panel_id}: ${p.detection_count} detection${p.detection_count === 1 ? "" : "s"}, worst ${p.worst_severity ?? "none"}`,
        `Panel ${p.panel_id}`, () => cb.current.onSelectPanel(p));
    }
  }, [pins, panels, selectedPlantId, selectedPanelId]);

  // Re-fit only when the set of points changes, not on selection.
  const fit: Array<[number, number]> = panels.length ? panels.map((p) => [p.gps.lat, p.gps.lon]) : pins.map((p) => [p.plant.latitude, p.plant.longitude]);
  const fitKey = fit.map((p) => p.join(",")).join("|");
  useEffect(() => {
    const m = map.current;
    if (!m || fit.length === 0) return;
    if (fit.length === 1) m.setView(fit[0], 15);
    else m.fitBounds(fit, { padding: [48, 48], maxZoom: 14 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey]);

  return <div ref={el} role="application" aria-label="Plant map" style={{ height: "100%", width: "100%" }} />;
}
