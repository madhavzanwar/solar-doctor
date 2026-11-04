'use client'

import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import * as THREE from 'three'
import { scrollStore } from '../../scrollStore'
import { computePanelPositions, computeFaultySet, PANEL_TILT } from './SolarField'

const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi)

// Pre-allocated colours — reused every frame to avoid GC pressure
const COL_CRITICAL = new THREE.Color('#ff1a00')
const COL_HIGH     = new THREE.Color('#ff8c00')

// Fault label data for the top detections
const FAULT_LABELS = [
  { label: 'Hot-spot',    color: '#ff1a00', severity: 'CRITICAL' },
  { label: 'Bypass Diode',color: '#ff2200', severity: 'CRITICAL' },
  { label: 'String Fault',color: '#ff1a00', severity: 'CRITICAL' },
  { label: 'Offline',     color: '#ff6b35', severity: 'HIGH'     },
  { label: 'Short Circuit',color: '#ff8c00', severity: 'HIGH'    },
  { label: 'Hot-spot',    color: '#ff0000', severity: 'CRITICAL' },
  { label: 'Cell Damage', color: '#ffc800', severity: 'MEDIUM'   },
  { label: 'String Fault',color: '#ff1a00', severity: 'CRITICAL' },
  { label: 'Bypass Diode',color: '#ff2200', severity: 'CRITICAL' },
  { label: 'Offline',     color: '#ff6b35', severity: 'HIGH'     },
  { label: 'Hot-spot',    color: '#ff1a00', severity: 'CRITICAL' },
  { label: 'Short Circuit',color: '#ff8c00', severity: 'HIGH'    },
]

export default function DetectionBoxes() {
  // Shared geometry — one EdgesGeometry for all boxes (single GPU upload)
  const edgesGeo = useMemo(() => {
    const box = new THREE.BoxGeometry(1.05, 0.5, 0.65)
    return new THREE.EdgesGeometry(box)
  }, [])

  // Precompute faulty panel positions (same deterministic logic as SolarField)
  const faultyPositions = useMemo(() => {
    const positions = computePanelPositions()
    const faultySet = computeFaultySet()
    return Array.from(faultySet).map(i => positions[i])
  }, [])

  // Refs for each detection box group
  const groupRefs  = useRef<(THREE.Group | null)[]>([])
  const matRefs    = useRef<(THREE.LineBasicMaterial | null)[]>([])

  // Daytime sun light ref — fades in during scene 3
  const sunRef  = useRef<THREE.DirectionalLight>(null)
  const fillRef = useRef<THREE.DirectionalLight>(null)

  useFrame(({ clock }) => {
    const t = scrollStore.progress
    // Scene 3 occupies scroll 2/6 → 3/6
    const detectionP = clamp((t - 2 / 6) / (1 / 6), 0, 1)
    const active = detectionP > 0.01

    // Daytime directional light fades in
    if (sunRef.current) {
      sunRef.current.intensity = detectionP * 1.1
      sunRef.current.visible = active
    }
    if (fillRef.current) {
      fillRef.current.intensity = detectionP * 0.35
      fillRef.current.visible = active
    }

    const count = faultyPositions.length

    groupRefs.current.forEach((grp, i) => {
      if (!grp) return

      // Staggered reveal: box i appears when detectionP > i/count
      const threshold = i / count
      const boxActive = active && detectionP > threshold

      grp.visible = boxActive
      if (!boxActive) return

      // Pulsing scale — critical panels pulse faster
      const labelInfo = FAULT_LABELS[i % FAULT_LABELS.length]
      const isCritical = labelInfo.severity === 'CRITICAL'
      const freq = isCritical ? 3.5 : 2.2
      const pulse = 1 + Math.sin(clock.elapsedTime * freq + i * 0.7) * 0.04
      grp.scale.setScalar(pulse)

      // Colour: scan progress past this box → switch to fault colour
      const revealed = (detectionP - threshold) / (1 / count)
      const mat = matRefs.current[i]
      if (mat) {
        mat.color.lerp(isCritical ? COL_CRITICAL : COL_HIGH, Math.min(revealed * 4, 1))
        // Opacity flicker on critical
        mat.opacity = isCritical
          ? 0.7 + Math.sin(clock.elapsedTime * 5 + i) * 0.25
          : 0.85
      }
    })
  })

  return (
    <group>
      {/* Daytime sun — fades in to replace the dark night lighting */}
      <directionalLight
        ref={sunRef}
        position={[15, 30, 10]}
        intensity={0}
        color="#fff5e0"
        visible={false}
      />
      <directionalLight
        ref={fillRef}
        position={[-10, 10, -5]}
        intensity={0}
        color="#e0f0ff"
        visible={false}
      />

      {/* Detection bounding boxes */}
      {faultyPositions.map((pos, i) => {
        const labelInfo = FAULT_LABELS[i % FAULT_LABELS.length]
        const isCritical = labelInfo.severity === 'CRITICAL'
        const showLabel  = i < FAULT_LABELS.length   // only first N get labels

        // Per-instance material so colour can animate independently
        const mat = new THREE.LineBasicMaterial({
          color: isCritical ? '#ff1a00' : '#ff8c00',
          transparent: true,
          opacity: 0.85,
        })

        return (
          <group
            key={i}
            ref={el => { groupRefs.current[i] = el }}
            position={[pos.x, pos.y + 0.28, pos.z]}
            rotation={[PANEL_TILT, 0, 0]}
            visible={false}
          >
            {/* Bounding box wireframe */}
            <lineSegments
              geometry={edgesGeo}
              ref={el => { if (el) matRefs.current[i] = el.material as THREE.LineBasicMaterial }}
            >
              <lineBasicMaterial
                ref={el => { if (el) matRefs.current[i] = el }}
                color={isCritical ? '#ff1a00' : '#ff8c00'}
                transparent
                opacity={0.85}
              />
            </lineSegments>

            {/* Corner tick marks — inner corner lines for a tighter "AI detection" look */}
            <lineSegments geometry={edgesGeo}>
              <lineBasicMaterial
                color={isCritical ? '#ff4400' : '#ffaa00'}
                transparent
                opacity={0.25}
              />
            </lineSegments>

            {/* HTML confidence label (only for first 12 boxes) */}
            {showLabel && (
              <Html
                position={[0, 0.32, 0]}
                center
                distanceFactor={12}
                zIndexRange={[10, 20]}
                style={{ pointerEvents: 'none' }}
              >
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.3rem',
                  background: 'rgba(2,2,8,0.82)',
                  border: `1px solid ${labelInfo.color}44`,
                  padding: '0.1rem 0.4rem',
                  whiteSpace: 'nowrap',
                }}>
                  <span style={{
                    width: '4px', height: '4px',
                    borderRadius: '50%',
                    background: labelInfo.color,
                    boxShadow: `0 0 4px ${labelInfo.color}`,
                    display: 'inline-block',
                    flexShrink: 0,
                  }} />
                  <span style={{
                    fontFamily: 'Space Grotesk, sans-serif',
                    fontSize: '7px',
                    color: labelInfo.color,
                    letterSpacing: '0.06em',
                  }}>
                    {labelInfo.label}
                  </span>
                  <span style={{
                    fontFamily: 'Space Grotesk, sans-serif',
                    fontSize: '6px',
                    color: 'rgba(255,255,255,0.4)',
                  }}>
                    {(0.72 + Math.sin(i * 37.1) * 0.18).toFixed(2)}
                  </span>
                </div>
              </Html>
            )}
          </group>
        )
      })}
    </group>
  )
}
