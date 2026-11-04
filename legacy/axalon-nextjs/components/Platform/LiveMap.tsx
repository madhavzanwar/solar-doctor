// website/nextjs/components/Platform/LiveMap.tsx
"use client";

import { useEffect, useRef, useState } from "react";
import "leaflet/dist/leaflet.css";
import type { LatLon } from "@/lib/track";
import type { PlannedPoint } from "@/lib/missionToWaypoints";
import { routeBounds, routeLatLngs, routeMarkers, shouldFitToRoute } from "@/lib/liveRoute";

// Leaflet is loaded client-side only (same approach as PlanMap.tsx).
interface Props {
  position: LatLon | null;
  headingDeg: number;
  track: LatLon[];
  follow?: boolean;
  /** Route staged in the Plan tab — what "Upload mission" would send. */
  plannedRoute?: PlannedPoint[];
}

const NO_ROUTE: PlannedPoint[] = [];

export default function LiveMap({ position, headingDeg, track, follow = true, plannedRoute = NO_ROUTE }: Props) {
  const leafletRef = useRef<any>(null);
  const mapRef = useRef<any>(null);
  const markerRef = useRef<any>(null);
  const lineRef = useRef<any>(null);
  const routeLayerRef = useRef<any>(null);
  const routeFittedRef = useRef(false);
  const hasTelemetryRef = useRef(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  // Leaflet arrives via dynamic import; layer effects wait for this so a route
  // or first fix that lands before the map exists still gets drawn.
  const [isMapReady, setIsMapReady] = useState(false);

  // init map once
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const L = (await import("leaflet")).default;
      if (cancelled || !containerRef.current || mapRef.current) return;
      const map = L.map(containerRef.current).setView([20, 0], 2);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap",
        maxZoom: 19,
      }).addTo(map);
      // Added before the breadcrumb so the flown track draws over the plan.
      routeLayerRef.current = L.layerGroup().addTo(map);
      leafletRef.current = L;
      mapRef.current = map;
      setIsMapReady(true);
    })();
    return () => {
      cancelled = true;
      const map = mapRef.current;
      // Drop every layer handle first: nothing may touch a removed map.
      mapRef.current = null;
      markerRef.current = null;
      lineRef.current = null;
      routeLayerRef.current = null;
      map?.remove();
    };
  }, []);

  useEffect(() => {
    hasTelemetryRef.current = position !== null;
  }, [position]);

  // update marker + breadcrumb on telemetry
  useEffect(() => {
    const L = leafletRef.current;
    const map = mapRef.current;
    if (!isMapReady || !L || !map || !position) return;
    const latlng: [number, number] = [position.lat, position.lon];

    // rotated drone marker via a divIcon (▲ rotated to heading)
    const icon = L.divIcon({
      className: "live-drone-marker",
      html: `<div style="transform:rotate(${headingDeg}deg)">▲</div>`,
      iconSize: [24, 24],
      iconAnchor: [12, 12],
    });
    if (!markerRef.current) {
      markerRef.current = L.marker(latlng, { icon, zIndexOffset: 1000 }).addTo(map);
    } else {
      markerRef.current.setLatLng(latlng);
      markerRef.current.setIcon(icon);
    }

    const pts = track.map((p) => [p.lat, p.lon] as [number, number]);
    if (!lineRef.current) {
      lineRef.current = L.polyline(pts, { color: "#14b8a6", weight: 2 }).addTo(map);
    } else {
      lineRef.current.setLatLngs(pts);
    }

    if (follow) map.panTo(latlng, { animate: true });
    if (map.getZoom() < 15) map.setView(latlng, 17);
  }, [isMapReady, position, headingDeg, track, follow]);

  // planned route: dashed line + S / numbered / E markers, rebuilt in place
  useEffect(() => {
    const L = leafletRef.current;
    const map = mapRef.current;
    const layer = routeLayerRef.current;
    if (!isMapReady || !L || !map || !layer) return;

    layer.clearLayers();
    if (plannedRoute.length === 0) {
      // A cleared route may be replaced by a new one: frame that one too.
      routeFittedRef.current = false;
      return;
    }

    const pts = routeLatLngs(plannedRoute);
    if (pts.length >= 2) {
      L.polyline(pts, {
        color: "#f59e0b",
        weight: 3,
        opacity: 0.9,
        dashArray: "8 6",
        interactive: false,
      }).addTo(layer);
    }
    for (const marker of routeMarkers(plannedRoute)) {
      L.marker(marker.latlng, {
        icon: L.divIcon({
          className: `live-route-marker live-route-marker--${marker.kind}`,
          html: marker.label,
          iconSize: [18, 18],
          iconAnchor: [9, 9],
        }),
        interactive: false,
        keyboard: false,
      }).addTo(layer);
    }

    const shouldFit = shouldFitToRoute({
      routeLength: pts.length,
      hasTelemetry: hasTelemetryRef.current,
      alreadyFitted: routeFittedRef.current,
    });
    const bounds = routeBounds(plannedRoute);
    if (shouldFit && bounds) {
      // No animation: an animation frame must not outlive an unmounted map.
      map.fitBounds(bounds, { padding: [32, 32], maxZoom: 18, animate: false });
      routeFittedRef.current = true;
    }
  }, [isMapReady, plannedRoute]);

  return <div ref={containerRef} className="live-map" />;
}
