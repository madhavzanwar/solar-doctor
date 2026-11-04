'use client'

import { useRef, useMemo, useEffect, forwardRef, useImperativeHandle } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

// ── Layout constants ────────────────────────────────────────────────────────
const COLS        = 22
const ROWS        = 18
const PANEL_W     = 0.95   // width  (X)
const PANEL_THICK = 0.04   // height (Y)
const PANEL_D     = 0.55   // depth  (Z)
const GAP_X       = 0.15   // gap between panels in a row
const GAP_Z_ROW   = 0.10   // gap within row (same as panels)
const GAP_Z_PATH  = 0.70   // wider gap every 3 rows (maintenance path)
const TILT        = -Math.PI / 10   // ~18° south-facing tilt

export const PANEL_COUNT = COLS * ROWS   // 396

// ── Exported helpers for sibling components ──────────────────────────────────
export function computePanelPositions(): THREE.Vector3[] {
  const positions: THREE.Vector3[] = []
  const zOffsets: number[] = []
  let zCursor = 0
  for (let r = 0; r < ROWS; r++) {
    zOffsets.push(zCursor)
    const gap = r % 3 === 2 ? GAP_Z_PATH : GAP_Z_ROW
    zCursor += PANEL_D + gap
  }
  const zCenter = zCursor / 2
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const x = (c - COLS / 2) * (PANEL_W + GAP_X)
      const z = zOffsets[r] - zCenter
      positions.push(new THREE.Vector3(x, 0, z))
    }
  }
  return positions
}

export function computeFaultySet(): Set<number> {
  const faultySet = new Set<number>()
  for (let i = 0; i < PANEL_COUNT; i++) {
    if (Math.sin(i * 137.5) > 0.72) faultySet.add(i)
  }
  return faultySet
}

export const PANEL_TILT = TILT

// Panel centre colour palette (healthy = dark blue)
const HEALTHY_COLOR   = new THREE.Color('#0d1a3a')
const WARM_COLOR      = new THREE.Color('#ff6b35')
const FAULTY_COLOR    = new THREE.Color('#ff1a00')

export interface SolarFieldHandle {
  setThermalProgress: (p: number) => void
  getFaultyIndices: () => number[]
}

const SolarField = forwardRef<SolarFieldHandle>(function SolarField(_, ref) {
  const meshRef   = useRef<THREE.InstancedMesh>(null)
  const colorBuf  = useRef<THREE.Color[]>([])
  const scanProg  = useRef(0)

  // Precompute positions + mark ~15% as "faulty"
  const { positions, faultySet } = useMemo(() => {
    const positions: THREE.Vector3[] = []
    const faultySet = new Set<number>()

    // Build Z offsets accounting for maintenance paths every 3 rows
    const zOffsets: number[] = []
    let zCursor = 0
    for (let r = 0; r < ROWS; r++) {
      zOffsets.push(zCursor)
      const gap = r % 3 === 2 ? GAP_Z_PATH : GAP_Z_ROW
      zCursor += PANEL_D + gap
    }
    const zCenter = zCursor / 2

    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const x = (c - COLS / 2) * (PANEL_W + GAP_X)
        const z = zOffsets[r] - zCenter
        positions.push(new THREE.Vector3(x, 0, z))
      }
    }

    // Mark ~15% panels as faulty (pseudo-random spread)
    for (let i = 0; i < PANEL_COUNT; i++) {
      if (Math.sin(i * 137.5) > 0.72) faultySet.add(i)
    }

    return { positions, faultySet }
  }, [])

  // Set initial transforms
  useEffect(() => {
    const mesh = meshRef.current
    if (!mesh) return
    const dummy = new THREE.Object3D()
    const colors: THREE.Color[] = []

    positions.forEach((pos, i) => {
      dummy.position.set(pos.x, pos.y, pos.z)
      dummy.rotation.x = TILT
      dummy.scale.set(1, 1, 1)
      dummy.updateMatrix()
      mesh.setMatrixAt(i, dummy.matrix)

      const c = HEALTHY_COLOR.clone()
      colors.push(c)
      mesh.setColorAt(i, c)
    })

    mesh.instanceMatrix.needsUpdate = true
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
    colorBuf.current = colors
  }, [positions])

  // Expose handle for thermal scan control
  useImperativeHandle(ref, () => ({
    setThermalProgress(p: number) {
      scanProg.current = p
    },
    getFaultyIndices() {
      return Array.from(faultySet)
    },
  }))

  // Animate thermal scan: sweep colours left-to-right
  useFrame(() => {
    const mesh = meshRef.current
    if (!mesh || scanProg.current <= 0) return

    const t = scanProg.current           // 0 → 1 through section 2
    const sweepX = (t * 2 - 1) * (COLS / 2) * (PANEL_W + GAP_X)

    positions.forEach((pos, i) => {
      const dist = pos.x - sweepX
      let target: THREE.Color

      if (dist > 2) {
        target = HEALTHY_COLOR           // ahead of scan — untouched
      } else if (faultySet.has(i)) {
        target = FAULTY_COLOR            // fault — bright red emissive
      } else {
        // Lerp healthy → slightly warm behind scan
        const heat = Math.min(1, Math.max(0, (-dist + 2) / 4))
        target = HEALTHY_COLOR.clone().lerp(WARM_COLOR.clone().multiplyScalar(0.35), heat * 0.4)
      }

      colorBuf.current[i].lerp(target, 0.08)
      mesh.setColorAt(i, colorBuf.current[i])
    })

    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
  })

  return (
    <>
      {/* Ground plane */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.18, 0]} receiveShadow>
        <planeGeometry args={[60, 60]} />
        <meshStandardMaterial color="#050510" roughness={0.9} metalness={0.1} />
      </mesh>

      {/* Grid overlay on ground */}
      <gridHelper args={[60, 40, '#0a0a1f', '#0a0a1f']} position={[0, -0.17, 0]} />

      {/* Solar panels — single instanced draw call */}
      <instancedMesh
        ref={meshRef}
        args={[undefined, undefined, PANEL_COUNT]}
        castShadow
        receiveShadow
      >
        <boxGeometry args={[PANEL_W, PANEL_THICK, PANEL_D]} />
        <meshStandardMaterial
          metalness={0.75}
          roughness={0.25}
          envMapIntensity={0.5}
        />
      </instancedMesh>
    </>
  )
})

export default SolarField
