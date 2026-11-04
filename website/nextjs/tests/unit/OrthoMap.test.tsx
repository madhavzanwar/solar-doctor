import '@testing-library/jest-dom/vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { OrthoMap } from '@/components/Platform/OrthoMap'

const BOUNDS = { west: 71.9, south: 27.5, east: 71.95, north: 27.55 }

const PANELS = [
  {
    panel_id: 'R1-C1',
    row: 0,
    col: 0,
    worst_severity: 'CRITICAL' as const,
    detection_count: 2,
    detections: [],
    gps: { lat: 27.52, lon: 71.92 },
  },
  {
    panel_id: 'R1-C2',
    row: 0,
    col: 1,
    worst_severity: null,
    detection_count: 0,
    detections: [],
    gps: null,
  },
]

const fitBounds = vi.fn()
const overlayPush = vi.fn()
const markerSetMap = vi.fn()
const markerAddListener = vi.fn(() => ({ remove: vi.fn() }))

function installGoogleMapsMock() {
  const overlayMapTypes = {
    getLength: vi.fn(() => 0),
    removeAt: vi.fn(),
    push: overlayPush,
  }

  const google = {
    maps: {
      Map: vi.fn(function MockMap() {
        return { fitBounds, overlayMapTypes }
      }),
      LatLngBounds: vi.fn(function MockLatLngBounds() {}),
      ImageMapType: vi.fn(function MockImageMapType(options) {
        return options
      }),
      Size: vi.fn(function MockSize() {}),
      Marker: vi.fn(function MockMarker() {
        return { addListener: markerAddListener, setMap: markerSetMap }
      }),
      InfoWindow: vi.fn(function MockInfoWindow() {
        return { open: vi.fn() }
      }),
      SymbolPath: { CIRCLE: 'circle' },
    },
  }

  ;(window as unknown as { google: typeof google }).google = google
  return google
}

describe('OrthoMap', () => {
  beforeEach(() => {
    vi.stubEnv('NEXT_PUBLIC_GOOGLE_MAPS_API_KEY', 'test-key')
    fitBounds.mockClear()
    overlayPush.mockClear()
    markerSetMap.mockClear()
    markerAddListener.mockClear()
    installGoogleMapsMock()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    delete (window as unknown as { google?: unknown }).google
  })

  test('renders map container', () => {
    render(
      <OrthoMap
        parkId="DEMO"
        orthoName="ortho.tif"
        bounds={BOUNDS}
        center={{ lat: 27.52, lon: 71.92 }}
        panels={PANELS}
      />,
    )

    expect(screen.getByTestId('google-map')).toBeInTheDocument()
  })

  test('adds the orthomosaic as a Google Maps tile overlay', async () => {
    render(
      <OrthoMap
        parkId="DEMO"
        orthoName="ortho.tif"
        bounds={BOUNDS}
        center={{ lat: 27.52, lon: 71.92 }}
        panels={PANELS}
      />,
    )

    await waitFor(() => expect(overlayPush).toHaveBeenCalledTimes(1))
    expect(overlayPush.mock.calls[0][0].getTileUrl({ x: 3, y: 4 }, 16)).toContain(
      '/park/DEMO/ortho/ortho.tif/tiles/16/3/4.png',
    )
  })

  test('renders markers only for panels with GPS', async () => {
    const google = installGoogleMapsMock()

    render(
      <OrthoMap
        parkId="DEMO"
        orthoName="ortho.tif"
        bounds={BOUNDS}
        center={{ lat: 27.52, lon: 71.92 }}
        panels={PANELS}
      />,
    )

    await waitFor(() => expect(google.maps.Marker).toHaveBeenCalledTimes(1))
  })

  test('shows a configuration message without a Google Maps API key', async () => {
    vi.stubEnv('NEXT_PUBLIC_GOOGLE_MAPS_API_KEY', '')

    render(
      <OrthoMap
        parkId="DEMO"
        orthoName="ortho.tif"
        bounds={BOUNDS}
        center={{ lat: 27.52, lon: 71.92 }}
        panels={PANELS}
      />,
    )

    expect(await screen.findByRole('status')).toHaveTextContent('NEXT_PUBLIC_GOOGLE_MAPS_API_KEY')
  })
})
