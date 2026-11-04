import '@testing-library/jest-dom/vitest'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { AlertTestPanel } from '@/components/Platform/AlertTestPanel'
import { api, ApiError } from '@/lib/api'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('AlertTestPanel', () => {
  test('sends a test alert and shows each channel result', async () => {
    const spy = vi.spyOn(api, 'testAlert').mockResolvedValueOnce({
      configured: true,
      min_severity: 'HIGH',
      channels: {
        webhook: { status: 'sent', detail: 'HTTP 200' },
        email: { status: 'failed', detail: 'SMTPAuthenticationError' },
      },
    })
    render(<AlertTestPanel />)
    fireEvent.click(screen.getByRole('button', { name: /send test alert/i }))
    await waitFor(() => expect(screen.getByText('sent')).toBeInTheDocument())
    expect(spy).toHaveBeenCalledOnce()
    expect(screen.getByText('failed')).toBeInTheDocument()
    expect(screen.getByText(/SMTPAuthenticationError/)).toBeInTheDocument()
    expect(screen.getByText(/HIGH/)).toBeInTheDocument()
  })

  test('explains when no channel is configured', async () => {
    vi.spyOn(api, 'testAlert').mockResolvedValueOnce({
      configured: false,
      min_severity: 'CRITICAL',
      channels: {
        webhook: { status: 'not_configured', detail: '' },
        email: { status: 'not_configured', detail: '' },
      },
    })
    render(<AlertTestPanel />)
    fireEvent.click(screen.getByRole('button', { name: /send test alert/i }))
    await waitFor(() =>
      expect(screen.getByText(/no alert channels are configured/i)).toBeInTheDocument(),
    )
    expect(screen.getAllByText('not configured')).toHaveLength(2)
  })

  test('shows the error when the request fails', async () => {
    vi.spyOn(api, 'testAlert').mockRejectedValueOnce(new ApiError(500, 'boom'))
    render(<AlertTestPanel />)
    fireEvent.click(screen.getByRole('button', { name: /send test alert/i }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/HTTP 500/))
  })
})
