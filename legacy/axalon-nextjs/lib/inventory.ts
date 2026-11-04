// Pure helpers for the Inventory tab — no fetch, no React (vitest-covered).
import type { ComponentOrder, InventoryComponent } from '@/lib/api'

/** Total purchase value of everything owned (unit_cost × qty_total). */
export function stockValue(components: InventoryComponent[]): number {
  return components.reduce(
    (sum, c) => sum + (c.unit_cost ?? 0) * (c.qty_total ?? 0),
    0,
  )
}

/** Components with nothing left on the shelf (everything is installed or qty 0). */
export function lowStockComponents(
  components: InventoryComponent[],
): InventoryComponent[] {
  return components.filter((c) => (c.qty_available ?? 0) < 1)
}

/** Group components by category, preserving first-seen category order. */
export function groupByCategory(
  components: InventoryComponent[],
): [string, InventoryComponent[]][] {
  const groups = new Map<string, InventoryComponent[]>()
  for (const c of components) {
    const key = c.category ?? 'other'
    const bucket = groups.get(key)
    if (bucket) {
      groups.set(key, [...bucket, c])
    } else {
      groups.set(key, [c])
    }
  }
  return Array.from(groups.entries())
}

export type OrderCostTotals = {
  planned: number
  ordered: number
  total: number
}

/** Estimated spend per open order status (cancelled/received excluded from totals). */
export function orderCostByStatus(orders: ComponentOrder[]): OrderCostTotals {
  const costOf = (o: ComponentOrder) => (o.est_unit_cost ?? 0) * (o.qty ?? 0)
  const planned = orders
    .filter((o) => o.status === 'planned')
    .reduce((sum, o) => sum + costOf(o), 0)
  const ordered = orders
    .filter((o) => o.status === 'ordered')
    .reduce((sum, o) => sum + costOf(o), 0)
  return { planned, ordered, total: planned + ordered }
}

/** "₹92,000" style display; em dash when unknown. */
export function formatMoney(value: number | null | undefined, currency: string): string {
  if (value === null || value === undefined) return '—'
  try {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: currency || 'INR',
      maximumFractionDigits: 0,
    }).format(value)
  } catch {
    return `${currency} ${value.toLocaleString('en-IN')}`
  }
}
