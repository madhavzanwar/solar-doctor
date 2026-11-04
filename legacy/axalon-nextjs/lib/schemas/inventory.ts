import { z } from 'zod'

import type { ComponentCategory } from '@/lib/api'

// Shared field builders ────────────────────────────────────────────────────
// Every input is string-in (that's what the DOM gives us) and parses to the
// shape the API wants. Blank optional fields become null rather than silently
// becoming 0 via `Number(x) || 0`, which is what the old hand-rolled forms did.

const requiredText = (label: string, max = 200) =>
  z.string().trim().min(1, `${label} is required`).max(max, `${label} must be ${max} characters or fewer`)

const optionalText = (max = 200) =>
  z.string().trim().max(max, `Must be ${max} characters or fewer`)

const optionalNullableText = (max = 200) =>
  optionalText(max).transform((v): string | null => (v === '' ? null : v))

/** Whole number ≥ min, entered as text. */
const quantity = (min: number) =>
  z
    .string()
    .trim()
    .refine((v) => v !== '' && Number.isInteger(Number(v)), 'Quantity must be a whole number')
    .refine((v) => Number(v) >= min, `Quantity must be at least ${min}`)
    .refine((v) => Number(v) <= 1_000_000, 'Quantity is unrealistically large')
    .transform((v) => Number(v))

/** Optional money value. Blank means "not specified" → null. */
const optionalMoney = z
  .string()
  .trim()
  .refine(
    (v) => v === '' || (v !== '' && !Number.isNaN(Number(v)) && Number(v) >= 0),
    'Cost must be a non-negative number',
  )
  .transform((v): number | null => (v === '' ? null : Number(v)))

/** Optional http(s) URL. Blank → null. Rejects javascript:/data: schemes. */
const optionalUrl = z
  .string()
  .trim()
  .refine((v) => {
    if (v === '') return true
    try {
      return ['http:', 'https:'].includes(new URL(v).protocol)
    } catch {
      return false
    }
  }, 'Must be a valid http(s) URL')
  .transform((v): string | null => (v === '' ? null : v))

// Schemas ──────────────────────────────────────────────────────────────────

export const addComponentSchema = z.object({
  name: requiredText('Component name'),
  category: z.string().min(1).transform((v) => v as ComponentCategory),
  qty_total: quantity(0),
  unit_cost: optionalMoney,
  vendor: optionalNullableText(),
  link: optionalUrl,
})
export type AddComponentInput = z.input<typeof addComponentSchema>

export const assignComponentSchema = z.object({
  component_id: requiredText('Component'),
  qty: quantity(1),
})
export type AssignComponentInput = z.input<typeof assignComponentSchema>

export const addPrototypeSchema = z.object({
  name: requiredText('Prototype name'),
  description: optionalNullableText(2000),
})
export type AddPrototypeInput = z.input<typeof addPrototypeSchema>

export const addOrderSchema = z
  .object({
    // Either a free-text item name or a link to an existing component is
    // required — enforced by the cross-field refine below, not per-field.
    name: optionalText(),
    component_id: optionalNullableText(),
    qty: quantity(1),
    est_cost: optionalMoney,
    needed_by: optionalNullableText(40),
  })
  .refine((v) => Boolean(v.name) || Boolean(v.component_id), {
    message: 'Give the order a name or link it to a component',
    path: ['name'],
  })
export type AddOrderInput = z.input<typeof addOrderSchema>
