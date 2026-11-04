import '@testing-library/jest-dom/vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { FusionCalibrationPanel } from '@/components/Platform/FusionCalibrationPanel'
import { api, ApiError } from '@/lib/api'
import type { CalibrationStatus } from '@/lib/calibration'
import { withQueryClient } from './queryWrapper'

afterEach(() => {
  vi.restoreAllMocks()
})

const NONE: CalibrationStatus = { configured: false, source: null, path: null, error: null, calibration: null }
const STORED: CalibrationStatus = {
  configured: true,
  source: 'database',
  path: null,
  error: null,
  calibration: { rig_id: 'rig-7', rms_error_px: 1.25 },
}

describe('FusionCalibrationPanel', () => {
  test('an upload shows the new calibration and refetches the status', async () => {
    const status = vi.spyOn(api, 'fusionCalibration').mockResolvedValueOnce(NONE).mockResolvedValue(STORED)
    vi.spyOn(api, 'uploadFusionCalibration').mockResolvedValue({
      ok: true,
      calibration: STORED.calibration!,
      active: STORED,
    })
    render(<FusionCalibrationPanel />, { wrapper: withQueryClient() })

    expect(await screen.findByText(/No calibration/)).toBeInTheDocument()
    fireEvent.change(screen.getByTestId('fusion-calibration-upload'), {
      target: { files: [new File(['{}'], 'cal.json')] },
    })

    expect(await screen.findByText('rig-7')).toBeInTheDocument()
    expect(screen.getByText('1.25 px')).toBeInTheDocument()
    await waitFor(() => expect(status).toHaveBeenCalledTimes(2))
  })

  test('shows the load error in place of the source label', async () => {
    vi.spyOn(api, 'fusionCalibration').mockRejectedValue(new ApiError(500, '', 'Calibration unavailable'))
    render(<FusionCalibrationPanel />, { wrapper: withQueryClient() })

    expect(await screen.findByText('Calibration unavailable')).toBeInTheDocument()
  })
})
