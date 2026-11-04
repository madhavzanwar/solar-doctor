import { z } from 'zod'

import type { FaultPriority, FaultStatus } from '@/lib/api'

// Limits mirror platform/api/routers/faults.py — the server re-validates.
export const MAX_PROOF_PHOTO_BYTES = 15 * 1024 * 1024
export const PROOF_PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp'] as const

const STATUS_VALUES = ['open', 'stale', 'assigned', 'in_progress', 'resolved'] as const
const PRIORITY_VALUES = ['urgent', 'high', 'medium', 'low'] as const

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/

function isRealIsoDate(v: string): boolean {
  if (!ISO_DATE_RE.test(v)) return false
  const d = new Date(`${v}T00:00:00Z`)
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === v
}

/** Optional <input type="date"> value. Blank → null. */
const optionalIsoDate = z
  .string()
  .trim()
  .refine((v) => v === '' || isRealIsoDate(v), 'Due date must be a valid date (YYYY-MM-DD)')
  .transform((v): string | null => (v === '' ? null : v))

/** Optional priority override. Blank → null, meaning "derive from severity". */
const optionalPriority = z
  .string()
  .trim()
  .refine(
    (v) => v === '' || (PRIORITY_VALUES as readonly string[]).includes(v),
    `Priority must be one of ${PRIORITY_VALUES.join(', ')}`,
  )
  .transform((v): FaultPriority | null => (v === '' ? null : (v as FaultPriority)))

export const assignFaultSchema = z.object({
  assignee: z
    .string()
    .trim()
    .min(1, 'Assignee is required')
    .max(200, 'Assignee must be 200 characters or fewer'),
  due_date: optionalIsoDate,
  priority: optionalPriority,
})
export type AssignFaultInput = z.input<typeof assignFaultSchema>

export const statusChangeSchema = z
  .object({
    status: z.enum(STATUS_VALUES, { errorMap: () => ({ message: 'Choose a valid status' }) }),
    resolution_note: z
      .string()
      .trim()
      .max(4000, 'Resolution note must be 4000 characters or fewer')
      .transform((v): string | null => (v === '' ? null : v)),
  })
  .refine((v) => v.status !== 'resolved' || Boolean(v.resolution_note), {
    message: 'Add a resolution note describing the repair',
    path: ['resolution_note'],
  })
export type StatusChangeInput = z.input<typeof statusChangeSchema>
export type StatusChangeValues = { status: FaultStatus; resolution_note: string | null }

/** Validates a picked File's metadata before it is uploaded. */
export const proofPhotoSchema = z.object({
  name: z.string().min(1),
  type: z.enum(PROOF_PHOTO_TYPES, {
    errorMap: () => ({ message: 'Photo must be a JPEG, PNG or WebP image' }),
  }),
  size: z
    .number()
    .positive('Photo is empty')
    .max(MAX_PROOF_PHOTO_BYTES, 'Photo must be 15 MB or smaller'),
})
