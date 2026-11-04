import { describe, expect, test } from 'vitest'

import { ApiError } from '@/lib/api'
import { isTerminalHttpError } from '@/lib/queryPolicy'

describe('isTerminalHttpError', () => {
  test.each([401, 403, 404])('treats HTTP %i as terminal', (status) => {
    expect(isTerminalHttpError(new ApiError(status, ''))).toBe(true)
  })

  test.each([0, 400, 500, 503])('keeps polling through HTTP %i', (status) => {
    expect(isTerminalHttpError(new ApiError(status, ''))).toBe(false)
  })

  test('ignores non-API errors', () => {
    expect(isTerminalHttpError(new Error('boom'))).toBe(false)
    expect(isTerminalHttpError(null)).toBe(false)
  })
})
