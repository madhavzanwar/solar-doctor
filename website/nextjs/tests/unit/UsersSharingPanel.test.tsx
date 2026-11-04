import '@testing-library/jest-dom/vitest'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { UsersSharingPanel } from '@/components/Platform/UsersSharingPanel'
import { withQueryClient } from './queryWrapper'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status })
}

const users = [
  { id: 1, email: 'admin@axalon.test', role: 'admin', disabled: false, project_ids: [], created_at: null },
  { id: 2, email: 'op@axalon.test', role: 'operator', disabled: false, project_ids: [10], created_at: null },
]
const projects = [
  { id: 10, name: 'North', client: null, description: null, status: 'active', created_at: null, updated_at: null },
  { id: 11, name: 'South', client: null, description: null, status: 'active', created_at: null, updated_at: null },
]
const links = [
  {
    id: 5, project_id: 10, label: 'Client preview', created_by: 1, created_at: null,
    expires_at: '2099-01-01T00:00:00', revoked_at: null, revoked: false, expired: false,
  },
]

function mockBackend() {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    if (url.endsWith('/users') && method === 'GET') return json(users)
    if (url.endsWith('/projects')) return json(projects)
    if (url.endsWith('/share-links') && method === 'GET') return json(links)
    if (url.endsWith('/users') && method === 'POST') return json({ ...users[1], id: 3, email: 'new@axalon.test' }, 201)
    if (url.includes('/users/2') && method === 'PATCH') return json({ ...users[1], role: 'viewer' })
    if (url.endsWith('/share-links') && method === 'POST') return json({ ...links[0], id: 6, token: 'tok-xyz' }, 201)
    if (url.includes('/share-links/5') && method === 'DELETE') return new Response(null, { status: 204 })
    return json({ detail: 'unmocked' }, 404)
  })
}

function renderPanel() {
  return render(<UsersSharingPanel />, { wrapper: withQueryClient() })
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('UsersSharingPanel', () => {
  test('lists users with their roles', async () => {
    mockBackend()
    renderPanel()
    const row = (await screen.findByText('op@axalon.test')).closest('tr') as HTMLElement
    expect(within(row).getByLabelText(/role for op@axalon.test/i)).toHaveValue('operator')
  })

  test('adds a user with role and projects', async () => {
    const fetchSpy = mockBackend()
    renderPanel()
    await screen.findByText('op@axalon.test')
    fireEvent.change(screen.getByLabelText(/new user email/i), { target: { value: 'new@axalon.test' } })
    fireEvent.change(screen.getByLabelText(/initial password/i), { target: { value: 'long-enough-pw' } })
    fireEvent.change(screen.getByLabelText(/new user role/i), { target: { value: 'viewer' } })
    fireEvent.click(screen.getByLabelText(/grant South/i))
    fireEvent.click(screen.getByRole('button', { name: /add user/i }))
    await waitFor(() =>
      expect(fetchSpy.mock.calls.some(([u, i]) => String(u).endsWith('/users') && i?.method === 'POST')).toBe(true),
    )
    const call = fetchSpy.mock.calls.find(([u, i]) => String(u).endsWith('/users') && i?.method === 'POST')
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      email: 'new@axalon.test', password: 'long-enough-pw', role: 'viewer', project_ids: [11],
    })
  })

  test('changing a role PATCHes the user', async () => {
    const fetchSpy = mockBackend()
    renderPanel()
    fireEvent.change(await screen.findByLabelText(/role for op@axalon.test/i), { target: { value: 'viewer' } })
    await waitFor(() =>
      expect(fetchSpy.mock.calls.some(([u, i]) => String(u).includes('/users/2') && i?.method === 'PATCH')).toBe(true),
    )
  })

  test('creating a share link reveals its URL once', async () => {
    mockBackend()
    renderPanel()
    await screen.findByText('Client preview')
    fireEvent.change(screen.getByLabelText(/share project/i), { target: { value: '10' } })
    fireEvent.click(screen.getByRole('button', { name: /create link/i }))
    const input = (await screen.findByLabelText(/new share url/i)) as HTMLInputElement
    expect(input.value).toContain('/platform?share=tok-xyz')
  })

  test('revoking a share link calls DELETE', async () => {
    const fetchSpy = mockBackend()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderPanel()
    await screen.findByText('Client preview')
    fireEvent.click(screen.getByRole('button', { name: /revoke client preview/i }))
    await waitFor(() =>
      expect(fetchSpy.mock.calls.some(([u, i]) => String(u).includes('/share-links/5') && i?.method === 'DELETE')).toBe(true),
    )
  })

  test('the user list is refetched after adding someone', async () => {
    const created = { ...users[1], id: 3, email: 'new@axalon.test' }
    let hasNewUser = false
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      if (url.endsWith('/users') && method === 'POST') {
        hasNewUser = true
        return json(created, 201)
      }
      if (url.endsWith('/users')) return json(hasNewUser ? [...users, created] : users)
      if (url.endsWith('/projects')) return json(projects)
      if (url.endsWith('/share-links')) return json(links)
      return json({ detail: 'unmocked' }, 404)
    })
    renderPanel()
    await screen.findByText('op@axalon.test')
    fireEvent.change(screen.getByLabelText(/new user email/i), { target: { value: 'new@axalon.test' } })
    fireEvent.change(screen.getByLabelText(/initial password/i), { target: { value: 'long-enough-pw' } })
    fireEvent.click(screen.getByRole('button', { name: /add user/i }))

    expect(await screen.findByRole('cell', { name: 'new@axalon.test' })).toBeInTheDocument()
  })

  test('a revoked link is refetched from the server', async () => {
    let revoked = false
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      if (url.includes('/share-links/5') && method === 'DELETE') {
        revoked = true
        return new Response(null, { status: 204 })
      }
      if (url.endsWith('/share-links')) return json(revoked ? [{ ...links[0], revoked: true }] : links)
      if (url.endsWith('/users')) return json(users)
      if (url.endsWith('/projects')) return json(projects)
      return json({ detail: 'unmocked' }, 404)
    })
    renderPanel()
    fireEvent.click(await screen.findByRole('button', { name: /revoke client preview/i }))

    expect(await screen.findByText('revoked')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /revoke client preview/i })).not.toBeInTheDocument()
  })
})
