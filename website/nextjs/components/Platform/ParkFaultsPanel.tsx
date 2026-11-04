'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ClipboardList, FileSpreadsheet, FileText } from 'lucide-react'
import { api, ApiError, type FaultStatus, type WorkOrderFormat } from '@/lib/api'
import { FAULT_STATUSES, STATUS_LABEL } from '@/lib/faultWorkflow'
import { queryKeys } from '@/lib/queryKeys'
import { FaultWorkflowPanel } from '@/components/Platform/FaultWorkflowPanel'
import { useToast } from '@/components/Platform/Toast'

type StatusFilter = FaultStatus | 'active' | 'all'
const ACTIVE_STATUSES: FaultStatus[] = ['open', 'assigned', 'in_progress']

type Props = {
  parkId: string
  /** When a grid panel is selected, only that panel's faults are listed. */
  panelId: string | null
  onClearPanel: () => void
}

/** Tracked faults for a park with dispatch/close-out controls and work-order export. */
export function ParkFaultsPanel({ parkId, panelId, onClearPanel }: Props) {
  const toast = useToast()
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('active')
  const [assigneeFilter, setAssigneeFilter] = useState('')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [exporting, setExporting] = useState<WorkOrderFormat | null>(null)

  const faultsQuery = useQuery({
    queryKey: queryKeys.faults.park(parkId),
    queryFn: () => api.parkFaults(parkId),
  })
  const all = faultsQuery.data?.faults ?? []
  const counts = faultsQuery.data?.counts_by_status

  const wantedAssignee = assigneeFilter.trim().toLowerCase()
  const visible = all.filter((f) => {
    if (panelId && f.panel_id !== panelId) return false
    if (statusFilter === 'active' && !ACTIVE_STATUSES.includes(f.status)) return false
    if (statusFilter !== 'active' && statusFilter !== 'all' && f.status !== statusFilter) return false
    if (wantedAssignee && (f.assignee ?? '').trim().toLowerCase() !== wantedAssignee) return false
    return true
  })
  const selected = all.find((f) => f.id === selectedId) ?? null

  async function exportWorkOrders(format: WorkOrderFormat) {
    setExporting(format)
    try {
      const status =
        statusFilter === 'all' ? [...FAULT_STATUSES] : statusFilter === 'active' ? ACTIVE_STATUSES : [statusFilter]
      const blob = await api.workOrders(parkId, format, { status, assignee: assigneeFilter })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `${parkId}_work_orders.${format}`
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      toast.error(err instanceof ApiError ? `Work-order export failed (HTTP ${err.status})` : 'Work-order export failed')
    } finally {
      setExporting(null)
    }
  }

  return (
    <section className="park-faults" aria-label="Park faults">
      <header className="park-faults-head">
        <h2>
          <ClipboardList size={16} /> Faults &amp; repairs
        </h2>
        <select
          aria-label="Filter faults by status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
        >
          <option value="active">Actionable (open · assigned · in progress)</option>
          <option value="all">All statuses</option>
          {FAULT_STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
              {counts ? ` (${counts[s] ?? 0})` : ''}
            </option>
          ))}
        </select>
        <input
          aria-label="Filter faults by assignee"
          placeholder="Assignee"
          value={assigneeFilter}
          onChange={(e) => setAssigneeFilter(e.target.value)}
        />
        <div className="park-faults-export">
          <button
            type="button"
            className="secondary"
            data-testid="work-orders-csv"
            disabled={exporting !== null}
            onClick={() => exportWorkOrders('csv')}
          >
            <FileText size={14} /> Work orders CSV
          </button>
          <button
            type="button"
            className="secondary"
            data-testid="work-orders-xlsx"
            disabled={exporting !== null}
            onClick={() => exportWorkOrders('xlsx')}
          >
            <FileSpreadsheet size={14} /> XLSX
          </button>
        </div>
      </header>

      {panelId && (
        <p className="park-faults-scope">
          Showing panel {panelId}.{' '}
          <button type="button" className="link-button" onClick={onClearPanel}>
            Show whole park
          </button>
        </p>
      )}

      {faultsQuery.isPending && <div className="empty">Loading faults…</div>}
      {faultsQuery.error && (
        <div className="empty">
          Could not load faults — {faultsQuery.error instanceof Error ? faultsQuery.error.message : 'unknown error'}
        </div>
      )}
      {!faultsQuery.isPending && !faultsQuery.error && visible.length === 0 && (
        <div className="empty">No faults match these filters.</div>
      )}

      <div className="park-faults-body">
        {visible.length > 0 && (
          <ul className="park-faults-list">
            {visible.map((f) => (
              <li key={f.id}>
                <button
                  type="button"
                  className={`park-fault-row ${f.id === selectedId ? 'is-selected' : ''}`}
                  onClick={() => setSelectedId(f.id)}
                  aria-pressed={f.id === selectedId}
                >
                  <span className="park-fault-panel">{f.panel_id}</span>
                  <span className="park-fault-class">{f.class}</span>
                  {f.priority && <span className={`fault-priority fault-priority-${f.priority}`}>{f.priority}</span>}
                  <span className={`fault-status fault-status-${f.status}`}>{STATUS_LABEL[f.status]}</span>
                  <span className="park-fault-owner">
                    {f.assignee ?? 'unassigned'}
                    {f.due_date ? ` · due ${f.due_date}` : ''}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {selected && <FaultWorkflowPanel fault={selected} onClose={() => setSelectedId(null)} />}
      </div>
    </section>
  )
}
