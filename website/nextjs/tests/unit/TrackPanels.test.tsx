import '@testing-library/jest-dom/vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { TrackFilesPanel } from '@/components/Track/TrackFilesPanel'
import { TrackNotesPanel } from '@/components/Track/TrackNotesPanel'
import { api, type TrackFileMeta, type TrackNote } from '@/lib/api'
import { withQueryClient } from './queryWrapper'

afterEach(() => {
  vi.restoreAllMocks()
})

const note = (overrides: Partial<TrackNote> = {}): TrackNote =>
  ({ id: 1, title: 'Gimbal drift', kind: 'log', body: null, url: null, tags: null, ...overrides }) as TrackNote

const file = (overrides: Partial<TrackFileMeta> = {}): TrackFileMeta =>
  ({ id: 7, original_name: 'mount.stl', label: null, size_bytes: 2048, created_at: null, ...overrides }) as TrackFileMeta

describe('TrackNotesPanel', () => {
  test('adding a note clears the form and refetches the list', async () => {
    const list = vi
      .spyOn(api, 'trackNotes')
      .mockResolvedValueOnce([])
      .mockResolvedValue([note({ id: 2, title: 'Battery sag' })])
    const create = vi.spyOn(api, 'createNote').mockResolvedValue(note({ id: 2, title: 'Battery sag' }))
    render(<TrackNotesPanel />, { wrapper: withQueryClient() })

    expect(await screen.findByText('No notes yet.')).toBeInTheDocument()
    fireEvent.change(screen.getByPlaceholderText('Title *'), { target: { value: 'Battery sag' } })
    fireEvent.click(screen.getByRole('button', { name: /add note/i }))

    expect(await screen.findByText('Battery sag')).toBeInTheDocument()
    expect(create).toHaveBeenCalledWith(expect.objectContaining({ title: 'Battery sag', kind: 'research' }))
    expect(list).toHaveBeenCalledTimes(2)
    expect(screen.getByPlaceholderText('Title *')).toHaveValue('')
  })

  test('the kind filter is sent to the API', async () => {
    const list = vi.spyOn(api, 'trackNotes').mockResolvedValue([note()])
    render(<TrackNotesPanel />, { wrapper: withQueryClient() })

    await screen.findByText('Gimbal drift')
    fireEvent.change(screen.getByDisplayValue('All kinds'), { target: { value: 'log' } })
    await waitFor(() => expect(list).toHaveBeenLastCalledWith('log'))
    expect(list).toHaveBeenCalledWith(undefined)
  })
})

describe('TrackFilesPanel', () => {
  test('deleting a file refetches the library', async () => {
    const list = vi.spyOn(api, 'trackFiles').mockResolvedValueOnce([file()]).mockResolvedValue([])
    const remove = vi.spyOn(api, 'deleteTrackFile').mockResolvedValue(undefined)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<TrackFilesPanel />, { wrapper: withQueryClient() })

    fireEvent.click(await screen.findByTitle('Delete'))
    expect(await screen.findByText('No files uploaded yet.')).toBeInTheDocument()
    expect(remove).toHaveBeenCalledWith(7)
    expect(list).toHaveBeenCalledTimes(2)
  })

  test('a failed load is reported', async () => {
    vi.spyOn(api, 'trackFiles').mockRejectedValue(new Error('Track storage offline'))
    render(<TrackFilesPanel />, { wrapper: withQueryClient() })

    expect(await screen.findByText('Track storage offline')).toBeInTheDocument()
  })
})
