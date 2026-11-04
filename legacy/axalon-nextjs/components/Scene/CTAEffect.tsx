'use client'

import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import * as THREE from 'three'
import { scrollStore } from '../../scrollStore'

const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi)

const PARTICLE_COUNT = 180

export default function CTAEffect() {
  const groupRef    = useRef<THREE.Group>(null)
  const pointsRef   = useRef<THREE.Points>(null)
  const spotRef     = useRef<THREE.SpotLight>(null)
  const rimRef      = useRef<THREE.PointLight>(null)
  const ring1Ref    = useRef<THREE.Mesh>(null)
  const ring2Ref    = useRef<THREE.Mesh>(null)
  const ring3Ref    = useRef<THREE.Mesh>(null)

  // Rising particles — random XZ spread, animated Y in useFrame
  const { geo, baseY } = useMemo(() => {
    const positions = new Float32Array(PARTICLE_COUNT * 3)
    const by: number[] = []
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const x = (Math.random() - 0.5) * 22
      const y = Math.random() * 8 - 0.5
      const z = (Math.random() - 0.5) * 16
      positions[i * 3]     = x
      positions[i * 3 + 1] = y
      positions[i * 3 + 2] = z
      by.push(y)
    }
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    return { geo: geometry, baseY: by }
  }, [])

  useFrame(({ clock }) => {
    const t = scrollStore.progress
    // Scene 6: scroll 5/6 → 6/6
    const ctaP  = clamp((t - 5 / 6) / (1 / 6), 0, 1)
    const active = ctaP > 0.005

    if (groupRef.current) groupRef.current.visible = active
    if (!active) return

    const elapsed = clock.elapsedTime

    // Animate rising particles
    if (pointsRef.current) {
      const pos = (pointsRef.current.geometry.attributes.position as THREE.BufferAttribute)
      const arr = pos.array as Float32Array
      for (let i = 0; i < PARTICLE_COUNT; i++) {
        arr[i * 3 + 1] = baseY[i] + ((elapsed * 0.4 + i * 0.07) % 9) - 0.5
      }
      pos.needsUpdate = true
      const mat = pointsRef.current.material as THREE.PointsMaterial
      mat.opacity = Math.min(ctaP * 2, 0.45)
    }

    // Spot sweep
    if (spotRef.current) {
      spotRef.current.intensity = ctaP * 80
      spotRef.current.position.x = Math.sin(elapsed * 0.3) * 4
    }

    // Rim pulse
    if (rimRef.current) {
      rimRef.current.intensity = ctaP * (2 + Math.sin(elapsed * 1.5) * 0.5)
    }

    // Landing zone rings — concentric pulse outward
    const rings = [ring1Ref.current, ring2Ref.current, ring3Ref.current]
    rings.forEach((ring, i) => {
      if (!ring) return
      const phase = (elapsed * 0.8 + i * 0.7) % 1
      const scale = 0.5 + phase * 1.5
      ring.scale.setScalar(scale)
      const mat = ring.material as THREE.MeshBasicMaterial
      mat.opacity = ctaP * (1 - phase) * 0.65
    })
  })

  return (
    <group ref={groupRef} visible={false}>
      {/* Rising particle field */}
      <points ref={pointsRef} geometry={geo}>
        <pointsMaterial
          color="#00f0c8"
          size={0.05}
          transparent
          opacity={0}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          sizeAttenuation
        />
      </points>

      {/* Hero spotlight from above */}
      <spotLight
        ref={spotRef}
        position={[0, 30, 10]}
        target-position={[0, 0, 0]}
        angle={0.25}
        penumbra={0.6}
        color="#c8f0ff"
        intensity={0}
        distance={60}
        decay={1.4}
        castShadow={false}
      />

      {/* Teal rim from below */}
      <pointLight
        ref={rimRef}
        position={[0, -2, 0]}
        color="#00f0c8"
        intensity={0}
        distance={30}
        decay={2}
      />

      {/* Landing zone — pulsing rings on the ground plane */}
      <group position={[0, -0.45, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        {[ring1Ref, ring2Ref, ring3Ref].map((ref, i) => (
          <mesh key={i} ref={ref}>
            <ringGeometry args={[1.8, 2.0, 64]} />
            <meshBasicMaterial
              color="#00f0c8"
              transparent
              opacity={0}
              depthWrite={false}
              blending={THREE.AdditiveBlending}
              side={THREE.DoubleSide}
            />
          </mesh>
        ))}

        {/* Static inner ring */}
        <mesh>
          <ringGeometry args={[0.55, 0.60, 48]} />
          <meshBasicMaterial
            color="#00f0c8"
            transparent
            opacity={0.35}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
            side={THREE.DoubleSide}
          />
        </mesh>

        {/* Cross-hairs */}
        {([0, Math.PI / 2] as number[]).map((angle, i) => (
          <mesh key={`ch-${i}`} rotation={[0, 0, angle]}>
            <planeGeometry args={[2.8, 0.012]} />
            <meshBasicMaterial
              color="#00f0c8"
              transparent
              opacity={0.18}
              depthWrite={false}
              blending={THREE.AdditiveBlending}
            />
          </mesh>
        ))}
      </group>

      {/* Landing zone label */}
      <Html
        position={[0, -0.4, -2.4]}
        center
        style={{ pointerEvents: 'none' }}
      >
        <span style={{
          fontFamily: 'Space Grotesk, sans-serif',
          fontSize: '9px',
          color: 'rgba(0,240,200,0.55)',
          letterSpacing: '0.28em',
          textTransform: 'uppercase',
          whiteSpace: 'nowrap',
        }}>
          LANDING ZONE ALPHA
        </span>
      </Html>
    </group>
  )
}
