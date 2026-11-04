import '@testing-library/jest-dom/vitest'
import { render, waitFor } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import LiveMap from '@/components/Platform/LiveMap'

const ROUTE = [
  { lat: 18.52, lon: 73.85, altitude: 40 },
  { lat: 18.53, lon: 73.86, altitude: 40 },
  { lat: 18.51, lon: 73.87, altitude: 40 },
]

function routeLabels(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll('.live-route-marker')).map((el) => el.textContent ?? '')
}

describe('LiveMap planned route', () => {
  test('draws the staged route with start, numbered and end markers', async () => {
    const { container } = render(<LiveMap position={null} headingDeg={0} track={[]} plannedRoute={ROUTE} />)

    await waitFor(() => expect(routeLabels(container)).toEqual(['S', '2', 'E']))
    expect(container.querySelector('.leaflet-overlay-pane path')).not.toBeNull()
  })

  test('updates the route layers in place and clears them when the route is emptied', async () => {
    const { container, rerender } = render(
      <LiveMap position={null} headingDeg={0} track={[]} plannedRoute={ROUTE} />,
    )
    await waitFor(() => expect(routeLabels(container)).toHaveLength(3))

    rerender(<LiveMap position={null} headingDeg={0} track={[]} plannedRoute={ROUTE.slice(0, 2)} />)
    await waitFor(() => expect(routeLabels(container)).toEqual(['S', 'E']))

    rerender(<LiveMap position={null} headingDeg={0} track={[]} plannedRoute={[]} />)
    await waitFor(() => expect(routeLabels(container)).toEqual([]))
  })

  test('unmounting before or after Leaflet loads does not throw', async () => {
    const early = render(<LiveMap position={null} headingDeg={0} track={[]} plannedRoute={ROUTE} />)
    early.unmount()

    const late = render(<LiveMap position={null} headingDeg={0} track={[]} plannedRoute={ROUTE} />)
    await waitFor(() => expect(routeLabels(late.container)).toHaveLength(3))
    expect(() => late.unmount()).not.toThrow()
  })
})
