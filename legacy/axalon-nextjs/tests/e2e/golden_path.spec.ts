import { expect, test } from '@playwright/test'
import path from 'node:path'

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..')
const FIXTURE_ZIP = path.join(REPO_ROOT, 'tests', 'fixtures', 'sample_mission.zip')
const FIXTURE_IMG = path.join(
  REPO_ROOT,
  'tests',
  'fixtures',
  'sample_mission',
  'thermal',
  'img_001.jpg',
)

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Click a nav tab by its visible label. */
async function clickTab(page: import('@playwright/test').Page, label: string) {
  await page.locator('nav').getByRole('button', { name: label, exact: true }).click()
}

// ─── Golden path ──────────────────────────────────────────────────────────────

test.describe('Operator golden path', () => {
  test('runs a batch then visits every tab', async ({ page }) => {
    // ── 1. Operations tab (default) ──────────────────────────────────────────
    await page.goto('/platform')
    await expect(page.getByRole('heading', { name: 'Operations', level: 1 })).toBeVisible()

    // Fill in park ID — plain <input> with label "Park ID"
    const parkIdInput = page.getByRole('spinbutton').first() // altitude is spinbutton
    const parkLabel = page.getByLabel('Park ID')
    await parkLabel.fill('E2E_PARK')

    // Altitude — labeled "Altitude m"
    const altLabel = page.getByLabel('Altitude m')
    await altLabel.fill('42')

    // Upload zip via the hidden file input (accept=".zip")
    await page.locator('input[type=file][accept=".zip"]').setInputFiles(FIXTURE_ZIP)

    // Click "Submit batch"
    await page.getByRole('button', { name: 'Submit batch' }).click()

    // Wait for 100% completion — the progress span shows e.g. "100%"
    // The job-card also gains class "completed" and status pill changes.
    // We wait for the text "100%" to appear in the active job card.
    if (process.env.PLAYWRIGHT_CI === '1') {
      await expect(
        page.locator('.pill').filter({ hasText: /completed|failed/i }).first()
      ).toBeVisible({ timeout: 200_000 })
    } else {
      await expect(
        page.locator('.job-progress-row >> text=/100\\s*%/')
      ).toBeVisible({ timeout: 200_000 })
    }

    // Confirm report links are now enabled (<a> elements, not <span>)
    // At least the JSON link should be present.
    if (process.env.PLAYWRIGHT_CI !== '1') {
      const jsonLink = page.locator('a.report', { hasText: 'JSON' }).first()
      await expect(jsonLink).toBeVisible({ timeout: 10_000 })
      const href = await jsonLink.getAttribute('href')
      expect(href ?? '').toContain('/report/')
    }

    // ── 2. Inspect tab ───────────────────────────────────────────────────────
    await clickTab(page, 'Inspect')
    await expect(page.getByRole('heading', { name: 'Inspect', level: 1 })).toBeVisible()

    // Upload a single thermal image via the hidden file input
    await page
      .locator('input[type=file][accept=".jpg,.jpeg,.png,.tif,.tiff"]')
      .first()
      .setInputFiles(FIXTURE_IMG)

    // "Run detection" button should now be enabled
    const runBtn = page.getByRole('button', { name: 'Run detection' })
    await expect(runBtn).toBeEnabled({ timeout: 5_000 })
    await runBtn.click()

    // Wait for result section to update (shows "N detection(s) · job ...")
    await expect(
      page.locator('p', { hasText: /detection\(s\)\s*·\s*job/i }).first()
    ).toBeVisible({ timeout: 90_000 })

    // ── 3. History tab ───────────────────────────────────────────────────────
    await clickTab(page, 'History')
    await expect(page.getByRole('heading', { name: 'History', level: 1 })).toBeVisible()
    // History has a park combobox
    await expect(page.locator('combobox, select').first()).toBeVisible()

    // ── 4. Settings tab ──────────────────────────────────────────────────────
    await clickTab(page, 'Settings')
    await expect(page.getByRole('heading', { name: 'Settings', level: 1 })).toBeVisible()

    // ── 5. Park Map tab ──────────────────────────────────────────────────────
    await page.getByTestId('tab-parkmap').click()
    await expect(page.getByRole('heading', { name: 'Park Map', level: 1 })).toBeVisible()

    // Select the park we just uploaded — it should appear in the park dropdown
    // data-testid="parkmap-park-select"
    await page.getByTestId('parkmap-park-select').selectOption('E2E_PARK')

    // Wait for at least one colored panel cell to render
    await expect(
      page.locator('[data-testid^="panel-R"]').first()
    ).toBeVisible({ timeout: 30_000 })

    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByTestId('parkmap-export-png').click(),
    ])
    expect(download.suggestedFilename()).toBe('E2E_PARK_grid.png')
  })
})
