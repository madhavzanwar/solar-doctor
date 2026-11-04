'use client'

import { useRef, useMemo, useEffect } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Float } from '@react-three/drei'
import * as THREE from 'three'

// ── Star field ──────────────────────────────────────────────────────────────
function StarField() {
  const meshRef = useRef<THREE.Points>(null)

  const [positions, sizes] = useMemo(() => {
    const count = 2000
    const pos = new Float32Array(count * 3)
    const sz = new Float32Array(count)
    for (let i = 0; i < count; i++) {
      pos[i * 3 + 0] = (Math.random() - 0.5) * 200
      pos[i * 3 + 1] = (Math.random() - 0.5) * 200
      pos[i * 3 + 2] = (Math.random() - 0.5) * 200
      sz[i] = Math.random() * 1.5 + 0.2
    }
    return [pos, sz]
  }, [])

  useFrame((_, delta) => {
    if (meshRef.current) {
      meshRef.current.rotation.y += delta * 0.02
      meshRef.current.rotation.x += delta * 0.005
    }
  })

  return (
    <points ref={meshRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          args={[positions, 3]}
        />
        <bufferAttribute
          attach="attributes-size"
          args={[sizes, 1]}
        />
      </bufferGeometry>
      <pointsMaterial
        size={0.3}
        color="#ffffff"
        transparent
        opacity={0.6}
        sizeAttenuation
      />
    </points>
  )
}

// ── Wireframe floating geometry ───────────────────────────────────────────
function FloatingShape({
  position,
  color,
  geometry,
  rotationSpeed,
}: {
  position: [number, number, number]
  color: string
  geometry: 'icosahedron' | 'octahedron' | 'tetrahedron'
  rotationSpeed: [number, number, number]
}) {
  const meshRef = useRef<THREE.Mesh>(null)

  useFrame((_, delta) => {
    if (meshRef.current) {
      meshRef.current.rotation.x += delta * rotationSpeed[0]
      meshRef.current.rotation.y += delta * rotationSpeed[1]
      meshRef.current.rotation.z += delta * rotationSpeed[2]
    }
  })

  const geo = useMemo(() => {
    if (geometry === 'icosahedron') return <icosahedronGeometry args={[1.5, 0]} />
    if (geometry === 'octahedron') return <octahedronGeometry args={[1.2, 0]} />
    return <tetrahedronGeometry args={[1.3, 0]} />
  }, [geometry])

  return (
    <Float speed={1.5} rotationIntensity={0.2} floatIntensity={0.5}>
      <mesh ref={meshRef} position={position}>
        {geo}
        <meshBasicMaterial color={color} wireframe transparent opacity={0.25} />
      </mesh>
    </Float>
  )
}

// ── Grid plane (landing pad) ─────────────────────────────────────────────
function GridPlane() {
  return (
    <gridHelper
      args={[60, 30, '#00f0c8', '#0d1a16']}
      position={[0, -12, 0]}
      rotation={[0, 0, 0]}
    />
  )
}

// ── Mouse parallax controller ────────────────────────────────────────────
function ParallaxRig({ mouse }: { mouse: React.MutableRefObject<[number, number]> }) {
  const { camera } = useThree()

  useFrame(() => {
    camera.position.x += (mouse.current[0] * 3 - camera.position.x) * 0.03
    camera.position.y += (-mouse.current[1] * 2 - camera.position.y + 2) * 0.03
    camera.lookAt(0, 0, 0)
  })

  return null
}

// ── Scene composition ────────────────────────────────────────────────────
function SceneContent({ mouse }: { mouse: React.MutableRefObject<[number, number]> }) {
  return (
    <>
      <ambientLight intensity={0.5} />
      <ParallaxRig mouse={mouse} />
      <StarField />
      <FloatingShape
        position={[-8, 3, -10]}
        color="#00f0c8"
        geometry="icosahedron"
        rotationSpeed={[0.2, 0.3, 0.1]}
      />
      <FloatingShape
        position={[9, -2, -12]}
        color="#6c63ff"
        geometry="octahedron"
        rotationSpeed={[0.1, 0.2, 0.3]}
      />
      <FloatingShape
        position={[-5, -5, -8]}
        color="#6c63ff"
        geometry="tetrahedron"
        rotationSpeed={[0.3, 0.1, 0.2]}
      />
      <FloatingShape
        position={[6, 6, -15]}
        color="#00f0c8"
        geometry="icosahedron"
        rotationSpeed={[0.15, 0.25, 0.05]}
      />
      <GridPlane />
    </>
  )
}

// ── Exported wrapper ─────────────────────────────────────────────────────
export default function Scene3D() {
  const mouse = useRef<[number, number]>([0, 0])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      mouse.current = [
        (e.clientX / window.innerWidth) * 2 - 1,
        (e.clientY / window.innerHeight) * 2 - 1,
      ]
    }
    window.addEventListener('mousemove', onMove)
    return () => window.removeEventListener('mousemove', onMove)
  }, [])

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 0,
        pointerEvents: 'none',
      }}
    >
      <Canvas
        camera={{ position: [0, 2, 20], fov: 60 }}
        gl={{ antialias: true, alpha: true }}
        style={{ background: 'transparent' }}
      >
        <SceneContent mouse={mouse} />
      </Canvas>
    </div>
  )
}
