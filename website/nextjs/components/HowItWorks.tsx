'use client'

import { useRef } from 'react'
import { motion, useInView } from 'framer-motion'
import { MapPin, Cpu, FileText } from 'lucide-react'

const C = {
  teal: '#00f0c8',
  bg: '#0d0d14',
  text: '#e8e8f0',
  muted: '#6b6b80',
}

const steps = [
  {
    num: '01',
    icon: MapPin,
    title: 'Plan the mission',
    desc: 'Define inspection boundaries and parameters. The system auto-generates optimized flight paths with full terrain awareness and no-fly zone avoidance.',
  },
  {
    num: '02',
    icon: Cpu,
    title: 'Autonomous capture',
    desc: 'Deploy the drone for fully autonomous data collection. Thermal IR and RGB sensors capture synchronized multi-layer datasets at 35m altitude.',
  },
  {
    num: '03',
    icon: FileText,
    title: 'AI-powered report',
    desc: 'YOLO11m processes data in real-time. Receive automated inspection reports with detected anomalies, severity classification, and GPS-tagged findings.',
  },
]

export default function HowItWorks() {
  const headerRef = useRef<HTMLDivElement>(null)
  const headerInView = useInView(headerRef, { once: true, margin: '-80px' })

  return (
    <section
      id="mission"
      style={{
        position: 'relative',
        padding: '7rem 0',
        background: C.bg,
        overflow: 'hidden',
      }}
    >
      {/* Top center separator line */}
      <div style={{
        position: 'absolute',
        top: 0,
        left: '50%',
        transform: 'translateX(-50%)',
        width: '600px',
        height: '1px',
        background: `linear-gradient(90deg, transparent, rgba(0,240,200,0.2), transparent)`,
      }} />

      <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '0 2rem' }}>

        {/* Header */}
        <motion.div
          ref={headerRef}
          initial={{ opacity: 0, y: 24 }}
          animate={headerInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
          style={{ marginBottom: '5rem' }}
        >
          <p style={{
            fontFamily: 'Space Grotesk, sans-serif',
            fontSize: '0.68rem',
            fontWeight: 500,
            letterSpacing: '0.28em',
            textTransform: 'uppercase' as const,
            color: C.teal,
            marginBottom: '0.75rem',
          }}>
            02 — How it works
          </p>
          <h2 style={{
            fontFamily: 'Syne, sans-serif',
            fontWeight: 800,
            fontSize: 'clamp(1.8rem, 3.5vw, 2.8rem)',
            color: C.text,
            lineHeight: 1.1,
          }}>
            From deployment to decisions<br /> in minutes
          </h2>
        </motion.div>

        {/* Steps grid */}
        <div className="steps-grid" style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          borderTop: '1px solid rgba(255,255,255,0.05)',
        }}>
          {steps.map((step, i) => (
            <StepCard key={step.num} step={step} index={i} total={steps.length} />
          ))}
        </div>
      </div>
    </section>
  )
}

function StepCard({
  step,
  index,
  total,
}: {
  step: typeof steps[0]
  index: number
  total: number
}) {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '-60px' })
  const Icon = step.icon

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 40 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.6, delay: index * 0.14, ease: [0.22, 1, 0.36, 1] }}
      style={{
        position: 'relative',
        borderRight: index < total - 1 ? '1px solid rgba(255,255,255,0.05)' : 'none',
        padding: '2.5rem',
      }}
    >
      {/* Animated top accent line */}
      <motion.div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          height: '1px',
          background: C.teal,
        }}
        initial={{ width: 0 }}
        animate={inView ? { width: '40%' } : { width: 0 }}
        transition={{ duration: 0.6, delay: 0.3 + index * 0.14 }}
      />

      {/* Number + icon */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '2rem' }}>
        <span style={{
          fontFamily: 'Syne, sans-serif',
          fontWeight: 800,
          fontSize: '3rem',
          color: 'rgba(0,240,200,0.12)',
          lineHeight: 1,
          userSelect: 'none',
        }}>
          {step.num}
        </span>
        <div style={{ width: '1px', height: '40px', background: 'rgba(255,255,255,0.07)' }} />
        <div style={{
          width: '32px',
          height: '32px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'rgba(0,240,200,0.08)',
        }}>
          <Icon size={15} color={C.teal} />
        </div>
      </div>

      <h3 style={{
        fontFamily: 'Syne, sans-serif',
        fontWeight: 700,
        fontSize: '1.05rem',
        color: C.text,
        marginBottom: '0.6rem',
      }}>
        {step.title}
      </h3>
      <p style={{
        fontFamily: 'Space Grotesk, sans-serif',
        fontSize: '0.875rem',
        lineHeight: 1.65,
        color: C.muted,
      }}>
        {step.desc}
      </p>
    </motion.div>
  )
}
