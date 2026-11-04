// website/nextjs/components/Platform/PlanTab.tsx
'use client'

import dynamic from 'next/dynamic'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useToast } from '@/components/Platform/Toast'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError, type MissionCreate, type MissionSummary } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'
import { useErrorToast } from '@/components/Platform/hooks/useErrorToast'
import { DEFAULT_CAMERA, getCamera, type Camera } from '@/lib/cameras'
import {
  generateGrid,
  generatePerimeter,
  generateCorridor,
  generateOrbit,
  generateSolar,
  resolvedHeadingDeg,
  splitByBattery,
  computeStats,
  computeFootprint,
  type LatLon,
  type MissionParams,
  type MissionType,
  type Waypoint,
} from '@/lib/missionGeometry'
import { downloadMission, type ExportFormat } from '@/lib/waypointExport'
import { parseBoundary, toGeoJson, toKml } from '@/lib/boundaryIO'
import { planReinspection, faultsFromMapData, type FaultPoint } from '@/lib/reinspect'
import { applyTerrainOffsets, fetchElevations, terrainDeltaRange } from '@/lib/terrain'
import type { Severity } from '@/lib/analytics'
import PlanSidebar from '@/components/Platform/PlanSidebar'
import { plannerToPlannedPoints, type PlannedPoint } from '@/lib/missionToWaypoints'

const PlanMap = dynamic(() => import('@/components/Platform/PlanMap'), {
  ssr: false,
  loading: () => (
    <div className="plan-map" style={{ display: 'grid', placeItems: 'center', color: '#64748b' }}>
      Loading map…
    </div>
  ),
})

const DEFAULT_PARAMS: MissionParams = {
  altitudeM: 20,
  frontOverlap: 0.8,
  sideOverlap: 0.7,
  speedMs: 8,
  headingDeg: 'auto',
  batteryMinutes: 18,
  batteryReservePct: 20,
  orbitRadiusM: 30,
  orbitPhotoCount: 16,
  gimbalPitchDeg: -90,
  rowAngleDeg: 0,
  droneHeadingDeg: 'auto',
}

const NO_MISSIONS: MissionSummary[] = []

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : String(err)
}

function downloadText(text: string, filename: string, mime: string) {
  const blob = new Blob([text], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

type Reinspect = { faults: FaultPoint[]; minSeverity: Severity }

type PlanTabProps = {
  /** Receives the current route (terrain offsets applied) for Live Ops upload. */
  onRouteChange?: (points: PlannedPoint[]) => void
}

export function PlanTab({ onRouteChange }: PlanTabProps = {}) {
  const toast = useToast()
  const [missionName, setMissionName] = useState('New Mission')
  const [parkId, setParkId] = useState('')
  const [missionType, setMissionType] = useState<MissionType>('grid')
  const [camera, setCamera] = useState<Camera>(DEFAULT_CAMERA)
  const [params, setParams] = useState<MissionParams>(DEFAULT_PARAMS)
  const [polygon, setPolygon] = useState<LatLon[] | null>(null)
  const [solarRows, setSolarRows] = useState<LatLon[]>([])
  const [selectingRows, setSelectingRows] = useState(false)
  const [reinspect, setReinspect] = useState<Reinspect | null>(null)
  const [fitKey, setFitKey] = useState(0)
  // Park filter applied to the saved-missions list. Captured on mount and
  // after save/delete — not on every keystroke in the park field.
  const [missionFilter, setMissionFilter] = useState('')
  const queryClient = useQueryClient()

  const flatWaypoints = useMemo(() => {
    let base: Waypoint[] = []
    if (reinspect && reinspect.faults.length) {
      base = planReinspection(reinspect.faults, { altitudeM: params.altitudeM, minSeverity: reinspect.minSeverity })
    } else if (missionType === 'orbit') {
      base = polygon && polygon.length >= 1 ? generateOrbit(polygon[0], camera, params) : []
    } else if (polygon && polygon.length >= 2) {
      if (missionType === 'grid') base = generateGrid(polygon, camera, params)
      else if (missionType === 'perimeter') base = generatePerimeter(polygon, camera, params)
      else if (missionType === 'solar') {
        base = polygon.length >= 3 && solarRows.length >= 1 ? generateSolar(polygon, solarRows, params) : []
      } else base = generateCorridor(polygon, camera, params)
    }
    return splitByBattery(base, params).waypoints
  }, [polygon, solarRows, camera, params, missionType, reinspect])

  // Terrain follow: elevations fetched for the CURRENT flat plan; any change to
  // the plan invalidates them (length check is the cheap guard below).
  const [terrainElevations, setTerrainElevations] = useState<number[] | null>(null)
  const [terrainBusy, setTerrainBusy] = useState(false)

  useEffect(() => {
    setTerrainElevations(null)
  }, [flatWaypoints])

  const terrainActive = !!terrainElevations && terrainElevations.length === flatWaypoints.length && flatWaypoints.length > 0

  const waypoints = useMemo(
    () => (terrainActive && terrainElevations ? applyTerrainOffsets(flatWaypoints, terrainElevations) : flatWaypoints),
    [flatWaypoints, terrainElevations, terrainActive],
  )

  // Stage the route for Live Ops. The tab unmounts on every tab switch and
  // remounts with an empty route, so an empty route is only reported once this
  // mount has reported a real one (i.e. the operator cleared it). Otherwise
  // opening Plan to look at something would wipe the route already staged —
  // and React StrictMode's double effect run would do the same in dev.
  const hasReportedRoute = useRef(false)
  useEffect(() => {
    if (!onRouteChange) return
    if (waypoints.length === 0 && !hasReportedRoute.current) return
    hasReportedRoute.current = waypoints.length > 0
    onRouteChange(plannerToPlannedPoints(waypoints))
  }, [waypoints, onRouteChange])

  const terrainDelta = useMemo(() => {
    if (!terrainActive) return null
    const range = terrainDeltaRange(flatWaypoints, waypoints)
    return range ? `${range.min >= 0 ? '+' : ''}${range.min} … +${range.max} m` : null
  }, [terrainActive, flatWaypoints, waypoints])

  async function handleApplyTerrain() {
    if (flatWaypoints.length < 2) {
      toast.error('Generate a flight path first')
      return
    }
    setTerrainBusy(true)
    try {
      const elevations = await fetchElevations(flatWaypoints.map((w) => ({ lat: w.lat, lon: w.lon })))
      if (!elevations) {
        toast.error('Elevation service unavailable — keeping constant altitude')
        return
      }
      setTerrainElevations(elevations)
      toast.success('Terrain follow applied')
    } finally {
      setTerrainBusy(false)
    }
  }

  const stats = useMemo(() => {
    if (waypoints.length < 2) return null
    return computeStats(waypoints, polygon ?? [], camera, params)
  }, [waypoints, polygon, camera, params])

  const resolvedAlpha = useMemo(() => {
    if (missionType !== 'grid') return null
    if (typeof params.headingDeg === 'number') return params.headingDeg
    return polygon && polygon.length >= 3 ? Math.round(resolvedHeadingDeg(polygon, params)) : null
  }, [missionType, params, polygon])

  const missionsQuery = useQuery({
    queryKey: queryKeys.missions.list(missionFilter),
    queryFn: () => api.missions(missionFilter || undefined),
  })
  useErrorToast(missionsQuery.error, errorMessage)
  const savedMissions = missionsQuery.data ?? NO_MISSIONS

  function refreshMissions() {
    setMissionFilter(parkId)
    void queryClient.invalidateQueries({ queryKey: queryKeys.missions.all })
  }

  const saveMutation = useMutation({
    mutationFn: (body: MissionCreate) => api.createMission(body),
    onSuccess: (_res, body) => {
      toast.success(`Saved "${body.name}"`)
      refreshMissions()
    },
    onError: (err) => toast.error(errorMessage(err)),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.deleteMission(id),
    onSuccess: refreshMissions,
    onError: (err) => toast.error(errorMessage(err)),
  })

  function handleShapeDrawn(pts: LatLon[]) {
    setReinspect(null)
    setPolygon(pts)
    if (missionType === 'solar') setSolarRows([])
  }

  function handleExport(format: ExportFormat) {
    if (waypoints.length < 2) return
    const fp = computeFootprint(camera, params)
    const triggerDist = Math.max(fp.h * (1 - params.frontOverlap), 0.5)
    downloadMission(waypoints, params, missionName, triggerDist, format)
  }

  async function handleImportBoundary(file: File) {
    try {
      const text = await file.text()
      const pts = parseBoundary(text, file.name)
      setReinspect(null)
      setPolygon(pts)
      setSolarRows([])
      setFitKey((k) => k + 1)
      toast.success(`Imported ${pts.length}-point boundary`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    }
  }

  function handleExportBoundary(format: 'geojson' | 'kml') {
    if (!polygon || polygon.length < 3) {
      toast.error('Draw or import an area first')
      return
    }
    const slug = missionName.trim().replace(/[^A-Za-z0-9]+/g, '_') || 'boundary'
    if (format === 'geojson') downloadText(toGeoJson(polygon), `${slug}.geojson`, 'application/geo+json')
    else downloadText(toKml(polygon), `${slug}.kml`, 'application/vnd.google-earth.kml+xml')
  }

  async function handleLoadReinspect(jobId: string, minSeverity: Severity) {
    const id = jobId.trim()
    if (!id) {
      toast.error('Enter a Job ID')
      return
    }
    try {
      const data = await api.mapData(id)
      const faults = faultsFromMapData(data)
      if (faults.length === 0) {
        toast.error('No geo-located faults in that job')
        return
      }
      const kept = planReinspection(faults, { altitudeM: params.altitudeM, minSeverity }).length
      setPolygon(null)
      setSolarRows([])
      setReinspect({ faults, minSeverity })
      setFitKey((k) => k + 1)
      toast.success(`Re-inspecting ${kept} of ${faults.length} faults`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : String(err))
    }
  }

  function handleClearReinspect() {
    setReinspect(null)
  }

  function handleClearShape() {
    setPolygon(null)
    setSolarRows([])
    setSelectingRows(false)
  }

  function handleSave() {
    const savePolygon = polygon ?? (reinspect ? reinspect.faults.map((f) => ({ lat: f.lat, lon: f.lon })) : null)
    if (waypoints.length < 2 || !savePolygon || !stats) {
      toast.error('Draw a survey area or load faults first')
      return
    }
    saveMutation.mutate({
      name: missionName,
      park_id: parkId || null,
      mission_type: missionType,
      camera_id: camera.id,
      params: params as unknown as Record<string, unknown>,
      polygon: savePolygon,
      waypoints,
      area_ha: stats.areaHa,
      image_count: stats.imageCount,
    })
  }

  async function handleLoad(id: number) {
    try {
      const m = await api.mission(id)
      setReinspect(null)
      setMissionName(m.name)
      setParkId(m.park_id ?? '')
      setMissionType(m.mission_type)
      setCamera(getCamera(m.camera_id ?? DEFAULT_CAMERA.id))
      setParams({ ...DEFAULT_PARAMS, ...(m.params as Partial<MissionParams>) })
      setPolygon(m.polygon.length ? m.polygon : null)
      setSolarRows([])
      setSelectingRows(false)
      setFitKey((k) => k + 1)
      toast.success(`Loaded "${m.name}"`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : String(err))
    }
  }

  function handleDelete(id: number) {
    deleteMutation.mutate(id)
  }

  return (
    <div className="plan-layout">
      <div className="plan-map-wrap">
        <PlanMap
          missionType={missionType}
          polygon={polygon}
          waypoints={waypoints}
          stats={stats}
          orbitRadiusM={params.orbitRadiusM}
          fitKey={fitKey}
          solarRows={solarRows}
          selectingRows={selectingRows}
          onShapeDrawn={handleShapeDrawn}
          onSolarRowsChange={setSolarRows}
          onClear={handleClearShape}
        />
      </div>
      <PlanSidebar
        missionName={missionName}
        onMissionNameChange={setMissionName}
        parkId={parkId}
        onParkIdChange={setParkId}
        missionType={missionType}
        onMissionTypeChange={setMissionType}
        camera={camera}
        onCameraChange={setCamera}
        params={params}
        onParamsChange={setParams}
        stats={stats}
        resolvedAlpha={resolvedAlpha}
        savedMissions={savedMissions}
        onLoadMission={handleLoad}
        onDeleteMission={handleDelete}
        onExport={handleExport}
        onSave={handleSave}
        onImportBoundary={handleImportBoundary}
        onExportBoundary={handleExportBoundary}
        canExportBoundary={!!polygon && polygon.length >= 3}
        selectingRows={selectingRows}
        onToggleSelectRows={() => setSelectingRows((v) => !v)}
        solarRowCount={solarRows.length}
        onClearRows={() => setSolarRows([])}
        onLoadReinspect={handleLoadReinspect}
        onClearReinspect={handleClearReinspect}
        reinspectActive={!!reinspect}
        reinspectTargets={reinspect ? waypoints.length : 0}
        canExport={waypoints.length >= 2}
        terrainActive={terrainActive}
        terrainBusy={terrainBusy}
        terrainDelta={terrainDelta}
        onApplyTerrain={handleApplyTerrain}
        onClearTerrain={() => setTerrainElevations(null)}
      />
    </div>
  )
}
