'use client'

import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { scrollStore } from '../../scrollStore'

const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi)
const lerp  = (a: number, b: number, t: number) => a + (b - a) * t

// Field sweep bounds (Z axis)
const SWEEP_Z_START =  9    // back of field (drones start here)
const SWEEP_Z_END   = -9    // front of field

// Formation layout — [xPosition, phaseOffset]
// Lead drone in center, wings staggered 1.5 units back in Z
const FORMATION: [number, number, number][] = [
  [  0,   0,   0.0  ],   // lead  — center
  [ -5.5, 2.0, 1.3  ],   // left  — wing
  [  5.5, 2.0, 2.6  ],   // right — wing
]

// Arm tip positions (4 per drone), rotated 45° so arms face diagonals
const ARM_TIPS: [number, number, number][] = [
  [ 0.20, 0,  0.20],
  [-0.20, 0,  0.20],
  [-0.20, 0, -0.20],
  [ 0.20, 0, -0.20],
]

export default function DroneFleet() {
  // Per-drone refs
  const droneGroupRefs = useRef<(THREE.Group | null)[]>([null, null, null])
  const lightRefs      = useRef<(THREE.PointLight | null)[]>([null, null, null])
  // Per-drone coverage strip refs
  const stripRefs      = useRef<(THREE.Mesh | null)[]>([null, null, null])
  // All rotors: 4 per drone × 3 = 12
  const rotorRefs      = useRef<(THREE.Mesh | null)[]>(Array(12).fill(null))
  // Whole fleet container
  const fleetRef       = useRef<THREE.Group>(null)
  // Ambient scan fill
  const scanLightRef   = useRef<THREE.PointLight>(null)

  useFrame(({ clock }) => {
    const t = scrollStore.progress
    // Scene 4: scroll 3/6 → 4/6
    const fleetP = clamp((t - 3 / 6) / (1 / 6), 0, 1)
    const active = fleetP > 0.005

    if (fleetRef.current) fleetRef.current.visible = active

    if (!active) return

    // Ease-in-out so fleet doesn't rush
    const eased = fleetP < 0.5
      ? 2 * fleetP * fleetP
      : 1 - Math.pow(-2 * fleetP + 2, 2) / 2

    const sweepZ = lerp(SWEEP_Z_START, SWEEP_Z_END, eased)

    // Rotor spin — alternating CW/CCW per arm
    const rs = clock.elapsedTime * 24
    rotorRefs.current.forEach((r, idx) => {
      if (!r) return
      r.rotation.y = idx % 2 === 0 ? rs : -rs
    })

    // Per-drone updates
    FORMATION.forEach(([xPos, zOffset, phase], di) => {
      const drone = droneGroupRefs.current[di]
      if (!drone) return

      const hover    = Math.sin(clock.elapsedTime * 1.05 + phase) * 0.20
      const wobbleX  = Math.sin(clock.elapsedTime * 0.7  + phase) * 0.06
      drone.position.set(xPos + wobbleX, 6.0 + hover, sweepZ + zOffset)

      // ── Coverage strip: grows from sweep start to current droneZ ──
      const strip = stripRefs.current[di]
      if (strip) {
        const coveredLen = Math.abs(SWEEP_Z_START - (sweepZ + zOffset))
        const midZ = SWEEP_Z_START - coveredLen / 2
        strip.position.set(xPos, 0.08, midZ)
        strip.scale.set(1, 1, coveredLen)
        const mat = strip.material as THREE.MeshBasicMaterial
        mat.opacity = 0.06 + Math.sin(clock.elapsedTime * 2 + phase) * 0.015
      }

      // Light colour pulse
      const light = lightRefs.current[di]
      if (light) {
        const pulse = 4.5 + Math.sin(clock.elapsedTime * 2.5 + phase) * 0.8
        light.intensity = pulse
      }
    })

    // Ambient scan light follows fleet centre
    if (scanLightRef.current) {
      scanLightRef.current.position.z = sweepZ
      scanLightRef.current.intensity  = fleetP * 3.5
    }
  })

  return (
    <group ref={fleetRef} visible={false}>

      {/* ── Ambient coverage glow — wide teal fill under the formation ── */}
      <pointLight
        ref={scanLightRef}
        position={[0, 10, SWEEP_Z_START]}
        color="#00f0c8"
        intensity={0}
        distance={28}
        decay={1.6}
      />

      {/* ── Three drones ── */}
      {FORMATION.map(([xPos, zOffset, phase], di) => (
        <group
          key={di}
          ref={el => { droneGroupRefs.current[di] = el }}
          position={[xPos, 6.0, SWEEP_Z_START + zOffset]}
        >
          {/* Body */}
          <mesh castShadow>
            <boxGeometry args={[0.38, 0.08, 0.38]} />
            <meshStandardMaterial color="#0c0e1a" metalness={0.94} roughness={0.08} />
          </mesh>

          {/* Top teal identity strip */}
          <mesh position={[0, 0.052, 0]}>
            <boxGeometry args={[0.14, 0.012, 0.14]} />
            <meshStandardMaterial color="#00f0c8" emissive="#00f0c8" emissiveIntensity={5} />
          </mesh>

          {/* Belly ridge */}
          <mesh position={[0, -0.048, 0]}>
            <boxGeometry args={[0.22, 0.01, 0.22]} />
            <meshStandardMaterial color="#0a0f20" metalness={0.9} roughness={0.2} />
          </mesh>

          {/* ── 4 Arms + motors + rotors ── */}
          {ARM_TIPS.map(([ax, , az], ai) => (
            <group key={ai}>
              {/* Diagonal arm */}
              <mesh
                position={[ax / 2, 0, az / 2]}
                rotation={[0, Math.atan2(ax, az), 0]}
              >
                <boxGeometry args={[0.008, 0.008, 0.32]} />
                <meshStandardMaterial color="#0c0e1a" metalness={0.85} roughness={0.2} />
              </mesh>

              {/* Motor hub */}
              <mesh position={[ax, 0.028, az]}>
                <cylinderGeometry args={[0.022, 0.022, 0.038, 8]} />
                <meshStandardMaterial color="#00f0c8" emissive="#00f0c8" emissiveIntensity={3} />
              </mesh>

              {/* Rotor ring */}
              <mesh
                ref={el => { rotorRefs.current[di * 4 + ai] = el }}
                position={[ax, 0.050, az]}
                rotation={[Math.PI / 2, 0, 0]}
              >
                <torusGeometry args={[0.11, 0.009, 4, 28]} />
                <meshStandardMaterial
                  color="#6c63ff"
                  emissive="#6c63ff"
                  emissiveIntensity={3}
                  transparent
                  opacity={0.82}
                />
              </mesh>
            </group>
          ))}

          {/* Gimbal camera pod */}
          <mesh position={[0, -0.065, 0.10]}>
            <sphereGeometry args={[0.042, 10, 10]} />
            <meshStandardMaterial color="#00f0c8" emissive="#00f0c8" emissiveIntensity={6} />
          </mesh>

          {/* Downward thermal cone */}
          <mesh position={[0, -3.5, 0]}>
            <cylinderGeometry args={[0.12, 1.5, 7, 12, 1, true]} />
            <meshBasicMaterial
              color="#00f0c8"
              transparent
              opacity={0.05}
              side={THREE.DoubleSide}
              depthWrite={false}
            />
          </mesh>

          {/* Formation ID light (lead = brighter) */}
          <pointLight
            ref={el => { lightRefs.current[di] = el }}
            position={[0, -0.8, 0]}
            color="#00f0c8"
            intensity={4.5}
            distance={18}
            decay={2}
          />
        </group>
      ))}

      {/* ── Coverage strips: one teal band per drone column ── */}
      {FORMATION.map(([xPos], di) => (
        <mesh
          key={`strip-${di}`}
          ref={el => { stripRefs.current[di] = el }}
          position={[xPos, 0.08, SWEEP_Z_START]}
          rotation={[-Math.PI / 2, 0, 0]}
        >
          {/* 1×1 plane — scaled in useFrame to cover distance swept */}
          <planeGeometry args={[3.2, 1]} />
          <meshBasicMaterial
            color="#00f0c8"
            transparent
            opacity={0.06}
            side={THREE.DoubleSide}
            depthWrite={false}
          />
        </mesh>
      ))}

      {/* ── Formation connector lines (visible leader lines between drones) ── */}
      <FormationLines />
    </group>
  )
}

// Thin connectors showing the V-formation shape
function FormationLines() {
  const lineObj = useMemo(() => {
    const pts = [
      new THREE.Vector3(-5.5, 6, 2.0),
      new THREE.Vector3(0,    6, 0),
      new THREE.Vector3( 5.5, 6, 2.0),
    ]
    const geo = new THREE.BufferGeometry().setFromPoints(pts)
    const mat = new THREE.LineBasicMaterial({ color: '#00f0c8', transparent: true, opacity: 0 })
    return new THREE.Line(geo, mat)
  }, [])

  useFrame(() => {
    const t = scrollStore.progress
    const fleetP = clamp((t - 3/6) / (1/6), 0, 1)
    ;(lineObj.material as THREE.LineBasicMaterial).opacity = Math.min(fleetP * 3, 0.3)
  })

  return <primitive object={lineObj} />
}
