'use client'

import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, FolderOpen, Trash2, Upload } from 'lucide-react'
import { api, type TrackFileMeta } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'
import { useToast } from '@/components/Platform/Toast'
import { useErrorToast } from '@/components/Platform/hooks/useErrorToast'

const NO_FILES: TrackFileMeta[] = []

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${bytes} B`
}

export function TrackFilesPanel() {
  const toast = useToast()
  const queryClient = useQueryClient()
  const [label, setLabel] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const filesQuery = useQuery({ queryKey: queryKeys.track.files, queryFn: () => api.trackFiles() })
  useErrorToast(filesQuery.error)
  const files = filesQuery.data ?? NO_FILES

  const refreshFiles = () => void queryClient.invalidateQueries({ queryKey: queryKeys.track.files })
  const onError = (err: unknown) => toast.error(err instanceof Error ? err.message : String(err))

  const uploadMutation = useMutation({
    mutationFn: (form: FormData) => api.uploadTrackFile(form),
    onSuccess: () => {
      setLabel('')
      if (inputRef.current) inputRef.current.value = ''
      refreshFiles()
    },
    onError,
  })
  const isBusy = uploadMutation.isPending

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.deleteTrackFile(id),
    onSuccess: refreshFiles,
    onError,
  })

  function upload(selected: File) {
    const form = new FormData()
    form.append('file', selected)
    if (label.trim()) form.append('label', label.trim())
    uploadMutation.mutate(form)
  }

  function remove(f: TrackFileMeta) {
    if (!window.confirm(`Delete "${f.original_name}"?`)) return
    deleteMutation.mutate(f.id)
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <div className="panel-title"><FolderOpen size={15} /> File library</div>
          <p>CAD models (.stl/.step), datasheets (.pdf), photos — up to 200 MB each</p>
        </div>
      </div>

      <div className="inv-form">
        <input
          placeholder="Label (e.g. Camera mount v2 print file)"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
        <label className="track-upload">
          <Upload size={14} /> {isBusy ? 'Uploading…' : 'Choose file'}
          <input
            ref={inputRef}
            type="file"
            hidden
            disabled={isBusy}
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) upload(f)
            }}
          />
        </label>
      </div>

      {files.length === 0 && <div className="empty">No files uploaded yet.</div>}
      {files.length > 0 && (
        <div className="table">
          <div className="table-head track-file-head">
            <span>File</span>
            <span>Size</span>
            <span>Uploaded</span>
            <span />
          </div>
          {files.map((f) => (
            <div className="track-file-row" key={f.id}>
              <span className="inv-part">
                <strong>{f.original_name}</strong>
                {f.label && <small>{f.label}</small>}
              </span>
              <span>{formatBytes(f.size_bytes)}</span>
              <span>{f.created_at ? new Date(f.created_at).toLocaleDateString() : '—'}</span>
              <span className="track-file-actions">
                <a className="inv-icon-btn" href={api.trackFileUrl(f.id)} title="Download">
                  <Download size={14} />
                </a>
                <button type="button" className="inv-icon-btn" onClick={() => remove(f)} title="Delete">
                  <Trash2 size={14} />
                </button>
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
