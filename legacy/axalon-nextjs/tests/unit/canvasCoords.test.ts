import { describe, expect, it } from 'vitest'
import { isTooSmall, normalizeBox, yoloToCanvas } from '@/components/Platform/canvasCoords'

describe('normalizeBox', () => {
  it('normalizes drag coords to 0-1 range', () => {
    const r = normalizeBox(10, 20, 110, 120, 200, 200)
    expect(r).toEqual({ x1n: 0.05, y1n: 0.1, x2n: 0.55, y2n: 0.6 })
  })

  it('handles reversed drag', () => {
    const r = normalizeBox(110, 120, 10, 20, 200, 200)
    expect(r.x1n).toBeLessThan(r.x2n)
    expect(r.y1n).toBeLessThan(r.y2n)
  })

  it('clamps to [0,1]', () => {
    const r = normalizeBox(-10, -20, 220, 240, 200, 200)
    expect(r).toEqual({ x1n: 0, y1n: 0, x2n: 1, y2n: 1 })
  })
})

describe('yoloToCanvas', () => {
  it('scales pixel coords from natural image size to canvas size', () => {
    const r = yoloToCanvas(100, 50, 200, 150, 400, 300, 800, 600)
    expect(r).toEqual({ x1c: 200, y1c: 100, x2c: 400, y2c: 300 })
  })

  it('handles non-square canvas scaling', () => {
    const r = yoloToCanvas(0, 0, 100, 100, 100, 200, 50, 50)
    expect(r.x2c).toBe(50)
    expect(r.y2c).toBe(25)
  })
})

describe('isTooSmall', () => {
  it('returns true when box width < 1% of canvas', () => {
    expect(isTooSmall(0, 0, 0.005, 0.1)).toBe(true)
  })

  it('returns true when box height < 1% of canvas', () => {
    expect(isTooSmall(0, 0, 0.1, 0.005)).toBe(true)
  })

  it('returns false for a valid box', () => {
    expect(isTooSmall(0.1, 0.1, 0.4, 0.4)).toBe(false)
  })
})
