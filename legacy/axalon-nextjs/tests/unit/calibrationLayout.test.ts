import { afterEach, describe, expect, test, vi } from 'vitest'
import { api } from '@/lib/api'
import { calibrationSourceLabel, rmsTone } from '@/lib/calibration'
import { layoutModeLabel, layoutFileKind } from '@/lib/parkLayout'

afterEach(() => {
  vi.restoreAllMocks()
})

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status })
}

describe('fusion calibration API', () => {
  test('fusionCalibration GETs the summary endpoint', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      jsonResponse({ configured: true, source: 'database', path: null, error: null,
        calibration: { rig_id: 'RIG', rms_error_px: 0.8 } }),
    )
    const status = await api.fusionCalibration()
    expect(spy.mock.calls[0][0]).toContain('/settings/fusion-calibration')
    expect(status.calibration?.rig_id).toBe('RIG')
  })

  test('uploadFusionCalibration POSTs multipart form data', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      jsonResponse({ ok: true, calibration: { rig_id: 'RIG' } }, 201),
    )
    const form = new FormData()
    form.append('file', new Blob(['{}']), 'cal.json')
    await api.uploadFusionCalibration(form)
    const init = spy.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('POST')
    expect(init.body).toBe(form)
  })
})

describe('park layout API', () => {
  test('parkLayout GETs /park/{id}/layout with encoded id', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      jsonResponse({ park_id: 'P A', mode: 'auto', summary: null, layout: null, error: null }),
    )
    const status = await api.parkLayout('P A')
    expect(spy.mock.calls[0][0]).toContain('/park/P%20A/layout')
    expect(status.mode).toBe('auto')
  })

  test('uploadParkLayout POSTs and deleteParkLayout DELETEs', async () => {
    const spy = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse({ park_id: 'P', mode: 'manual', summary: { total_panels: 3 } }, 201))
      .mockResolvedValueOnce(jsonResponse({ park_id: 'P', mode: 'auto', deleted: true }))
    const form = new FormData()
    await api.uploadParkLayout('P', form)
    await api.deleteParkLayout('P')
    expect((spy.mock.calls[0][1] as RequestInit).method).toBe('POST')
    expect(spy.mock.calls[1][0]).toContain('/park/P/layout')
    expect((spy.mock.calls[1][1] as RequestInit).method).toBe('DELETE')
  })
})

describe('calibration helpers', () => {
  test('rmsTone grades reprojection error', () => {
    expect(rmsTone(0.9)).toBe('ok')
    expect(rmsTone(3.5)).toBe('info')
    expect(rmsTone(9)).toBe('crit')
    expect(rmsTone(null)).toBe('muted')
  })

  test('calibrationSourceLabel names where the calibration came from', () => {
    expect(calibrationSourceLabel('env')).toMatch(/AXALON_FUSION_CALIBRATION/)
    expect(calibrationSourceLabel('settings')).toMatch(/settings\.yaml/)
    expect(calibrationSourceLabel('database')).toMatch(/Uploaded/)
    expect(calibrationSourceLabel(null)).toBe('Not configured')
  })
})

describe('park layout helpers', () => {
  test('layoutModeLabel distinguishes manual, broken and auto layouts', () => {
    expect(layoutModeLabel({ mode: 'auto', summary: null, error: null })).toBe('Auto-grid')
    expect(
      layoutModeLabel({ mode: 'manual', summary: { total_panels: 28, tables: 8 } as never, error: null }),
    ).toBe('Manual · 28 panels / 8 tables')
    expect(layoutModeLabel({ mode: 'manual', summary: null, error: 'bad' })).toBe('Manual · invalid')
    expect(layoutModeLabel(null)).toBe('—')
  })

  test('layoutFileKind accepts json and geojson only', () => {
    expect(layoutFileKind('layout.json')).toBe('layout')
    expect(layoutFileKind('PANELS.GeoJSON')).toBe('geojson')
    expect(layoutFileKind('ortho.tif')).toBeNull()
  })
})
