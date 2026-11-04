import { describe, it, expect } from 'vitest'
import {
  formatTempC,
  formatDeltaT,
  formatRevenueLoss,
  sumRevenueLoss,
  thermalReadout,
} from '@/lib/thermalFormat'

describe('formatTempC', () => {
  it('formats to one decimal with a degree-Celsius unit', () => {
    expect(formatTempC(72.25)).toBe('72.3 °C')
    expect(formatTempC(0)).toBe('0.0 °C')
    expect(formatTempC(-4.04)).toBe('-4.0 °C')
  })

  it('returns null for missing or non-finite values', () => {
    expect(formatTempC(null)).toBeNull()
    expect(formatTempC(undefined)).toBeNull()
    expect(formatTempC(Number.NaN)).toBeNull()
    expect(formatTempC(Number.POSITIVE_INFINITY)).toBeNull()
  })
})

describe('formatDeltaT', () => {
  it('prefixes ΔT with an explicit sign and unit', () => {
    expect(formatDeltaT(37.25)).toBe('ΔT +37.3 °C')
    expect(formatDeltaT(-2)).toBe('ΔT -2.0 °C')
    expect(formatDeltaT(0)).toBe('ΔT 0.0 °C')
  })

  it('returns null when ΔT is absent', () => {
    expect(formatDeltaT(null)).toBeNull()
    expect(formatDeltaT(undefined)).toBeNull()
    expect(formatDeltaT(Number.NaN)).toBeNull()
  })
})

describe('thermalReadout', () => {
  it('joins max temperature and ΔT when both exist', () => {
    expect(thermalReadout({ max_temp: 72.25, delta_t_measured: 37.25 })).toBe(
      'max 72.3 °C · ΔT +37.3 °C',
    )
  })

  it('shows whichever part is present', () => {
    expect(thermalReadout({ max_temp: 50, delta_t_measured: null })).toBe('max 50.0 °C')
    expect(thermalReadout({ delta_t_measured: 12 })).toBe('ΔT +12.0 °C')
  })

  it('returns null when there is no radiometric data', () => {
    expect(thermalReadout({})).toBeNull()
    expect(thermalReadout({ max_temp: null, delta_t_measured: undefined })).toBeNull()
  })
})

describe('formatRevenueLoss', () => {
  it('formats USD with two decimals', () => {
    expect(formatRevenueLoss(0.32)).toBe('$0.32')
    expect(formatRevenueLoss(1234.5)).toBe('$1,234.50')
    expect(formatRevenueLoss(0)).toBe('$0.00')
  })

  it('respects a currency code from the API', () => {
    expect(formatRevenueLoss(10, 'EUR')).toBe('€10.00')
  })

  it('falls back to USD when the currency code is missing or invalid', () => {
    expect(formatRevenueLoss(5, null)).toBe('$5.00')
    expect(formatRevenueLoss(5, 'not-a-currency')).toBe('$5.00')
  })

  it('returns null for missing values', () => {
    expect(formatRevenueLoss(null)).toBeNull()
    expect(formatRevenueLoss(undefined)).toBeNull()
    expect(formatRevenueLoss(Number.NaN)).toBeNull()
  })
})

describe('sumRevenueLoss', () => {
  it('sums finite values and ignores missing ones', () => {
    expect(sumRevenueLoss([0.32, null, 1.28, undefined])).toBeCloseTo(1.6)
  })

  it('returns null when no value is known', () => {
    expect(sumRevenueLoss([])).toBeNull()
    expect(sumRevenueLoss([null, undefined])).toBeNull()
  })
})
