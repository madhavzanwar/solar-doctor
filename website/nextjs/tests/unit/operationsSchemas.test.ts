import { describe, expect, test } from 'vitest'

import { altitudeSchema, batchUploadSchema, firstError, parkIdSchema } from '@/lib/schemas/operations'

describe('parkIdSchema — mirrors platform/api/support/security.py::_validate_park_id', () => {
  test.each(['MH_SOLAR_07', 'park-1', 'A', 'a1_B-2', 'x'.repeat(64)])(
    'accepts %s',
    (id) => expect(parkIdSchema.safeParse(id).success).toBe(true),
  )

  test.each([
    ['spaces', 'MH SOLAR 07'],
    ['path traversal', '../etc'],
    ['slash', 'park/1'],
    ['dot', 'park.1'],
    ['empty', ''],
    ['whitespace only', '   '],
    ['too long', 'x'.repeat(65)],
  ])('rejects %s', (_label, id) => {
    expect(parkIdSchema.safeParse(id).success).toBe(false)
  })

  test('trims before validating', () => {
    expect(parkIdSchema.parse('  PARK_1  ')).toBe('PARK_1')
  })
})

describe('altitudeSchema', () => {
  test('accepts a normal survey altitude', () => {
    expect(altitudeSchema.safeParse(42).success).toBe(true)
  })

  test.each([0, -5, 1001])('rejects %s', (v) => {
    expect(altitudeSchema.safeParse(v).success).toBe(false)
  })
})

describe('batchUploadSchema', () => {
  const valid = { park_id: 'MH_SOLAR_07', altitude_m: 42, file_name: 'mission.zip' }

  test('accepts a valid batch', () => {
    expect(batchUploadSchema.safeParse(valid).success).toBe(true)
  })

  test('accepts uppercase .ZIP', () => {
    expect(batchUploadSchema.safeParse({ ...valid, file_name: 'MISSION.ZIP' }).success).toBe(true)
  })

  test('rejects a non-zip file', () => {
    const r = batchUploadSchema.safeParse({ ...valid, file_name: 'mission.tar.gz' })
    expect(firstError(r)).toMatch(/only \.zip/i)
  })

  test('rejects a park id with spaces before any upload happens', () => {
    const r = batchUploadSchema.safeParse({ ...valid, park_id: 'MH SOLAR 07' })
    expect(firstError(r)).toMatch(/letters, digits, hyphens/i)
  })
})

describe('firstError', () => {
  test('returns null when valid', () => {
    expect(firstError(parkIdSchema.safeParse('OK_1'))).toBeNull()
  })

  test('returns a message when invalid', () => {
    expect(firstError(parkIdSchema.safeParse(''))).toBeTruthy()
  })
})
