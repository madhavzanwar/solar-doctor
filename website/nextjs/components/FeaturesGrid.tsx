'use client'

import { useRef } from 'react'
import { motion, useInView } from 'framer-motion'
import { Zap, Scan, Shield, Cpu, Layers } from 'lucide-react'

const features = [
  {
    icon: Zap,
    title: 'Autonomous Flight',
    desc: 'Fully autonomous mission planning and execution with intelligent path optimization and obstacle avoidance across complex terrain.',
    large: true,
  },
  {
    icon: Scan,
    title: 'Thermal Detection',
    desc: 'YOLO11m model trained on 20,000 thermal IR images. Detects 11 fault classes from hot-spot-high to vegetation shading.',
  },
  {
    icon: Shield,
    title: 'Telemetry Security',
    desc: 'End-to-end encrypted communication with AES-256 data protection for all mission and inspection data.',
  },
  {
    icon: Cpu,
    title: 'Onboard AI',
    desc: 'Edge-compute inference for real-time anomaly detection, severity classification (CRITICAL / HIGH / MEDIUM / LOW), and automated reporting.',
    large: true,
  },
  {
    icon: Layers,
    title: 'Modular Payload',
    desc: 'Hot-swappable sensor bays supporting thermal IR, RGB, LiDAR, and multispectral payloads — one platform, every use case.',
  },
]

const C = {
  teal: '#00f0c8',
  purple: '#6c63ff',
  bg: '#050508',
  surface: '#0d0d14',
  text: '#e8e8f0',
  muted: '#6b6b80',
}

function FeatureCard({
  feature,
  index,
  large,
}: {
  feature: typeof features[0]
  index: number
  large?: boolean
}) {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '-60px' })
  const Icon = feature.icon

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 28 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.55, delay: index * 0.08, ease: [0.22, 1, 0.36, 1] }}
      style={{
        gridColumn: large ? 'span 2' : 'span 1',
      // className applied below
        position: 'relative',
        background: C.bg,
        padding: '2.5rem',
        overflow: 'hidden',
        cursor: 'default',
      }}
      whileHover={{ backgroundColor: '#0a0a10' }}
      className={`feature-card group${large ? ' col-span-2' : ''}`}
    >
      {/* Hover top-edge accent */}
      <motion.div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          height: '1px',
          background: C.teal,
          width: 0,
        }}
        whileHover={{ width: '100%' }}
        transition={{ duration: 0.4 }}
      />

      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        {/* Icon */}
        <div style={{
          width: '40px',
          height: '40px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'rgba(0,240,200,0.08)',
          marginBottom: '2rem',
        }}>
          <Icon size={18} color={C.teal} />
        </div>

        <h3 style={{
          fontFamily: 'Syne, sans-serif',
          fontWeight: 700,
          fontSize: '1.05rem',
          color: C.text,
          marginBottom: '0.6rem',
        }}>
          {feature.title}
        </h3>

        <p style={{
          fontFamily: 'Space Grotesk, sans-serif',
          fontSize: '0.875rem',
          lineHeight: 1.65,
          color: C.muted,
        }}>
          {feature.desc}
        </p>

        {large && (
          <div style={{ marginTop: 'auto', paddingTop: '2rem' }}>
            <div style={{
              height: '1px',
              background: `linear-gradient(90deg, rgba(0,240,200,0.3), rgba(108,99,255,0.2), transparent)`,
            }} />
          </div>
        )}
      </div>
    </motion.div>
  )
}

export default function FeaturesGrid() {
  const headerRef = useRef<HTMLDivElement>(null)
  const headerInView = useInView(headerRef, { once: true, margin: '-80px' })

  return (
    <section
      id="technology"
      style={{
        position: 'relative',
        padding: '7rem 0',
        background: C.bg,
      }}
    >
      <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '0 2rem' }}>

        {/* Header */}
        <motion.div
          ref={headerRef}
          initial={{ opacity: 0 }}
          animate={headerInView ? { opacity: 1 } : {}}
          transition={{ duration: 0.6 }}
          style={{
            marginBottom: '4rem',
            display: 'flex',
            alignItems: 'flex-end',
            justifyContent: 'space-between',
            gap: '2rem',
            paddingBottom: '2rem',
            borderBottom: '1px solid rgba(255,255,255,0.06)',
          }}
        >
          <div>
            <motion.p
              initial={{ opacity: 0, y: 12 }}
              animate={headerInView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.5 }}
              style={{
                fontFamily: 'Space Grotesk, sans-serif',
                fontSize: '0.68rem',
                fontWeight: 500,
                letterSpacing: '0.28em',
                textTransform: 'uppercase' as const,
                color: C.teal,
                marginBottom: '0.75rem',
              }}
            >
              01 — Capabilities
            </motion.p>
            <motion.h2
              initial={{ opacity: 0, y: 16 }}
              animate={headerInView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.6, delay: 0.1 }}
              style={{
                fontFamily: 'Syne, sans-serif',
                fontWeight: 800,
                fontSize: 'clamp(1.8rem, 3.5vw, 2.8rem)',
                color: C.text,
                lineHeight: 1.1,
              }}
            >
              Engineering precision<br /> at every layer
            </motion.h2>
          </div>
          <motion.p
            initial={{ opacity: 0 }}
            animate={headerInView ? { opacity: 1 } : {}}
            transition={{ duration: 0.6, delay: 0.2 }}
            style={{
              fontFamily: 'Space Grotesk, sans-serif',
              fontSize: '0.875rem',
              color: C.muted,
              maxWidth: '280px',
              textAlign: 'right' as const,
              lineHeight: 1.65,
              display: 'none',
            }}
            className="md:block"
          >
            Five integrated modules, each precision-engineered for demanding solar inspection environments.
          </motion.p>
        </motion.div>

        {/* Bento grid — gap: 1px acts as border via bg on the wrapper */}
        <div className="bento-grid" style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: '1px',
          background: 'rgba(255,255,255,0.04)',
        }}>
          {/* Row 1: large (2col) + small (1col) */}
          {features.slice(0, 3).map((f, i) => (
            <FeatureCard key={f.title} feature={f} index={i} large={f.large} />
          ))}
          {/* Row 2: small (1col) + large (2col) — reorder with CSS order */}
          <FeatureCard feature={features[4]} index={4} large={false} />
          <FeatureCard feature={features[3]} index={3} large={true} />
        </div>
      </div>
    </section>
  )
}
