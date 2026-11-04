'use client'

import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

interface DroneProps {
  position?: [number, number, number]
  scale?: number
  phase?: number        // sine wave phase offset for formation flying
  lightIntensity?: number
}

// Shared geometry/material refs (created once, reused across instances)
const TEAL   = '#00f0c8'
const PURPLE = '#6c63ff'
const DARK   = '#111320'

export default function Drone({
  position = [0, 4, 0],
  scale = 1,
  phase = 0,
  lightIntensity = 4,
}: DroneProps) {
  const groupRef   = useRef<THREE.Group>(null)
  const rotor1Ref  = useRef<THREE.Mesh>(null)
  const rotor2Ref  = useRef<THREE.Mesh>(null)
  const rotor3Ref  = useRef<THREE.Mesh>(null)
  const rotor4Ref  = useRef<THREE.Mesh>(null)

  // Hover and rotor animation
  useFrame(({ clock }) => {
    const t = clock.elapsedTime
    if (groupRef.current) {
      groupRef.current.position.y = position[1] + Math.sin(t * 0.9 + phase) * 0.22
      groupRef.current.rotation.z = Math.sin(t * 0.4 + phase) * 0.04
      groupRef.current.rotation.x = Math.sin(t * 0.3 + phase + 1) * 0.03
    }

    const speed = t * 18
    if (rotor1Ref.current) rotor1Ref.current.rotation.y =  speed
    if (rotor2Ref.current) rotor2Ref.current.rotation.y = -speed
    if (rotor3Ref.current) rotor3Ref.current.rotation.y =  speed + Math.PI
    if (rotor4Ref.current) rotor4Ref.current.rotation.y = -speed + Math.PI
  })

  const armOffsets: [number, number, number, number][] = [
    [ 0.22,  0, -0.22,  Math.PI * 0.25],
    [-0.22,  0, -0.22, -Math.PI * 0.25],
    [-0.22,  0,  0.22,  Math.PI * 0.25],
    [ 0.22,  0,  0.22, -Math.PI * 0.25],
  ]

  const rotorRefs = [rotor1Ref, rotor2Ref, rotor3Ref, rotor4Ref]

  return (
    <group ref={groupRef} position={position} scale={scale}>

      {/* ── Body ── */}
      <mesh castShadow>
        <boxGeometry args={[0.38, 0.08, 0.38]} />
        <meshStandardMaterial color={DARK} metalness={0.9} roughness={0.15} />
      </mesh>

      {/* Body top accent (teal strip) */}
      <mesh position={[0, 0.045, 0]}>
        <boxGeometry args={[0.16, 0.012, 0.16]} />
        <meshStandardMaterial
          color={TEAL}
          emissive={TEAL}
          emissiveIntensity={2.5}
          metalness={0.5}
          roughness={0.2}
        />
      </mesh>

      {/* Status LED */}
      <mesh position={[0, 0.052, 0.12]}>
        <sphereGeometry args={[0.018, 8, 8]} />
        <meshStandardMaterial
          color={TEAL}
          emissive={TEAL}
          emissiveIntensity={4}
        />
      </mesh>

      {/* ── Arms + rotors ── */}
      {armOffsets.map(([ax, , az, ry], i) => (
        <group key={i} position={[ax, 0, az]} rotation={[0, ry, 0]}>
          {/* Arm */}
          <mesh>
            <cylinderGeometry args={[0.014, 0.014, 0.42, 6]} />
            <meshStandardMaterial color={DARK} metalness={0.85} roughness={0.2} />
          </mesh>

          {/* Motor hub */}
          <mesh position={[0, 0.028, -0.21]}>
            <cylinderGeometry args={[0.028, 0.028, 0.044, 8]} />
            <meshStandardMaterial color={TEAL} emissive={TEAL} emissiveIntensity={1.5} />
          </mesh>

          {/* Rotor ring */}
          <mesh ref={rotorRefs[i]} position={[0, 0.042, -0.21]} rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[0.12, 0.012, 4, 24]} />
            <meshStandardMaterial
              color={PURPLE}
              emissive={PURPLE}
              emissiveIntensity={1.8}
              transparent
              opacity={0.85}
            />
          </mesh>
        </group>
      ))}

      {/* ── Gimbal camera pod ── */}
      <mesh position={[0, -0.07, 0.1]}>
        <sphereGeometry args={[0.05, 10, 8]} />
        <meshStandardMaterial color={DARK} metalness={0.95} roughness={0.05} />
      </mesh>
      {/* Camera lens */}
      <mesh position={[0, -0.09, 0.14]}>
        <cylinderGeometry args={[0.022, 0.018, 0.03, 12]} />
        <meshStandardMaterial color={TEAL} emissive={TEAL} emissiveIntensity={3} />
      </mesh>

      {/* ── Landing legs ── */}
      {([[-0.15, 0.15], [-0.15, -0.15], [0.15, 0.15], [0.15, -0.15]] as [number, number][]).map(([lx, lz], i) => (
        <mesh key={i} position={[lx, -0.07, lz]}>
          <cylinderGeometry args={[0.008, 0.008, 0.14, 5]} />
          <meshStandardMaterial color="#0d0d1a" metalness={0.7} roughness={0.4} />
        </mesh>
      ))}

      {/* ── Lighting — teal point light below drone ── */}
      <pointLight
        position={[0, -0.5, 0]}
        color={TEAL}
        intensity={lightIntensity}
        distance={14}
        decay={2}
      />
      {/* Subtle purple fill */}
      <pointLight
        position={[0, 0.2, 0]}
        color={PURPLE}
        intensity={lightIntensity * 0.4}
        distance={6}
        decay={2}
      />
    </group>
  )
}
