'use client'

import { useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { motion, useScroll, useTransform } from 'framer-motion'
import * as THREE from 'three'

// ── 3D Drone model ────────────────────────────────────────────────────────
function DroneModel() {
  const groupRef = useRef<THREE.Group>(null)
  const rotor1 = useRef<THREE.Mesh>(null)
  const rotor2 = useRef<THREE.Mesh>(null)
  const rotor3 = useRef<THREE.Mesh>(null)
  const rotor4 = useRef<THREE.Mesh>(null)

  useFrame(({ clock }) => {
    if (groupRef.current) {
      // Hover animation - gentle sine wave
      groupRef.current.position.y = Math.sin(clock.elapsedTime * 0.8) * 0.18
      // Slight tilt
      groupRef.current.rotation.x = Math.sin(clock.elapsedTime * 0.4) * 0.06
      groupRef.current.rotation.z = Math.sin(clock.elapsedTime * 0.5) * 0.04
    }
    // Rotor spin
    const rotorSpeed = clock.elapsedTime * 12
    if (rotor1.current) rotor1.current.rotation.y = rotorSpeed
    if (rotor2.current) rotor2.current.rotation.y = -rotorSpeed
    if (rotor3.current) rotor3.current.rotation.y = rotorSpeed
    if (rotor4.current) rotor4.current.rotation.y = -rotorSpeed
  })

  const bodyMat = (
    <meshStandardMaterial color="#0d1a24" metalness={0.8} roughness={0.2} />
  )
  const accentMat = (
    <meshStandardMaterial
      color="#00f0c8"
      emissive="#00f0c8"
      emissiveIntensity={0.6}
      metalness={0.5}
      roughness={0.3}
    />
  )
  const rotorMat = (
    <meshStandardMaterial
      color="#6c63ff"
      emissive="#6c63ff"
      emissiveIntensity={0.4}
      transparent
      opacity={0.7}
    />
  )

  // Arm positions
  const armPos: [number, number, number, number][] = [
    [0.9, 0, 0.9, Math.PI / 4],
    [-0.9, 0, 0.9, -Math.PI / 4],
    [0.9, 0, -0.9, -Math.PI / 4],
    [-0.9, 0, -0.9, Math.PI / 4],
  ]

  return (
    <group ref={groupRef} position={[0, 0, 0]}>
      {/* Main body */}
      <mesh position={[0, 0, 0]}>
        <boxGeometry args={[1.2, 0.22, 1.2]} />
        {bodyMat}
      </mesh>

      {/* Center accent stripe */}
      <mesh position={[0, 0.12, 0]}>
        <boxGeometry args={[0.6, 0.04, 0.6]} />
        {accentMat}
      </mesh>

      {/* Camera pod */}
      <mesh position={[0, -0.18, 0.2]}>
        <sphereGeometry args={[0.14, 12, 8]} />
        <meshStandardMaterial color="#00f0c8" emissive="#00f0c8" emissiveIntensity={0.8} />
      </mesh>

      {/* Arms + rotors */}
      {armPos.map(([x, y, z, rot], i) => {
        const rotorRef = [rotor1, rotor2, rotor3, rotor4][i]
        return (
          <group key={i} position={[x * 0.6, y, z * 0.6]} rotation={[0, rot, 0]}>
            {/* Arm */}
            <mesh position={[0, 0, 0]}>
              <boxGeometry args={[0.08, 0.06, 0.9]} />
              {bodyMat}
            </mesh>
            {/* Rotor hub */}
            <mesh position={[0, 0.05, 0.5]}>
              <cylinderGeometry args={[0.06, 0.06, 0.05, 8]} />
              {accentMat}
            </mesh>
            {/* Rotor blade */}
            <mesh ref={rotorRef} position={[0, 0.1, 0.5]} rotation={[Math.PI / 2, 0, 0]}>
              <torusGeometry args={[0.28, 0.018, 4, 24]} />
              {rotorMat}
            </mesh>
          </group>
        )
      })}

      {/* Landing legs */}
      {([-0.5, 0.5] as number[]).map((x) =>
        ([-0.5, 0.5] as number[]).map((z) => (
          <mesh key={`${x}-${z}`} position={[x, -0.2, z]}>
            <cylinderGeometry args={[0.02, 0.02, 0.2, 6]} />
            <meshStandardMaterial color="#1a1a2e" metalness={0.6} roughness={0.4} />
          </mesh>
        ))
      )}
    </group>
  )
}

function DroneScene() {
  return (
    <>
      <ambientLight intensity={0.4} />
      <pointLight position={[3, 5, 5]} intensity={1.5} color="#00f0c8" />
      <pointLight position={[-3, -2, 3]} intensity={0.8} color="#6c63ff" />
      <DroneModel />
    </>
  )
}

// ── Stat pill ──────────────────────────────────────────────────────────────
function StatPill({
  label,
  delay,
  style,
}: {
  label: string
  delay: number
  style: React.CSSProperties
}) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ delay, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      style={{
        position: 'absolute',
        padding: '0.4rem 0.85rem',
        background: 'rgba(13, 13, 20, 0.85)',
        backdropFilter: 'blur(12px)',
        border: '1px solid rgba(0, 240, 200, 0.2)',
        borderRadius: '100px',
        color: '#00f0c8',
        fontFamily: 'Space Grotesk, sans-serif',
        fontSize: '0.72rem',
        fontWeight: 500,
        letterSpacing: '0.04em',
        whiteSpace: 'nowrap',
        boxShadow: '0 0 12px rgba(0,240,200,0.15)',
        ...style,
      }}
    >
      {label}
    </motion.div>
  )
}

// ── Hero Section ──────────────────────────────────────────────────────────
export default function HeroSection() {
  const containerRef = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ['start start', 'end start'],
  })

  const opacity = useTransform(scrollYProgress, [0, 0.6], [1, 0])
  const y = useTransform(scrollYProgress, [0, 0.6], [0, -60])

  return (
    <section
      ref={containerRef}
      id="hero"
      style={{
        position: 'relative',
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
        paddingTop: '64px',
      }}
    >
      <motion.div
        style={{ opacity, y }}
        className="w-full"
      >
        <div
          className="hero-layout"
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            maxWidth: '1200px',
            margin: '0 auto',
            padding: '0 2rem',
            gap: '3rem',
          }}
        >
          {/* ── Left: Text content ── */}
          <div style={{ flex: '1', maxWidth: '560px' }}>
            {/* Eyebrow */}
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.3, duration: 0.6 }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.6rem',
                marginBottom: '1.5rem',
              }}
            >
              <span
                style={{
                  display: 'inline-block',
                  width: '28px',
                  height: '2px',
                  background: '#00f0c8',
                  borderRadius: '1px',
                }}
              />
              <span
                style={{
                  fontFamily: 'Space Grotesk, sans-serif',
                  fontSize: '0.72rem',
                  fontWeight: 500,
                  letterSpacing: '0.18em',
                  color: '#00f0c8',
                  textTransform: 'uppercase',
                }}
              >
                Solar Asset Intelligence
              </span>
            </motion.div>

            {/* Headline */}
            <motion.h1
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4, duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
              style={{
                fontFamily: 'Syne, sans-serif',
                fontWeight: 800,
                fontSize: 'clamp(2.4rem, 5vw, 4rem)',
                lineHeight: 1.05,
                color: '#e8e8f0',
                marginBottom: '1.2rem',
              }}
            >
              Autonomous
              <br />
              <span
                style={{
                  background: 'linear-gradient(135deg, #00f0c8 0%, #6c63ff 100%)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  backgroundClip: 'text',
                }}
              >
                inspection.
              </span>
              <br />
              Zero blind spots.
            </motion.h1>

            {/* Subline */}
            <motion.p
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.55, duration: 0.7 }}
              style={{
                fontFamily: 'Space Grotesk, sans-serif',
                fontSize: '1.05rem',
                fontWeight: 400,
                color: '#6b6b80',
                lineHeight: 1.65,
                marginBottom: '2.5rem',
                maxWidth: '440px',
              }}
            >
              AI-powered drone systems for solar asset management.
              Thermal + RGB fusion with YOLO11m detection across 11 fault classes.
            </motion.p>

            {/* CTAs */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.7, duration: 0.6 }}
              style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}
            >
              <CTAButton href="#technology" primary>
                See the technology
              </CTAButton>
              <CTAButton href="#contact" primary={false}>
                Request a demo
              </CTAButton>
            </motion.div>

            {/* Stats row */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 1, duration: 0.8 }}
              style={{
                marginTop: '2.5rem',
                paddingTop: '2rem',
                borderTop: '1px solid rgba(255,255,255,0.06)',
                display: 'flex',
                gap: '2.5rem',
              }}
            >
              {[
                { value: '99.7%', label: 'Detection accuracy' },
                { value: '10x', label: 'Faster than manual' },
                { value: '50MW+', label: 'Capacity inspected' },
              ].map((s) => (
                <div key={s.label}>
                  <p style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '1.6rem', color: '#e8e8f0', lineHeight: 1 }}>
                    {s.value}
                  </p>
                  <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.65rem', letterSpacing: '0.15em', textTransform: 'uppercase', color: '#6b6b80', marginTop: '0.35rem' }}>
                    {s.label}
                  </p>
                </div>
              ))}
            </motion.div>
          </div>

          {/* ── Right: 3D Drone ── */}
          <div
            className="hero-drone"
            style={{
              flex: '1',
              maxWidth: '540px',
              height: '500px',
              position: 'relative',
            }}
          >
            {/* Drone canvas */}
            <Canvas
              camera={{ position: [0, 1, 5], fov: 45 }}
              style={{ width: '100%', height: '100%' }}
              gl={{ antialias: true, alpha: true }}
            >
              <DroneScene />
            </Canvas>

            {/* Stat pills */}
            <StatPill
              label="0.734 mAP50"
              delay={0.9}
              style={{ top: '15%', left: '-5%' }}
            />
            <StatPill
              label="11-class detection"
              delay={1.05}
              style={{ top: '45%', right: '-8%' }}
            />
            <StatPill
              label="Thermal + RGB fusion"
              delay={1.2}
              style={{ bottom: '18%', left: '-3%' }}
            />

            {/* Glow circle behind drone */}
            <div
              style={{
                position: 'absolute',
                top: '50%',
                left: '50%',
                transform: 'translate(-50%, -50%)',
                width: '300px',
                height: '300px',
                background: 'radial-gradient(circle, rgba(0,240,200,0.06) 0%, transparent 70%)',
                pointerEvents: 'none',
                zIndex: -1,
              }}
            />
          </div>
        </div>

        {/* Scroll indicator */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.5 }}
          style={{
            position: 'absolute',
            bottom: '2rem',
            left: '50%',
            transform: 'translateX(-50%)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <span
            style={{
              fontFamily: 'Space Grotesk, sans-serif',
              fontSize: '0.65rem',
              letterSpacing: '0.15em',
              color: '#6b6b80',
              textTransform: 'uppercase',
            }}
          >
            Scroll
          </span>
          <motion.div
            animate={{ y: [0, 6, 0] }}
            transition={{ repeat: Infinity, duration: 1.5, ease: 'easeInOut' }}
            style={{
              width: '1px',
              height: '24px',
              background: 'linear-gradient(to bottom, #00f0c8, transparent)',
            }}
          />
        </motion.div>
      </motion.div>
    </section>
  )
}

function CTAButton({
  href,
  primary,
  children,
}: {
  href: string
  primary: boolean
  children: React.ReactNode
}) {
  return (
    <motion.a
      href={href}
      whileHover={{ scale: 1.03 }}
      whileTap={{ scale: 0.97 }}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.5rem',
        padding: '0.75rem 1.6rem',
        borderRadius: '4px',
        fontFamily: 'Space Grotesk, sans-serif',
        fontWeight: 600,
        fontSize: '0.88rem',
        letterSpacing: '0.04em',
        textDecoration: 'none',
        transition: 'all 0.2s ease',
        ...(primary
          ? {
              background: 'linear-gradient(135deg, #00f0c8 0%, #6c63ff 100%)',
              color: '#050508',
              boxShadow: '0 0 24px rgba(0,240,200,0.25)',
            }
          : {
              background: 'transparent',
              border: '1px solid rgba(232,232,240,0.15)',
              color: '#e8e8f0',
            }),
      }}
    >
      {children}
      {primary && (
        <span style={{ fontSize: '1rem', marginLeft: '2px' }}>→</span>
      )}
    </motion.a>
  )
}
