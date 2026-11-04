import '@testing-library/jest-dom/vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { AssetsTab } from '@/components/Platform/AssetsTab'
import { api, ApiError, type Project, type ProjectDetail } from '@/lib/api'
import { withQueryClient } from './queryWrapper'

afterEach(() => {
  vi.restoreAllMocks()
})

const project = (overrides: Partial<Project> = {}): Project =>
  ({
    id: 1,
    name: 'North',
    client: 'Acme',
    description: null,
    status: 'active',
    site_count: 0,
    ...overrides,
  }) as Project

describe('AssetsTab', () => {
  test('creating a project refetches the list instead of patching it locally', async () => {
    vi.spyOn(api, 'parks').mockResolvedValue([])
    const list = vi
      .spyOn(api, 'projects')
      .mockResolvedValueOnce([project()])
      .mockResolvedValue([project(), project({ id: 2, name: 'South' })])
    const create = vi.spyOn(api, 'createProject').mockResolvedValue(project({ id: 2, name: 'South' }))
    render(<AssetsTab />, { wrapper: withQueryClient() })

    expect(await screen.findByText('North')).toBeInTheDocument()
    fireEvent.change(screen.getByPlaceholderText(/new project name/i), { target: { value: ' South ' } })
    fireEvent.click(screen.getByRole('button', { name: /create project/i }))

    expect(await screen.findByText('South')).toBeInTheDocument()
    expect(create).toHaveBeenCalledWith({ name: 'South', client: null, description: null })
    expect(list).toHaveBeenCalledTimes(2)
    expect(screen.getByPlaceholderText(/new project name/i)).toHaveValue('')
  })

  test('assigning a site refreshes both the site list and the project list', async () => {
    vi.spyOn(api, 'parks').mockResolvedValue([{ id: 'P1', name: 'Park One' }])
    const list = vi.spyOn(api, 'projects').mockResolvedValue([project()])
    const empty: ProjectDetail = { ...project(), sites: [] }
    const detail = vi.spyOn(api, 'project').mockResolvedValue(empty)
    const update = vi.spyOn(api, 'updatePark').mockResolvedValue({ id: 'P1', name: 'Park One', project_id: 1 })
    render(<AssetsTab />, { wrapper: withQueryClient() })

    fireEvent.click(await screen.findByText('North'))
    expect(await screen.findByText(/No sites assigned/)).toBeInTheDocument()
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'P1' } })
    fireEvent.click(screen.getByRole('button', { name: /assign/i }))

    await waitFor(() => expect(update).toHaveBeenCalledWith('P1', { project_id: 1 }))
    await waitFor(() => expect(detail).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2))
  })

  test('shows a retryable error when projects fail to load', async () => {
    vi.spyOn(api, 'parks').mockResolvedValue([])
    const list = vi
      .spyOn(api, 'projects')
      .mockRejectedValueOnce(new ApiError(500, '', 'Database down'))
      .mockResolvedValue([project()])
    render(<AssetsTab />, { wrapper: withQueryClient() })

    expect((await screen.findAllByText('Database down')).length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(await screen.findByText('North')).toBeInTheDocument()
    expect(list).toHaveBeenCalledTimes(2)
  })
})
