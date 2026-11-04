import '@testing-library/jest-dom/vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { OrthoGenerator } from '@/components/Platform/OrthoGenerator'
import { api, ApiError } from '@/lib/api'
import type { OdmJob } from '@/lib/odm'
import { withQueryClient } from './queryWrapper'

const CONFIGURED = { status: 'ok', capabilities: { odm: { configured: true, message: null } } }

const job = (overrides: Partial<OdmJob> = {}): OdmJob => ({
  job_id: 'odm-abc',
  park_id: 'P1',
  state: 'running',
  progress: 0.3,
  stage: 'Processing on NodeODM (27%)',
  error: null,
  message: null,
  ortho_name: null,
  ...overrides,
})

function renderGenerator(ui: React.ReactElement) {
  return render(ui, { wrapper: withQueryClient() })
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

beforeEach(() => {
  vi.spyOn(api, 'orthoGenerationJobs').mockResolvedValue([])
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('OrthoGenerator', () => {
  test('is disabled with the backend explanation when ODM is not configured', async () => {
    vi.spyOn(api, 'health').mockResolvedValue({
      status: 'ok',
      capabilities: { odm: { configured: false, message: 'Set AXALON_NODEODM_URL' } },
    })
    renderGenerator(<OrthoGenerator parkId="P1" onOrthoReady={vi.fn()} />)

    const button = await screen.findByRole('button', { name: /generate orthomosaic/i })
    await waitFor(() => expect(button).toBeDisabled())
    expect(screen.getByText(/Set AXALON_NODEODM_URL/)).toBeInTheDocument()
  })

  test('validates the zip before uploading', async () => {
    vi.spyOn(api, 'health').mockResolvedValue(CONFIGURED)
    const generate = vi.spyOn(api, 'generateOrtho')
    renderGenerator(<OrthoGenerator parkId="P1" onOrthoReady={vi.fn()} />)

    const open = await screen.findByRole('button', { name: /generate orthomosaic/i })
    await waitFor(() => expect(open).toBeEnabled())
    fireEvent.click(open)
    const input = screen.getByLabelText(/images zip/i)
    fireEvent.change(input, { target: { files: [new File(['x'], 'flight.tar')] } })
    fireEvent.click(screen.getByRole('button', { name: /^start/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/\.zip/)
    expect(generate).not.toHaveBeenCalled()
  })

  test('uploads, shows progress, and reports completion', async () => {
    vi.spyOn(api, 'health').mockResolvedValue(CONFIGURED)
    const generate = vi.spyOn(api, 'generateOrtho').mockResolvedValue(job({ state: 'queued', progress: 0 }))
    vi.spyOn(api, 'orthoGenerationStatus')
      .mockResolvedValueOnce(job())
      .mockResolvedValue(job({ state: 'succeeded', progress: 1, ortho_name: 'odm_abc.tif' }))
    const onReady = vi.fn()
    renderGenerator(<OrthoGenerator parkId="P1" onOrthoReady={onReady} pollMs={10} />)

    const open = await screen.findByRole('button', { name: /generate orthomosaic/i })
    await waitFor(() => expect(open).toBeEnabled())
    fireEvent.click(open)
    fireEvent.change(screen.getByLabelText(/images zip/i), {
      target: { files: [new File(['zip'], 'flight.zip')] },
    })
    fireEvent.click(screen.getByRole('button', { name: /^start/i }))

    await waitFor(() => expect(generate).toHaveBeenCalledTimes(1))
    const form = generate.mock.calls[0][1] as FormData
    expect((form.get('images') as File).name).toBe('flight.zip')
    expect(form.get('sensor')).toBe('auto')

    await waitFor(() => expect(onReady).toHaveBeenCalledWith('odm_abc.tif'))
    expect(screen.getByText(/completed/i)).toBeInTheDocument()
  })

  test('shows the active job with a working cancel button', async () => {
    vi.spyOn(api, 'health').mockResolvedValue(CONFIGURED)
    vi.mocked(api.orthoGenerationJobs).mockResolvedValue([job()])
    vi.spyOn(api, 'orthoGenerationStatus').mockResolvedValue(job())
    const cancel = vi
      .spyOn(api, 'cancelOrthoGeneration')
      .mockResolvedValue(job({ state: 'cancelled' }))
    renderGenerator(<OrthoGenerator parkId="P1" onOrthoReady={vi.fn()} pollMs={60_000} />)

    expect(await screen.findByRole('progressbar')).toHaveAttribute('aria-valuenow', '30')
    expect(screen.getByText(/Processing on NodeODM/)).toBeInTheDocument()

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    })
    expect(cancel).toHaveBeenCalledWith('P1', 'odm-abc')
    expect(await screen.findByText(/cancelled/i)).toBeInTheDocument()
  })

  test('surfaces a failed job error', async () => {
    vi.spyOn(api, 'health').mockResolvedValue(CONFIGURED)
    vi.mocked(api.orthoGenerationJobs).mockResolvedValue([
      job({ state: 'failed', error: 'NodeODM task failed: Not enough overlap' }),
    ])
    renderGenerator(<OrthoGenerator parkId="P1" onOrthoReady={vi.fn()} />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/Not enough overlap/)
  })

  test('shows upload errors from the API', async () => {
    vi.spyOn(api, 'health').mockResolvedValue(CONFIGURED)
    vi.spyOn(api, 'generateOrtho').mockRejectedValue(
      new ApiError(400, '{"detail":"ZIP holds 2 images"}', 'ZIP holds 2 images'),
    )
    renderGenerator(<OrthoGenerator parkId="P1" onOrthoReady={vi.fn()} />)
    const open = await screen.findByRole('button', { name: /generate orthomosaic/i })
    await waitFor(() => expect(open).toBeEnabled())
    fireEvent.click(open)
    fireEvent.change(screen.getByLabelText(/images zip/i), {
      target: { files: [new File(['zip'], 'flight.zip')] },
    })
    fireEvent.click(screen.getByRole('button', { name: /^start/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/ZIP holds 2 images/)
  })

  test('stops polling once the job finishes and reports it exactly once', async () => {
    vi.spyOn(api, 'health').mockResolvedValue(CONFIGURED)
    vi.mocked(api.orthoGenerationJobs).mockResolvedValue([job()])
    const status = vi
      .spyOn(api, 'orthoGenerationStatus')
      .mockResolvedValue(job({ state: 'succeeded', progress: 1, ortho_name: 'odm_abc.tif' }))
    const onReady = vi.fn()
    renderGenerator(<OrthoGenerator parkId="P1" onOrthoReady={onReady} pollMs={10} />)

    await waitFor(() => expect(onReady).toHaveBeenCalledWith('odm_abc.tif'))
    const calls = status.mock.calls.length
    await sleep(80)
    expect(status.mock.calls.length).toBe(calls)
    expect(onReady).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })

  test('stops polling when the job is gone on the server', async () => {
    vi.spyOn(api, 'health').mockResolvedValue(CONFIGURED)
    vi.mocked(api.orthoGenerationJobs).mockResolvedValue([job()])
    const status = vi.spyOn(api, 'orthoGenerationStatus').mockRejectedValue(new ApiError(404, ''))
    renderGenerator(<OrthoGenerator parkId="P1" onOrthoReady={vi.fn()} pollMs={10} />)

    await waitFor(() => expect(status).toHaveBeenCalled())
    await sleep(80)
    expect(status).toHaveBeenCalledTimes(1)
  })

  test('does not report an ortho for a job that had already finished', async () => {
    vi.spyOn(api, 'health').mockResolvedValue(CONFIGURED)
    vi.mocked(api.orthoGenerationJobs).mockResolvedValue([
      job({ state: 'succeeded', progress: 1, ortho_name: 'old.tif' }),
    ])
    const status = vi.spyOn(api, 'orthoGenerationStatus')
    const onReady = vi.fn()
    renderGenerator(<OrthoGenerator parkId="P1" onOrthoReady={onReady} pollMs={10} />)

    expect(await screen.findByText(/completed/i)).toBeInTheDocument()
    await sleep(50)
    expect(onReady).not.toHaveBeenCalled()
    expect(status).not.toHaveBeenCalled()
  })
})
