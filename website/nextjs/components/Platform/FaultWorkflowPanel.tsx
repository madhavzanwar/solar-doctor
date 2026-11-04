'use client'

import { useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Camera, CheckCircle2, Trash2, UserPlus, X } from 'lucide-react'
import { api, ApiError, type PanelFault } from '@/lib/api'
import { FAULT_PRIORITIES, STATUS_LABEL, buildAssignPayload, nextStatuses } from '@/lib/faultWorkflow'
import {
  assignFaultSchema,
  proofPhotoSchema,
  statusChangeSchema,
  type AssignFaultInput,
  type StatusChangeInput,
} from '@/lib/schemas/faults'
import { queryKeys } from '@/lib/queryKeys'
import { FieldError } from '@/components/Platform/FieldError'
import { useToast } from '@/components/Platform/Toast'
import { CanWrite, useAuth } from '@/components/Platform/AuthGate'

function errMessage(err: unknown): string {
  if (err instanceof ApiError) {
    try {
      const detail = (JSON.parse(err.body) as { detail?: unknown }).detail
      if (typeof detail === 'string') return detail
    } catch {
      // body was not JSON — fall through to the generic message
    }
  }
  return err instanceof Error ? err.message : String(err)
}

type Props = {
  fault: PanelFault
  onClose: () => void
}

/** Dispatch and close-out controls for one tracked fault. */
export function FaultWorkflowPanel({ fault, onClose }: Props) {
  const queryClient = useQueryClient()
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: queryKeys.faults.park(fault.park_id) })

  return (
    <section className="fault-workflow" aria-label={`Fault ${fault.id} workflow`}>
      <header className="fault-workflow-head">
        <div>
          <div className="fault-workflow-title">
            {fault.panel_id} · {fault.class}
          </div>
          <div className="fault-workflow-meta">
            <span className={`fault-status fault-status-${fault.status}`}>{STATUS_LABEL[fault.status]}</span>
            {fault.priority && <span className={`fault-priority fault-priority-${fault.priority}`}>{fault.priority}</span>}
            {fault.assignee && <span>→ {fault.assignee}</span>}
            {fault.due_date && <span>due {fault.due_date}</span>}
          </div>
        </div>
        <button type="button" className="inv-icon-btn" onClick={onClose} aria-label="Close fault workflow">
          <X size={14} />
        </button>
      </header>

      {fault.resolved_at && (
        <p className="fault-workflow-resolved">
          <CheckCircle2 size={13} /> Resolved {fault.resolved_at.slice(0, 10)}
          {fault.resolution_note ? ` — ${fault.resolution_note}` : ''}
        </p>
      )}

      {/* Viewers and share-link visitors get the read-only view; the API refuses writes regardless. */}
      <CanWrite>
        {fault.status !== 'resolved' && <AssignForm key={`assign-${fault.id}`} fault={fault} onSaved={invalidate} />}
        <StatusForm key={`status-${fault.id}-${fault.status}`} fault={fault} onSaved={invalidate} />
      </CanWrite>
      <ProofPhotos fault={fault} onChanged={invalidate} />
    </section>
  )
}

function AssignForm({ fault, onSaved }: { fault: PanelFault; onSaved: () => void }) {
  const toast = useToast()
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<AssignFaultInput>({
    resolver: zodResolver(assignFaultSchema),
    defaultValues: {
      assignee: fault.assignee ?? '',
      due_date: fault.due_date ?? '',
      priority: fault.priority_override ?? '',
    },
  })

  const onSubmit = handleSubmit(async (raw) => {
    const values = assignFaultSchema.parse(raw)
    try {
      await api.updateFault(fault.id, buildAssignPayload(fault.status, values))
      toast.success(`Assigned to ${values.assignee}`)
      onSaved()
    } catch (err) {
      toast.error(errMessage(err))
    }
  })

  return (
    <form className="inv-form" onSubmit={onSubmit} noValidate aria-label="Assign repair">
      <input placeholder="Assignee (name or email) *" aria-label="Assignee" {...register('assignee')} />
      <FieldError message={errors.assignee?.message} />
      <input type="date" aria-label="Due date" {...register('due_date')} />
      <FieldError message={errors.due_date?.message} />
      <select aria-label="Priority" {...register('priority')}>
        <option value="">Priority: from severity ({fault.priority_override ? 'reset' : fault.priority ?? '—'})</option>
        {FAULT_PRIORITIES.map((p) => (
          <option key={p} value={p}>
            {p}
          </option>
        ))}
      </select>
      <FieldError message={errors.priority?.message} />
      <div className="inv-form-actions">
        <button type="submit" className="primary" disabled={isSubmitting}>
          <UserPlus size={14} /> {fault.assignee ? 'Update' : 'Assign'}
        </button>
      </div>
    </form>
  )
}

function StatusForm({ fault, onSaved }: { fault: PanelFault; onSaved: () => void }) {
  const toast = useToast()
  const options = nextStatuses(fault.status)
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<StatusChangeInput>({
    resolver: zodResolver(statusChangeSchema),
    defaultValues: { status: options[0] ?? fault.status, resolution_note: fault.resolution_note ?? '' },
  })
  const target = watch('status')

  const onSubmit = handleSubmit(async (raw) => {
    const values = statusChangeSchema.parse(raw)
    try {
      await api.updateFault(fault.id, {
        status: values.status,
        ...(values.resolution_note !== null ? { resolution_note: values.resolution_note } : {}),
      })
      toast.success(`Fault moved to ${STATUS_LABEL[values.status]}`)
      onSaved()
    } catch (err) {
      toast.error(errMessage(err))
    }
  })

  if (options.length === 0) return null
  return (
    <form className="inv-form" onSubmit={onSubmit} noValidate aria-label="Change status">
      <select aria-label="New status" {...register('status')}>
        {options.map((s) => (
          <option key={s} value={s}>
            {fault.status === 'resolved' && s === 'open' ? 'Reopen' : STATUS_LABEL[s]}
          </option>
        ))}
      </select>
      <FieldError message={errors.status?.message} />
      {target === 'resolved' && (
        <>
          <textarea
            rows={2}
            placeholder="Resolution note — what was repaired? *"
            aria-label="Resolution note"
            {...register('resolution_note')}
          />
          <FieldError message={errors.resolution_note?.message} />
        </>
      )}
      <div className="inv-form-actions">
        <button type="submit" className="secondary" disabled={isSubmitting}>
          Set status
        </button>
      </div>
    </form>
  )
}

function ProofPhotos({ fault, onChanged }: { fault: PanelFault; onChanged: () => void }) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const { canWrite } = useAuth()
  const inputRef = useRef<HTMLInputElement>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [fileError, setFileError] = useState<string | undefined>()

  const photosQuery = useQuery({
    queryKey: queryKeys.faults.photos(fault.id),
    queryFn: () => api.faultPhotos(fault.id),
  })
  const photos = photosQuery.data ?? []

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.faults.photos(fault.id) })
    onChanged()
  }

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    const check = proofPhotoSchema.safeParse({ name: file.name, type: file.type, size: file.size })
    if (!check.success) {
      setFileError(check.error.issues[0]?.message)
      return
    }
    setFileError(undefined)
    setIsUploading(true)
    try {
      await api.uploadFaultPhoto(fault.id, file)
      toast.success('Proof photo uploaded')
      refresh()
    } catch (err) {
      toast.error(errMessage(err))
    } finally {
      setIsUploading(false)
    }
  }

  async function handleDelete(photoId: number) {
    try {
      await api.deleteFaultPhoto(fault.id, photoId)
      refresh()
    } catch (err) {
      toast.error(errMessage(err))
    }
  }

  return (
    <div className="fault-photos">
      <div className="fault-photos-head">
        <span>Repair proof ({photos.length})</span>
        {canWrite && (
          <>
            <button
              type="button"
              className="secondary"
              onClick={() => inputRef.current?.click()}
              disabled={isUploading}
            >
              <Camera size={14} /> {isUploading ? 'Uploading…' : 'Add photo'}
            </button>
            <input
              ref={inputRef}
              type="file"
              hidden
              accept="image/jpeg,image/png,image/webp"
              aria-label="Upload proof photo"
              onChange={handleFile}
            />
          </>
        )}
      </div>
      <FieldError message={fileError} />
      {photosQuery.error && <FieldError message={`Could not load photos — ${errMessage(photosQuery.error)}`} />}
      {photos.length > 0 && (
        <ul className="fault-photo-grid">
          {photos.map((p) => (
            <li key={p.id}>
              <a href={api.faultPhotoUrl(fault.id, p.id)} target="_blank" rel="noreferrer">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={api.faultPhotoUrl(fault.id, p.id)} alt={`Proof photo ${p.original_name}`} loading="lazy" />
              </a>
              {canWrite && (
                <button
                  type="button"
                  className="inv-icon-btn"
                  onClick={() => handleDelete(p.id)}
                  aria-label={`Delete photo ${p.original_name}`}
                >
                  <Trash2 size={12} />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
