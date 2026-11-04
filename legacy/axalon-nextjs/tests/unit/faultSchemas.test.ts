import { describe, expect, test } from 'vitest'

import {
  MAX_PROOF_PHOTO_BYTES,
  assignFaultSchema,
  proofPhotoSchema,
  statusChangeSchema,
} from '@/lib/schemas/faults'
import { buildAssignPayload, nextStatuses } from '@/lib/faultWorkflow'
import { workOrdersQuery } from '@/lib/api'

describe('workOrdersQuery', () => {
  test('format only by default', () => {
    expect(workOrdersQuery('csv')).toBe('format=csv')
  })

  test('joins statuses and trims the assignee filter', () => {
    const q = new URLSearchParams(workOrdersQuery('xlsx', { status: ['assigned', 'in_progress'], assignee: ' Ravi ' }))
    expect(q.get('format')).toBe('xlsx')
    expect(q.get('status')).toBe('assigned,in_progress')
    expect(q.get('assignee')).toBe('Ravi')
  })
})

describe('assignFaultSchema', () => {
  test('parses assignee, due date and priority override', () => {
    const r = assignFaultSchema.parse({ assignee: '  Ravi  ', due_date: '2026-10-01', priority: 'high' })
    expect(r).toEqual({ assignee: 'Ravi', due_date: '2026-10-01', priority: 'high' })
  })

  test('blank due date and priority become null (derived priority)', () => {
    const r = assignFaultSchema.parse({ assignee: 'crew-a', due_date: '', priority: '' })
    expect(r.due_date).toBeNull()
    expect(r.priority).toBeNull()
  })

  test('requires an assignee', () => {
    const r = assignFaultSchema.safeParse({ assignee: '   ', due_date: '', priority: '' })
    expect(r.success).toBe(false)
    if (!r.success) expect(r.error.issues[0].message).toMatch(/assignee is required/i)
  })

  test('rejects an impossible calendar date', () => {
    expect(assignFaultSchema.safeParse({ assignee: 'a', due_date: '2026-02-30', priority: '' }).success).toBe(false)
    expect(assignFaultSchema.safeParse({ assignee: 'a', due_date: '01/10/2026', priority: '' }).success).toBe(false)
  })

  test('rejects an unknown priority', () => {
    expect(assignFaultSchema.safeParse({ assignee: 'a', due_date: '', priority: 'asap' }).success).toBe(false)
  })
})

describe('statusChangeSchema', () => {
  test('accepts a plain status change with no note', () => {
    expect(statusChangeSchema.parse({ status: 'in_progress', resolution_note: '' })).toEqual({
      status: 'in_progress',
      resolution_note: null,
    })
  })

  test('requires a resolution note when resolving', () => {
    const r = statusChangeSchema.safeParse({ status: 'resolved', resolution_note: '  ' })
    expect(r.success).toBe(false)
    if (!r.success) {
      expect(r.error.issues[0].path).toEqual(['resolution_note'])
      expect(r.error.issues[0].message).toMatch(/resolution note/i)
    }
  })

  test('rejects statuses the API does not know', () => {
    expect(statusChangeSchema.safeParse({ status: 'done', resolution_note: '' }).success).toBe(false)
  })
})

describe('proofPhotoSchema', () => {
  const photo = { name: 'after.jpg', type: 'image/jpeg', size: 2048 }

  test('accepts jpeg, png and webp', () => {
    for (const type of ['image/jpeg', 'image/png', 'image/webp']) {
      expect(proofPhotoSchema.safeParse({ ...photo, type }).success).toBe(true)
    }
  })

  test('rejects other file types', () => {
    const r = proofPhotoSchema.safeParse({ ...photo, name: 'report.pdf', type: 'application/pdf' })
    expect(r.success).toBe(false)
  })

  test('rejects empty and oversize files', () => {
    expect(proofPhotoSchema.safeParse({ ...photo, size: 0 }).success).toBe(false)
    expect(proofPhotoSchema.safeParse({ ...photo, size: MAX_PROOF_PHOTO_BYTES + 1 }).success).toBe(false)
    expect(proofPhotoSchema.safeParse({ ...photo, size: MAX_PROOF_PHOTO_BYTES }).success).toBe(true)
  })
})

describe('fault workflow helpers', () => {
  test('a resolved fault can only be reopened', () => {
    expect(nextStatuses('resolved')).toEqual(['open'])
  })

  test('dispatched work cannot be marked stale by hand', () => {
    expect(nextStatuses('assigned')).not.toContain('stale')
    expect(nextStatuses('in_progress')).toEqual(['open', 'assigned', 'resolved'])
  })

  test('assigning an undispatched fault also moves it to assigned', () => {
    const values = { assignee: 'Ravi', due_date: null, priority: null }
    expect(buildAssignPayload('open', values)).toEqual({ ...values, status: 'assigned' })
    expect(buildAssignPayload('stale', values).status).toBe('assigned')
  })

  test('reassigning in-flight work keeps its status', () => {
    const values = { assignee: 'Crew B', due_date: '2026-10-02', priority: 'urgent' as const }
    expect(buildAssignPayload('in_progress', values)).toEqual(values)
  })
})
