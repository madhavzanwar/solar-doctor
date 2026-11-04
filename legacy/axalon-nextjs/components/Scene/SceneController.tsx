'use client'

/**
 * SceneController — lives inside the R3F Canvas.
 * Reads scrollStore every frame and coordinates scene state
 * without triggering any React re-renders.
 */

import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { scrollStore } from '../../scrollStore'
import type { SolarFieldHandle } from './SolarField'

const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi)

// Section boundaries (6 sections of equal height)
const S = (i: number) => i / 6   // start of section i (0-indexed)

interface Props {
  fieldRef: React.RefObject<SolarFieldHandle>
}

export default function SceneController({ fieldRef }: Props) {
  useFrame(() => {
    const t = scrollStore.progress

    // ── Section 2: Thermal scan (1/6 → 2/6) ──────────────────
    const thermalP = clamp((t - S(1)) / (S(2) - S(1)), 0, 1)

    // ── Section 3: RGB Detection (2/6 → 3/6) — fade thermal out ──
    // When scene 3 enters, progressively reset thermal colours back to healthy
    const detectionP = clamp((t - S(2)) / (S(3) - S(2)), 0, 1)
    // During scene 3, lerp thermalProgress back down so panels cool off
    const effectiveThermal = thermalP * (1 - detectionP * 0.9)
    fieldRef.current?.setThermalProgress(effectiveThermal)
  })

  return null
}
