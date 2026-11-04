// website/nextjs/components/Platform/PlanMap.tsx
'use client'

import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import 'leaflet-draw'
import 'leaflet-draw/dist/leaflet.draw.css'
import type { LatLon, Waypoint, MissionStats, MissionType } from '@/lib/missionGeometry'

// Mapbox temporarily disabled — fall back to the previous Esri World Imagery
// tiles. Set USE_MAPBOX back to true (with NEXT_PUBLIC_MAPBOX_TOKEN set) to re-enable.
const USE_MAPBOX = false
const MAPBOX_TOKEN = USE_MAPBOX ? (process.env.NEXT_PUBLIC_MAPBOX_TOKEN || '') : ''

const SAT_URL = MAPBOX_TOKEN
  ? `https://api.mapbox.com/styles/v1/mapbox/satellite-streets-v12/tiles/{z}/{x}/{y}?access_token=${MAPBOX_TOKEN}`
  : 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'

const SAT_ATTR = MAPBOX_TOKEN
  ? '© Mapbox © OpenStreetMap'
  : 'Tiles © Esri — Source: Esri, DigitalGlobe, GeoEye, Earthstar Geographics, CNES/Airbus DS, USDA, USGS, AeroGRID, IGN, and the GIS User Community'
// Esri World Imagery often serves "Map data not yet available" placeholders at
// z19+ outside dense coverage areas. Cap native fetches at 18 and let Leaflet
// upscale so operators can still zoom closer without losing the image.
const SAT_MAX_NATIVE_ZOOM = MAPBOX_TOKEN ? 22 : 18
const SAT_MAX_ZOOM = 24

const LEG_COLORS = ['#06b6d4', '#f59e0b', '#a855f7', '#10b981', '#ef4444', '#3b82f6']
const MAX_ARROWS = 40

type Props = {
  missionType: MissionType
  polygon: LatLon[] | null
  waypoints: Waypoint[]
  stats: MissionStats | null
  orbitRadiusM?: number
  fitKey?: number
  solarRows?: LatLon[]
  selectingRows?: boolean
  onShapeDrawn: (points: LatLon[]) => void
  onSolarRowsChange?: (rows: LatLon[]) => void
  onClear: () => void
}

function fmtTime(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = Math.round(sec % 60)
  return `${m}m ${s}s`
}

// Planar (equirectangular) ring area in m², around the first point.
function ringAreaM2(pts: L.LatLng[]): number {
  if (pts.length < 3) return 0
  const lat0 = (pts[0].lat * Math.PI) / 180
  const mPerLon = 111320 * Math.cos(lat0)
  const mPerLat = 111320
  const xy = pts.map((p) => ({ x: (p.lng - pts[0].lng) * mPerLon, y: (p.lat - pts[0].lat) * mPerLat }))
  let a = 0
  for (let i = 0; i < xy.length; i++) {
    const j = (i + 1) % xy.length
    a += xy[i].x * xy[j].y - xy[j].x * xy[i].y
  }
  return Math.abs(a / 2)
}

export default function PlanMap({
  missionType,
  polygon,
  waypoints,
  stats,
  orbitRadiusM,
  fitKey,
  solarRows = [],
  selectingRows = false,
  onShapeDrawn,
  onSolarRowsChange,
  onClear,
}: Props) {
  const mapDivRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const drawnRef = useRef<L.FeatureGroup | null>(null)
  const pathRef = useRef<L.LayerGroup | null>(null)
  const boundaryRef = useRef<L.LayerGroup | null>(null)
  const rowsLayerRef = useRef<L.LayerGroup | null>(null)
  const rowsRef = useRef<LatLon[]>([])
  const measureLayerRef = useRef<L.LayerGroup | null>(null)
  const measurePtsRef = useRef<L.LatLng[]>([])
  const onShapeDrawnRef = useRef(onShapeDrawn)
  const onClearRef = useRef(onClear)
  onShapeDrawnRef.current = onShapeDrawn
  onClearRef.current = onClear

  const [north, setNorth] = useState('')
  const [east, setEast] = useState('')
  const [coordError, setCoordError] = useState('')
  const [measuring, setMeasuring] = useState(false)
  const [measureInfo, setMeasureInfo] = useState({ dist: 0, area: 0, count: 0 })

  function recenter() {
    const map = mapRef.current
    const lat = parseFloat(north)
    const lon = parseFloat(east)
    if (!map) return
    if (Number.isNaN(lat) || Number.isNaN(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      setCoordError('Enter valid N/E')
      return
    }
    setCoordError('')
    map.setView([lat, lon], Math.max(map.getZoom(), 17))
  }

  function redrawMeasure() {
    const layer = measureLayerRef.current
    if (!layer) return
    layer.clearLayers()
    const pts = measurePtsRef.current
    for (const p of pts) L.circleMarker(p, { radius: 3, color: '#f59e0b', fillOpacity: 1 }).addTo(layer)
    if (pts.length >= 2) L.polyline(pts, { color: '#f59e0b', weight: 2, dashArray: '4' }).addTo(layer)
    let dist = 0
    for (let i = 1; i < pts.length; i++) dist += pts[i - 1].distanceTo(pts[i])
    setMeasureInfo({ dist, area: ringAreaM2(pts), count: pts.length })
  }

  function clearMeasure() {
    measurePtsRef.current = []
    redrawMeasure()
  }

  // Initialise map once
  useEffect(() => {
    if (!mapDivRef.current || mapRef.current) return
    const map = L.map(mapDivRef.current, { center: [18.5204, 73.8567], zoom: 16, maxZoom: SAT_MAX_ZOOM })
    // Plain tile layer for both providers. SAT_URL already points at the same
    // Esri World Imagery endpoint esri-leaflet's basemapLayer('Imagery') uses,
    // and basemapLayer additionally fires an XHR for dynamic attribution whose
    // callback calls map.getBounds() with no liveness check — switching away
    // from the Plan tab before it lands threw "Cannot read properties of
    // undefined (reading '_leaflet_pos')". It also logs a deprecation warning.
    L.tileLayer(SAT_URL, {
      attribution: SAT_ATTR,
      maxZoom: SAT_MAX_ZOOM,
      maxNativeZoom: SAT_MAX_NATIVE_ZOOM,
    }).addTo(map)

    const drawn = new L.FeatureGroup()
    map.addLayer(drawn)
    drawnRef.current = drawn
    boundaryRef.current = L.layerGroup().addTo(map)
    rowsLayerRef.current = L.layerGroup().addTo(map)
    pathRef.current = L.layerGroup().addTo(map)
    measureLayerRef.current = L.layerGroup().addTo(map)

    map.on(L.Draw.Event.CREATED, (e: any) => {
      drawn.clearLayers()
      const layer = e.layer
      drawn.addLayer(layer)
      if (typeof layer.getLatLngs === 'function') {
        const raw = layer.getLatLngs()
        const latlngs = (Array.isArray(raw?.[0]) ? raw[0] : raw ?? []) as L.LatLng[]
        const pts: LatLon[] = (Array.isArray(latlngs) ? latlngs : []).map((ll: L.LatLng) => ({ lat: ll.lat, lon: ll.lng }))
        onShapeDrawnRef.current(pts)
      } else if (typeof layer.getLatLng === 'function') {
        const ll = layer.getLatLng() as L.LatLng
        onShapeDrawnRef.current([{ lat: ll.lat, lon: ll.lng }])
      }
    })

    map.on(L.Draw.Event.DELETED, () => {
      onClearRef.current()
    })

    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  // Draw control by mission type (polygon / polyline / marker)
  useEffect(() => {
    const map = mapRef.current
    const drawn = drawnRef.current
    if (!map || !drawn) return
    const tool = missionType === 'corridor' ? 'polyline' : missionType === 'orbit' ? 'marker' : 'polygon'
    const control = new L.Control.Draw({
      draw: {
        polygon: tool === 'polygon' ? ({ shapeOptions: { color: '#0ea5e9' } } as any) : false,
        polyline: tool === 'polyline' ? ({ shapeOptions: { color: '#0ea5e9' } } as any) : false,
        marker: tool === 'marker' ? ({} as any) : false,
        rectangle: false,
        circle: false,
        circlemarker: false,
      },
      edit: { featureGroup: drawn, remove: true } as any,
    })
    map.addControl(control)
    return () => {
      map.removeControl(control)
    }
  }, [missionType])

  useEffect(() => {
    rowsRef.current = solarRows
  }, [solarRows])

  // Solar row picker: click one center point per row after drawing the area.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    function onClick(e: L.LeafletMouseEvent) {
      const next = [...rowsRef.current, { lat: e.latlng.lat, lon: e.latlng.lng }]
      rowsRef.current = next
      onSolarRowsChange?.(next)
    }
    if (selectingRows && missionType === 'solar') map.on('click', onClick)
    return () => {
      map.off('click', onClick)
    }
  }, [selectingRows, missionType, onSolarRowsChange])

  // Redraw clicked solar row centers.
  useEffect(() => {
    const layer = rowsLayerRef.current
    if (!layer) return
    layer.clearLayers()
    if (missionType !== 'solar') return
    for (const row of solarRows) {
      L.circleMarker([row.lat, row.lon], { radius: 4, color: '#2563eb', fillColor: '#2563eb', fillOpacity: 1 })
        .bindTooltip('Solar row')
        .addTo(layer)
    }
  }, [solarRows, missionType])

  // Boundary outline of the current survey polygon (visible before waypoints compute)
  useEffect(() => {
    const layer = boundaryRef.current
    if (!layer) return
    layer.clearLayers()
    if (missionType !== 'orbit' && polygon && polygon.length >= 2) {
      const ll = polygon.map((p) => [p.lat, p.lon] as [number, number])
      L.polyline([...ll, ll[0]], { color: '#0ea5e9', weight: 1, opacity: 0.5, dashArray: '6' }).addTo(layer)
    }
  }, [polygon, missionType])

  // Fit the map to the generated route (or polygon) on import / load (fitKey changes)
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const src: [number, number][] = waypoints.length >= 1
      ? waypoints.map((w) => [w.lat, w.lon] as [number, number])
      : (polygon ?? []).map((p) => [p.lat, p.lon] as [number, number])
    if (src.length < 1) return
    const bounds = L.latLngBounds(src)
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 19 })
  }, [fitKey]) // eslint-disable-line react-hooks/exhaustive-deps

  // Measure tool: collect clicks while active
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    function onClick(e: L.LeafletMouseEvent) {
      measurePtsRef.current.push(e.latlng)
      redrawMeasure()
    }
    if (measuring) {
      map.on('click', onClick)
    } else {
      clearMeasure()
    }
    return () => {
      map.off('click', onClick)
    }
  }, [measuring])

  // Redraw the flight path (leg-colored), drone-facing arrows, and orbit guide
  useEffect(() => {
    const layer = pathRef.current
    if (!layer) return
    layer.clearLayers()

    if (missionType === 'orbit' && polygon && polygon[0] && orbitRadiusM) {
      L.circle([polygon[0].lat, polygon[0].lon], {
        radius: orbitRadiusM, color: '#0ea5e9', weight: 1, fill: false, dashArray: '4',
      }).addTo(layer)
      L.circleMarker([polygon[0].lat, polygon[0].lon], { radius: 4, color: '#0ea5e9', fillOpacity: 1 })
        .bindTooltip('Center')
        .addTo(layer)
    }

    if (waypoints.length < 2) return

    type Group = { leg: number; pts: [number, number][] }
    const groups: Group[] = []
    for (const wp of waypoints) {
      const leg = wp.leg ?? 0
      const last = groups[groups.length - 1]
      const ll: [number, number] = [wp.lat, wp.lon]
      if (!last || last.leg !== leg) {
        const seed: [number, number][] = last ? [last.pts[last.pts.length - 1]] : []
        groups.push({ leg, pts: [...seed, ll] })
      } else {
        last.pts.push(ll)
      }
    }
    for (const g of groups) {
      L.polyline(g.pts, { color: LEG_COLORS[g.leg % LEG_COLORS.length], weight: 2, opacity: 0.9 }).addTo(layer)
    }

    const step = Math.max(1, Math.floor(waypoints.length / MAX_ARROWS))
    for (let i = 0; i < waypoints.length; i += step) {
      const wp = waypoints[i]
      const h = wp.heading ?? 0
      const icon = L.divIcon({
        className: 'drone-arrow',
        html: `<div style="transform:rotate(${h}deg);color:#0ea5e9;font-size:14px;line-height:1">▲</div>`,
        iconSize: [14, 14],
        iconAnchor: [7, 7],
      })
      L.marker([wp.lat, wp.lon], { icon, interactive: false }).addTo(layer)
    }

    const first: [number, number] = [waypoints[0].lat, waypoints[0].lon]
    const lastWp: [number, number] = [waypoints[waypoints.length - 1].lat, waypoints[waypoints.length - 1].lon]
    L.circleMarker(first, { radius: 6, color: '#0ea5e9', fillOpacity: 1 }).bindTooltip('Start').addTo(layer)
    L.circleMarker(lastWp, { radius: 6, color: '#10b981', fillOpacity: 1 }).bindTooltip('End').addTo(layer)
  }, [waypoints, missionType, polygon, orbitRadiusM])

  return (
    <div className="plan-map">
      <div ref={mapDivRef} style={{ position: 'absolute', inset: 0 }} />

      {/* Jump-to-coordinate box */}
      <div
        className="plan-coord-box"
        style={{
          position: 'absolute', top: 12, right: 12, zIndex: 800,
          display: 'flex', alignItems: 'center', gap: 6,
          background: 'rgba(255,255,255,.92)', border: '1px solid #e2e8f0',
          borderRadius: 6, padding: '6px 8px', boxShadow: '0 2px 8px rgba(15,23,42,.12)',
        }}
      >
        <input
          value={north} onChange={(e) => setNorth(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') recenter() }}
          placeholder="North (lat)" inputMode="decimal" aria-label="North latitude"
          style={{ width: 92, fontSize: 12, boxSizing: 'border-box' }}
        />
        <input
          value={east} onChange={(e) => setEast(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') recenter() }}
          placeholder="East (lon)" inputMode="decimal" aria-label="East longitude"
          style={{ width: 92, fontSize: 12, boxSizing: 'border-box' }}
        />
        <button type="button" className="secondary" style={{ padding: '2px 8px', fontSize: 12 }} onClick={recenter}>Go</button>
        {coordError && <span style={{ color: '#ef4444', fontSize: 11 }}>{coordError}</span>}
      </div>

      {/* Measure tool (bottom-left) */}
      <div
        style={{
          position: 'absolute', bottom: 12, left: 12, zIndex: 800,
          display: 'flex', alignItems: 'center', gap: 8,
          background: 'rgba(255,255,255,.92)', border: '1px solid #e2e8f0',
          borderRadius: 6, padding: '6px 8px', boxShadow: '0 2px 8px rgba(15,23,42,.12)', fontSize: 12,
        }}
      >
        <button
          type="button"
          className={measuring ? 'primary' : 'secondary'}
          style={{ padding: '2px 8px', fontSize: 12 }}
          onClick={() => setMeasuring((v) => !v)}
        >
          {measuring ? 'Measuring…' : 'Measure'}
        </button>
        {measuring && (
          <>
            <span>{(measureInfo.dist / 1000).toFixed(3)} km</span>
            {measureInfo.count >= 3 && <span>{(measureInfo.area / 10000).toFixed(2)} ha</span>}
            <button type="button" className="secondary" style={{ padding: '2px 8px', fontSize: 12 }} onClick={clearMeasure}>Clear</button>
          </>
        )}
      </div>

      {stats && (
        <div className="plan-stats-bar">
          <span>Area <strong>{stats.areaHa.toFixed(1)} ha</strong></span>
          <span>Images <strong>{stats.imageCount}</strong></span>
          <span>Distance <strong>{(stats.distanceM / 1000).toFixed(2)} km</strong></span>
          <span>Time <strong>{fmtTime(stats.flightTimeSec)}</strong></span>
          <span>Batteries <strong>{stats.batteryCount}</strong></span>
          <span>GSD <strong style={{ color: '#0ea5e9' }}>{stats.gsdCm.toFixed(2)} cm/px</strong></span>
        </div>
      )}
    </div>
  )
}
