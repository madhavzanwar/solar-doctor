'use client'

import { useRef, useMemo, Suspense } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { EffectComposer, Bloom, Vignette } from '@react-three/postprocessing'
import { OrbitControls, Stars } from '@react-three/drei'
import * as THREE from 'three'

const ROWS = 14
const COLS = 22
const PANEL_W = 1.0
const PANEL_H = 0.55
const GAP_X = 0.18
const GAP_Z = 0.45
const TOTAL = ROWS * COLS

// Deterministic pseudo-random so anomalies stay put across renders
function rand(seed: number) {
  const x = Math.sin(seed * 9301 + 49297) * 233280
  return x - Math.floor(x)
}

type Anomaly = {
  id: string
  row: number
  col: number
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
  cls: string
}

export const ANOMALIES: Anomaly[] = (() => {
  const classes = [
    ['hot-spot-high', 'CRITICAL'],
    ['bypass-diode', 'CRITICAL'],
    ['string', 'CRITICAL'],
    ['offline-module', 'HIGH'],
    ['short-circuit', 'HIGH'],
    ['hot-spot-low', 'HIGH'],
    ['cell', 'MEDIUM'],
    ['cell-multi', 'MEDIUM'],
    ['module', 'MEDIUM'],
    ['soiling', 'LOW'],
    ['vegetation-shading', 'LOW'],
  ] as const
  const out: Anomaly[] = []
  let seed = 7
  for (let i = 0; i < 38; i++) {
    seed += 1
    const r = Math.floor(rand(seed) * ROWS)
    const c = Math.floor(rand(seed + 100) * COLS)
    const k = classes[Math.floor(rand(seed + 200) * classes.length)]
    out.push({
      id: `R${r + 1}-C${c + 1}-${i}`,
      row: r,
      col: c,
      cls: k[0],
      severity: k[1] as Anomaly['severity'],
    })
  }
  return out
})()

const SEV_COLOR: Record<Anomaly['severity'], string> = {
  CRITICAL: '#ff2a4d',
  HIGH: '#ff8a1f',
  MEDIUM: '#ffd23f',
  LOW: '#3aa6ff',
}

function panelPos(row: number, col: number): [number, number, number] {
  const x = (col - (COLS - 1) / 2) * (PANEL_W + GAP_X)
  const z = (row - (ROWS - 1) / 2) * (PANEL_H + GAP_Z)
  return [x, 0, z]
}

function SolarGrid({ selectedId }: { selectedId: string | null }) {
  const meshRef = useRef<THREE.InstancedMesh>(null!)
  const dummy = useMemo(() => new THREE.Object3D(), [])

  // Build anomaly lookup for coloring
  const anomalyMap = useMemo(() => {
    const m = new Map<number, Anomaly>()
    for (const a of ANOMALIES) m.set(a.row * COLS + a.col, a)
    return m
  }, [])

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    let i = 0
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const [x, , z] = panelPos(r, c)
        dummy.position.set(x, 0, z)
        dummy.rotation.set(-Math.PI / 2 + 0.18, 0, 0)
        // pulse anomaly panels
        const idx = r * COLS + c
        const an = anomalyMap.get(idx)
        const isSel = an && selectedId === an.id
        const lift = an ? 0.05 + 0.04 * Math.sin(t * 3 + i) : 0
        dummy.position.y = lift + (isSel ? 0.15 : 0)
        dummy.scale.setScalar(isSel ? 1.08 : 1)
        dummy.updateMatrix()
        meshRef.current.setMatrixAt(i, dummy.matrix)

        // Color
        const color = new THREE.Color()
        if (an) {
          color.set(SEV_COLOR[an.severity])
          const k = 0.55 + 0.45 * Math.sin(t * 4 + i)
          color.multiplyScalar(0.5 + 0.6 * k)
        } else {
          color.set('#0e2742')
        }
        meshRef.current.setColorAt(i, color)
        i++
      }
    }
    meshRef.current.instanceMatrix.needsUpdate = true
    if (meshRef.current.instanceColor) meshRef.current.instanceColor.needsUpdate = true
  })

  return (
    <instancedMesh
      ref={meshRef}
      args={[undefined, undefined, TOTAL]}
      castShadow
      receiveShadow
    >
      <boxGeometry args={[PANEL_W, 0.04, PANEL_H]} />
      <meshStandardMaterial
        metalness={0.4}
        roughness={0.35}
        emissive="#000000"
        emissiveIntensity={0}
        toneMapped={false}
      />
    </instancedMesh>
  )
}

function AnomalyMarkers({
  onSelect,
  selectedId,
}: {
  onSelect: (a: Anomaly) => void
  selectedId: string | null
}) {
  return (
    <group>
      {ANOMALIES.map((a) => {
        const [x, , z] = panelPos(a.row, a.col)
        const color = SEV_COLOR[a.severity]
        const isSel = selectedId === a.id
        return (
          <Marker
            key={a.id}
            position={[x, 0.4, z]}
            color={color}
            highlighted={isSel}
            onClick={(e) => {
              e.stopPropagation()
              onSelect(a)
            }}
          />
        )
      })}
    </group>
  )
}

function Marker({
  position,
  color,
  highlighted,
  onClick,
}: {
  position: [number, number, number]
  color: string
  highlighted: boolean
  onClick: (e: any) => void
}) {
  const ref = useRef<THREE.Mesh>(null!)
  useFrame(({ clock }) => {
    if (!ref.current) return
    const t = clock.getElapsedTime()
    const s = highlighted ? 1.4 : 1
    const pulse = 1 + 0.18 * Math.sin(t * 3 + position[0] + position[2])
    ref.current.scale.setScalar(s * pulse * 0.18)
    ref.current.position.y = position[1] + 0.15 + 0.08 * Math.sin(t * 2 + position[0])
  })
  return (
    <mesh ref={ref} position={position} onClick={onClick}>
      <sphereGeometry args={[1, 14, 14]} />
      <meshBasicMaterial color={color} toneMapped={false} />
    </mesh>
  )
}

function ScanDrone() {
  const ref = useRef<THREE.Group>(null!)
  const beamRef = useRef<THREE.Mesh>(null!)

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    // Sweep across the field in a serpentine path
    const sweepX = Math.sin(t * 0.25) * (COLS * (PANEL_W + GAP_X)) * 0.5
    const sweepZ = Math.cos(t * 0.25) * (ROWS * (PANEL_H + GAP_Z)) * 0.5
    if (ref.current) {
      ref.current.position.set(sweepX, 4.5 + Math.sin(t * 1.2) * 0.1, sweepZ)
      ref.current.rotation.y = Math.atan2(Math.cos(t * 0.25), -Math.sin(t * 0.25))
    }
    if (beamRef.current) {
      ;(beamRef.current.material as THREE.MeshBasicMaterial).opacity =
        0.15 + 0.1 * Math.sin(t * 4)
    }
  })

  return (
    <group ref={ref}>
      {/* Body */}
      <mesh castShadow>
        <boxGeometry args={[0.55, 0.12, 0.55]} />
        <meshStandardMaterial color="#1a1f3a" metalness={0.7} roughness={0.3} />
      </mesh>
      {/* Arms */}
      {[
        [0.4, 0, 0.4],
        [-0.4, 0, 0.4],
        [0.4, 0, -0.4],
        [-0.4, 0, -0.4],
      ].map((p, i) => (
        <mesh key={i} position={p as any}>
          <cylinderGeometry args={[0.04, 0.04, 0.28, 8]} />
          <meshStandardMaterial color="#2a2f4a" />
        </mesh>
      ))}
      {/* Rotors (just disks) */}
      {[
        [0.4, 0.12, 0.4],
        [-0.4, 0.12, 0.4],
        [0.4, 0.12, -0.4],
        [-0.4, 0.12, -0.4],
      ].map((p, i) => (
        <Rotor key={`r${i}`} position={p as any} />
      ))}
      {/* Teal under-light */}
      <pointLight position={[0, -0.2, 0]} color="#00f0c8" intensity={4} distance={6} />
      <mesh position={[0, -0.05, 0]}>
        <sphereGeometry args={[0.08, 12, 12]} />
        <meshBasicMaterial color="#00f0c8" toneMapped={false} />
      </mesh>
      {/* Scan cone — downward */}
      <mesh ref={beamRef} position={[0, -2.25, 0]} rotation={[Math.PI, 0, 0]}>
        <coneGeometry args={[1.4, 4.5, 24, 1, true]} />
        <meshBasicMaterial
          color="#00f0c8"
          transparent
          opacity={0.18}
          side={THREE.DoubleSide}
          depthWrite={false}
          toneMapped={false}
        />
      </mesh>
    </group>
  )
}

function Rotor({ position }: { position: [number, number, number] }) {
  const ref = useRef<THREE.Mesh>(null!)
  useFrame(() => {
    if (ref.current) ref.current.rotation.y += 0.9
  })
  return (
    <mesh ref={ref} position={position}>
      <cylinderGeometry args={[0.22, 0.22, 0.01, 16]} />
      <meshBasicMaterial color="#00f0c8" transparent opacity={0.25} toneMapped={false} />
    </mesh>
  )
}

function ScanLine() {
  const ref = useRef<THREE.Mesh>(null!)
  const length = COLS * (PANEL_W + GAP_X) + 2

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    const span = ROWS * (PANEL_H + GAP_Z) + 2
    const z = ((t * 1.6) % span) - span / 2
    if (ref.current) ref.current.position.z = z
  })
  return (
    <mesh ref={ref} position={[0, 0.15, 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={[length, 0.18]} />
      <meshBasicMaterial color="#00f0c8" transparent opacity={0.55} toneMapped={false} />
    </mesh>
  )
}

function GridFloor() {
  return (
    <>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.2, 0]} receiveShadow>
        <planeGeometry args={[160, 160]} />
        <meshStandardMaterial color="#03050d" metalness={0.2} roughness={1} />
      </mesh>
      <gridHelper
        args={[160, 80, '#0a2740', '#06121f']}
        position={[0, -0.18, 0]}
      />
    </>
  )
}

export default function PlatformScene({
  selectedId,
  onSelect,
}: {
  selectedId: string | null
  onSelect: (a: Anomaly | null) => void
}) {
  return (
    <Canvas
      shadows
      camera={{ position: [0, 12, 18], fov: 55, near: 0.1, far: 300 }}
      gl={{ antialias: true, powerPreference: 'high-performance' }}
      dpr={[1, 1.6]}
      onPointerMissed={() => onSelect(null)}
    >
      <Suspense fallback={null}>
        <color attach="background" args={['#02030a']} />
        <fog attach="fog" args={['#02030a', 30, 80]} />

        <ambientLight intensity={0.2} color="#1a2848" />
        <directionalLight
          position={[14, 22, 10]}
          intensity={0.55}
          color="#cfd8ff"
          castShadow
          shadow-mapSize={[1024, 1024]}
        />
        <pointLight position={[0, 6, 0]} color="#00f0c8" intensity={0.7} distance={40} />
        <pointLight position={[-12, 4, -8]} color="#6c63ff" intensity={0.6} distance={30} />

        <Stars radius={120} depth={50} count={2000} factor={3} fade speed={0.15} />

        <GridFloor />
        <SolarGrid selectedId={selectedId} />
        <ScanLine />
        <AnomalyMarkers onSelect={onSelect} selectedId={selectedId} />
        <ScanDrone />

        <OrbitControls
          enablePan={false}
          minDistance={10}
          maxDistance={32}
          minPolarAngle={0.2}
          maxPolarAngle={Math.PI / 2.2}
          autoRotate
          autoRotateSpeed={0.35}
        />

        <EffectComposer>
          <Bloom luminanceThreshold={0.35} luminanceSmoothing={0.4} intensity={1.2} />
          <Vignette darkness={0.6} offset={0.3} />
        </EffectComposer>
      </Suspense>
    </Canvas>
  )
}
