'use client'

import { useRef } from 'react'
import { motion, useInView } from 'framer-motion'

const stats = [
  { display: '99.7%', label: 'Defect detection rate' },
  { display: '3x',    label: 'Faster than manual' },
  { display: '50MW+', label: 'Solar capacity inspected' },
  { display: '<2hr',  label: 'From flight to report' },
]

function StatItem({ stat, index }: { stat: typeof stats[0]; index: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '-60px' })

  return (
    <motion.div
      ref={ref}
      style={{ textAlign: 'center', padding: '0 2rem' }}
      initial={{ opacity: 0, y: 20 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.5, delay: index * 0.1 }}
    >
      <p style={{
        fontFamily: 'Syne, sans-serif',
        fontWeight: 700,
        fontSize: 'clamp(1.8rem, 3vw, 2.5rem)',
        color: '#e8e8f0',
        marginBottom: '0.4rem',
      }}>
        {stat.display}
      </p>
      <p style={{
        fontFamily: 'Space Grotesk, sans-serif',
        fontSize: '0.65rem',
        letterSpacing: '0.18em',
        textTransform: 'uppercase' as const,
        color: '#6b6b80',
      }}>
        {stat.label}
      </p>
    </motion.div>
  )
}

export default function TrustStrip() {
  return (
    <section style={{
      padding: '4rem 0',
      borderTop: '1px solid rgba(255,255,255,0.05)',
      borderBottom: '1px solid rgba(255,255,255,0.05)',
      background: 'rgba(13,13,20,0.6)',
      backdropFilter: 'blur(4px)',
    }}>
      <div className="stats-grid" style={{
        maxWidth: '1200px',
        margin: '0 auto',
        padding: '0 2rem',
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: '0',
      }}>
        {stats.map((s, i) => (
          <div key={s.label} style={{
            borderRight: i < 3 ? '1px solid rgba(255,255,255,0.05)' : 'none',
          }}>
            <StatItem stat={s} index={i} />
          </div>
        ))}
      </div>
    </section>
  )
}
