'use client'

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, NotebookPen, Plus, Trash2 } from 'lucide-react'
import { api, type NoteCreate, type NoteKind, type TrackNote } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'
import { useToast } from '@/components/Platform/Toast'
import { useErrorToast } from '@/components/Platform/hooks/useErrorToast'

const KINDS: NoteKind[] = ['research', 'log', 'doc', 'link', 'idea', 'other']
const NO_NOTES: TrackNote[] = []

export function TrackNotesPanel() {
  const toast = useToast()
  const queryClient = useQueryClient()
  const [filter, setFilter] = useState<string>('')
  const [title, setTitle] = useState('')
  const [kind, setKind] = useState<NoteKind>('research')
  const [body, setBody] = useState('')
  const [url, setUrl] = useState('')
  const [tags, setTags] = useState('')

  const notesQuery = useQuery({
    queryKey: queryKeys.track.notes(filter),
    queryFn: () => api.trackNotes(filter || undefined),
  })
  useErrorToast(notesQuery.error)
  const notes = notesQuery.data ?? NO_NOTES

  // Every kind filter shows the change, so refresh all cached note lists.
  const refreshNotes = () => void queryClient.invalidateQueries({ queryKey: queryKeys.track.notesAll })
  const onError = (err: unknown) => toast.error(err instanceof Error ? err.message : String(err))

  const createMutation = useMutation({
    mutationFn: (body: NoteCreate) => api.createNote(body),
    onSuccess: () => {
      setTitle(''); setBody(''); setUrl(''); setTags('')
      refreshNotes()
    },
    onError,
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.deleteNote(id),
    onSuccess: refreshNotes,
    onError,
  })

  function create() {
    if (!title.trim()) {
      toast.error('Note title is required')
      return
    }
    createMutation.mutate({
      title: title.trim(),
      kind,
      body: body.trim() || null,
      url: url.trim() || null,
      tags: tags.trim() || null,
    })
  }

  function remove(note: TrackNote) {
    if (!window.confirm(`Delete note "${note.title}"?`)) return
    deleteMutation.mutate(note.id)
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <div className="panel-title"><NotebookPen size={15} /> Research & logs</div>
          <p>Notes, hardware logs, datasheet links — anything useful for future work</p>
        </div>
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">All kinds</option>
          {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
        </select>
      </div>

      <div className="inv-form">
        <input placeholder="Title *" value={title} onChange={(e) => setTitle(e.target.value)} />
        <select value={kind} onChange={(e) => setKind(e.target.value as NoteKind)}>
          {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
        </select>
        <input placeholder="Link (optional)" value={url} onChange={(e) => setUrl(e.target.value)} />
        <input placeholder="Tags (comma-separated)" value={tags} onChange={(e) => setTags(e.target.value)} />
        <textarea
          className="inv-note-body"
          rows={3}
          placeholder="Details, findings, measurements…"
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
        <div className="inv-form-actions">
          <button type="button" className="primary" onClick={create}><Plus size={14} /> Add note</button>
        </div>
      </div>

      {notes.length === 0 && <div className="empty">No notes yet.</div>}
      <div className="track-notes">
        {notes.map((n) => (
          <article className="track-note" key={n.id}>
            <header>
              <span className={`inv-status inv-note-${n.kind}`}>{n.kind}</span>
              <strong>{n.title}</strong>
              {n.url && (
                <a href={n.url} target="_blank" rel="noopener noreferrer" title="Open link">
                  <ExternalLink size={12} />
                </a>
              )}
              <button type="button" className="inv-icon-btn" onClick={() => remove(n)} title="Delete note">
                <Trash2 size={13} />
              </button>
            </header>
            {n.body && <p>{n.body}</p>}
            <footer>
              {n.tags && <span className="track-note-tags">{n.tags}</span>}
              {n.created_at && <time>{new Date(n.created_at).toLocaleDateString()}</time>}
            </footer>
          </article>
        ))}
      </div>
    </section>
  )
}
