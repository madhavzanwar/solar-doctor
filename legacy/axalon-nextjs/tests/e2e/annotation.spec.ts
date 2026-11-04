import { expect, test } from '@playwright/test'
import path from 'node:path'

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..')
const THERMAL_IMG = path.join(
  REPO_ROOT,
  'tests',
  'fixtures',
  'sample_mission',
  'thermal',
  'img_001.jpg',
)

test.describe('Annotation editor', () => {
  test('draw a correction box, assign class, save, then delete', async ({ page }) => {
    await page.goto('/platform')
    await page.getByRole('button', { name: /^Inspect$/ }).click()
    await page.locator('input[type=file][accept=".jpg,.jpeg,.png,.tif,.tiff"]').first().setInputFiles(THERMAL_IMG)
    await page.getByRole('button', { name: /Run detection/i }).click()

    const canvas = page.locator('canvas').first()
    await expect(canvas).toBeVisible({ timeout: 60_000 })
    await expect(page.getByRole('link', { name: /Download Report/i })).toBeVisible({ timeout: 10_000 })

    const box = await canvas.boundingBox()
    if (!box) throw new Error('Canvas bounding box not found')
    const startX = box.x + box.width * 0.2
    const startY = box.y + box.height * 0.2
    const endX = box.x + box.width * 0.6
    const endY = box.y + box.height * 0.6

    await page.mouse.move(startX, startY)
    await page.mouse.down()
    await page.mouse.move(endX, endY, { steps: 10 })
    await page.mouse.up()

    await expect(page.getByText('Assign class')).toBeVisible({ timeout: 5_000 })
    await page.selectOption('.annotation-class-picker select', 'hot-spot-low')
    await page.getByRole('button', { name: /^Save$/ }).click()
    await expect(page.getByText('Assign class')).not.toBeVisible()

    await page.mouse.click((startX + endX) / 2, (startY + endY) / 2)
    await expect(page.getByRole('button', { name: /Delete/i })).toBeVisible({ timeout: 5_000 })
    await page.getByRole('button', { name: /Delete/i }).click()
    await expect(page.getByRole('button', { name: /Delete/i })).not.toBeVisible()
  })

  test('cancel discards the box without saving', async ({ page }) => {
    await page.goto('/platform')
    await page.getByRole('button', { name: /^Inspect$/ }).click()
    await page.locator('input[type=file][accept=".jpg,.jpeg,.png,.tif,.tiff"]').first().setInputFiles(THERMAL_IMG)
    await page.getByRole('button', { name: /Run detection/i }).click()

    const canvas = page.locator('canvas').first()
    await expect(canvas).toBeVisible({ timeout: 60_000 })

    const box = await canvas.boundingBox()
    if (!box) throw new Error('Canvas bounding box not found')
    await page.mouse.move(box.x + 30, box.y + 30)
    await page.mouse.down()
    await page.mouse.move(box.x + 150, box.y + 100, { steps: 5 })
    await page.mouse.up()

    await expect(page.getByText('Assign class')).toBeVisible({ timeout: 5_000 })
    await page.getByRole('button', { name: /^Cancel$/ }).click()
    await expect(page.getByText('Assign class')).not.toBeVisible()
    await expect(page.getByRole('button', { name: /Delete/i })).not.toBeVisible()
  })
})
