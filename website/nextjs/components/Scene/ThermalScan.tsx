'use client'

import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { scrollStore } from '../../scrollStore'

// ── Field geometry constants (must match SolarField.tsx) ───────────────────
const COLS       = 22
const PANEL_W    = 0.95
const GAP_X      = 0.15
const FIELD_HALF = (COLS * (PANEL_W + GAP_X)) / 2   // ≈ 12.1
const FIELD_LEFT  = -FIELD_HALF
const FIELD_RIGHT  =  FIELD_HALF
const FIELD_DEPTH  = 15          // approximate Z span of all rows

const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi)
const lerp  = (a: number, b: number, t: number) => a + (b - a) * t

export default function ThermalScan() {
  const scanLineRef  = useRef<THREE.Mesh>(null)
  const glowLineRef  = useRef<THREE.Mesh>(null)
  const droneRef     = useRef<THREE.Group>(null)
  const beamRef      = useRef<THREE.Mesh>(null)
  const lightRef     = useRef<THREE.PointLight>(null)
  const rotor1       = useRef<THREE.Mesh>(null)
  const rotor2       = useRef<THREE.Mesh>(null)
  const rotor3       = useRef<THREE.Mesh>(null)
  const rotor4       = useRef<THREE.Mesh>(null)

  useFrame(({ clock }) => {
    const t = scrollStore.progress
    // Section 2 occupies scroll 1/6 → 2/6
    const thermalP = clamp((t - 1 / 6) / (1 / 6), 0, 1)
    const active = thermalP > 0.02 && thermalP < 0.98

    const scanX = lerp(FIELD_LEFT, FIELD_RIGHT, thermalP)

    // ── Scan line ──
    if (scanLineRef.current) {
      scanLineRef.current.visible = active
      scanLineRef.current.position.x = scanX
    }
    if (glowLineRef.current) {
      glowLineRef.current.visible = active
      glowLineRef.current.position.x = scanX
    }

    // ── Scanning drone ──
    if (droneRef.current) {
      droneRef.current.visible = active
      // Slight sine drift on Y for hover effect
      const hover = Math.sin(clock.elapsedTime * 1.1) * 0.15
      droneRef.current.position.set(scanX, 5.2 + hover, 0)
    }

    // ── Rotor spin ──
    const rs = clock.elapsedTime * 20
    if (rotor1.current) rotor1.current.rotation.y =  rs
    if (rotor2.current) rotor2.current.rotation.y = -rs
    if (rotor3.current) rotor3.current.rotation.y =  rs + Math.PI
    if (rotor4.current) rotor4.current.rotation.y = -rs + Math.PI

    // ── Dynamic light: shifts teal → orange → red as faults accumulate ──
    if (lightRef.current) {
      lightRef.current.visible = active
      // Heat colour ramp
      const r = clamp(lerp(0, 1.0, thermalP * 0.9), 0, 1)
      const g = clamp(lerp(0.94, 0.25, thermalP * 0.85), 0, 1)
      const b = clamp(lerp(0.78, 0.0, thermalP * 1.2), 0, 1)
      lightRef.current.color.setRGB(r, g, b)
    }
  })

  const ARM_OFFSETS: [number, number, number][] = [
    [ 0.16, 0, -0.16],
    [-0.16, 0, -0.16],
    [-0.16, 0,  0.16],
    [ 0.16, 0,  0.16],
  ]
  const rotorRefs = [rotor1, rotor2, rotor3, rotor4]

  return (
    <group>
      {/* ── Scan line — flat teal band sweeping across panels ── */}
      <mesh
        ref={scanLineRef}
        position={[FIELD_LEFT, 0.12, 0]}
        rotation={[-Math.PI / 2, 0, 0]}
        visible={false}
      >
        <planeGeometry args={[0.06, FIELD_DEPTH]} />
        <meshBasicMaterial
          color="#00f0c8"
          transparent
          opacity={0.75}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>

      {/* Wider soft glow band behind the hard line */}
      <mesh
        ref={glowLineRef}
        position={[FIELD_LEFT, 0.11, 0]}
        rotation={[-Math.PI / 2, 0, 0]}
        visible={false}
      >
        <planeGeometry args={[0.6, FIELD_DEPTH]} />
        <meshBasicMaterial
          color="#00f0c8"
          transparent
          opacity={0.08}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>

      {/* ── Scanning drone ── */}
      <group ref={droneRef} position={[FIELD_LEFT, 5.2, 0]} visible={false}>
        {/* Body */}
        <mesh>
          <boxGeometry args={[0.28, 0.055, 0.28]} />
          <meshStandardMaterial color="#0d1020" metalness={0.92} roughness={0.1} />
        </mesh>

        {/* Top teal strip */}
        <mesh position={[0, 0.034, 0]}>
          <boxGeometry args={[0.1, 0.009, 0.1]} />
          <meshStandardMaterial color="#00f0c8" emissive="#00f0c8" emissiveIntensity={3.5} />
        </mesh>

        {/* Arms + rotors */}
        {ARM_OFFSETS.map(([ax, , az], i) => (
          <group key={i} position={[ax, 0, az]}>
            <mesh>
              <cylinderGeometry args={[0.009, 0.009, 0.28, 5]} />
              <meshStandardMaterial color="#0d1020" metalness={0.85} roughness={0.2} />
            </mesh>
            {/* Motor */}
            <mesh position={[0, 0.02, -0.14]}>
              <cylinderGeometry args={[0.018, 0.018, 0.03, 8]} />
              <meshStandardMaterial color="#00f0c8" emissive="#00f0c8" emissiveIntensity={2} />
            </mesh>
            {/* Rotor */}
            <mesh ref={rotorRefs[i]} position={[0, 0.034, -0.14]} rotation={[Math.PI / 2, 0, 0]}>
              <torusGeometry args={[0.085, 0.008, 4, 20]} />
              <meshStandardMaterial color="#6c63ff" emissive="#6c63ff" emissiveIntensity={2} transparent opacity={0.8} />
            </mesh>
          </group>
        ))}

        {/* Downward beam — cone shape from gimbal to panels */}
        <mesh ref={beamRef} position={[0, -2.5, 0]}>
          <cylinderGeometry args={[0.08, 0.6, 5, 12, 1, true]} />
          <meshBasicMaterial color="#00f0c8" transparent opacity={0.06} side={THREE.DoubleSide} depthWrite={false} />
        </mesh>

        {/* Gimbal camera */}
        <mesh position={[0, -0.06, 0.08]}>
          <sphereGeometry args={[0.035, 8, 8]} />
          <meshStandardMaterial color="#00f0c8" emissive="#00f0c8" emissiveIntensity={4} />
        </mesh>

        {/* Scanning point light — colour animated in useFrame */}
        <pointLight
          ref={lightRef}
          position={[0, -0.8, 0]}
          intensity={5}
          distance={14}
          decay={2}
          visible={false}
        />
      </group>
    </group>
  )
}
