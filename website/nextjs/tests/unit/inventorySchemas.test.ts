import { describe, expect, test } from 'vitest'

import {
  addComponentSchema,
  addOrderSchema,
  addPrototypeSchema,
  assignComponentSchema,
} from '@/lib/schemas/inventory'

const validComponent = {
  name: 'T-Motor F60', category: 'motor', qty_total: '4',
  unit_cost: '1200', vendor: 'RotorHub', link: 'https://example.com/f60',
}

describe('addComponentSchema', () => {
  test('parses a fully populated component', () => {
    const r = addComponentSchema.parse(validComponent)
    expect(r).toEqual({
      name: 'T-Motor F60', category: 'motor', qty_total: 4,
      unit_cost: 1200, vendor: 'RotorHub', link: 'https://example.com/f60',
    })
  })

  test('converts blank optional fields to null instead of 0 or empty string', () => {
    const r = addComponentSchema.parse({ ...validComponent, unit_cost: '', vendor: '', link: '' })
    expect(r.unit_cost).toBeNull()
    expect(r.vendor).toBeNull()
    expect(r.link).toBeNull()
  })

  test('rejects a blank name', () => {
    const r = addComponentSchema.safeParse({ ...validComponent, name: '   ' })
    expect(r.success).toBe(false)
    if (!r.success) expect(r.error.issues[0].message).toMatch(/name is required/i)
  })

  test('rejects a non-numeric quantity rather than coercing it to 0', () => {
    const r = addComponentSchema.safeParse({ ...validComponent, qty_total: 'abc' })
    expect(r.success).toBe(false)
  })

  test('rejects a negative quantity', () => {
    const r = addComponentSchema.safeParse({ ...validComponent, qty_total: '-3' })
    expect(r.success).toBe(false)
  })

  test('rejects a fractional quantity', () => {
    expect(addComponentSchema.safeParse({ ...validComponent, qty_total: '1.5' }).success).toBe(false)
  })

  test('rejects a negative unit cost', () => {
    expect(addComponentSchema.safeParse({ ...validComponent, unit_cost: '-1' }).success).toBe(false)
  })

  test('rejects a javascript: URL', () => {
    const r = addComponentSchema.safeParse({ ...validComponent, link: 'javascript:alert(1)' })
    expect(r.success).toBe(false)
  })

  test('rejects a non-URL string in the link field', () => {
    expect(addComponentSchema.safeParse({ ...validComponent, link: 'not a url' }).success).toBe(false)
  })

  test('trims surrounding whitespace on text fields', () => {
    const r = addComponentSchema.parse({ ...validComponent, name: '  Padded  ', vendor: '  Ace  ' })
    expect(r.name).toBe('Padded')
    expect(r.vendor).toBe('Ace')
  })
})

describe('assignComponentSchema', () => {
  test('parses a valid assignment', () => {
    expect(assignComponentSchema.parse({ component_id: '7', qty: '2' }))
      .toEqual({ component_id: '7', qty: 2 })
  })

  test('rejects qty of 0 — installing zero units is meaningless', () => {
    expect(assignComponentSchema.safeParse({ component_id: '7', qty: '0' }).success).toBe(false)
  })

  test('rejects a missing component', () => {
    expect(assignComponentSchema.safeParse({ component_id: '', qty: '1' }).success).toBe(false)
  })
})

describe('addPrototypeSchema', () => {
  test('parses name with blank description as null', () => {
    expect(addPrototypeSchema.parse({ name: 'Quad v3', description: '' }))
      .toEqual({ name: 'Quad v3', description: null })
  })

  test('rejects a blank name', () => {
    expect(addPrototypeSchema.safeParse({ name: '', description: 'x' }).success).toBe(false)
  })
})

describe('addOrderSchema', () => {
  const base = { name: '', component_id: '', qty: '1', est_cost: '', needed_by: '' }

  test('accepts a name with no linked component', () => {
    expect(addOrderSchema.safeParse({ ...base, name: 'Spare props' }).success).toBe(true)
  })

  test('accepts a linked component with no name', () => {
    expect(addOrderSchema.safeParse({ ...base, component_id: '12' }).success).toBe(true)
  })

  test('rejects when neither name nor component is given', () => {
    const r = addOrderSchema.safeParse(base)
    expect(r.success).toBe(false)
    if (!r.success) {
      expect(r.error.issues[0].message).toMatch(/name or link it to a component/i)
      expect(r.error.issues[0].path).toEqual(['name'])
    }
  })

  test('rejects qty below 1', () => {
    expect(addOrderSchema.safeParse({ ...base, name: 'x', qty: '0' }).success).toBe(false)
  })
})
