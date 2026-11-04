'use client'

import { useRef, useEffect, useState } from 'react'
import { motion, useInView } from 'framer-motion'
import { scrollStore } from '../../scrollStore'

const C = {
  teal:   '#00f0c8',
  purple: '#6c63ff',
  text:   '#e8e8f0',
  muted:  '#6b6b80',
  bg:     'rgba(2,2,8,0.88)',
}

const DRONE_IDS = ['AXL-01', 'AXL-02', 'AXL-03']
const ROLES     = ['LEAD', 'WING-L', 'WING-R']

type DroneStatus = {
  id: string
  role: string
  alt: number
  speed: number
  battery: number
  panels: number
}

export default function FleetOverlay() {
  const [fleetP,     setFleetP]     = useState(0)
  const [panelsTotal, setPanelsTotal] = useState(0)
  const [coverage,   setCoverage]   = useState(0)
  const [drones, setDrones] = useState<DroneStatus[]>(DRONE_IDS.map((id, i) => ({
    id, role: ROLES[i], alt: 0, speed: 0, battery: 100, panels: 0,
  })))

  const ref    = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: false, margin: '-20%' })
  const rafRef = useRef<number>(0)

  useEffect(() => {
    if (!inView) { cancelAnimationFrame(rafRef.current); return }

    const update = () => {
      const t = scrollStore.progress
      const p = Math.min(Math.max((t - 3 / 6) / (1 / 6), 0), 1)
      setFleetP(p)
      const total = Math.floor(p * 396)
      setPanelsTotal(total)
      setCoverage(Math.floor(p * 100))

      setDrones([
        { id: 'AXL-01', role: 'LEAD',   alt: 35 + Math.sin(Date.now() / 900) * 1,  speed: 9.2 + Math.sin(Date.now() / 1200) * 0.3,  battery: Math.max(0, 100 - p * 22), panels: Math.floor(p * 148) },
        { id: 'AXL-02', role: 'WING-L', alt: 36 + Math.sin(Date.now() / 800) * 1,  speed: 9.0 + Math.sin(Date.now() / 1100) * 0.3,  battery: Math.max(0, 100 - p * 19), panels: Math.floor(p * 124) },
        { id: 'AXL-03', role: 'WING-R', alt: 34 + Math.sin(Date.now() / 700) * 1,  speed: 9.4 + Math.sin(Date.now() / 1300) * 0.3,  battery: Math.max(0, 100 - p * 21), panels: Math.floor(p * 124) },
      ])

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
            color: C.teal,
            opacity: 0.8,
            marginBottom: '1rem',
          }}
        >
          04 — Full-Site Coverage
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
          One flight.<br />
          <span style={{
            background: `linear-gradient(135deg, ${C.teal} 0%, ${C.purple} 100%)`,
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
            textShadow: '0 0 40px rgba(0,240,200,0.3)',
          }}>
            Every panel.
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
          Three autonomous drones sweep the entire site in formation.
          Full coverage in a single coordinated flight — no manual targeting.
        </motion.p>

        {/* Coverage bar */}
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: false }}
          transition={{ delay: 0.3 }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
            <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.62rem', letterSpacing: '0.12em', textTransform: 'uppercase' as const, color: C.muted }}>
              Site coverage
            </span>
            <span style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '0.78rem', color: C.teal }}>
              {coverage}%
            </span>
          </div>
          <div style={{ height: '2px', background: 'rgba(255,255,255,0.06)', borderRadius: '1px', overflow: 'hidden' }}>
            <div style={{
              height: '100%',
              width: `${coverage}%`,
              background: `linear-gradient(90deg, ${C.teal}, ${C.purple})`,
              transition: 'width 0.1s linear',
              boxShadow: `0 0 8px rgba(0,240,200,0.6)`,
            }} />
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '0.6rem' }}>
            <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.6rem', color: C.muted }}>
              {panelsTotal} / 396 panels scanned
            </span>
            <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.6rem', color: 'rgba(0,240,200,0.5)' }}>
              ~{Math.max(0, Math.ceil((1 - fleetP) * 4.2)).toFixed(1)} min remaining
            </span>
          </div>
        </motion.div>
      </div>

      {/* ── Right: fleet telemetry panel ── */}
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
          minWidth: '290px',
          pointerEvents: 'auto',
        }}
      >
        {/* Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '1rem',
          paddingBottom: '0.75rem',
          borderBottom: '1px solid rgba(255,255,255,0.06)',
        }}>
          <div>
            <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.58rem', letterSpacing: '0.2em', textTransform: 'uppercase' as const, color: C.muted, marginBottom: '0.15rem' }}>
              Fleet status
            </p>
            <p style={{ fontFamily: 'Syne, sans-serif', fontWeight: 800, fontSize: '1.4rem', color: C.teal }}>
              3 ACTIVE
            </p>
          </div>
          <div style={{ textAlign: 'right' as const }}>
            <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.6rem', color: 'rgba(0,240,200,0.4)', letterSpacing: '0.1em' }}>
              AXALON·FLEET
            </p>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', justifyContent: 'flex-end', marginTop: '0.25rem' }}>
              <span style={{ width: '5px', height: '5px', borderRadius: '50%', background: C.teal, animation: 'pulse-glow 0.8s ease-in-out infinite' }} />
              <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.55rem', color: C.teal, letterSpacing: '0.08em' }}>AUTONOMOUS</span>
            </div>
          </div>
        </div>

        {/* Per-drone rows */}
        <div style={{ display: 'flex', flexDirection: 'column' as const, gap: '0.7rem' }}>
          {drones.map((d, i) => (
            <div key={d.id} style={{
              padding: '0.65rem 0.75rem',
              background: 'rgba(255,255,255,0.025)',
              border: '1px solid rgba(0,240,200,0.08)',
            }}>
              {/* Drone header row */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                  <span style={{
                    width: '6px', height: '6px',
                    borderRadius: '50%',
                    background: C.teal,
                    boxShadow: `0 0 6px ${C.teal}`,
                    animation: 'pulse-glow 0.9s ease-in-out infinite',
                    animationDelay: `${i * 0.3}s`,
                  }} />
                  <span style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '0.75rem', color: C.text }}>
                    {d.id}
                  </span>
                  <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.52rem', color: 'rgba(0,240,200,0.45)', letterSpacing: '0.08em' }}>
                    {d.role}
                  </span>
                </div>
                <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.58rem', color: C.teal }}>
                  {d.panels}p
                </span>
              </div>

              {/* Telemetry mini-grid */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.3rem' }}>
                {[
                  { k: 'ALT', v: `${d.alt.toFixed(0)}m` },
                  { k: 'SPD', v: `${d.speed.toFixed(1)}m/s` },
                  { k: 'BAT', v: `${d.battery.toFixed(0)}%` },
                ].map(({ k, v }) => (
                  <div key={k} style={{ textAlign: 'center' as const }}>
                    <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.48rem', color: C.muted, letterSpacing: '0.1em', marginBottom: '0.1rem' }}>{k}</p>
                    <p style={{ fontFamily: 'Syne, sans-serif', fontWeight: 600, fontSize: '0.68rem', color: k === 'BAT' && d.battery < 30 ? '#ff6b35' : 'rgba(0,240,200,0.8)' }}>{v}</p>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div style={{
          marginTop: '0.75rem',
          paddingTop: '0.6rem',
          borderTop: '1px solid rgba(255,255,255,0.05)',
          fontFamily: 'Space Grotesk, sans-serif',
          fontSize: '0.55rem',
          color: 'rgba(0,240,200,0.3)',
          letterSpacing: '0.08em',
        }}>
          RTK·GPS · MESH·COMMS · AUTO-RTH
        </div>
      </motion.div>
    </div>
  )
}
