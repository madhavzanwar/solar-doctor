'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import type { GridPanel } from '@/lib/api'
import { API_BASE, api } from '@/lib/api'

const SEVERITY_COLOR: Record<string, string> = {
  CRITICAL: '#dc2626',
  HIGH: '#ea580c',
  MEDIUM: '#ca8a04',
  LOW: '#0284c7',
}

export type OrthoMapProps = {
  parkId: string
  orthoName: string
  bounds: { west: number; south: number; east: number; north: number }
  center: { lat: number; lon: number }
  panels: GridPanel[]
}

type GoogleMaps = {
  Map: new (node: HTMLElement, options: Record<string, unknown>) => GoogleMap
  LatLngBounds: new (
    sw: { lat: number; lng: number },
    ne: { lat: number; lng: number },
  ) => GoogleLatLngBounds
  ImageMapType: new (options: Record<string, unknown>) => unknown
  Size: new (width: number, height: number) => unknown
  Marker: new (options: Record<string, unknown>) => GoogleMarker
  InfoWindow: new (options: Record<string, unknown>) => GoogleInfoWindow
  SymbolPath: { CIRCLE: unknown }
}

type GoogleMap = {
  fitBounds: (bounds: GoogleLatLngBounds) => void
  overlayMapTypes: {
    getLength: () => number
    removeAt: (index: number) => void
    push: (overlay: unknown) => void
  }
}

type GoogleLatLngBounds = unknown

type GoogleMarker = {
  addListener: (eventName: string, handler: () => void) => { remove: () => void }
  setMap: (map: GoogleMap | null) => void
}

type GoogleInfoWindow = {
  open: (options: { anchor: GoogleMarker; map: GoogleMap }) => void
}

export function OrthoMap({ parkId, orthoName, bounds, center, panels }: OrthoMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<GoogleMap | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const tileUrl = `${API_BASE}/park/${encodeURIComponent(parkId)}/ortho/${encodeURIComponent(
    orthoName,
  )}/tiles/{z}/{x}/{y}.png${api.authQuery('?')}`
  const panelsWithGps = useMemo(() => panels.filter((panel) => panel.gps !== null), [panels])
  const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY

  useEffect(() => {
    if (!apiKey) {
      setLoadError('Set NEXT_PUBLIC_GOOGLE_MAPS_API_KEY to enable Google Maps.')
      return
    }

    let cancelled = false
    let cleanupMarkers: Array<() => void> = []

    loadGoogleMaps(apiKey)
      .then((googleMaps) => {
        if (cancelled || !containerRef.current) return

        const map =
          mapRef.current ??
          new googleMaps.Map(containerRef.current, {
            center: { lat: center.lat, lng: center.lon },
            mapTypeId: 'satellite',
            streetViewControl: false,
            fullscreenControl: true,
            mapTypeControl: true,
            zoom: 16,
          })

        mapRef.current = map

        const fitBounds = new googleMaps.LatLngBounds(
          { lat: bounds.south, lng: bounds.west },
          { lat: bounds.north, lng: bounds.east },
        )
        map.fitBounds(fitBounds)

        while (map.overlayMapTypes.getLength() > 0) {
          map.overlayMapTypes.removeAt(0)
        }

        map.overlayMapTypes.push(
          new googleMaps.ImageMapType({
            getTileUrl: (coord: { x: number; y: number }, zoom: number) =>
              tileUrl
                .replace('{z}', String(zoom))
                .replace('{x}', String(coord.x))
                .replace('{y}', String(coord.y)),
            name: 'Axalon orthomosaic',
            tileSize: new googleMaps.Size(256, 256),
            maxZoom: 24,
            minZoom: 0,
            opacity: 1,
          }),
        )

        cleanupMarkers = panelsWithGps.map((panel) => {
          const color = SEVERITY_COLOR[panel.worst_severity ?? ''] ?? '#64748b'
          const marker = new googleMaps.Marker({
            map,
            position: { lat: panel.gps!.lat, lng: panel.gps!.lon },
            title: panel.panel_id,
            icon: {
              path: googleMaps.SymbolPath.CIRCLE,
              scale: 7,
              fillColor: color,
              fillOpacity: 0.9,
              strokeColor: '#ffffff',
              strokeWeight: 1.5,
            },
          })
          const infoWindow = new googleMaps.InfoWindow({
            content: `<strong>${escapeHtml(panel.panel_id)}</strong><br />${
              panel.worst_severity ?? 'No detections'
            } - ${panel.detection_count} fault${panel.detection_count !== 1 ? 's' : ''}`,
          })
          const listener = marker.addListener('click', () => infoWindow.open({ anchor: marker, map }))

          return () => {
            listener.remove()
            marker.setMap(null)
          }
        })

        setLoadError(null)
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : 'Google Maps failed to load.')
      })

    return () => {
      cancelled = true
      cleanupMarkers.forEach((cleanup) => cleanup())
    }
  }, [apiKey, bounds, center.lat, center.lon, panelsWithGps, tileUrl])

  return (
    <div style={{ position: 'relative', height: 420, width: '100%', borderRadius: 8, overflow: 'hidden' }}>
      <div ref={containerRef} data-testid="google-map" style={{ height: '100%', width: '100%' }} />
      {loadError ? (
        <div
          role="status"
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: '#0f172a',
            color: '#cbd5e1',
            fontSize: 13,
            padding: 16,
            textAlign: 'center',
          }}
        >
          {loadError}
        </div>
      ) : null}
    </div>
  )
}

function loadGoogleMaps(apiKey: string): Promise<GoogleMaps> {
  const existing = getGoogleMaps()
  if (existing) return Promise.resolve(existing)

  const scriptId = 'google-maps-js-api'
  const priorScript = document.getElementById(scriptId) as HTMLScriptElement | null
  if (priorScript) {
    return new Promise((resolve, reject) => {
      priorScript.addEventListener('load', () => {
        const maps = getGoogleMaps()
        if (maps) resolve(maps)
        else reject(new Error('Google Maps loaded without the maps library.'))
      })
      priorScript.addEventListener('error', () => reject(new Error('Google Maps failed to load.')))
    })
  }

  return new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.id = scriptId
    script.async = true
    script.defer = true
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}`
    script.addEventListener('load', () => {
      const maps = getGoogleMaps()
      if (maps) resolve(maps)
      else reject(new Error('Google Maps loaded without the maps library.'))
    })
    script.addEventListener('error', () => reject(new Error('Google Maps failed to load.')))
    document.head.appendChild(script)
  })
}

function getGoogleMaps(): GoogleMaps | null {
  const maybeGoogle = (window as unknown as { google?: { maps?: GoogleMaps } }).google
  return maybeGoogle?.maps ?? null
}

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, (char) => {
    const entities: Record<string, string> = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }
    return entities[char]
  })
}
