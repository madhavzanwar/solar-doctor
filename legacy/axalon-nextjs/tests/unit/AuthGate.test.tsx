import '@testing-library/jest-dom/vitest'
import { afterEach, describe, expect, test } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { AuthGate } from '@/components/Platform/AuthGate'

const STORAGE_KEY = 'axalon_api_key'

afterEach(() => {
  sessionStorage.clear()
})

describe('AuthGate', () => {
  test('renders children without dialog when no key exists (keyless backend)', () => {
    // Locks only on a real 401 (axalon:unauthorized) — not preemptively.
    render(<AuthGate><div>content</div></AuthGate>)
    expect(screen.getByText('content')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  test('seeds key from env var and renders without dialog', () => {
    process.env.NEXT_PUBLIC_AXALON_API_KEY = 'env-key'
    try {
      render(<AuthGate><div>content</div></AuthGate>)
      expect(screen.getByText('content')).toBeInTheDocument()
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(sessionStorage.getItem(STORAGE_KEY)).toBe('env-key')
    } finally {
      delete process.env.NEXT_PUBLIC_AXALON_API_KEY
    }
  })

  test('shows lock screen when unauthorized event fires', () => {
    render(<AuthGate><div>content</div></AuthGate>)
    act(() => window.dispatchEvent(new Event('axalon:unauthorized')))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/Bearer key/i)).toBeInTheDocument()
  })

  test('children remain visible behind the lock overlay', () => {
    render(<AuthGate><div>content</div></AuthGate>)
    act(() => window.dispatchEvent(new Event('axalon:unauthorized')))
    expect(screen.getByText('content')).toBeInTheDocument()
  })

  test('unlock dismisses dialog and stores key', () => {
    render(<AuthGate><div>content</div></AuthGate>)
    act(() => window.dispatchEvent(new Event('axalon:unauthorized')))
    fireEvent.change(screen.getByPlaceholderText(/Bearer key/i), { target: { value: 'secret123' } })
    fireEvent.click(screen.getByRole('button', { name: /Unlock/i }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(sessionStorage.getItem(STORAGE_KEY)).toBe('secret123')
  })

  test('shows error when submitting empty key', () => {
    render(<AuthGate><div>content</div></AuthGate>)
    act(() => window.dispatchEvent(new Event('axalon:unauthorized')))
    fireEvent.click(screen.getByRole('button', { name: /Unlock/i }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText(/Enter a key/i)).toBeInTheDocument()
  })

  test('Enter key submits the form', () => {
    render(<AuthGate><div>content</div></AuthGate>)
    act(() => window.dispatchEvent(new Event('axalon:unauthorized')))
    const input = screen.getByPlaceholderText(/Bearer key/i)
    fireEvent.change(input, { target: { value: 'mykey' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(sessionStorage.getItem(STORAGE_KEY)).toBe('mykey')
  })

  test('reads pre-stored key and does not show lock on mount', () => {
    sessionStorage.setItem(STORAGE_KEY, 'pre-stored')
    render(<AuthGate><div>content</div></AuthGate>)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
