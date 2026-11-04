import '@testing-library/jest-dom/vitest'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { act, render, screen } from '@testing-library/react'
import { ToastProvider, useToast } from '@/components/Platform/Toast'

afterEach(() => {
  vi.useRealTimers()
})

function Pusher({ kind, text }: { kind: 'error' | 'info' | 'success'; text: string }) {
  const toast = useToast()
  return <button onClick={() => toast[kind](text)}>push</button>
}

describe('Toast', () => {
  test('useToast throws outside provider', () => {
    function Bad() {
      useToast()
      return null
    }
    // Suppress React's error log for the expected throw
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<Bad />)).toThrow(/inside <ToastProvider>/)
    spy.mockRestore()
  })

  test('renders an error toast after push', async () => {
    render(
      <ToastProvider>
        <Pusher kind="error" text="kaboom" />
      </ToastProvider>
    )
    act(() => {
      screen.getByText('push').click()
    })
    expect(await screen.findByText('kaboom')).toBeInTheDocument()
  })

  test('auto-dismisses after 6 seconds', async () => {
    vi.useFakeTimers()
    render(
      <ToastProvider>
        <Pusher kind="info" text="bye" />
      </ToastProvider>
    )
    act(() => {
      screen.getByText('push').click()
    })
    expect(screen.getByText('bye')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(6001)
    })
    expect(screen.queryByText('bye')).not.toBeInTheDocument()
  })
})
