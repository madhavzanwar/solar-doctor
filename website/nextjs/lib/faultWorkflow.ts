// Fault repair workflow rules — pure, vitest-covered.
//
// Mirrors platform/core/fault_workflow.py so the UI only offers moves the API
// will accept. The server stays authoritative; keep the two in sync.
import type { FaultPriority, FaultStatus, FaultUpdate } from '@/lib/api'

export const FAULT_STATUSES: readonly FaultStatus[] = [
  'open',
  'stale',
  'assigned',
  'in_progress',
  'resolved',
] as const

export const FAULT_PRIORITIES: readonly FaultPriority[] = ['urgent', 'high', 'medium', 'low'] as const

export const STATUS_LABEL: Record<FaultStatus, string> = {
  open: 'Open',
  stale: 'Stale',
  assigned: 'Assigned',
  in_progress: 'In progress',
  resolved: 'Resolved',
}

const ALLOWED_TRANSITIONS: Record<FaultStatus, readonly FaultStatus[]> = {
  open: ['stale', 'assigned', 'in_progress', 'resolved'],
  stale: ['open', 'assigned', 'in_progress', 'resolved'],
  assigned: ['open', 'in_progress', 'resolved'],
  in_progress: ['open', 'assigned', 'resolved'],
  resolved: ['open'],
}

/** Statuses an operator may move a fault to from `current`. */
export function nextStatuses(current: FaultStatus): FaultStatus[] {
  return [...(ALLOWED_TRANSITIONS[current] ?? [])]
}

export type AssignValues = {
  assignee: string
  due_date: string | null
  priority: FaultPriority | null
}

/** PATCH body for the Assign form — dispatches an undispatched fault. */
export function buildAssignPayload(current: FaultStatus, values: AssignValues): FaultUpdate {
  const isUndispatched = current === 'open' || current === 'stale'
  return isUndispatched ? { ...values, status: 'assigned' } : { ...values }
}
