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

const FAULT_CLASSES = [
  { name: 'Hot-spot High',    severity: 'CRITICAL', color: '#ff0000' },
  { name: 'Bypass Diode',     severity: 'CRITICAL', color: '#ff2200' },
  { name: 'String Fault',     severity: 'CRITICAL', color: '#ff1a00' },
  { name: 'Offline Module',   severity: 'HIGH',     color: '#ff6b35' },
  { name: 'Short Circuit',    severity: 'HIGH',     color: '#ff8c00' },
  { name: 'Hot-spot Low',     severity: 'HIGH',     color: '#ff9900' },
  { name: 'Cell Damage',      severity: 'MEDIUM',   color: '#ffc800' },
  { name: 'Soiling',          severity: 'LOW',      color: C.teal },
]

const SEVERITY_BG: Record<string, string> = {
  CRITICAL: 'rgba(255,26,0,0.12)',
  HIGH:     'rgba(255,107,53,0.12)',
  MEDIUM:   'rgba(255,200,0,0.10)',
  LOW:      'rgba(0,240,200,0.08)',
}

export default function ThermalOverlay() {
  const [faultCount, setFaultCount]       = useState(0)
  const [visibleFaults, setVisibleFaults] = useState<typeof FAULT_CLASSES>([])
  const [scanPct, setScanPct]             = useState(0)
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
      const thermalP = Math.min(Math.max((t - 1 / 6) / (1 / 6), 0), 1)

      setFaultCount(Math.floor(thermalP * 47))
      setScanPct(Math.floor(thermalP * 100))
      setVisibleFaults(FAULT_CLASSES.slice(0, Math.floor(thermalP * FAULT_CLASSES.length)))

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
        maxWidth: '480px',
        padding: '2rem 3rem 2rem 0',
        background: 'linear-gradient(90deg, rgba(2,2,8,0.82) 0%, transparent 100%)',
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
            color: C.teal,
            opacity: 0.8,
            marginBottom: '1rem',
          }}
        >
          02 — Thermal Intelligence
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
          Thermal<br />
          <span style={{
            background: `linear-gradient(135deg, ${C.red} 0%, ${C.orange} 100%)`,
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
            textShadow: '0 0 40px rgba(0,240,200,0.3)',
          }}>
            Intelligence
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
          11-class fault detection at 0.734 mAP50 accuracy.
          Trained on 20,000 thermal IR images captured across real solar farms.
        </motion.p>

        {/* Scan progress bar */}
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: false }}
          transition={{ delay: 0.3 }}
        >
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            marginBottom: '0.4rem',
          }}>
            <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.62rem', letterSpacing: '0.12em', textTransform: 'uppercase' as const, color: C.muted }}>
              Scan coverage
            </span>
            <span style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '0.78rem', color: C.teal }}>
              {scanPct}%
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
              width: `${scanPct}%`,
              background: `linear-gradient(90deg, ${C.teal}, ${C.orange})`,
              transition: 'width 0.1s linear',
              boxShadow: `0 0 8px rgba(0,240,200,0.6)`,
            }} />
          </div>
        </motion.div>
      </div>

      {/* ── Right: live fault readout ── */}
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
          border: '1px solid rgba(0,240,200,0.12)',
          backdropFilter: 'blur(20px)',
          padding: '1.5rem',
          minWidth: '270px',
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
              Anomalies detected
            </p>
            <p style={{
              fontFamily: 'Syne, sans-serif',
              fontWeight: 800,
              fontSize: '3rem',
              color: C.red,
              lineHeight: 1,
              textShadow: `0 0 20px rgba(255,26,0,0.5)`,
            }}>
              {faultCount.toString().padStart(2, '0')}
            </p>
          </div>
          <div style={{ textAlign: 'right' as const }}>
            <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.6rem', color: 'rgba(0,240,200,0.4)', letterSpacing: '0.1em' }}>
              AXALON·SCAN
            </p>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', justifyContent: 'flex-end', marginTop: '0.25rem' }}>
              <span style={{ width: '5px', height: '5px', borderRadius: '50%', background: C.teal, animation: 'pulse-glow 1s ease-in-out infinite' }} />
              <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.55rem', color: C.teal, letterSpacing: '0.08em' }}>LIVE</span>
            </div>
          </div>
        </div>

        {/* Fault list */}
        <div style={{ display: 'flex', flexDirection: 'column' as const, gap: '0.45rem' }}>
          {FAULT_CLASSES.map((f, i) => {
            const visible = visibleFaults.includes(f)
            return (
              <motion.div
                key={f.name}
                initial={{ opacity: 0, x: 12 }}
                animate={visible ? { opacity: 1, x: 0 } : { opacity: 0.18, x: 0 }}
                transition={{ duration: 0.3 }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '0.75rem',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span style={{
                    width: '5px', height: '5px',
                    borderRadius: '50%',
                    background: visible ? f.color : '#2a2a3a',
                    boxShadow: visible ? `0 0 5px ${f.color}` : 'none',
                    flexShrink: 0,
                  }} />
                  <span style={{
                    fontFamily: 'Space Grotesk, sans-serif',
                    fontSize: '0.72rem',
                    color: visible ? '#8888a0' : '#2a2a3a',
                  }}>
                    {f.name}
                  </span>
                </div>
                <span style={{
                  fontFamily: 'Space Grotesk, sans-serif',
                  fontSize: '0.52rem',
                  letterSpacing: '0.08em',
                  padding: '0.15rem 0.45rem',
                  background: visible ? SEVERITY_BG[f.severity] : 'transparent',
                  color: visible ? f.color : '#2a2a3a',
                  border: visible ? `1px solid ${f.color}28` : '1px solid transparent',
                }}>
                  {f.severity}
                </span>
              </motion.div>
            )
          })}
        </div>

        {/* Footer telemetry */}
        <div style={{
          marginTop: '1rem',
          paddingTop: '0.75rem',
          borderTop: '1px solid rgba(255,255,255,0.05)',
          fontFamily: 'Space Grotesk, sans-serif',
          fontSize: '0.55rem',
          color: 'rgba(0,240,200,0.3)',
          letterSpacing: '0.08em',
        }}>
          THERMAL·IR · 320×256px · 30Hz · YOLO11m
        </div>
      </motion.div>
    </div>
  )
}
