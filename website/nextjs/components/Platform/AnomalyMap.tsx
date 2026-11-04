'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'

export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'

export type ImagePoint = {
  image_id: string
  lat: number
  lon: number
  altitude_m: number
  detection_count: number
  critical_count: number
  synthetic: boolean
  thermal_filename?: string
  rgb_filename?: string
}

export type Anomaly = {
  id: string
  image_id: string
  lat: number
  lon: number
  severity: Severity
  class: string
  class_id: number
  confidence: number
  panel_id: string
  color: string
  synthetic: boolean
  thermal_filename?: string
}

export type AnomalyMapData = {
  job_id: string
  park_id: string
  flight_date: string
  total_images: number
  total_anomalies: number
  summary: Record<Severity, number>
  bounds:
    | {
        south: number
        north: number
        west: number
        east: number
        center: { lat: number; lon: number }
      }
    | null
  synthetic: boolean
  images: ImagePoint[]
  anomalies: Anomaly[]
}

export type ViewMode = 'markers' | 'cluster' | 'heatmap'
export type BasemapId = 'mapbox' | 'esri' | 'osm'

export type OrthoMeta = {
  park_id: string
  name: string
  crs: string
  width: number
  height: number
  band_count: number
  bounds: { west: number; south: number; east: number; north: number }
  center: { lat: number; lon: number }
  size_bytes: number
}

type Props = {
  apiBase: string
  data: AnomalyMapData
  loading?: boolean
  selectedAnomalyId?: string | null
  onAnomalySelect?: (id: string | null) => void
  viewMode?: ViewMode
  onViewModeChange?: (mode: ViewMode) => void
  basemap?: BasemapId
  onBasemapChange?: (id: BasemapId) => void
  ortho?: OrthoMeta | null
  orthos?: OrthoMeta[]
  onOrthoChange?: (ortho: OrthoMeta | null) => void
}

const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || ''

const BASEMAPS: Record<
  BasemapId,
  { label: string; url: string; attribution: string; maxZoom: number; needsToken?: boolean }
> = {
  mapbox: {
    label: 'Mapbox Satellite',
    url: `https://api.mapbox.com/styles/v1/mapbox/satellite-streets-v12/tiles/256/{z}/{x}/{y}@2x?access_token=${MAPBOX_TOKEN}`,
    attribution:
      '&copy; <a href="https://www.mapbox.com/about/maps/">Mapbox</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 22,
    needsToken: true,
  },
  esri: {
    // World Imagery only has high-res tiles in dense regions; setting maxNativeZoom
    // conservatively at 18 lets Leaflet upsample rather than fetch the "Map data
    // not yet available" placeholder tile that Esri serves at higher zoom.
    label: 'Esri World Imagery',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Imagery &copy; Esri',
    maxZoom: 18,
  },
  osm: {
    label: 'OpenStreetMap',
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  },
}

// 6 decimals ≈ 11 cm, 7 ≈ 1.1 cm at the equator
const COORD_PRECISION = 7

const LEAFLET_CSS = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'
const LEAFLET_JS = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'
const CLUSTER_CSS = 'https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css'
const CLUSTER_DEFAULT_CSS =
  'https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css'
const CLUSTER_JS = 'https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js'
const HEAT_JS = 'https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js'

const SEVERITY_ORDER: Severity[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
const SEVERITY_COLOR: Record<Severity, string> = {
  CRITICAL: '#dc2626',
  HIGH: '#ea580c',
  MEDIUM: '#d97706',
  LOW: '#0284c7',
}
const SEVERITY_WEIGHT: Record<Severity, number> = {
  CRITICAL: 1.0,
  HIGH: 0.75,
  MEDIUM: 0.5,
  LOW: 0.25,
}

function ensureLink(href: string) {
  if (typeof document === 'undefined') return
  if (!document.querySelector(`link[href="${href}"]`)) {
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = href
    document.head.appendChild(link)
  }
}

function loadScript(src: string): Promise<void> {
  if (typeof window === 'undefined') return Promise.resolve()
  const existing = document.querySelector<HTMLScriptElement>(`script[src="${src}"]`)
  if (existing) {
    if (existing.dataset.loaded === 'true') return Promise.resolve()
    return new Promise((resolve, reject) => {
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', () => reject(new Error(`Failed: ${src}`)))
    })
  }
  return new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = src
    script.async = true
    script.onload = () => {
      script.dataset.loaded = 'true'
      resolve()
    }
    script.onerror = () => reject(new Error(`Failed: ${src}`))
    document.head.appendChild(script)
  })
}

let leafletPromise: Promise<any> | null = null

async function loadLeaflet(): Promise<any> {
  if (typeof window === 'undefined') return null
  const w = window as any
  if (w.L && w.L.markerClusterGroup && w.L.heatLayer) return w.L
  if (leafletPromise) return leafletPromise

  leafletPromise = (async () => {
    ensureLink(LEAFLET_CSS)
    ensureLink(CLUSTER_CSS)
    ensureLink(CLUSTER_DEFAULT_CSS)
    await loadScript(LEAFLET_JS)
    await Promise.all([loadScript(CLUSTER_JS), loadScript(HEAT_JS)])
    return (window as any).L
  })()
  return leafletPromise
}

function buildDemoData(jobId: string): AnomalyMapData {
  const origin = { lat: 27.5396, lon: 71.907 }
  const images: ImagePoint[] = []
  const anomalies: Anomaly[] = []
  const cols = 8
  const total = 48
  const R = 6_371_000
  const toDeg = (m: number, lat0: number, axis: 'lat' | 'lon') => {
    if (axis === 'lat') return (m / R) * (180 / Math.PI)
    return (m / (R * Math.cos((lat0 * Math.PI) / 180))) * (180 / Math.PI)
  }

  for (let i = 0; i < total; i += 1) {
    let row = Math.floor(i / cols)
    let col = i % cols
    if (row % 2 === 1) col = cols - 1 - col
    const dx = (col - cols / 2) * 20
    const dy = -row * 25
    const lat = origin.lat + toDeg(dy, origin.lat, 'lat')
    const lon = origin.lon + toDeg(dx, origin.lat, 'lon')
    images.push({
      image_id: `IMG-${String(i).padStart(4, '0')}`,
      lat,
      lon,
      altitude_m: 42,
      detection_count: 0,
      critical_count: 0,
      synthetic: true,
    })
  }

  const seed = jobId.split('').reduce((acc, ch) => (acc + ch.charCodeAt(0)) % 9973, 1)
  const rand = (() => {
    let state = seed || 1
    return () => {
      state = (state * 1664525 + 1013904223) % 4294967296
      return state / 4294967296
    }
  })()
  const severities: Severity[] = ['CRITICAL', 'HIGH', 'HIGH', 'MEDIUM', 'MEDIUM', 'MEDIUM', 'LOW']
  const classes = [
    'hot-spot-high',
    'bypass-diode',
    'short-circuit',
    'cell-multi',
    'cell',
    'soiling',
    'module',
  ]

  for (let i = 0; i < 86; i += 1) {
    const parent = images[Math.floor(rand() * images.length)]
    const sev = severities[Math.floor(rand() * severities.length)]
    const dxm = (rand() - 0.5) * 18
    const dym = (rand() - 0.5) * 14
    const lat = parent.lat + toDeg(dym, parent.lat, 'lat')
    const lon = parent.lon + toDeg(dxm, parent.lat, 'lon')
    anomalies.push({
      id: `DEMO-${String(i).padStart(4, '0')}`,
      image_id: parent.image_id,
      lat,
      lon,
      severity: sev,
      class: classes[Math.floor(rand() * classes.length)],
      class_id: -1,
      confidence: 0.7 + rand() * 0.29,
      panel_id: `R${String(Math.floor(rand() * 22) + 1).padStart(2, '0')}-C${String(
        Math.floor(rand() * 26) + 1,
      ).padStart(2, '0')}`,
      color: SEVERITY_COLOR[sev],
      synthetic: true,
    })
    parent.detection_count += 1
    if (sev === 'CRITICAL') parent.critical_count += 1
  }

  const lats = [...images.map((i) => i.lat), ...anomalies.map((a) => a.lat)]
  const lons = [...images.map((i) => i.lon), ...anomalies.map((a) => a.lon)]

  return {
    job_id: jobId,
    park_id: 'DEMO',
    flight_date: new Date().toISOString().slice(0, 10),
    total_images: images.length,
    total_anomalies: anomalies.length,
    summary: anomalies.reduce(
      (acc, a) => {
        acc[a.severity] += 1
        return acc
      },
      { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 } as Record<Severity, number>,
    ),
    bounds: {
      south: Math.min(...lats),
      north: Math.max(...lats),
      west: Math.min(...lons),
      east: Math.max(...lons),
      center: {
        lat: lats.reduce((a, b) => a + b, 0) / lats.length,
        lon: lons.reduce((a, b) => a + b, 0) / lons.length,
      },
    },
    synthetic: true,
    images,
    anomalies,
  }
}

export function useMapData(apiBase: string, jobId: string, jobStatus: string) {
  // Only fetch real map data once the job is complete; use demo data for
  // in-progress or seeded jobs so we never fire a 404 against a job that
  // hasn't been fully persisted yet.
  const isComplete = jobStatus === 'completed'
  const query = useQuery({
    queryKey: [...queryKeys.jobs.mapData(jobId), apiBase],
    queryFn: async (): Promise<AnomalyMapData> => {
      const res = await fetch(`${apiBase}/map/${jobId}${api.authQuery('?')}`)
      if (!res.ok) throw new Error(`API returned ${res.status}`)
      return res.json()
    },
    enabled: isComplete,
    // One attempt, then the demo map — as before. Keep the previous map on
    // screen while the next job's loads.
    retry: false,
    placeholderData: keepPreviousData,
  })

  const demo = useMemo(() => buildDemoData(jobId), [jobId])
  const payload = query.data
  let data: AnomalyMapData | null = null
  if (!isComplete || query.isError) data = demo
  else if (payload) {
    data = payload.total_images === 0 && payload.total_anomalies === 0 ? demo : payload
  }
  const error = isComplete && query.error ? (query.error instanceof Error ? query.error.message : 'Map data unavailable') : null

  return { data, loading: isComplete && query.isFetching, error }
}

export default function AnomalyMap({
  apiBase,
  data,
  loading,
  selectedAnomalyId,
  onAnomalySelect,
  viewMode = 'markers',
  onViewModeChange,
  basemap,
  onBasemapChange,
  ortho,
  orthos,
  onOrthoChange,
}: Props) {
  const mapHostRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<any>(null)
  const baseTileRef = useRef<any>(null)
  const orthoTileRef = useRef<any>(null)
  const layersRef = useRef<{
    images?: any
    anomalies?: any
    cluster?: any
    heat?: any
  }>({})
  const markerIndexRef = useRef<Map<string, any>>(new Map())

  const effectiveBasemap: BasemapId = basemap || (MAPBOX_TOKEN ? 'mapbox' : 'esri')

  const [activeSeverities, setActiveSeverities] = useState<Record<Severity, boolean>>({
    CRITICAL: true,
    HIGH: true,
    MEDIUM: true,
    LOW: true,
  })

  const filteredAnomalies = useMemo(
    () => data.anomalies.filter((a) => activeSeverities[a.severity]),
    [data.anomalies, activeSeverities],
  )

  useEffect(() => {
    let cancelled = false

    async function mount() {
      if (!mapHostRef.current) return
      const L = await loadLeaflet()
      if (cancelled || !L || !mapHostRef.current) return

      if (!mapRef.current) {
        const map = L.map(mapHostRef.current, {
          zoomControl: true,
          attributionControl: true,
          scrollWheelZoom: true,
          maxZoom: 24,
        })
        mapRef.current = map
      }

      const map = mapRef.current

      // Basemap (managed by separate effect — make sure one is present on first mount)
      if (!baseTileRef.current) {
        const cfg = BASEMAPS[effectiveBasemap]
        baseTileRef.current = L.tileLayer(cfg.url, {
          maxNativeZoom: cfg.maxZoom,
          maxZoom: 24,
          attribution: cfg.attribution,
        }).addTo(map)
      }

      // Tear down previous layers
      const layers = layersRef.current
      if (layers.images) map.removeLayer(layers.images)
      if (layers.anomalies) map.removeLayer(layers.anomalies)
      if (layers.cluster) map.removeLayer(layers.cluster)
      if (layers.heat) map.removeLayer(layers.heat)
      markerIndexRef.current.clear()

      // Image-position layer (always shown — small dots underneath)
      const imagesLayer = L.layerGroup()
      data.images.forEach((img) => {
        const marker = L.circleMarker([img.lat, img.lon], {
          radius: 4,
          color: '#475569',
          weight: 1,
          fillColor: img.critical_count > 0 ? '#dc2626' : '#cbd5e1',
          fillOpacity: 0.7,
        })
        const imageUrl = img.thermal_filename
          ? `${apiBase}/image/${data.job_id}/${img.thermal_filename}${api.authQuery('?')}`
          : null
        marker.bindPopup(
          `<div style="font: 600 12px/1.4 Inter, sans-serif; color:#111827; min-width:220px">
            <div style="margin-bottom:4px">${img.image_id}</div>
            ${
              imageUrl
                ? `<img src="${imageUrl}" style="display:block; width:100%; max-width:240px; border-radius:6px; margin-bottom:6px" alt="thermal" />`
                : ''
            }
            <div style="color:#64748b; font-weight:500">
              ${img.detection_count} detection${img.detection_count === 1 ? '' : 's'} ·
              ${img.critical_count} critical
            </div>
            <div style="color:#94a3b8; font-weight:500; margin-top:4px">
              ${img.lat.toFixed(COORD_PRECISION)}, ${img.lon.toFixed(COORD_PRECISION)} · ${img.altitude_m} m
            </div>
          </div>`,
          { maxWidth: 280 },
        )
        imagesLayer.addLayer(marker)
      })
      imagesLayer.addTo(map)
      layers.images = imagesLayer

      if (viewMode === 'heatmap') {
        const points = filteredAnomalies.map((a) => [a.lat, a.lon, SEVERITY_WEIGHT[a.severity]])
        if (points.length > 0 && (L as any).heatLayer) {
          const heat = (L as any).heatLayer(points, {
            radius: 24,
            blur: 18,
            maxZoom: 18,
            gradient: { 0.2: '#0284c7', 0.4: '#d97706', 0.7: '#ea580c', 1.0: '#dc2626' },
          })
          heat.addTo(map)
          layers.heat = heat
        }
      } else {
        const container =
          viewMode === 'cluster' && (L as any).markerClusterGroup
            ? (L as any).markerClusterGroup({
                showCoverageOnHover: false,
                disableClusteringAtZoom: 19,
                spiderfyOnMaxZoom: true,
                maxClusterRadius: 45,
              })
            : L.layerGroup()

        filteredAnomalies.forEach((a) => {
          const isSelected = selectedAnomalyId === a.id
          const marker = L.circleMarker([a.lat, a.lon], {
            radius: isSelected
              ? 11
              : a.severity === 'CRITICAL'
                ? 8
                : a.severity === 'HIGH'
                  ? 7
                  : 6,
            color: isSelected ? '#0f172a' : '#0f172a',
            weight: isSelected ? 3 : 1.4,
            fillColor: a.color,
            fillOpacity: 0.95,
          })
          const imageUrl = a.thermal_filename
            ? `${apiBase}/image/${data.job_id}/${a.thermal_filename}${api.authQuery('?')}`
            : null
          marker.bindPopup(
            `<div style="font: 500 12px/1.5 Inter, sans-serif; color:#111827; min-width:220px">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px">
                <strong style="font-size:13px">${a.class}</strong>
                <span style="background:${a.color}; color:#fff; padding:2px 8px; border-radius:999px; font-size:10px; font-weight:800; text-transform:uppercase">
                  ${a.severity}
                </span>
              </div>
              ${
                imageUrl
                  ? `<img src="${imageUrl}" style="display:block; width:100%; max-width:240px; border-radius:6px; margin-bottom:6px" alt="annotated thermal" />`
                  : ''
              }
              <div style="color:#475569">Panel <strong>${a.panel_id}</strong></div>
              <div style="color:#475569">Image <strong>${a.image_id}</strong></div>
              <div style="color:#475569">Confidence <strong>${Math.round(a.confidence * 100)}%</strong></div>
              <div style="color:#94a3b8; font-size:11px; margin-top:4px">
                ${a.lat.toFixed(COORD_PRECISION)}, ${a.lon.toFixed(COORD_PRECISION)}
              </div>
            </div>`,
            { maxWidth: 280 },
          )
          marker.on('click', () => onAnomalySelect?.(a.id))
          marker.on('popupclose', () => {
            if (selectedAnomalyId === a.id) onAnomalySelect?.(null)
          })
          markerIndexRef.current.set(a.id, marker)
          container.addLayer(marker)
        })
        container.addTo(map)
        if (viewMode === 'cluster') layers.cluster = container
        else layers.anomalies = container
      }

      if (data.bounds) {
        const { south, west, north, east } = data.bounds
        map.fitBounds(
          [
            [south, west],
            [north, east],
          ],
          { padding: [28, 28], maxZoom: 19 },
        )
      } else {
        map.setView([27.54, 71.91], 16)
      }
    }

    mount()
    return () => {
      cancelled = true
    }
  }, [data, filteredAnomalies, viewMode, apiBase, selectedAnomalyId, onAnomalySelect])

  useEffect(() => {
    if (!selectedAnomalyId) return
    const marker = markerIndexRef.current.get(selectedAnomalyId)
    if (marker && mapRef.current) {
      mapRef.current.flyTo(marker.getLatLng(), Math.max(mapRef.current.getZoom(), 18), {
        duration: 0.6,
      })
      marker.openPopup()
    }
  }, [selectedAnomalyId])

  // Basemap swap effect — keeps Leaflet's tile layer in sync with the prop
  useEffect(() => {
    let cancelled = false
    async function swap() {
      const L = await loadLeaflet()
      if (cancelled || !L || !mapRef.current) return
      const cfg = BASEMAPS[effectiveBasemap]
      if (baseTileRef.current) {
        mapRef.current.removeLayer(baseTileRef.current)
      }
      baseTileRef.current = L.tileLayer(cfg.url, {
        maxNativeZoom: cfg.maxZoom,
        maxZoom: 24,
        attribution: cfg.attribution,
      })
      baseTileRef.current.addTo(mapRef.current)
      // Keep ortho on top
      if (orthoTileRef.current) {
        orthoTileRef.current.bringToFront()
      }
    }
    swap()
    return () => {
      cancelled = true
    }
  }, [effectiveBasemap])

  // Ortho overlay effect — adds/removes the customer's georeferenced tiles
  useEffect(() => {
    let cancelled = false
    async function attach() {
      const L = await loadLeaflet()
      if (cancelled || !L || !mapRef.current) return
      if (orthoTileRef.current) {
        mapRef.current.removeLayer(orthoTileRef.current)
        orthoTileRef.current = null
      }
      if (!ortho) return

      const url = `${apiBase}/park/${encodeURIComponent(ortho.park_id)}/ortho/${encodeURIComponent(
        ortho.name,
      )}/tiles/{z}/{x}/{y}.png${api.authQuery('?')}`
      const tile = L.tileLayer(url, {
        maxZoom: 24,
        opacity: 0.95,
        attribution: `Ortho · ${ortho.name}`,
      })
      tile.addTo(mapRef.current)
      orthoTileRef.current = tile

      // Snap to ortho footprint
      const { south, west, north, east } = ortho.bounds
      mapRef.current.fitBounds(
        [
          [south, west],
          [north, east],
        ],
        { padding: [28, 28], maxZoom: 22 },
      )
    }
    attach()
    return () => {
      cancelled = true
    }
  }, [ortho, apiBase])

  useEffect(() => {
    return () => {
      if (mapRef.current) {
        mapRef.current.remove()
        mapRef.current = null
        layersRef.current = {}
        markerIndexRef.current.clear()
      }
    }
  }, [])

  function toggleSeverity(sev: Severity) {
    setActiveSeverities((current) => ({ ...current, [sev]: !current[sev] }))
  }

  const modes: { id: ViewMode; label: string }[] = [
    { id: 'markers', label: 'Markers' },
    { id: 'cluster', label: 'Cluster' },
    { id: 'heatmap', label: 'Heatmap' },
  ]

  return (
    <div className="anomaly-map">
      <style jsx>{`
        .anomaly-map {
          display: grid;
          grid-template-rows: auto 1fr auto;
          gap: 10px;
        }
        .controls {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          align-items: center;
          justify-content: space-between;
        }
        .legend,
        .modes {
          display: flex;
          gap: 6px;
          flex-wrap: wrap;
        }
        .legend button,
        .modes button {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 4px 10px;
          font: inherit;
          font-size: 11px;
          font-weight: 800;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          border: 1px solid #e2e8f0;
          border-radius: 999px;
          background: #ffffff;
          color: #475569;
          cursor: pointer;
        }
        .legend button.active,
        .modes button.active {
          color: #0f172a;
          border-color: #0f172a;
          background: #f8fafc;
        }
        .legend .dot {
          width: 10px;
          height: 10px;
          border-radius: 999px;
          border: 1.5px solid #0f172a;
        }
        .map-host {
          position: relative;
          height: 380px;
          border-radius: 8px;
          border: 1px solid #e2e8f0;
          overflow: hidden;
          background: #e2e8f0;
        }
        .status {
          position: absolute;
          top: 10px;
          left: 10px;
          z-index: 500;
          padding: 6px 10px;
          border-radius: 6px;
          background: rgba(15, 23, 42, 0.85);
          color: #f8fafc;
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 0.03em;
        }
        .meta {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          font-size: 11px;
          color: #475569;
        }
        .badge {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 4px 8px;
          border: 1px solid #e2e8f0;
          border-radius: 999px;
          background: #f8fafc;
          font-weight: 700;
        }
        .badge.synthetic {
          background: #fff7ed;
          border-color: #fed7aa;
          color: #9a3412;
        }
        .badge.ortho {
          background: #ecfeff;
          border-color: #a5f3fc;
          color: #155e75;
        }
        .selector {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          font-size: 11px;
          font-weight: 700;
          color: #475569;
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }
        .selector select {
          font: inherit;
          padding: 4px 8px;
          border: 1px solid #cbd5e1;
          border-radius: 6px;
          background: #ffffff;
          color: #0f172a;
          text-transform: none;
          letter-spacing: 0;
          font-weight: 600;
        }
        .note {
          font-size: 11px;
          color: #64748b;
          padding: 6px 0;
        }
      `}</style>

      <div className="controls">
        <div className="legend">
          {SEVERITY_ORDER.map((sev) => (
            <button
              key={sev}
              type="button"
              className={activeSeverities[sev] ? 'active' : ''}
              onClick={() => toggleSeverity(sev)}
            >
              <span className="dot" style={{ background: SEVERITY_COLOR[sev] }} />
              {sev} ({data.summary[sev] ?? 0})
            </button>
          ))}
        </div>
        <div className="modes">
          {modes.map((mode) => (
            <button
              key={mode.id}
              type="button"
              className={viewMode === mode.id ? 'active' : ''}
              onClick={() => onViewModeChange?.(mode.id)}
            >
              {mode.label}
            </button>
          ))}
        </div>
      </div>

      <div className="controls">
        <label className="selector">
          Basemap
          <select
            value={effectiveBasemap}
            onChange={(event) => onBasemapChange?.(event.target.value as BasemapId)}
          >
            {(Object.keys(BASEMAPS) as BasemapId[]).map((id) => {
              const cfg = BASEMAPS[id]
              const disabled = cfg.needsToken && !MAPBOX_TOKEN
              return (
                <option key={id} value={id} disabled={disabled}>
                  {cfg.label}
                  {disabled ? ' — token required' : ''}
                </option>
              )
            })}
          </select>
        </label>
        {orthos !== undefined && (
          <label className="selector">
            Orthomosaic
            <select
              value={ortho?.name ?? ''}
              onChange={(event) => {
                const name = event.target.value
                if (!name) {
                  onOrthoChange?.(null)
                  return
                }
                const found = (orthos || []).find((o) => o.name === name) || null
                onOrthoChange?.(found)
              }}
            >
              <option value="">— none —</option>
              {(orthos || []).map((o) => (
                <option key={o.name} value={o.name}>
                  {o.name} ({o.width}×{o.height})
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div className="map-host" ref={mapHostRef}>
        {loading && <div className="status">Loading map…</div>}
        {!loading && data.synthetic && (
          <div className="status">Demo coordinates — upload geotagged images for live GPS</div>
        )}
      </div>

      <div className="meta">
        <span className="badge">{data.total_images} images</span>
        <span className="badge">{data.total_anomalies} anomalies</span>
        <span className="badge">{filteredAnomalies.length} shown</span>
        {data.bounds && (
          <span className="badge">
            center {data.bounds.center.lat.toFixed(COORD_PRECISION)},{' '}
            {data.bounds.center.lon.toFixed(COORD_PRECISION)}
          </span>
        )}
        {ortho && (
          <span className="badge ortho">
            ortho · {ortho.width}×{ortho.height} · {ortho.crs}
          </span>
        )}
        {data.synthetic && <span className="badge synthetic">synthetic GPS</span>}
      </div>
      <div className="note">
        Centimeter accuracy requires either an RTK/PPK source drone or an uploaded orthomosaic with
        ground-control points. EXIF GPS alone is ±2–5 m.
      </div>
    </div>
  )
}
