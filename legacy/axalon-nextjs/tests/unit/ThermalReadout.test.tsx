import '@testing-library/jest-dom/vitest'
import { afterEach, describe, expect, test } from 'vitest'
import { cleanup, render } from '@testing-library/react'
import { ThermalReadout } from '@/components/Platform/ThermalReadout'

afterEach(cleanup)

describe('ThermalReadout', () => {
  test('renders max temperature and ΔT with units', () => {
    const { container } = render(<ThermalReadout max_temp={72.25} delta_t_measured={37.25} />)
    expect(container.textContent).toContain('72.3 °C')
    expect(container.textContent).toContain('ΔT +37.3 °C')
  })

  test('renders nothing when temperatures are absent', () => {
    const { container } = render(<ThermalReadout max_temp={null} delta_t_measured={undefined} />)
    expect(container).toBeEmptyDOMElement()
    expect(container.textContent).not.toMatch(/NaN|undefined|null/)
  })

  test('renders only the part that is present', () => {
    const { container } = render(<ThermalReadout max_temp={50} />)
    expect(container.textContent).toContain('50.0 °C')
    expect(container.textContent).not.toContain('ΔT')
  })
})
