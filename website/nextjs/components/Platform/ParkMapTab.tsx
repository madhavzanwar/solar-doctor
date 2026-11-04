'use client'

import { Download, UploadCloud } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { DynamicOrthoMap } from '@/components/Platform/DynamicOrthoMap'
import { OrthoGenerator } from '@/components/Platform/OrthoGenerator'
import { useToast } from '@/components/Platform/Toast'
import { CanWrite } from '@/components/Platform/AuthGate'
import { useParks } from '@/components/Platform/hooks/useParks'
import { inspectionsOf, useParkSummary, type InspectionRef } from '@/components/Platform/hooks/useParkSummary'
import { useErrorToast } from '@/components/Platform/hooks/useErrorToast'
import { queryKeys } from '@/lib/queryKeys'
import { api, ApiError } from '@/lib/api'
import { ParkMapGrid } from '@/components/Platform/ParkMapGrid'
import { ParkPanelDetail } from '@/components/Platform/ParkPanelDetail'
import { ParkFaultsPanel } from '@/components/Platform/ParkFaultsPanel'
import { ParkLayoutControl } from '@/components/Platform/ParkLayoutControl'
import type { GridPanel, OrthoMeta, ParkGrid } from '@/lib/api'

const NO_INSPECTIONS: InspectionRef[] = []
const NO_ORTHOS: OrthoMeta[] = []

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : String(err)
}

export function ParkMapTab() {
  const toast = useToast()
  const { parks } = useParks()

  const queryClient = useQueryClient()
  const [parkMapParkId, setParkMapParkId] = useState<string>('')
  const [parkMapInspectionId, setParkMapInspectionId] = useState<string>('')
  const [parkMapSelectedPanel, setParkMapSelectedPanel] = useState<GridPanel | null>(null)
  const [orthoView, setOrthoView] = useState(false)
  const [orthoUploading, setOrthoUploading] = useState(false)
  // Name of a just-generated ortho, listed first so the map opens on it.
  const [preferredOrtho, setPreferredOrtho] = useState<string | null>(null)

  // Inspection list for the chosen park (shared cache with History/Diff).
  const summaryQuery = useParkSummary(parkMapParkId)
  useErrorToast(summaryQuery.error, errorMessage)
  const parkMapInspections = parkMapParkId && !summaryQuery.isError ? inspectionsOf(summaryQuery.data) : NO_INSPECTIONS

  // default to most recent if not already chosen
  useEffect(() => {
    if (!parkMapInspectionId && parkMapInspections[0]) setParkMapInspectionId(parkMapInspections[0].id)
  }, [parkMapInspections, parkMapInspectionId])

  // Same cache entry Operations uploads into, so an ortho added there shows here.
  const orthosQuery = useQuery({
    queryKey: queryKeys.ops.orthos(parkMapParkId),
    queryFn: () => api.orthos(parkMapParkId),
    enabled: Boolean(parkMapParkId),
  })
  const orthos = useMemo(() => {
    if (!parkMapParkId || orthosQuery.isError) return NO_ORTHOS
    const list = orthosQuery.data ?? NO_ORTHOS
    if (!preferredOrtho) return list
    return [...list.filter((o) => o.name === preferredOrtho), ...list.filter((o) => o.name !== preferredOrtho)]
  }, [parkMapParkId, orthosQuery.isError, orthosQuery.data, preferredOrtho])

  // The map view needs an ortho: drop back to the grid when a park has none.
  useEffect(() => {
    if (!parkMapParkId || orthosQuery.isError || (orthosQuery.isSuccess && orthos.length === 0)) {
      setOrthoView(false)
    }
  }, [parkMapParkId, orthosQuery.isError, orthosQuery.isSuccess, orthos.length])

  // Fetch grid when park/inspection changes. The previous grid stays on screen
  // while the next one loads, as before.
  const gridQuery = useQuery({
    queryKey: queryKeys.parks.grid(parkMapParkId, parkMapInspectionId),
    queryFn: () => api.parkGrid(parkMapParkId, parkMapInspectionId || undefined),
    enabled: Boolean(parkMapParkId),
    placeholderData: keepPreviousData,
  })
  useErrorToast(gridQuery.error, errorMessage)
  const parkMapGrid: ParkGrid | null = parkMapParkId && !gridQuery.isError ? (gridQuery.data ?? null) : null
  const parkMapLoading = gridQuery.isFetching

  // A freshly loaded grid clears the panel selection.
  const loadedGrid = gridQuery.isPlaceholderData ? undefined : gridQuery.data
  useEffect(() => {
    if (loadedGrid) setParkMapSelectedPanel(null)
  }, [loadedGrid])

  async function handleOrthoUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file || !parkMapParkId) return
    setOrthoUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      const meta = await api.uploadOrtho(parkMapParkId, form)
      queryClient.setQueryData<OrthoMeta[]>(queryKeys.ops.orthos(parkMapParkId), (current = []) => [
        ...current.filter((o) => o.name !== meta.name),
        meta,
      ])
      void queryClient.invalidateQueries({ queryKey: queryKeys.ops.orthos(parkMapParkId) })
      setOrthoView(true)
      toast.success(`Ortho "${meta.name}" uploaded`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Upload failed')
    } finally {
      setOrthoUploading(false)
      e.target.value = ''
    }
  }

  async function handleGeneratedOrtho(orthoName: string) {
    if (!parkMapParkId) return
    try {
      await queryClient.fetchQuery({
        queryKey: queryKeys.ops.orthos(parkMapParkId),
        queryFn: () => api.orthos(parkMapParkId),
        staleTime: 0,
      })
      setPreferredOrtho(orthoName)
      setOrthoView(true)
      toast.success(`Orthomosaic "${orthoName}" generated`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not load the generated ortho')
    }
  }

  async function exportGridPng() {
    if (!parkMapParkId) return
    try {
      const blob = await api.parkGridPng(parkMapParkId, parkMapInspectionId || undefined)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `${parkMapParkId}_grid.png`
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Export failed')
    }
  }

  return (
    <section style={{ padding: '16px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <header style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <h1 style={{ margin: 0, fontSize: 24 }}>Park Map</h1>
      </header>

      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
        <label
          style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: '#64748b' }}
        >
          Park
          <select
            data-testid="parkmap-park-select"
            value={parkMapParkId}
            onChange={(e) => {
              setParkMapParkId(e.target.value)
              setParkMapInspectionId('')
              setPreferredOrtho(null)
            }}
            style={{ padding: '6px 10px', border: '1px solid #cbd5e1', borderRadius: 6 }}
          >
            <option value="">— select a park —</option>
            {parks.map((p) => (
              <option key={p.id} value={p.id}>
                {p.id}
                {p.name ? ` — ${p.name}` : ''}
              </option>
            ))}
          </select>
        </label>

        <label
          style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: '#64748b' }}
        >
          Inspection
          <select
            data-testid="parkmap-inspection-select"
            value={parkMapInspectionId}
            onChange={(e) => setParkMapInspectionId(e.target.value)}
            disabled={parkMapInspections.length === 0}
            style={{
              padding: '6px 10px',
              border: '1px solid #cbd5e1',
              borderRadius: 6,
              minWidth: 220,
            }}
          >
            <option value="">— most recent —</option>
            {parkMapInspections.map((i) => (
              <option key={i.id} value={i.id}>
                {i.id}
                {i.flight_date ? ` (${i.flight_date})` : ''}
              </option>
            ))}
          </select>
        </label>

        {parkMapLoading ? (
          <span style={{ fontSize: 12, color: '#64748b' }}>Loading…</span>
        ) : null}
      </div>

      {parkMapParkId && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', gap: 4 }}>
            <button
              onClick={() => setOrthoView(false)}
              style={{
                padding: '5px 14px',
                borderRadius: 6,
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                background: !orthoView ? '#0ea5e9' : 'transparent',
                color: !orthoView ? '#fff' : '#64748b',
                border: '1px solid #cbd5e1',
              }}
            >
              Grid
            </button>
            <button
              onClick={() => setOrthoView(true)}
              disabled={orthos.length === 0}
              style={{
                padding: '5px 14px',
                borderRadius: 6,
                fontSize: 12,
                fontWeight: 600,
                cursor: orthos.length > 0 ? 'pointer' : 'not-allowed',
                background: orthoView ? '#0ea5e9' : 'transparent',
                color: orthoView ? '#fff' : '#64748b',
                border: '1px solid #cbd5e1',
                opacity: orthos.length === 0 ? 0.5 : 1,
              }}
            >
              Map {orthos.length > 0 ? `(${orthos.length})` : ''}
            </button>
          </div>
          <CanWrite>
          <label
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              fontSize: 12,
              cursor: orthoUploading ? 'progress' : 'pointer',
              color: '#0ea5e9',
            }}
          >
            <UploadCloud size={14} />
            <input
              type="file"
              hidden
              accept=".tif,.tiff"
              onChange={handleOrthoUpload}
              disabled={orthoUploading}
            />
            {orthoUploading ? 'Uploading...' : 'Upload Ortho'}
          </label>
          <ParkLayoutControl parkId={parkMapParkId} />
          </CanWrite>
          {parkMapGrid && (
            <button
              data-testid="parkmap-export-png"
              style={{
                marginLeft: 'auto',
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                padding: '5px 14px',
                borderRadius: 6,
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                background: 'transparent',
                color: '#64748b',
                border: '1px solid #cbd5e1',
              }}
              onClick={exportGridPng}
            >
              <Download size={14} />
              Export PNG
            </button>
          )}
        </div>
      )}

      <CanWrite>
        {parkMapParkId && <OrthoGenerator parkId={parkMapParkId} onOrthoReady={handleGeneratedOrtho} />}
      </CanWrite>

      {orthoView && orthos[0] ? (
        <DynamicOrthoMap
          parkId={parkMapParkId}
          orthoName={orthos[0].name}
          bounds={orthos[0].bounds}
          center={orthos[0].center}
          panels={parkMapGrid?.panels ?? []}
        />
      ) : (
        <div
          className="park-map-layout"
          style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 320px', gap: 16 }}
        >
          <ParkMapGrid
            grid={parkMapGrid}
            selectedPanelId={parkMapSelectedPanel?.panel_id ?? null}
            onSelect={(p) => setParkMapSelectedPanel(p)}
          />
          <div className={`park-panel-detail ${parkMapSelectedPanel ? 'is-open' : ''}`}>
            <ParkPanelDetail
              panel={parkMapSelectedPanel}
              jobId={parkMapGrid?.inspection_id ?? null}
              onClose={() => setParkMapSelectedPanel(null)}
            />
          </div>
        </div>
      )}

      {parkMapParkId && (
        <ParkFaultsPanel
          parkId={parkMapParkId}
          panelId={parkMapSelectedPanel?.panel_id ?? null}
          onClearPanel={() => setParkMapSelectedPanel(null)}
        />
      )}
    </section>
  )
}
