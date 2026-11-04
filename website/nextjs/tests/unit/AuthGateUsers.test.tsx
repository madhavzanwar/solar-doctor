import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { AuthGate, CanWrite, useAuth } from '@/components/Platform/AuthGate'
import { RailAccount } from '@/components/Platform/RailAccount'

const STORAGE_KEY = 'axalon_api_key'

type Route = (url: string, init?: RequestInit) => Response | undefined

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status })
}

function mockApi(route: Route) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    return route(url, init) ?? json({ detail: 'unmocked' }, 404)
  })
}

const operatorMe = {
  mode: 'users',
  kind: 'user',
  role: 'operator',
  project_ids: [1],
  user: { id: 2, email: 'op@axalon.test', role: 'operator', disabled: false, project_ids: [1], created_at: null },
}

function Probe() {
  const { mode, me, canWrite, isAdmin } = useAuth()
  return (
    <div data-testid="probe">
      {mode}|{me?.role ?? 'none'}|{String(canWrite)}|{String(isAdmin)}
    </div>
  )
}

beforeEach(() => {
  window.history.replaceState({}, '', '/platform')
})

afterEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
})

describe('AuthGate in users mode', () => {
  test('shows an email/password login instead of the key dialog', async () => {
    mockApi((url) => {
      if (url.includes('/auth/mode')) return json({ mode: 'users' })
      if (url.includes('/auth/me')) return json({ detail: 'Not authenticated' }, 401)
    })
    render(<AuthGate><div>content</div></AuthGate>)
    expect(await screen.findByLabelText(/email/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
    expect(screen.queryByPlaceholderText(/Bearer key/i)).not.toBeInTheDocument()
    // Nothing behind the login is rendered until someone is signed in.
    expect(screen.queryByText('content')).not.toBeInTheDocument()
  })

  test('signing in stores the session token like the key and reveals the console', async () => {
    const fetchSpy = mockApi((url, init) => {
      if (url.includes('/auth/mode')) return json({ mode: 'users' })
      if (url.includes('/auth/me')) return json({ detail: 'Not authenticated' }, 401)
      if (url.endsWith('/auth/login') && init?.method === 'POST') {
        return json({ token: 'sess-123', expires_at: '2099-01-01T00:00:00', user: operatorMe.user })
      }
    })
    render(<AuthGate><div>content</div><Probe /></AuthGate>)
    fireEvent.change(await screen.findByLabelText(/email/i), { target: { value: 'op@axalon.test' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'correct-horse' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByText('content')).toBeInTheDocument()
    expect(sessionStorage.getItem(STORAGE_KEY)).toBe('sess-123')
    expect(screen.getByTestId('probe')).toHaveTextContent('users|operator|true|false')
    const loginCall = fetchSpy.mock.calls.find(([u]) => String(u).endsWith('/auth/login'))
    expect(JSON.parse(String(loginCall?.[1]?.body))).toEqual({ email: 'op@axalon.test', password: 'correct-horse' })
  })

  test('bad credentials show a generic error', async () => {
    mockApi((url) => {
      if (url.includes('/auth/mode')) return json({ mode: 'users' })
      if (url.includes('/auth/me')) return json({ detail: 'Not authenticated' }, 401)
      if (url.endsWith('/auth/login')) return json({ detail: 'Invalid email or password' }, 401)
    })
    render(<AuthGate><div>content</div></AuthGate>)
    fireEvent.change(await screen.findByLabelText(/email/i), { target: { value: 'op@axalon.test' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'nope' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    expect(await screen.findByText(/invalid email or password/i)).toBeInTheDocument()
  })

  test('rate limiting is explained', async () => {
    mockApi((url) => {
      if (url.includes('/auth/mode')) return json({ mode: 'users' })
      if (url.includes('/auth/me')) return json({ detail: 'Not authenticated' }, 401)
      if (url.endsWith('/auth/login')) return json({ detail: 'Too many' }, 429)
    })
    render(<AuthGate><div>content</div></AuthGate>)
    fireEvent.change(await screen.findByLabelText(/email/i), { target: { value: 'op@axalon.test' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'nope' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    expect(await screen.findByText(/too many attempts/i)).toBeInTheDocument()
  })

  test('an existing session is resumed without a login prompt', async () => {
    sessionStorage.setItem(STORAGE_KEY, 'sess-existing')
    const fetchSpy = mockApi((url) => {
      if (url.includes('/auth/mode')) return json({ mode: 'users' })
      if (url.includes('/auth/me')) return json({ ...operatorMe, role: 'viewer' })
    })
    render(<AuthGate><div>content</div><Probe /></AuthGate>)
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('users|viewer|false|false'))
    expect(screen.getByText('content')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    const meCall = fetchSpy.mock.calls.find(([u]) => String(u).includes('/auth/me'))
    expect((meCall?.[1]?.headers as Record<string, string>).Authorization).toBe('Bearer sess-existing')
  })

  test('a share link opens a read-only view without logging in', async () => {
    window.history.replaceState({}, '', '/platform?share=tok-abc')
    const fetchSpy = mockApi((url) => {
      if (url.includes('/auth/mode')) return json({ mode: 'users' })
      if (url.includes('/auth/me')) return json({ mode: 'users', kind: 'share', role: 'viewer', project_ids: [1], user: null })
    })
    render(<AuthGate><div>content</div><Probe /><RailAccount /></AuthGate>)
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('users|viewer|false|false'))
    expect(screen.getByText('content')).toBeInTheDocument()
    expect(screen.getByText(/shared view/i)).toBeInTheDocument()
    const meCall = fetchSpy.mock.calls.find(([u]) => String(u).includes('/auth/me'))
    expect(String(meCall?.[0])).toContain('share=tok-abc')
  })

  test('rail shows the signed-in user and logs out', async () => {
    sessionStorage.setItem(STORAGE_KEY, 'sess-existing')
    const fetchSpy = mockApi((url) => {
      if (url.includes('/auth/mode')) return json({ mode: 'users' })
      if (url.includes('/auth/me')) return json(operatorMe)
      if (url.endsWith('/auth/logout')) return new Response(null, { status: 204 })
    })
    render(<AuthGate><RailAccount /></AuthGate>)
    expect(await screen.findByText('op@axalon.test')).toBeInTheDocument()
    expect(screen.getByText(/operator/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /sign out/i }))
    expect(await screen.findByLabelText(/email/i)).toBeInTheDocument()
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull()
    expect(fetchSpy.mock.calls.some(([u]) => String(u).endsWith('/auth/logout'))).toBe(true)
  })

  test('CanWrite hides mutating controls from viewers', async () => {
    sessionStorage.setItem(STORAGE_KEY, 'sess-existing')
    mockApi((url) => {
      if (url.includes('/auth/mode')) return json({ mode: 'users' })
      if (url.includes('/auth/me')) return json({ ...operatorMe, role: 'viewer' })
    })
    render(<AuthGate><div>content</div><Probe /><CanWrite><button type="button">Delete</button></CanWrite></AuthGate>)
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('users|viewer'))
    expect(screen.getByText('content')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
  })
})

describe('AuthGate outside users mode', () => {
  test('apikey mode keeps the key dialog and shows no account in the rail', async () => {
    const fetchSpy = mockApi((url) => {
      if (url.includes('/auth/mode')) return json({ mode: 'apikey' })
    })
    render(<AuthGate><div>content</div><Probe /><RailAccount /><CanWrite><span>editable</span></CanWrite></AuthGate>)
    await waitFor(() => expect(screen.getByTestId('probe')).toHaveTextContent('apikey|none|true|false'))
    expect(screen.getByText('editable')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /sign out/i })).not.toBeInTheDocument()
    act(() => window.dispatchEvent(new Event('axalon:unauthorized')))
    expect(screen.getByPlaceholderText(/Bearer key/i)).toBeInTheDocument()
    expect(fetchSpy.mock.calls.some(([u]) => String(u).includes('/auth/me'))).toBe(false)
  })

  test('an unreachable API falls back to legacy behaviour', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('offline'))
    render(<AuthGate><div>content</div><CanWrite><span>editable</span></CanWrite></AuthGate>)
    expect(screen.getByText('content')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('editable')).toBeInTheDocument())
  })
})
