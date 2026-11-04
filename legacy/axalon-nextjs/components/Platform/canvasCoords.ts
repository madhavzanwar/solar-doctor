export type NormalizedBox = {
  x1n: number
  y1n: number
  x2n: number
  y2n: number
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value))
}

export function normalizeBox(
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  canvasW: number,
  canvasH: number,
): NormalizedBox {
  return {
    x1n: clamp01(Math.min(x0, x1) / canvasW),
    y1n: clamp01(Math.min(y0, y1) / canvasH),
    x2n: clamp01(Math.max(x0, x1) / canvasW),
    y2n: clamp01(Math.max(y0, y1) / canvasH),
  }
}

export function yoloToCanvas(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  natW: number,
  natH: number,
  canvasW: number,
  canvasH: number,
): { x1c: number; y1c: number; x2c: number; y2c: number } {
  const sx = canvasW / natW
  const sy = canvasH / natH
  return { x1c: x1 * sx, y1c: y1 * sy, x2c: x2 * sx, y2c: y2 * sy }
}

export function isTooSmall(x1n: number, y1n: number, x2n: number, y2n: number): boolean {
  return x2n - x1n < 0.01 || y2n - y1n < 0.01
}
