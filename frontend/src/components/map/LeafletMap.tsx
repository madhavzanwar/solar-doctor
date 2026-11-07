"use client";

import { useEffect } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { MapContainer, Marker, TileLayer, useMap } from "react-leaflet";
import type { GridPanel } from "@/lib/api";
import { BASEMAPS, severityKey, type BasemapId, type PlantPin } from "@/lib/map";

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

function Fit({ points }: { points: Array<[number, number]> }) {
  const map = useMap();
  const key = points.map((p) => p.join(",")).join("|");
  useEffect(() => {
    if (points.length === 1) map.setView(points[0], 15);
    else if (points.length > 1) map.fitBounds(points, { padding: [48, 48], maxZoom: 14 });
    // re-fit only when the point set changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, map]);
  return null;
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
  const base = BASEMAPS[basemap];
  const fitPoints: Array<[number, number]> = panels.length
    ? panels.map((p) => [p.gps.lat, p.gps.lon])
    : pins.map((p) => [p.plant.latitude, p.plant.longitude]);
  return (
    <MapContainer center={[22.5, 79]} zoom={4} scrollWheelZoom style={{ height: "100%", width: "100%" }} aria-label="Plant map">
      <TileLayer key={basemap} url={base.url} attribution={base.attribution} maxZoom={base.maxZoom} maxNativeZoom={base.maxZoom} />
      <Fit points={fitPoints} />
      {pins.map(({ plant, severity, openAlerts }) => (
        <Marker
          key={plant.id}
          position={[plant.latitude, plant.longitude]}
          icon={icon("plant", severity, plant.id === selectedPlantId)}
          title={`${plant.name}: ${severity ? `${openAlerts.length} open, worst ${severity}` : "no open alerts"}`}
          alt={`Plant ${plant.name}`}
          eventHandlers={{ click: () => onSelectPlant(plant.id), keypress: (e) => (e.originalEvent as KeyboardEvent).key === "Enter" && onSelectPlant(plant.id) }}
        />
      ))}
      {panels.map((p) => (
        <Marker
          key={p.panel_id}
          position={[p.gps.lat, p.gps.lon]}
          icon={icon("panel", p.worst_severity, p.panel_id === selectedPanelId)}
          title={`Panel ${p.panel_id}: ${p.detection_count} detection${p.detection_count === 1 ? "" : "s"}, worst ${p.worst_severity ?? "none"}`}
          alt={`Panel ${p.panel_id}`}
          eventHandlers={{ click: () => onSelectPanel(p), keypress: (e) => (e.originalEvent as KeyboardEvent).key === "Enter" && onSelectPanel(p) }}
        />
      ))}
    </MapContainer>
  );
}
