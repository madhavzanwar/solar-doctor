'use client'

import { motion } from 'framer-motion'

const WORDS = ['Autonomous', 'inspection', 'drones', 'built', 'for', 'reliable', 'industrial', 'decisions.']

const C = {
  teal: '#00f0c8',
  purple: '#6c63ff',
  text: '#e8e8f0',
  muted: '#8888a0',
}

export default function HeroOverlay() {
  return (
    <div style={{
      position: 'absolute',
      inset: 0,
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      padding: '0 6vw',
      maxWidth: '780px',
      // Gradient mask so text is readable against 3D scene
      background: 'linear-gradient(90deg, rgba(2,2,8,0.75) 0%, rgba(2,2,8,0.3) 60%, transparent 100%)',
    }}>
      {/* Eyebrow */}
      <motion.div
        initial={{ opacity: 0, x: -24 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 0.3, duration: 0.7 }}
        style={{ display: 'flex', alignItems: 'center', gap: '0.7rem', marginBottom: '1.5rem' }}
      >
        <span style={{ width: '28px', height: '1px', background: C.teal }} />
        <span style={{
          fontFamily: 'Space Grotesk, sans-serif',
          fontSize: '0.7rem',
          fontWeight: 500,
          letterSpacing: '0.28em',
          textTransform: 'uppercase' as const,
          color: C.teal,
        }}>
          Autonomous Inspection Platform
        </span>
      </motion.div>

      {/* Headline — word by word */}
      <h1 style={{
        fontFamily: 'Syne, sans-serif',
        fontWeight: 800,
        fontSize: 'clamp(2.6rem, 6.5vw, 5.2rem)',
        lineHeight: 0.92,
        color: C.text,
        marginBottom: '1.5rem',
        letterSpacing: '-0.03em',
      }}>
        {WORDS.map((word, i) => (
          <span key={i} style={{ display: 'inline-block', overflow: 'hidden', marginRight: '0.3em' }}>
            <motion.span
              style={{ display: 'inline-block' }}
              initial={{ y: '110%', opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ duration: 0.65, delay: 0.5 + i * 0.07, ease: [0.22, 1, 0.36, 1] }}
            >
              {/* Highlight "autonomous" */}
              {i === 0 ? (
                <span style={{
                  background: `linear-gradient(135deg, ${C.teal} 0%, ${C.purple} 100%)`,
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  backgroundClip: 'text',
                }}>
                  {word}
                </span>
              ) : word}
            </motion.span>
          </span>
        ))}
      </h1>

      {/* Subtitle */}
      <motion.p
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 1.2, duration: 0.7 }}
        style={{
          fontFamily: 'Space Grotesk, sans-serif',
          fontSize: '1rem',
          color: C.muted,
          lineHeight: 1.75,
          marginBottom: '2.5rem',
          maxWidth: '420px',
        }}
      >
        AI-enabled drone systems for precise solar asset inspection.
        Thermal + RGB fusion · 11-class fault detection · Real-time reports.
      </motion.p>

      {/* CTAs */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 1.5, duration: 0.6 }}
        style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}
      >
        <motion.a
          href="#technology"
          whileHover={{ scale: 1.04 }}
          whileTap={{ scale: 0.97 }}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '0.8rem 1.8rem',
            background: `linear-gradient(135deg, ${C.teal}, ${C.purple})`,
            color: '#030308',
            fontFamily: 'Space Grotesk, sans-serif',
            fontWeight: 700,
            fontSize: '0.85rem',
            letterSpacing: '0.04em',
            textDecoration: 'none',
            borderRadius: '3px',
            boxShadow: `0 0 28px rgba(0,240,200,0.35)`,
          }}
        >
          See Technology →
        </motion.a>
        <motion.a
          href="#contact"
          whileHover={{ scale: 1.04 }}
          whileTap={{ scale: 0.97 }}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '0.8rem 1.8rem',
            background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(232,232,240,0.15)',
            color: C.text,
            fontFamily: 'Space Grotesk, sans-serif',
            fontWeight: 600,
            fontSize: '0.85rem',
            letterSpacing: '0.04em',
            textDecoration: 'none',
            borderRadius: '3px',
            backdropFilter: 'blur(8px)',
          }}
        >
          Request Demo
        </motion.a>
      </motion.div>

      {/* Stats row */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 2, duration: 0.8 }}
        style={{
          marginTop: '3rem',
          paddingTop: '2rem',
          borderTop: '1px solid rgba(255,255,255,0.07)',
          display: 'flex',
          gap: '2.5rem',
        }}
      >
        {[
          { v: '99.7%', l: 'Accuracy' },
          { v: '10x', l: 'Faster' },
          { v: '50MW+', l: 'Inspected' },
        ].map(s => (
          <div key={s.l}>
            <p style={{ fontFamily: 'Syne, sans-serif', fontWeight: 800, fontSize: '1.7rem', color: C.text, lineHeight: 1 }}>
              {s.v}
            </p>
            <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.62rem', letterSpacing: '0.15em', textTransform: 'uppercase' as const, color: C.muted, marginTop: '0.3rem' }}>
              {s.l}
            </p>
          </div>
        ))}
      </motion.div>

      {/* Telemetry badge */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 2.2 }}
        style={{
          position: 'absolute',
          bottom: '2.5rem',
          left: '6vw',
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
        }}
      >
        <span style={{
          display: 'inline-block', width: '6px', height: '6px',
          borderRadius: '50%', background: C.teal,
          animation: 'pulse-glow 2s ease-in-out infinite',
        }} />
        <span style={{
          fontFamily: 'Space Grotesk, monospace',
          fontSize: '0.62rem',
          letterSpacing: '0.14em',
          textTransform: 'uppercase' as const,
          color: 'rgba(0,240,200,0.5)',
        }}>
          ALT 35M · 9.4M/S · 18°55′N 72°49′E
        </span>
      </motion.div>
    </div>
  )
}
