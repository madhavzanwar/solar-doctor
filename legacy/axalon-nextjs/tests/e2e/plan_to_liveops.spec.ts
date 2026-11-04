import { expect, test, type Page } from '@playwright/test'

// ~60 m square near Pune — small enough for a quick grid, big enough for >2 waypoints.
const BOUNDARY = JSON.stringify({
  type: 'Feature',
  properties: {},
  geometry: {
    type: 'Polygon',
    coordinates: [[
      [73.8560, 18.5200], [73.8566, 18.5200], [73.8566, 18.5205],
      [73.8560, 18.5205], [73.8560, 18.5200],
    ]],
  },
})

async function clickTab(page: Page, label: string) {
  await page.locator('nav').getByRole('button', { name: label, exact: true }).click()
}

function uploadButton(page: Page) {
  return page.getByRole('button', { name: /^Upload mission \(\d+\)$/ })
}

async function stagedCount(page: Page): Promise<number> {
  const label = await uploadButton(page).innerText()
  return Number(/\((\d+)\)/.exec(label)?.[1] ?? NaN)
}

test.describe('Plan → Live Ops route handoff', () => {
  test('route planned in Plan is staged for upload in Live Ops and survives revisiting Plan', async ({ page }) => {
    await page.goto('/platform')

    // Before planning, nothing is staged.
    await clickTab(page, 'Live Ops')
    await expect(uploadButton(page)).toHaveText('Upload mission (0)')

    // Plan a route by importing a boundary.
    await clickTab(page, 'Plan')
    await page.locator('input[type=file][accept=".geojson,.json,.kml"]').setInputFiles({
      name: 'site.geojson',
      mimeType: 'application/geo+json',
      buffer: Buffer.from(BOUNDARY),
    })
    await expect(page.getByText(/Imported \d+-point boundary/)).toBeVisible()

    // Live Ops now offers the planned route.
    await clickTab(page, 'Live Ops')
    await expect.poll(() => stagedCount(page)).toBeGreaterThan(2)
    const staged = await stagedCount(page)

    // Opening Plan again remounts it with an empty route; that must not wipe
    // the route already staged.
    await clickTab(page, 'Plan')
    await expect(page.locator('.plan-map')).toBeVisible()
    await clickTab(page, 'Live Ops')
    await expect(uploadButton(page)).toHaveText(`Upload mission (${staged})`)
  })
})
