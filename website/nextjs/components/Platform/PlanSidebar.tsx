// website/nextjs/components/Platform/PlanSidebar.tsx
'use client'

import { useState } from 'react'
import { Download, Save, Trash2, Upload } from 'lucide-react'
import { CanWrite } from '@/components/Platform/AuthGate'
import type { Camera } from '@/lib/cameras'
import { CAMERAS } from '@/lib/cameras'
import type { MissionParams, MissionType, MissionStats } from '@/lib/missionGeometry'
import { computeFootprint } from '@/lib/missionGeometry'
import type { MissionSummary } from '@/lib/api'
import type { ExportFormat } from '@/lib/waypointExport'
import type { Severity } from '@/lib/analytics'

type Props = {
  missionName: string
  onMissionNameChange: (v: string) => void
  parkId: string
  onParkIdChange: (v: string) => void
  missionType: MissionType
  onMissionTypeChange: (t: MissionType) => void
  camera: Camera
  onCameraChange: (c: Camera) => void
  params: MissionParams
  onParamsChange: (p: MissionParams) => void
  stats: MissionStats | null
  resolvedAlpha: number | null
  savedMissions: MissionSummary[]
  onLoadMission: (id: number) => void
  onDeleteMission: (id: number) => void
  onExport: (format: ExportFormat) => void
  onSave: () => void
  onImportBoundary: (file: File) => void
  onExportBoundary: (format: 'geojson' | 'kml') => void
  canExportBoundary: boolean
  selectingRows: boolean
  onToggleSelectRows: () => void
  solarRowCount: number
  onClearRows: () => void
  onLoadReinspect: (jobId: string, minSeverity: Severity) => void
  onClearReinspect: () => void
  reinspectActive: boolean
  reinspectTargets: number
  canExport: boolean
  terrainActive: boolean
  terrainBusy: boolean
  terrainDelta: string | null
  onApplyTerrain: () => void
  onClearTerrain: () => void
}

const TYPES: MissionType[] = ['grid', 'perimeter', 'corridor', 'orbit', 'solar']

const EXPORT_FORMATS: { value: ExportFormat; label: string; short: string }[] = [
  { value: 'litchi', label: 'Litchi CSV', short: 'Litchi CSV' },
  { value: 'kml', label: 'KML (Google Earth)', short: 'KML' },
  { value: 'plan', label: 'QGroundControl .plan', short: '.plan' },
  { value: 'waypoints', label: 'ArduPilot .waypoints', short: '.waypoints' },
  { value: 'capture-points', label: 'Capture points (GeoJSON)', short: '.geojson' },
]

export default function PlanSidebar(props: Props) {
  const {
    missionName, onMissionNameChange, parkId, onParkIdChange,
    missionType, onMissionTypeChange, camera, onCameraChange,
    params, onParamsChange, stats, resolvedAlpha, savedMissions,
    onLoadMission, onDeleteMission, onExport, onSave,
    onImportBoundary, onExportBoundary, canExportBoundary,
    selectingRows, onToggleSelectRows, solarRowCount, onClearRows,
    onLoadReinspect, onClearReinspect, reinspectActive, reinspectTargets, canExport,
    terrainActive, terrainBusy, terrainDelta, onApplyTerrain, onClearTerrain,
  } = props

  const [exportFormat, setExportFormat] = useState<ExportFormat>('litchi')
  const [reJobId, setReJobId] = useState('')
  const [reSev, setReSev] = useState<Severity>('HIGH')
  const fp = computeFootprint(camera, params)
  const exportLabel = EXPORT_FORMATS.find((f) => f.value === exportFormat)?.short ?? 'file'

  const batteryMinutes = params.batteryMinutes ?? 18
  const reservePct = params.batteryReservePct ?? 20
  const orbitRadiusM = params.orbitRadiusM ?? 30
  const orbitPhotoCount = params.orbitPhotoCount ?? 16
  const isAlphaAuto = params.headingDeg === 'auto'
  const rowAngleDeg = params.rowAngleDeg ?? 0
  const isDroneHeadingAuto = params.droneHeadingDeg === 'auto' || params.droneHeadingDeg === undefined
  const droneHeadingDeg = isDroneHeadingAuto ? 0 : (params.droneHeadingDeg as number)

  function setCamById(id: string) {
    const next = CAMERAS.find((c) => c.id === id)
    if (next) onCameraChange(next)
  }

  function patchParams(patch: Partial<MissionParams>) {
    onParamsChange({ ...params, ...patch })
  }

  function patchCamera(patch: Partial<Camera>) {
    onCameraChange({ ...camera, ...patch })
  }

  return (
    <aside className="plan-sidebar">
      {/* Mission */}
      <section className="panel">
        <div className="panel-head compact"><div className="panel-title">Mission</div></div>
        <div className="plan-param">
          <input
            value={missionName}
            onChange={(e) => onMissionNameChange(e.target.value)}
            placeholder="Mission name"
            style={{ width: '100%', boxSizing: 'border-box' }}
          />
          <input
            value={parkId}
            onChange={(e) => onParkIdChange(e.target.value)}
            placeholder="Park ID (optional)"
            style={{ width: '100%', boxSizing: 'border-box', marginTop: 8 }}
          />
          <div style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
            {TYPES.map((t) => (
              <button
                key={t}
                type="button"
                className={t === missionType ? 'primary' : 'secondary'}
                style={{ flex: '1 0 40%', textTransform: 'capitalize', padding: '5px' }}
                onClick={() => onMissionTypeChange(t)}
              >
                {t}
              </button>
            ))}
          </div>
          <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
            {reinspectActive
              ? 'Re-inspection route active — drawing or importing an area replaces it.'
              : missionType === 'orbit'
                ? 'Drop a center point; the drone circles it, camera aimed inward.'
                : missionType === 'corridor'
                  ? 'Draw a line; the drone flies it with a parallel return pass.'
                  : missionType === 'solar'
                    ? 'Draw the area, set the row angle, then Select solar rows and click each row.'
                    : 'Draw the survey area; lines run along the panel-row angle.'}
          </div>
        </div>
      </section>

      {/* Re-inspect from a completed inspection */}
      <section className="panel">
        <div className="panel-head compact"><div className="panel-title">Re-inspect Faults</div></div>
        <div className="plan-param">
          <input
            value={reJobId}
            onChange={(e) => setReJobId(e.target.value)}
            placeholder="Inspection / Job ID"
            style={{ width: '100%', boxSizing: 'border-box' }}
          />
          <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
            <select value={reSev} onChange={(e) => setReSev(e.target.value as Severity)} style={{ flex: 1 }}>
              <option value="CRITICAL">Critical only</option>
              <option value="HIGH">Critical + High</option>
              <option value="MEDIUM">+ Medium</option>
              <option value="LOW">All faults</option>
            </select>
            <button className="secondary" style={{ padding: '4px 10px' }} onClick={() => onLoadReinspect(reJobId, reSev)}>
              Load
            </button>
          </div>
          {reinspectActive && (
            <div className="cam-row" style={{ marginTop: 6 }}>
              <span style={{ color: '#0ea5e9' }}>{reinspectTargets} re-fly targets</span>
              <button className="secondary" style={{ padding: '2px 8px' }} onClick={onClearReinspect}>Clear</button>
            </div>
          )}
          <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
            Builds a targeted re-fly route from a completed inspection's detected faults.
          </div>
        </div>
      </section>

      {/* Site boundary (import / export) */}
      <section className="panel">
        <div className="panel-head compact"><div className="panel-title">Site Boundary</div></div>
        <div className="plan-param">
          <label style={{ display: 'block', marginBottom: 6 }}>
            <input
              type="file"
              accept=".geojson,.json,.kml"
              style={{ display: 'none' }}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) onImportBoundary(f); e.currentTarget.value = '' }}
            />
            <span
              className="secondary"
              role="button"
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, padding: '6px', borderRadius: 4, cursor: 'pointer', fontSize: 13 }}
            >
              <Upload size={14} /> Import GeoJSON / KML
            </span>
          </label>
          <div style={{ display: 'flex', gap: 6 }}>
            <button className="secondary" style={{ flex: 1 }} disabled={!canExportBoundary} onClick={() => onExportBoundary('geojson')}>
              Export GeoJSON
            </button>
            <button className="secondary" style={{ flex: 1 }} disabled={!canExportBoundary} onClick={() => onExportBoundary('kml')}>
              Export KML
            </button>
          </div>
        </div>
      </section>

      {/* Camera */}
      <section className="panel">
        <div className="panel-head compact"><div className="panel-title">Camera</div></div>
        <div className="plan-param">
          <select
            value={camera.id}
            onChange={(e) => setCamById(e.target.value)}
            style={{ width: '100%', boxSizing: 'border-box' }}
          >
            {CAMERAS.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <div className="plan-camera-card">
            {camera.custom ? (
              <>
                <label>Sensor W (mm)
                  <input type="number" step="0.01" value={camera.sensorWidthMm}
                    onChange={(e) => patchCamera({ sensorWidthMm: Number(e.target.value) })} />
                </label>
                <label>Sensor H (mm)
                  <input type="number" step="0.01" value={camera.sensorHeightMm}
                    onChange={(e) => patchCamera({ sensorHeightMm: Number(e.target.value) })} />
                </label>
                <label>Focal (mm)
                  <input type="number" step="0.1" value={camera.focalLengthMm}
                    onChange={(e) => patchCamera({ focalLengthMm: Number(e.target.value) })} />
                </label>
                <label>Res W (px)
                  <input type="number" value={camera.resolutionW}
                    onChange={(e) => patchCamera({ resolutionW: Number(e.target.value) })} />
                </label>
              </>
            ) : (
              <>
                <div className="cam-row"><span>Sensor</span><span>{camera.sensorWidthMm} × {camera.sensorHeightMm} mm</span></div>
                <div className="cam-row"><span>Focal length</span><span>{camera.focalLengthMm} mm</span></div>
                <div className="cam-row"><span>Resolution</span><span>{camera.resolutionW} × {camera.resolutionH} px</span></div>
              </>
            )}
            <div className="cam-row" style={{ marginTop: 4 }}>
              <span>Footprint @ {params.altitudeM}m</span>
              <span style={{ color: '#0ea5e9' }}>{fp.w.toFixed(1)} × {fp.h.toFixed(1)} m</span>
            </div>
          </div>
        </div>
      </section>

      {/* Flight params */}
      <section className="panel">
        <div className="panel-head compact"><div className="panel-title">Flight Params</div></div>
        <div className="plan-param">
          <label>Altitude <span>{params.altitudeM} m</span></label>
          <input type="range" min={10} max={120} value={params.altitudeM}
            onChange={(e) => patchParams({ altitudeM: Number(e.target.value) })} />
          <label>Front overlap <span>{Math.round(params.frontOverlap * 100)} %</span></label>
          <input type="range" min={50} max={95} value={Math.round(params.frontOverlap * 100)}
            onChange={(e) => patchParams({ frontOverlap: Number(e.target.value) / 100 })} />
          <label>Side overlap <span>{Math.round(params.sideOverlap * 100)} %</span></label>
          <input type="range" min={50} max={95} value={Math.round(params.sideOverlap * 100)}
            onChange={(e) => patchParams({ sideOverlap: Number(e.target.value) / 100 })} />
          <label>Speed <span>{params.speedMs} m/s</span></label>
          <input type="range" min={3} max={15} value={params.speedMs}
            onChange={(e) => patchParams({ speedMs: Number(e.target.value) })} />

          {missionType !== 'orbit' && missionType !== 'solar' && (
            <>
              <label>Gimbal pitch <span>{params.gimbalPitchDeg ?? -90}°</span></label>
              <input type="range" min={-90} max={0} value={params.gimbalPitchDeg ?? -90}
                onChange={(e) => patchParams({ gimbalPitchDeg: Number(e.target.value) })} />
            </>
          )}

          {missionType === 'grid' && !reinspectActive && (
            <>
              <label>Panel row angle α <span>{isAlphaAuto ? `Auto · ${resolvedAlpha ?? '–'}°` : `${params.headingDeg}°`}</span></label>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <input
                  type="number" min={0} max={179}
                  disabled={isAlphaAuto}
                  value={isAlphaAuto ? '' : (params.headingDeg as number)}
                  placeholder="deg"
                  onChange={(e) => patchParams({ headingDeg: Number(e.target.value) })}
                  style={{ flex: 1, boxSizing: 'border-box' }}
                />
                <button
                  type="button"
                  className={isAlphaAuto ? 'primary' : 'secondary'}
                  style={{ padding: '4px 8px' }}
                  onClick={() => patchParams({ headingDeg: isAlphaAuto ? 0 : 'auto' })}
                >
                  Auto
                </button>
              </div>
            </>
          )}
        </div>
      </section>

      {/* Orbit params */}
      {missionType === 'orbit' && !reinspectActive && (
        <section className="panel">
          <div className="panel-head compact"><div className="panel-title">Orbit</div></div>
          <div className="plan-param">
            <label>Radius <span>{orbitRadiusM} m</span></label>
            <input type="range" min={10} max={120} value={orbitRadiusM}
              onChange={(e) => patchParams({ orbitRadiusM: Number(e.target.value) })} />
            <label>Photos <span>{orbitPhotoCount}</span></label>
            <input type="range" min={4} max={48} value={orbitPhotoCount}
              onChange={(e) => patchParams({ orbitPhotoCount: Number(e.target.value) })} />
          </div>
        </section>
      )}

      {/* Solar row params */}
      {missionType === 'solar' && !reinspectActive && (
        <section className="panel">
          <div className="panel-head compact"><div className="panel-title">Solar Rows</div></div>
          <div className="plan-param">
            <button
              type="button"
              className={selectingRows ? 'primary' : 'secondary'}
              style={{ width: '100%' }}
              onClick={onToggleSelectRows}
            >
              Select solar rows
            </button>
            <div className="cam-row" style={{ marginTop: 6 }}>
              <span>{solarRowCount} rows</span>
              <button type="button" className="secondary" style={{ padding: '2px 8px' }} onClick={onClearRows}>Clear</button>
            </div>

            <label>Row Angle α <span>{rowAngleDeg}°</span></label>
            <input type="range" min={0} max={180} value={rowAngleDeg}
              onChange={(e) => patchParams({ rowAngleDeg: Number(e.target.value) })} />

            <label>Drone Orientation <span>{isDroneHeadingAuto ? 'Auto' : `${droneHeadingDeg}°`}</span></label>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <input
                type="range"
                min={0}
                max={359}
                disabled={isDroneHeadingAuto}
                value={droneHeadingDeg}
                onChange={(e) => patchParams({ droneHeadingDeg: Number(e.target.value) })}
                style={{ flex: 1 }}
              />
              <button
                type="button"
                className={isDroneHeadingAuto ? 'primary' : 'secondary'}
                style={{ padding: '4px 8px' }}
                onClick={() => patchParams({ droneHeadingDeg: isDroneHeadingAuto ? 0 : 'auto' })}
              >
                Auto
              </button>
            </div>

            <label>Gimbal Tilt <span>{params.gimbalPitchDeg ?? -90}°</span></label>
            <input type="range" min={-90} max={0} value={params.gimbalPitchDeg ?? -90}
              onChange={(e) => patchParams({ gimbalPitchDeg: Number(e.target.value) })} />
          </div>
        </section>
      )}

      {/* Battery */}
      <section className="panel">
        <div className="panel-head compact"><div className="panel-title">Battery</div></div>
        <div className="plan-param">
          <label>Usable flight time <span>{batteryMinutes} min</span></label>
          <input type="range" min={5} max={40} value={batteryMinutes}
            onChange={(e) => patchParams({ batteryMinutes: Number(e.target.value) })} />
          <label>Reserve <span>{reservePct} %</span></label>
          <input type="range" min={0} max={40} value={reservePct}
            onChange={(e) => patchParams({ batteryReservePct: Number(e.target.value) })} />
          {stats && (
            <div className="cam-row" style={{ marginTop: 4 }}>
              <span>Batteries needed</span>
              <span style={{ color: '#0ea5e9' }}>{stats.batteryCount}</span>
            </div>
          )}
        </div>
      </section>

      {/* Terrain follow */}
      <section className="panel">
        <div className="panel-head compact"><div className="panel-title">Terrain (AGL)</div></div>
        <div className="plan-param">
          {!terrainActive && (
            <button
              className="secondary"
              style={{ width: '100%' }}
              disabled={!canExport || terrainBusy}
              onClick={onApplyTerrain}
            >
              {terrainBusy ? 'Fetching elevations…' : 'Follow terrain'}
            </button>
          )}
          {terrainActive && (
            <>
              <div className="cam-row">
                <span>Altitude adjusted</span>
                <span style={{ color: '#0ea5e9' }}>{terrainDelta ?? 'applied'}</span>
              </div>
              <button className="secondary" style={{ width: '100%', marginTop: 4 }} onClick={onClearTerrain}>
                Back to constant altitude
              </button>
            </>
          )}
          <p className="muted" style={{ fontSize: 11, margin: '6px 0 0' }}>
            Per-waypoint ground elevation via Open-Elevation; falls back to constant altitude if unavailable.
          </p>
        </div>
      </section>

      {/* Saved missions */}
      <section className="panel">
        <div className="panel-head compact"><div className="panel-title">Saved Missions</div></div>
        <div className="plan-param">
          {savedMissions.length === 0 && <div className="empty" style={{ fontSize: 12 }}>No saved missions</div>}
          {savedMissions.map((m) => (
            <div key={m.id} className="queue-item" style={{ marginBottom: 4 }}>
              <div className="queue-row" onClick={() => onLoadMission(m.id)} style={{ cursor: 'pointer' }}>
                <strong>{m.name}</strong>
                <CanWrite>
                  <button className="secondary" style={{ padding: 2 }} onClick={(e) => { e.stopPropagation(); onDeleteMission(m.id) }}>
                    <Trash2 size={12} />
                  </button>
                </CanWrite>
              </div>
              <div className="queue-row sub">
                <span className="muted">{m.mission_type} · {m.area_ha?.toFixed(1) ?? '–'} ha</span>
                <span className="muted">{m.image_count ?? '–'} img</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Actions */}
      <section className="panel" style={{ marginTop: 'auto' }}>
        <div className="plan-param">
          <select
            value={exportFormat}
            onChange={(e) => setExportFormat(e.target.value as ExportFormat)}
            style={{ width: '100%', boxSizing: 'border-box', marginBottom: 6 }}
            aria-label="Export format"
          >
            {EXPORT_FORMATS.map((f) => (
              <option key={f.value} value={f.value}>{f.label}</option>
            ))}
          </select>
          <button className="primary" style={{ width: '100%', marginBottom: 6 }} disabled={!canExport} onClick={() => onExport(exportFormat)}>
            <Download size={15} /> Export {exportLabel}
          </button>
          <CanWrite>
            <button className="secondary" style={{ width: '100%' }} disabled={!canExport} onClick={onSave}>
              <Save size={15} /> Save Mission
            </button>
          </CanWrite>
        </div>
      </section>
    </aside>
  )
}
