'use client'

import { useRef, useEffect, useState } from 'react'
import { motion, useInView } from 'framer-motion'
import { scrollStore } from '../../scrollStore'

const C = {
  teal:   '#00f0c8',
  red:    '#ff1a00',
  orange: '#ff6b35',
  text:   '#e8e8f0',
  muted:  '#6b6b80',
  bg:     'rgba(2,2,8,0.88)',
}

const DETECTION_STATS = [
  { label: 'mAP50',        value: '0.734', unit: ''   },
  { label: 'Precision',    value: '88.3',  unit: '%'  },
  { label: 'Recall',       value: '79.1',  unit: '%'  },
  { label: 'Classes',      value: '11',    unit: ''   },
]

const SENSOR_MODES = [
  { id: 'thermal', label: 'THERMAL IR', active: true,  color: C.orange },
  { id: 'rgb',     label: 'RGB VISUAL', active: true,  color: '#60a5fa' },
  { id: 'fusion',  label: 'AI FUSION',  active: true,  color: C.teal   },
]

export default function DetectionOverlay() {
  const [detectionCount, setDetectionCount] = useState(0)
  const [confidence, setConfidence]         = useState(0)
  const [detectionP, setDetectionP]         = useState(0)
  const ref    = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: false, margin: '-20%' })
  const rafRef = useRef<number>(0)

  useEffect(() => {
    if (!inView) {
      cancelAnimationFrame(rafRef.current)
      return
    }

    const update = () => {
      const t = scrollStore.progress
      const p = Math.min(Math.max((t - 2 / 6) / (1 / 6), 0), 1)
      setDetectionP(p)
      setDetectionCount(Math.floor(p * 59))
      setConfidence(Math.floor(p * 100 * 0.734))
      rafRef.current = requestAnimationFrame(update)
    }
    rafRef.current = requestAnimationFrame(update)
    return () => cancelAnimationFrame(rafRef.current)
  }, [inView])

  return (
    <div
      ref={ref}
      style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}
    >
      {/* ── Left: headline ── */}
      <div style={{
        position: 'absolute',
        top: '50%',
        left: '6vw',
        transform: 'translateY(-50%)',
        maxWidth: '500px',
        padding: '2rem 3rem 2rem 0',
        background: 'linear-gradient(90deg, rgba(2,2,8,0.85) 0%, transparent 100%)',
      }}>
        <motion.p
          initial={{ opacity: 0, x: -20 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: false }}
          style={{
            fontFamily: 'Space Grotesk, sans-serif',
            fontSize: '0.7rem',
            letterSpacing: '0.25em',
            textTransform: 'uppercase' as const,
            color: '#60a5fa',
            opacity: 0.8,
            marginBottom: '1rem',
          }}
        >
          03 — Dual-Sensor Fusion
        </motion.p>

        <motion.h2
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: false }}
          transition={{ delay: 0.1, duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          style={{
            fontFamily: 'Syne, sans-serif',
            fontWeight: 800,
            fontSize: 'clamp(2rem, 4.5vw, 3.8rem)',
            color: C.text,
            lineHeight: 1.05,
            letterSpacing: '-0.02em',
            marginBottom: '1.2rem',
          }}
        >
          Thermal + RGB.<br />
          <span style={{
            background: `linear-gradient(135deg, #60a5fa 0%, ${C.teal} 100%)`,
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
            textShadow: '0 0 40px rgba(0,240,200,0.3)',
          }}>
            Cross-validated.
          </span>
        </motion.h2>

        <motion.p
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: false }}
          transition={{ delay: 0.2 }}
          style={{
            fontFamily: 'Space Grotesk, sans-serif',
            fontSize: '1rem',
            color: '#8888a0',
            lineHeight: 1.75,
            maxWidth: '420px',
            marginBottom: '2rem',
          }}
        >
          YOLO11m trained on 20,000 thermal frames, fused with RGB context.
          Every anomaly confirmed across both sensors before flagging.
        </motion.p>

        {/* Sensor mode indicators */}
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: false }}
          transition={{ delay: 0.3 }}
          style={{ display: 'flex', gap: '0.75rem' }}
        >
          {SENSOR_MODES.map(s => (
            <div key={s.id} style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.35rem',
              padding: '0.3rem 0.7rem',
              border: `1px solid ${s.color}33`,
              background: `${s.color}0a`,
            }}>
              <span style={{
                width: '5px', height: '5px',
                borderRadius: '50%',
                background: s.active ? s.color : '#2a2a3a',
                boxShadow: s.active ? `0 0 5px ${s.color}` : 'none',
                animation: s.active ? 'pulse-glow 1.2s ease-in-out infinite' : 'none',
              }} />
              <span style={{
                fontFamily: 'Space Grotesk, sans-serif',
                fontSize: '0.55rem',
                letterSpacing: '0.12em',
                color: s.active ? s.color : '#2a2a3a',
              }}>
                {s.label}
              </span>
            </div>
          ))}
        </motion.div>
      </div>

      {/* ── Right: live detection panel ── */}
      <motion.div
        initial={{ opacity: 0, x: 30 }}
        whileInView={{ opacity: 1, x: 0 }}
        viewport={{ once: false }}
        transition={{ delay: 0.2, duration: 0.6 }}
        style={{
          position: 'absolute',
          top: '50%',
          right: '6vw',
          transform: 'translateY(-50%)',
          background: C.bg,
          border: '1px solid rgba(96,165,250,0.12)',
          backdropFilter: 'blur(20px)',
          padding: '1.5rem',
          minWidth: '280px',
          pointerEvents: 'auto',
        }}
      >
        {/* Header */}
        <div style={{
          display: 'flex',
          alignItems: 'flex-end',
          justifyContent: 'space-between',
          marginBottom: '1rem',
          paddingBottom: '1rem',
          borderBottom: '1px solid rgba(255,255,255,0.06)',
        }}>
          <div>
            <p style={{
              fontFamily: 'Space Grotesk, sans-serif',
              fontSize: '0.58rem',
              letterSpacing: '0.2em',
              textTransform: 'uppercase' as const,
              color: C.muted,
              marginBottom: '0.2rem',
            }}>
              Detections confirmed
            </p>
            <p style={{
              fontFamily: 'Syne, sans-serif',
              fontWeight: 800,
              fontSize: '3rem',
              color: C.red,
              lineHeight: 1,
              textShadow: `0 0 20px rgba(255,26,0,0.4)`,
            }}>
              {detectionCount.toString().padStart(2, '0')}
            </p>
          </div>
          <div style={{ textAlign: 'right' as const }}>
            <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.6rem', color: 'rgba(96,165,250,0.5)', letterSpacing: '0.1em' }}>
              AXALON·AI
            </p>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', justifyContent: 'flex-end', marginTop: '0.25rem' }}>
              <span style={{ width: '5px', height: '5px', borderRadius: '50%', background: '#60a5fa', animation: 'pulse-glow 1s ease-in-out infinite' }} />
              <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.55rem', color: '#60a5fa', letterSpacing: '0.08em' }}>ACTIVE</span>
            </div>
          </div>
        </div>

        {/* Model stats */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '0.6rem',
          marginBottom: '1rem',
        }}>
          {DETECTION_STATS.map(stat => (
            <div key={stat.label} style={{
              padding: '0.6rem',
              background: 'rgba(255,255,255,0.03)',
              border: '1px solid rgba(255,255,255,0.05)',
            }}>
              <p style={{
                fontFamily: 'Space Grotesk, sans-serif',
                fontSize: '0.52rem',
                color: C.muted,
                letterSpacing: '0.1em',
                textTransform: 'uppercase' as const,
                marginBottom: '0.25rem',
              }}>
                {stat.label}
              </p>
              <p style={{
                fontFamily: 'Syne, sans-serif',
                fontWeight: 700,
                fontSize: '1.1rem',
                color: C.teal,
              }}>
                {stat.value}{stat.unit}
              </p>
            </div>
          ))}
        </div>

        {/* Confidence bar */}
        <div>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            marginBottom: '0.4rem',
          }}>
            <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.62rem', letterSpacing: '0.12em', textTransform: 'uppercase' as const, color: C.muted }}>
              Avg. confidence
            </span>
            <span style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '0.78rem', color: '#60a5fa' }}>
              {confidence}%
            </span>
          </div>
          <div style={{
            height: '2px',
            background: 'rgba(255,255,255,0.06)',
            borderRadius: '1px',
            overflow: 'hidden',
          }}>
            <div style={{
              height: '100%',
              width: `${confidence}%`,
              background: `linear-gradient(90deg, ${C.teal}, #60a5fa)`,
              transition: 'width 0.1s linear',
              boxShadow: `0 0 8px rgba(96,165,250,0.6)`,
            }} />
          </div>
        </div>

        {/* Footer */}
        <div style={{
          marginTop: '1rem',
          paddingTop: '0.75rem',
          borderTop: '1px solid rgba(255,255,255,0.05)',
          fontFamily: 'Space Grotesk, sans-serif',
          fontSize: '0.55rem',
          color: 'rgba(96,165,250,0.3)',
          letterSpacing: '0.08em',
        }}>
          YOLO11m · RGB+IR FUSION · 640×640px · 30Hz
        </div>
      </motion.div>
    </div>
  )
}
