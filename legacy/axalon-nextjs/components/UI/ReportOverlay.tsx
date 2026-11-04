'use client'

import { useRef, useEffect, useState } from 'react'
import { motion, useInView } from 'framer-motion'
import { scrollStore } from '../../scrollStore'

const C = {
  teal:   '#00f0c8',
  blue:   '#60a5fa',
  red:    '#ff1a00',
  orange: '#ff6b35',
  text:   '#e8e8f0',
  muted:  '#6b6b80',
  bg:     'rgba(2,2,8,0.88)',
}

const FAULT_SUMMARY = [
  { severity: 'CRITICAL', count: 12, color: C.red,    pct: 18  },
  { severity: 'HIGH',     count: 19, color: C.orange, pct: 28  },
  { severity: 'MEDIUM',   count: 28, color: '#ffc800', pct: 42 },
  { severity: 'LOW',      count: 8,  color: C.teal,   pct: 12  },
]

const REPORT_SECTIONS = [
  'Panel-level GPS localisation',
  'Automated severity classification',
  'Maintenance priority queue',
  'PDF + GeoJSON + Excel export',
]

export default function ReportOverlay() {
  const [reportP,       setReportP]       = useState(0)
  const [totalFaults,   setTotalFaults]   = useState(0)
  const [powerLoss,     setPowerLoss]     = useState(0)
  const [revenue,       setRevenue]       = useState(0)

  const ref    = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: false, margin: '-20%' })
  const rafRef = useRef<number>(0)

  useEffect(() => {
    if (!inView) { cancelAnimationFrame(rafRef.current); return }

    const update = () => {
      const t = scrollStore.progress
      const p = Math.min(Math.max((t - 4 / 6) / (1 / 6), 0), 1)
      setReportP(p)
      setTotalFaults(Math.floor(p * 67))
      setPowerLoss(parseFloat((p * 4.3).toFixed(1)))
      setRevenue(Math.floor(p * 18200))
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
        maxWidth: '420px',
        padding: '2rem 3rem 2rem 0',
        background: 'linear-gradient(90deg, rgba(2,2,8,0.88) 0%, transparent 100%)',
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
          05 — Instant Reports
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
          AI-generated<br />
          <span style={{
            background: `linear-gradient(135deg, ${C.teal} 0%, ${C.blue} 100%)`,
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
            textShadow: '0 0 40px rgba(0,240,200,0.3)',
          }}>
            fault maps.
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
            marginBottom: '1.8rem',
          }}
        >
          Every flight ends with a complete inspection report —
          panel-level fault maps with GPS coordinates, severity rankings,
          and maintenance priorities. Ready in minutes.
        </motion.p>

        {/* Report feature checklist — teal pills */}
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: false }}
          transition={{ delay: 0.3 }}
          style={{ display: 'flex', flexDirection: 'column' as const, gap: '0.45rem' }}
        >
          {REPORT_SECTIONS.map((item, i) => {
            const active = reportP > i * 0.22
            return (
              <motion.div
                key={i}
                animate={{ opacity: active ? 1 : 0.22, x: active ? 0 : -8 }}
                transition={{ duration: 0.4 }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.6rem',
                }}
              >
                <span style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '18px', height: '18px',
                  borderRadius: '50%',
                  background: active ? 'rgba(0,240,200,0.15)' : 'rgba(42,42,58,0.4)',
                  border: `1px solid ${active ? C.teal : '#2a2a3a'}`,
                  flexShrink: 0,
                  transition: 'all 0.4s',
                  boxShadow: active ? '0 0 8px rgba(0,240,200,0.25)' : 'none',
                }}>
                  <span style={{ fontSize: '8px', color: active ? C.teal : '#2a2a3a' }}>✓</span>
                </span>
                <span style={{
                  fontFamily: 'Space Grotesk, sans-serif',
                  fontSize: '0.8rem',
                  color: active ? C.text : C.muted,
                  transition: 'color 0.4s',
                }}>
                  {item}
                </span>
              </motion.div>
            )
          })}
        </motion.div>
      </div>

      {/* ── Right: report summary card ── */}
      <motion.div
        initial={{ opacity: 0, x: 30 }}
        whileInView={{ opacity: 1, x: 0 }}
        viewport={{ once: false }}
        transition={{ delay: 0.25, duration: 0.6 }}
        style={{
          position: 'absolute',
          top: '50%',
          right: '6vw',
          transform: 'translateY(-50%)',
          background: C.bg,
          border: '1px solid rgba(0,240,200,0.12)',
          backdropFilter: 'blur(20px)',
          padding: '1.5rem',
          minWidth: '285px',
          pointerEvents: 'auto',
        }}
      >
        {/* Header */}
        <div style={{
          marginBottom: '1rem',
          paddingBottom: '0.8rem',
          borderBottom: '1px solid rgba(255,255,255,0.06)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.3rem' }}>
            <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.58rem', letterSpacing: '0.2em', textTransform: 'uppercase' as const, color: C.muted }}>
              Report summary
            </p>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
              <span style={{
                width: '5px', height: '5px',
                borderRadius: '50%',
                background: C.teal,
                boxShadow: `0 0 6px ${C.teal}`,
                animation: 'pulse-glow 0.8s ease-in-out infinite',
              }} />
              <span style={{
                fontFamily: 'Space Grotesk, sans-serif',
                fontSize: '0.52rem',
                color: C.teal,
                letterSpacing: '0.12em',
                animation: 'pulse-glow 0.8s ease-in-out infinite',
              }}>
                LIVE
              </span>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', marginBottom: '0.6rem' }}>
            <p style={{
              fontFamily: 'Syne, sans-serif',
              fontWeight: 800,
              fontSize: '2.8rem',
              color: C.red,
              lineHeight: 1,
              textShadow: `0 0 24px rgba(255,26,0,0.5), 0 0 48px rgba(255,26,0,0.2)`,
              letterSpacing: '-0.02em',
            }}>
              {totalFaults.toString().padStart(2, '0')}
            </p>
            <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.7rem', color: C.muted, lineHeight: 1.4 }}>
              anomalies<br />detected
            </p>
          </div>
          {/* Analysis progress bar */}
          <div style={{ marginBottom: '0.2rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.3rem' }}>
              <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.52rem', color: C.muted, letterSpacing: '0.1em' }}>
                ANALYSIS PROGRESS
              </span>
              <span style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '0.6rem', color: C.teal }}>
                {Math.round(reportP * 100)}%
              </span>
            </div>
            <div style={{ height: '2px', background: 'rgba(255,255,255,0.05)', borderRadius: '1px', overflow: 'hidden' }}>
              <div style={{
                height: '100%',
                width: `${reportP * 100}%`,
                background: `linear-gradient(90deg, ${C.teal}, ${C.blue})`,
                transition: 'width 0.1s linear',
                boxShadow: `0 0 8px rgba(0,240,200,0.5)`,
              }} />
            </div>
          </div>
        </div>

        {/* Severity breakdown */}
        <div style={{ display: 'flex', flexDirection: 'column' as const, gap: '0.5rem', marginBottom: '1rem' }}>
          {FAULT_SUMMARY.map(({ severity, count, color, pct }) => {
            const displayCount = Math.round((reportP * count))
            return (
              <div key={severity}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.2rem' }}>
                  <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.6rem', color, letterSpacing: '0.08em' }}>
                    {severity}
                  </span>
                  <span style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '0.68rem', color }}>
                    {displayCount}
                  </span>
                </div>
                <div style={{ height: '2px', background: 'rgba(255,255,255,0.05)', borderRadius: '1px', overflow: 'hidden' }}>
                  <div style={{
                    height: '100%',
                    width: `${reportP * pct}%`,
                    background: color,
                    boxShadow: `0 0 5px ${color}80`,
                    transition: 'width 0.15s linear',
                  }} />
                </div>
              </div>
            )
          })}
        </div>

        {/* Financial impact */}
        <div style={{
          padding: '0.75rem',
          background: 'rgba(255,26,0,0.05)',
          border: '1px solid rgba(255,26,0,0.12)',
          marginBottom: '0.75rem',
        }}>
          <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.56rem', color: C.muted, letterSpacing: '0.1em', textTransform: 'uppercase' as const, marginBottom: '0.4rem' }}>
            Estimated impact
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
            <div>
              <p style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '1.1rem', color: C.orange }}>{powerLoss}%</p>
              <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.52rem', color: C.muted }}>Power loss</p>
            </div>
            <div>
              <p style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '1.1rem', color: C.orange }}>${revenue.toLocaleString()}</p>
              <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.52rem', color: C.muted }}>Annual loss</p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div style={{
          paddingTop: '0.6rem',
          borderTop: '1px solid rgba(255,255,255,0.05)',
          fontFamily: 'Space Grotesk, sans-serif',
          fontSize: '0.55rem',
          color: 'rgba(0,240,200,0.3)',
          letterSpacing: '0.08em',
        }}>
          PDF · GEOJSON · EXCEL · API
        </div>
      </motion.div>
    </div>
  )
}
