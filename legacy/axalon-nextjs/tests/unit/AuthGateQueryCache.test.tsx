import '@testing-library/jest-dom/vitest'
import { QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { AuthGate } from '@/components/Platform/AuthGate'
import { RailAccount } from '@/components/Platform/RailAccount'
import { makeQueryClient } from './queryWrapper'

const STORAGE_KEY = 'axalon_api_key'
const KEY = ['projects', 'list']

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status })
}

const operatorMe = {
  mode: 'users',
  kind: 'user',
  role: 'operator',
  project_ids: [1],
  user: { id: 2, email: 'op@axalon.test', role: 'operator', disabled: false, project_ids: [1], created_at: null },
}

beforeEach(() => {
  window.history.replaceState({}, '', '/platform')
})

afterEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
})

describe('AuthGate and the query cache', () => {
  test('signing out drops cached data so the next account never sees it', async () => {
    sessionStorage.setItem(STORAGE_KEY, 'sess-existing')
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url.includes('/auth/mode')) return json({ mode: 'users' })
      if (url.includes('/auth/me')) return json(operatorMe)
      if (url.endsWith('/auth/logout')) return new Response(null, { status: 204 })
      return json({ detail: 'unmocked' }, 404)
    })
    const client = makeQueryClient()
    client.setQueryData(KEY, [{ id: 1, name: 'Operator-only project' }])
    render(
      <QueryClientProvider client={client}>
        <AuthGate>
          <RailAccount />
        </AuthGate>
      </QueryClientProvider>,
    )

    fireEvent.click(await screen.findByRole('button', { name: /sign out/i }))
    expect(await screen.findByLabelText(/email/i)).toBeInTheDocument()
    expect(client.getQueryData(KEY)).toBeUndefined()
  })

  test('entering an API key marks cached queries stale so they reload with it', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (String(input).includes('/auth/mode')) return json({ mode: 'apikey' })
      return json({ detail: 'unmocked' }, 404)
    })
    const client = makeQueryClient()
    client.setQueryData(KEY, ['fetched with the old key'])
    expect(client.getQueryState(KEY)?.isInvalidated).toBe(false)
    render(
      <QueryClientProvider client={client}>
        <AuthGate>
          <div>content</div>
        </AuthGate>
      </QueryClientProvider>,
    )

    act(() => window.dispatchEvent(new Event('axalon:unauthorized')))
    fireEvent.change(screen.getByPlaceholderText(/Bearer key/i), { target: { value: 'k-123' } })
    fireEvent.click(screen.getByRole('button', { name: /unlock/i }))

    await waitFor(() => expect(client.getQueryState(KEY)?.isInvalidated).toBe(true))
  })

  test('works without a QueryClient provider', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('offline'))
    render(
      <AuthGate>
        <div>content</div>
      </AuthGate>,
    )
    expect(screen.getByText('content')).toBeInTheDocument()
  })
})
