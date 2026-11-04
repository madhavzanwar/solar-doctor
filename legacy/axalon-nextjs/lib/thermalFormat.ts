// Formatting for radiometric readouts (°C, ΔT) and estimated revenue loss. Pure + tested.
// Every formatter returns null for absent data so callers render nothing,
// never "NaN" / "undefined" — images without a _temp.raw companion have no temperatures.

export type ThermalFields = {
  max_temp?: number | null
  delta_t_measured?: number | null
}

const DEFAULT_CURRENCY = 'USD'

function isNum(v: number | null | undefined): v is number {
  return typeof v === 'number' && Number.isFinite(v)
}

export function formatTempC(v: number | null | undefined): string | null {
  return isNum(v) ? `${v.toFixed(1)} °C` : null
}

export function formatDeltaT(v: number | null | undefined): string | null {
  if (!isNum(v)) return null
  const fixed = v.toFixed(1)
  const sign = v > 0 && fixed !== '0.0' ? '+' : ''
  return `ΔT ${sign}${fixed} °C`
}

export function thermalReadout(d: ThermalFields): string | null {
  const parts = [
    isNum(d.max_temp) ? `max ${formatTempC(d.max_temp)}` : null,
    formatDeltaT(d.delta_t_measured),
  ].filter((p): p is string => p !== null)
  return parts.length ? parts.join(' · ') : null
}

function currencyFormatter(currency: string): Intl.NumberFormat {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

export function formatRevenueLoss(
  v: number | null | undefined,
  currency: string | null | undefined = DEFAULT_CURRENCY,
): string | null {
  if (!isNum(v)) return null
  try {
    return currencyFormatter(currency || DEFAULT_CURRENCY).format(v)
  } catch {
    // Unknown ISO code from the API — fall back rather than crash the tab.
    return currencyFormatter(DEFAULT_CURRENCY).format(v)
  }
}

export function sumRevenueLoss(values: Array<number | null | undefined>): number | null {
  const known = values.filter(isNum)
  return known.length ? known.reduce((a, b) => a + b, 0) : null
}

export const REVENUE_LOSS_NOTE =
  'Estimate: CRITICAL/HIGH panels × panel kW × peak sun hours × tariff (settings.yaml economics).'
