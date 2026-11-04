import { describe, expect, test } from 'vitest'
import {
  formatMoney,
  groupByCategory,
  lowStockComponents,
  orderCostByStatus,
  stockValue,
} from '@/lib/inventory'
import type { InventoryComponent, ComponentOrder } from '@/lib/api'

function comp(overrides: Partial<InventoryComponent> = {}): InventoryComponent {
  return {
    id: 1,
    name: 'Motor',
    category: 'motor',
    part_number: null,
    vendor: null,
    link: null,
    unit_cost: 100,
    currency: 'INR',
    qty_total: 4,
    qty_assigned: 0,
    qty_available: 4,
    specs: null,
    notes: null,
    created_at: null,
    updated_at: null,
    ...overrides,
  }
}

function order(overrides: Partial<ComponentOrder> = {}): ComponentOrder {
  return {
    id: 1,
    component_id: null,
    name: 'Props',
    qty: 2,
    est_unit_cost: 50,
    vendor: null,
    link: null,
    status: 'planned',
    needed_by: null,
    notes: null,
    created_at: null,
    updated_at: null,
    ...overrides,
  }
}

describe('stockValue', () => {
  test('sums unit_cost × qty_total across components', () => {
    // Arrange
    const components = [comp(), comp({ id: 2, unit_cost: 10, qty_total: 3 })]

    // Act / Assert
    expect(stockValue(components)).toBe(430)
  })

  test('treats missing unit_cost as zero', () => {
    expect(stockValue([comp({ unit_cost: null })])).toBe(0)
  })

  test('returns 0 for empty inventory', () => {
    expect(stockValue([])).toBe(0)
  })
})

describe('lowStockComponents', () => {
  test('returns only components with no availability', () => {
    const depleted = comp({ id: 2, qty_total: 2, qty_assigned: 2, qty_available: 0 })
    const result = lowStockComponents([comp(), depleted])
    expect(result.map((c) => c.id)).toEqual([2])
  })
})

describe('groupByCategory', () => {
  test('groups components preserving insertion order of categories', () => {
    const groups = groupByCategory([
      comp({ id: 1, category: 'motor' }),
      comp({ id: 2, category: 'esc' }),
      comp({ id: 3, category: 'motor' }),
    ])
    expect(groups.map(([cat]) => cat)).toEqual(['motor', 'esc'])
    expect(groups[0][1].map((c) => c.id)).toEqual([1, 3])
  })
})

describe('orderCostByStatus', () => {
  test('totals est_unit_cost × qty per status, ignoring cancelled', () => {
    const totals = orderCostByStatus([
      order(),                                            // planned 100
      order({ id: 2, status: 'ordered', est_unit_cost: 200, qty: 1 }),
      order({ id: 3, status: 'cancelled', est_unit_cost: 999 }),
      order({ id: 4, status: 'planned', est_unit_cost: null }),
    ])
    expect(totals.planned).toBe(100)
    expect(totals.ordered).toBe(200)
    expect(totals.total).toBe(300)
  })
})

describe('formatMoney', () => {
  test('formats with currency and grouping', () => {
    expect(formatMoney(92000, 'INR')).toMatch(/92,000/)
  })

  test('renders em dash for null', () => {
    expect(formatMoney(null, 'INR')).toBe('—')
  })
})
