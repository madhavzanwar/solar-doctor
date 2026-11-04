'use client'

import { useRef, useEffect, useState } from 'react'
import { motion, useInView, AnimatePresence } from 'framer-motion'
import { scrollStore } from '../../scrollStore'

// ─── Design tokens ───────────────────────────────────────────────────────────
const C = {
  teal:   '#00f0c8',
  purple: '#6c63ff',
  red:    '#ff1a00',
  orange: '#ff6b35',
  blue:   '#60a5fa',
  text:   '#e8e8f0',
  muted:  '#6b6b80',
  bg:     'rgba(2,2,8,0.88)',
}

// ─── Shared section wrapper ───────────────────────────────────────────────────
function Section({
  id,
  children,
}: {
  id: string
  children: React.ReactNode
}) {
  return (
    <section
      id={id}
      data-section={id}
      style={{
        minHeight: '100vh',
        padding: '6rem 3rem 6rem 5rem',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        position: 'relative',
        borderTop: '1px solid rgba(255,255,255,0.04)',
      }}
    >
      {children}
    </section>
  )
}

// ─── Eyebrow label ────────────────────────────────────────────────────────────
function Label({ text, color = C.teal }: { text: string; color?: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -16 }}
      whileInView={{ opacity: 1, x: 0 }}
      viewport={{ once: false }}
      transition={{ duration: 0.5 }}
      style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '1.4rem' }}
    >
      <span style={{ width: '22px', height: '1px', background: color, flexShrink: 0 }} />
      <span style={{
        fontFamily: 'Space Grotesk, sans-serif',
        fontSize: '0.65rem',
        fontWeight: 500,
        letterSpacing: '0.28em',
        textTransform: 'uppercase' as const,
        color,
      }}>
        {text}
      </span>
    </motion.div>
  )
}

// ─── Thin progress bar ────────────────────────────────────────────────────────
function ProgressBar({
  pct,
  label,
  color = C.teal,
  right,
}: {
  pct: number
  label: string
  color?: string
  right?: React.ReactNode
}) {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
        <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.6rem', letterSpacing: '0.12em', textTransform: 'uppercase' as const, color: C.muted }}>
          {label}
        </span>
        {right}
      </div>
      <div style={{ height: '2px', background: 'rgba(255,255,255,0.06)', borderRadius: '1px', overflow: 'hidden' }}>
        <div style={{
          height: '100%',
          width: `${pct}%`,
          background: `linear-gradient(90deg, ${color}, ${C.purple})`,
          transition: 'width 0.1s linear',
          boxShadow: `0 0 8px ${color}99`,
        }} />
      </div>
    </div>
  )
}

// ─── Dark card wrapper ────────────────────────────────────────────────────────
function Card({ children, borderColor = 'rgba(0,240,200,0.12)' }: { children: React.ReactNode; borderColor?: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: false }}
      transition={{ delay: 0.25, duration: 0.55 }}
      style={{
        marginTop: '2rem',
        background: C.bg,
        border: `1px solid ${borderColor}`,
        backdropFilter: 'blur(20px)',
        padding: '1.25rem',
      }}
    >
      {children}
    </motion.div>
  )
}

// ─── SECTION 1: HERO ─────────────────────────────────────────────────────────
const HERO_WORDS = ['Autonomous', 'inspection', 'drones', 'built', 'for', 'reliable', 'industrial', 'decisions.']

function HeroSection() {
  return (
    <Section id="hero">
      <Label text="01 — Autonomous Inspection Platform" />

      <h1 style={{
        fontFamily: 'Syne, sans-serif',
        fontWeight: 800,
        fontSize: 'clamp(2.2rem, 4vw, 3.8rem)',
        lineHeight: 0.95,
        color: C.text,
        marginBottom: '1.5rem',
        letterSpacing: '-0.03em',
      }}>
        {HERO_WORDS.map((word, i) => (
          <span key={i} style={{ display: 'inline-block', overflow: 'hidden', marginRight: '0.28em' }}>
            <motion.span
              style={{ display: 'inline-block' }}
              initial={{ y: '110%', opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ duration: 0.6, delay: 0.3 + i * 0.06, ease: [0.22, 1, 0.36, 1] }}
            >
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

      <motion.p
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 1.0, duration: 0.6 }}
        style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.95rem', color: C.muted, lineHeight: 1.75, marginBottom: '2rem', maxWidth: '380px' }}
      >
        AI-enabled drone systems for precise solar asset inspection.
        Thermal + RGB fusion · 11-class fault detection · Real-time reports.
      </motion.p>

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 1.3, duration: 0.5 }}
        style={{ display: 'flex', gap: '0.8rem', flexWrap: 'wrap' as const }}
      >
        <a href="#thermal" style={{
          display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
          padding: '0.7rem 1.5rem',
          background: `linear-gradient(135deg, ${C.teal}, ${C.purple})`,
          color: '#030308', fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700,
          fontSize: '0.82rem', letterSpacing: '0.04em', textDecoration: 'none', borderRadius: '3px',
          boxShadow: `0 0 24px rgba(0,240,200,0.3)`,
        }}>
          See Technology →
        </a>
        <a href="#contact" style={{
          display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
          padding: '0.7rem 1.5rem',
          background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(232,232,240,0.14)',
          color: C.text, fontFamily: 'Space Grotesk, sans-serif', fontWeight: 600,
          fontSize: '0.82rem', letterSpacing: '0.04em', textDecoration: 'none', borderRadius: '3px',
        }}>
          Request Demo
        </a>
      </motion.div>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.8, duration: 0.8 }}
        style={{ marginTop: '2.5rem', paddingTop: '1.8rem', borderTop: '1px solid rgba(255,255,255,0.06)', display: 'flex', gap: '2rem' }}
      >
        {[{ v: '99.7%', l: 'Accuracy' }, { v: '10x', l: 'Faster' }, { v: '50MW+', l: 'Inspected' }].map(s => (
          <div key={s.l}>
            <p style={{ fontFamily: 'Syne, sans-serif', fontWeight: 800, fontSize: '1.6rem', color: C.text, lineHeight: 1 }}>{s.v}</p>
            <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.58rem', letterSpacing: '0.14em', textTransform: 'uppercase' as const, color: C.muted, marginTop: '0.25rem' }}>{s.l}</p>
          </div>
        ))}
      </motion.div>

      {/* Live telemetry badge */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 2.2 }}
        style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', marginTop: '1.5rem' }}
      >
        <span style={{ display: 'inline-block', width: '6px', height: '6px', borderRadius: '50%', background: C.teal, animation: 'pulse-glow 2s ease-in-out infinite' }} />
        <span style={{ fontFamily: 'Space Grotesk, monospace', fontSize: '0.58rem', letterSpacing: '0.14em', textTransform: 'uppercase' as const, color: 'rgba(0,240,200,0.45)' }}>
          ALT 35M · 9.4M/S · 18°55′N 72°49′E
        </span>
      </motion.div>
    </Section>
  )
}

// ─── SECTION 2: THERMAL ──────────────────────────────────────────────────────
const FAULT_CLASSES = [
  { name: 'Hot-spot High',  severity: 'CRITICAL', color: '#ff0000' },
  { name: 'Bypass Diode',   severity: 'CRITICAL', color: '#ff2200' },
  { name: 'String Fault',   severity: 'CRITICAL', color: '#ff1a00' },
  { name: 'Offline Module', severity: 'HIGH',     color: '#ff6b35' },
  { name: 'Short Circuit',  severity: 'HIGH',     color: '#ff8c00' },
  { name: 'Hot-spot Low',   severity: 'HIGH',     color: '#ff9900' },
  { name: 'Cell Damage',    severity: 'MEDIUM',   color: '#ffc800' },
  { name: 'Soiling',        severity: 'LOW',      color: C.teal   },
]
const SEVERITY_BG: Record<string, string> = {
  CRITICAL: 'rgba(255,26,0,0.12)', HIGH: 'rgba(255,107,53,0.12)',
  MEDIUM: 'rgba(255,200,0,0.10)', LOW: 'rgba(0,240,200,0.08)',
}

function ThermalSection() {
  const [faultCount, setFaultCount]       = useState(0)
  const [visibleFaults, setVisibleFaults] = useState<typeof FAULT_CLASSES>([])
  const [scanPct, setScanPct]             = useState(0)
  const ref    = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: false, margin: '-20%' })
  const rafRef = useRef<number>(0)

  useEffect(() => {
    if (!inView) { cancelAnimationFrame(rafRef.current); return }
    const update = () => {
      const p = Math.min(Math.max((scrollStore.progress - 1 / 6) / (1 / 6), 0), 1)
      setFaultCount(Math.floor(p * 47))
      setScanPct(Math.floor(p * 100))
      setVisibleFaults(FAULT_CLASSES.slice(0, Math.floor(p * FAULT_CLASSES.length)))
      rafRef.current = requestAnimationFrame(update)
    }
    rafRef.current = requestAnimationFrame(update)
    return () => cancelAnimationFrame(rafRef.current)
  }, [inView])

  return (
    <Section id="thermal">
      <div ref={ref}>
        <Label text="02 — Thermal Intelligence" color={C.orange} />

        <motion.h2
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: false }}
          transition={{ delay: 0.1, duration: 0.65, ease: [0.22, 1, 0.36, 1] }}
          style={{ fontFamily: 'Syne, sans-serif', fontWeight: 800, fontSize: 'clamp(2rem, 3.5vw, 3.2rem)', color: C.text, lineHeight: 1.05, letterSpacing: '-0.02em', marginBottom: '1rem' }}
        >
          Thermal{' '}
          <span style={{ background: `linear-gradient(135deg, ${C.red} 0%, ${C.orange} 100%)`, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>
            Intelligence.
          </span>
        </motion.h2>

        <motion.p
          initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: false }} transition={{ delay: 0.2 }}
          style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.95rem', color: C.muted, lineHeight: 1.75, maxWidth: '380px', marginBottom: '1.5rem' }}
        >
          11-class fault detection at 0.734 mAP50 accuracy.
          Trained on 20,000 thermal IR images captured across real solar farms.
        </motion.p>

        <motion.div initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: false }} transition={{ delay: 0.3 }}>
          <ProgressBar
            pct={scanPct}
            label="Scan coverage"
            color={C.teal}
            right={<span style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '0.78rem', color: C.teal }}>{scanPct}%</span>}
          />
        </motion.div>

        {/* Live fault card */}
        <Card>
          <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: '0.9rem', paddingBottom: '0.9rem', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
            <div>
              <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.55rem', letterSpacing: '0.2em', textTransform: 'uppercase' as const, color: C.muted, marginBottom: '0.15rem' }}>Anomalies detected</p>
              <p style={{ fontFamily: 'Syne, sans-serif', fontWeight: 800, fontSize: '2.6rem', color: C.red, lineHeight: 1, textShadow: `0 0 20px rgba(255,26,0,0.5)` }}>
                {faultCount.toString().padStart(2, '0')}
              </p>
            </div>
            <div style={{ textAlign: 'right' as const }}>
              <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.55rem', color: 'rgba(0,240,200,0.4)', letterSpacing: '0.1em' }}>AXALON·SCAN</p>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', justifyContent: 'flex-end', marginTop: '0.2rem' }}>
                <span style={{ width: '5px', height: '5px', borderRadius: '50%', background: C.teal, animation: 'pulse-glow 1s ease-in-out infinite' }} />
                <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.52rem', color: C.teal, letterSpacing: '0.08em' }}>LIVE</span>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column' as const, gap: '0.4rem' }}>
            {FAULT_CLASSES.map(f => {
              const active = visibleFaults.includes(f)
              return (
                <motion.div
                  key={f.name}
                  animate={{ opacity: active ? 1 : 0.18 }}
                  transition={{ duration: 0.3 }}
                  style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.6rem' }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                    <span style={{ width: '5px', height: '5px', borderRadius: '50%', background: active ? f.color : '#2a2a3a', boxShadow: active ? `0 0 5px ${f.color}` : 'none', flexShrink: 0 }} />
                    <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.7rem', color: active ? '#8888a0' : '#2a2a3a' }}>{f.name}</span>
                  </div>
                  <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.5rem', letterSpacing: '0.08em', padding: '0.12rem 0.4rem', background: active ? SEVERITY_BG[f.severity] : 'transparent', color: active ? f.color : '#2a2a3a', border: active ? `1px solid ${f.color}28` : '1px solid transparent' }}>
                    {f.severity}
                  </span>
                </motion.div>
              )
            })}
          </div>
          <div style={{ marginTop: '0.8rem', paddingTop: '0.6rem', borderTop: '1px solid rgba(255,255,255,0.04)', fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.52rem', color: 'rgba(0,240,200,0.28)', letterSpacing: '0.08em' }}>
            THERMAL·IR · 320×256px · 30Hz · YOLO11m
          </div>
        </Card>
      </div>
    </Section>
  )
}

// ─── SECTION 3: DETECTION ─────────────────────────────────────────────────────
const DETECTION_STATS = [
  { label: 'mAP50', value: '0.734', unit: '' },
  { label: 'Precision', value: '88.3', unit: '%' },
  { label: 'Recall', value: '79.1', unit: '%' },
  { label: 'Classes', value: '11', unit: '' },
]
const SENSOR_MODES = [
  { id: 'thermal', label: 'THERMAL IR', color: C.orange },
  { id: 'rgb',     label: 'RGB VISUAL', color: C.blue   },
  { id: 'fusion',  label: 'AI FUSION',  color: C.teal   },
]

function DetectionSection() {
  const [detectionCount, setDetectionCount] = useState(0)
  const [confidence, setConfidence]         = useState(0)
  const ref    = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: false, margin: '-20%' })
  const rafRef = useRef<number>(0)

  useEffect(() => {
    if (!inView) { cancelAnimationFrame(rafRef.current); return }
    const update = () => {
      const p = Math.min(Math.max((scrollStore.progress - 2 / 6) / (1 / 6), 0), 1)
      setDetectionCount(Math.floor(p * 59))
      setConfidence(Math.floor(p * 73.4))
      rafRef.current = requestAnimationFrame(update)
    }
    rafRef.current = requestAnimationFrame(update)
    return () => cancelAnimationFrame(rafRef.current)
  }, [inView])

  return (
    <Section id="detection">
      <div ref={ref}>
        <Label text="03 — Dual-Sensor Fusion" color={C.blue} />

        <motion.h2
          initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: false }}
          transition={{ delay: 0.1, duration: 0.65, ease: [0.22, 1, 0.36, 1] }}
          style={{ fontFamily: 'Syne, sans-serif', fontWeight: 800, fontSize: 'clamp(2rem, 3.5vw, 3.2rem)', color: C.text, lineHeight: 1.05, letterSpacing: '-0.02em', marginBottom: '1rem' }}
        >
          Thermal + RGB.{' '}
          <span style={{ background: `linear-gradient(135deg, ${C.blue} 0%, ${C.teal} 100%)`, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>
            Cross-validated.
          </span>
        </motion.h2>

        <motion.p
          initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: false }} transition={{ delay: 0.2 }}
          style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.95rem', color: C.muted, lineHeight: 1.75, maxWidth: '380px', marginBottom: '1.5rem' }}
        >
          YOLO11m trained on 20,000 thermal frames, fused with RGB context.
          Every anomaly confirmed across both sensors before flagging.
        </motion.p>

        <motion.div
          initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: false }} transition={{ delay: 0.3 }}
          style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap' as const }}
        >
          {SENSOR_MODES.map(s => (
            <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', padding: '0.28rem 0.65rem', border: `1px solid ${s.color}33`, background: `${s.color}0a` }}>
              <span style={{ width: '5px', height: '5px', borderRadius: '50%', background: s.color, boxShadow: `0 0 5px ${s.color}`, animation: 'pulse-glow 1.2s ease-in-out infinite' }} />
              <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.52rem', letterSpacing: '0.12em', color: s.color }}>{s.label}</span>
            </div>
          ))}
        </motion.div>

        <Card borderColor="rgba(96,165,250,0.12)">
          <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: '0.9rem', paddingBottom: '0.9rem', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
            <div>
              <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.55rem', letterSpacing: '0.2em', textTransform: 'uppercase' as const, color: C.muted, marginBottom: '0.15rem' }}>Detections confirmed</p>
              <p style={{ fontFamily: 'Syne, sans-serif', fontWeight: 800, fontSize: '2.6rem', color: C.red, lineHeight: 1, textShadow: `0 0 20px rgba(255,26,0,0.4)` }}>
                {detectionCount.toString().padStart(2, '0')}
              </p>
            </div>
            <div style={{ textAlign: 'right' as const }}>
              <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.55rem', color: 'rgba(96,165,250,0.45)', letterSpacing: '0.1em' }}>AXALON·AI</p>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', justifyContent: 'flex-end', marginTop: '0.2rem' }}>
                <span style={{ width: '5px', height: '5px', borderRadius: '50%', background: C.blue, animation: 'pulse-glow 1s ease-in-out infinite' }} />
                <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.52rem', color: C.blue, letterSpacing: '0.08em' }}>ACTIVE</span>
              </div>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginBottom: '0.9rem' }}>
            {DETECTION_STATS.map(stat => (
              <div key={stat.label} style={{ padding: '0.55rem', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)' }}>
                <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.5rem', color: C.muted, letterSpacing: '0.1em', textTransform: 'uppercase' as const, marginBottom: '0.2rem' }}>{stat.label}</p>
                <p style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '1.05rem', color: C.teal }}>{stat.value}{stat.unit}</p>
              </div>
            ))}
          </div>

          <ProgressBar
            pct={confidence}
            label="Avg. confidence"
            color={C.blue}
            right={<span style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '0.75rem', color: C.blue }}>{confidence}%</span>}
          />
          <div style={{ marginTop: '0.8rem', paddingTop: '0.6rem', borderTop: '1px solid rgba(255,255,255,0.04)', fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.52rem', color: 'rgba(96,165,250,0.28)', letterSpacing: '0.08em' }}>
            YOLO11m · RGB+IR FUSION · 640×640px · 30Hz
          </div>
        </Card>
      </div>
    </Section>
  )
}

// ─── SECTION 4: FLEET ─────────────────────────────────────────────────────────
function FleetSection() {
  const [coverage, setCoverage]     = useState(0)
  const [panelsTotal, setPanelsTotal] = useState(0)
  const [drones, setDrones] = useState([
    { id: 'AXL-01', role: 'LEAD',   alt: 35, speed: 9.2, battery: 100 },
    { id: 'AXL-02', role: 'WING-L', alt: 36, speed: 9.0, battery: 100 },
    { id: 'AXL-03', role: 'WING-R', alt: 34, speed: 9.4, battery: 100 },
  ])
  const ref    = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: false, margin: '-20%' })
  const rafRef = useRef<number>(0)

  useEffect(() => {
    if (!inView) { cancelAnimationFrame(rafRef.current); return }
    const update = () => {
      const p = Math.min(Math.max((scrollStore.progress - 3 / 6) / (1 / 6), 0), 1)
      setCoverage(Math.floor(p * 100))
      setPanelsTotal(Math.floor(p * 396))
      setDrones([
        { id: 'AXL-01', role: 'LEAD',   alt: +(35 + Math.sin(Date.now() / 900) * 0.8).toFixed(0),  speed: +(9.2 + Math.sin(Date.now() / 1200) * 0.2).toFixed(1), battery: Math.max(0, Math.floor(100 - p * 22)) },
        { id: 'AXL-02', role: 'WING-L', alt: +(36 + Math.sin(Date.now() / 800) * 0.8).toFixed(0),  speed: +(9.0 + Math.sin(Date.now() / 1100) * 0.2).toFixed(1), battery: Math.max(0, Math.floor(100 - p * 19)) },
        { id: 'AXL-03', role: 'WING-R', alt: +(34 + Math.sin(Date.now() / 700) * 0.8).toFixed(0),  speed: +(9.4 + Math.sin(Date.now() / 1300) * 0.2).toFixed(1), battery: Math.max(0, Math.floor(100 - p * 21)) },
      ])
      rafRef.current = requestAnimationFrame(update)
    }
    rafRef.current = requestAnimationFrame(update)
    return () => cancelAnimationFrame(rafRef.current)
  }, [inView])

  return (
    <Section id="fleet">
      <div ref={ref}>
        <Label text="04 — Full-Site Coverage" />

        <motion.h2
          initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: false }}
          transition={{ delay: 0.1, duration: 0.65, ease: [0.22, 1, 0.36, 1] }}
          style={{ fontFamily: 'Syne, sans-serif', fontWeight: 800, fontSize: 'clamp(2rem, 3.5vw, 3.2rem)', color: C.text, lineHeight: 1.05, letterSpacing: '-0.02em', marginBottom: '1rem' }}
        >
          One flight.{' '}
          <span style={{ background: `linear-gradient(135deg, ${C.teal} 0%, ${C.purple} 100%)`, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>
            Every panel.
          </span>
        </motion.h2>

        <motion.p
          initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: false }} transition={{ delay: 0.2 }}
          style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.95rem', color: C.muted, lineHeight: 1.75, maxWidth: '380px', marginBottom: '1.5rem' }}
        >
          Three autonomous drones sweep the entire site in formation.
          Full coverage in a single coordinated flight — no manual targeting.
        </motion.p>

        <motion.div initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: false }} transition={{ delay: 0.3 }}>
          <ProgressBar
            pct={coverage}
            label="Site coverage"
            right={<span style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '0.78rem', color: C.teal }}>{coverage}%</span>}
          />
          <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.58rem', color: C.muted, marginTop: '0.4rem' }}>
            {panelsTotal} / 396 panels scanned
          </p>
        </motion.div>

        <Card>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.9rem', paddingBottom: '0.7rem', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
            <div>
              <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.55rem', letterSpacing: '0.18em', textTransform: 'uppercase' as const, color: C.muted, marginBottom: '0.12rem' }}>Fleet status</p>
              <p style={{ fontFamily: 'Syne, sans-serif', fontWeight: 800, fontSize: '1.3rem', color: C.teal }}>3 ACTIVE</p>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
              <span style={{ width: '5px', height: '5px', borderRadius: '50%', background: C.teal, animation: 'pulse-glow 0.8s ease-in-out infinite' }} />
              <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.52rem', color: C.teal, letterSpacing: '0.08em' }}>AUTONOMOUS</span>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column' as const, gap: '0.6rem' }}>
            {drones.map((d, i) => (
              <div key={d.id} style={{ padding: '0.6rem 0.7rem', background: 'rgba(255,255,255,0.025)', border: '1px solid rgba(0,240,200,0.07)' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: C.teal, boxShadow: `0 0 6px ${C.teal}`, animation: 'pulse-glow 0.9s ease-in-out infinite', animationDelay: `${i * 0.3}s` }} />
                    <span style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '0.72rem', color: C.text }}>{d.id}</span>
                    <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.5rem', color: 'rgba(0,240,200,0.4)', letterSpacing: '0.08em' }}>{d.role}</span>
                  </div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.25rem' }}>
                  {[['ALT', `${d.alt}m`], ['SPD', `${d.speed}m/s`], ['BAT', `${d.battery}%`]].map(([k, v]) => (
                    <div key={k} style={{ textAlign: 'center' as const }}>
                      <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.46rem', color: C.muted, letterSpacing: '0.1em', marginBottom: '0.08rem' }}>{k}</p>
                      <p style={{ fontFamily: 'Syne, sans-serif', fontWeight: 600, fontSize: '0.65rem', color: k === 'BAT' && d.battery < 30 ? C.orange : 'rgba(0,240,200,0.8)' }}>{v}</p>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: '0.7rem', paddingTop: '0.5rem', borderTop: '1px solid rgba(255,255,255,0.04)', fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.52rem', color: 'rgba(0,240,200,0.28)', letterSpacing: '0.08em' }}>
            RTK·GPS · MESH·COMMS · AUTO-RTH
          </div>
        </Card>
      </div>
    </Section>
  )
}

// ─── SECTION 5: REPORT ────────────────────────────────────────────────────────
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

function ReportSection() {
  const [reportP, setReportP]         = useState(0)
  const [totalFaults, setTotalFaults] = useState(0)
  const [powerLoss, setPowerLoss]     = useState(0)
  const [revenue, setRevenue]         = useState(0)
  const ref    = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: false, margin: '-20%' })
  const rafRef = useRef<number>(0)

  useEffect(() => {
    if (!inView) { cancelAnimationFrame(rafRef.current); return }
    const update = () => {
      const p = Math.min(Math.max((scrollStore.progress - 4 / 6) / (1 / 6), 0), 1)
      setReportP(p)
      setTotalFaults(Math.floor(p * 62))
      setPowerLoss(parseFloat((p * 4.0).toFixed(1)))
      setRevenue(Math.floor(p * 1480000))
      rafRef.current = requestAnimationFrame(update)
    }
    rafRef.current = requestAnimationFrame(update)
    return () => cancelAnimationFrame(rafRef.current)
  }, [inView])

  return (
    <Section id="report">
      <div ref={ref}>
        <Label text="05 — Instant Reports" color={C.blue} />

        <motion.h2
          initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: false }}
          transition={{ delay: 0.1, duration: 0.65, ease: [0.22, 1, 0.36, 1] }}
          style={{ fontFamily: 'Syne, sans-serif', fontWeight: 800, fontSize: 'clamp(2rem, 3.5vw, 3.2rem)', color: C.text, lineHeight: 1.05, letterSpacing: '-0.02em', marginBottom: '1rem' }}
        >
          AI-generated{' '}
          <span style={{ background: `linear-gradient(135deg, ${C.teal} 0%, ${C.blue} 100%)`, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>
            fault maps.
          </span>
        </motion.h2>

        <motion.p
          initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: false }} transition={{ delay: 0.2 }}
          style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.95rem', color: C.muted, lineHeight: 1.75, maxWidth: '380px', marginBottom: '1.5rem' }}
        >
          Every flight ends with a complete inspection report — panel-level
          fault maps with GPS coordinates, severity rankings, and maintenance priorities.
        </motion.p>

        {/* Checklist */}
        <motion.div
          initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: false }} transition={{ delay: 0.3 }}
          style={{ display: 'flex', flexDirection: 'column' as const, gap: '0.4rem', marginBottom: '0.5rem' }}
        >
          {REPORT_SECTIONS.map((item, i) => {
            const active = reportP > i * 0.22
            return (
              <motion.div
                key={i}
                animate={{ opacity: active ? 1 : 0.22, x: active ? 0 : -6 }}
                transition={{ duration: 0.35 }}
                style={{ display: 'flex', alignItems: 'center', gap: '0.55rem' }}
              >
                <span style={{
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  width: '17px', height: '17px', borderRadius: '50%', flexShrink: 0,
                  background: active ? 'rgba(0,240,200,0.12)' : 'rgba(42,42,58,0.4)',
                  border: `1px solid ${active ? C.teal : '#2a2a3a'}`,
                  boxShadow: active ? '0 0 8px rgba(0,240,200,0.25)' : 'none',
                  transition: 'all 0.4s',
                }}>
                  <span style={{ fontSize: '7px', color: active ? C.teal : '#2a2a3a' }}>✓</span>
                </span>
                <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.78rem', color: active ? C.text : C.muted, transition: 'color 0.4s' }}>{item}</span>
              </motion.div>
            )
          })}
        </motion.div>

        <Card>
          <div style={{ marginBottom: '0.9rem', paddingBottom: '0.8rem', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.3rem' }}>
              <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.55rem', letterSpacing: '0.18em', textTransform: 'uppercase' as const, color: C.muted }}>Report summary</p>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                <span style={{ width: '5px', height: '5px', borderRadius: '50%', background: C.teal, animation: 'pulse-glow 0.8s ease-in-out infinite' }} />
                <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.5rem', color: C.teal, letterSpacing: '0.1em' }}>LIVE</span>
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.4rem' }}>
              <p style={{ fontFamily: 'Syne, sans-serif', fontWeight: 800, fontSize: '2.4rem', color: C.red, lineHeight: 1, textShadow: `0 0 24px rgba(255,26,0,0.5)` }}>
                {totalFaults.toString().padStart(2, '0')}
              </p>
              <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.68rem', color: C.muted, lineHeight: 1.4 }}>anomalies<br />detected</p>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column' as const, gap: '0.45rem', marginBottom: '0.9rem' }}>
            {FAULT_SUMMARY.map(({ severity, count, color, pct }) => (
              <div key={severity}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.18rem' }}>
                  <span style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.58rem', color, letterSpacing: '0.08em' }}>{severity}</span>
                  <span style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '0.65rem', color }}>{Math.round(reportP * count)}</span>
                </div>
                <div style={{ height: '2px', background: 'rgba(255,255,255,0.04)', borderRadius: '1px', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${reportP * pct}%`, background: color, boxShadow: `0 0 5px ${color}80`, transition: 'width 0.12s linear' }} />
                </div>
              </div>
            ))}
          </div>

          <div style={{ padding: '0.65rem', background: 'rgba(255,26,0,0.05)', border: '1px solid rgba(255,26,0,0.1)' }}>
            <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.52rem', color: C.muted, letterSpacing: '0.1em', textTransform: 'uppercase' as const, marginBottom: '0.35rem' }}>Estimated impact</p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
              <div>
                <p style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '1.05rem', color: C.orange }}>{powerLoss}%</p>
                <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.5rem', color: C.muted }}>Power loss</p>
              </div>
              <div>
                <p style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '1.05rem', color: C.orange }}>₹{revenue.toLocaleString('en-IN')}</p>
                <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.5rem', color: C.muted }}>Annual loss</p>
              </div>
            </div>
          </div>
        </Card>
      </div>
    </Section>
  )
}

// ─── SECTION 6: CTA ──────────────────────────────────────────────────────────
type FormState = 'idle' | 'sending' | 'sent'

const inputStyle: React.CSSProperties = {
  width: '100%',
  background: 'rgba(0,240,200,0.03)',
  border: '1px solid rgba(0,240,200,0.12)',
  borderRadius: '4px',
  padding: '0.65rem 0.9rem',
  fontFamily: 'Space Grotesk, sans-serif',
  fontSize: '0.82rem',
  color: C.text,
  outline: 'none',
  boxSizing: 'border-box',
  transition: 'border-color 0.2s',
}

function CTASection() {
  const [form, setForm] = useState({ name: '', email: '', company: '', message: '' })
  const [formState, setFormState] = useState<FormState>('idle')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.email || !form.name) return
    setFormState('sending')
    setTimeout(() => setFormState('sent'), 1400)
  }

  return (
    <Section id="contact">
      <Label text="06 — Ready to Inspect?" />

      <motion.h2
        initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: false }}
        transition={{ delay: 0.1, duration: 0.65, ease: [0.22, 1, 0.36, 1] }}
        style={{ fontFamily: 'Syne, sans-serif', fontWeight: 800, fontSize: 'clamp(2rem, 3.5vw, 3.2rem)', color: C.text, lineHeight: 1.05, letterSpacing: '-0.02em', marginBottom: '1rem' }}
      >
        Request a{' '}
        <span style={{ background: `linear-gradient(135deg, ${C.teal} 0%, ${C.purple} 100%)`, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>
          demo flight.
        </span>
      </motion.h2>

      <motion.p
        initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: false }} transition={{ delay: 0.2 }}
        style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.95rem', color: C.muted, lineHeight: 1.75, maxWidth: '380px', marginBottom: '2rem' }}
      >
        Let us inspect your solar farm — no commitment.
        Full fault report within 48 hours of the flight.
      </motion.p>

      <motion.div
        initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: false }} transition={{ delay: 0.25, duration: 0.6 }}
        style={{ background: C.bg, border: '1px solid rgba(0,240,200,0.14)', backdropFilter: 'blur(24px)', padding: '1.75rem', maxWidth: '400px' }}
      >
        <AnimatePresence mode="wait">
          {formState === 'sent' ? (
            <motion.div key="sent" initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ textAlign: 'center', padding: '1.5rem 0' }}>
              <div style={{ width: '44px', height: '44px', border: `2px solid ${C.teal}`, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 1rem' }}>
                <span style={{ color: C.teal, fontSize: '1.1rem' }}>✓</span>
              </div>
              <p style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '1.05rem', color: C.text, marginBottom: '0.4rem' }}>Request received.</p>
              <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.8rem', color: C.muted, lineHeight: 1.6 }}>We'll reach out within 24 hours to schedule your demo flight.</p>
            </motion.div>
          ) : (
            <motion.form key="form" exit={{ opacity: 0 }} onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '0.7rem' }}>
              <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.58rem', letterSpacing: '0.2em', textTransform: 'uppercase' as const, color: C.muted, marginBottom: '0.2rem' }}>Get in touch</p>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.7rem' }}>
                <input type="text" placeholder="Full name" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} required style={inputStyle} />
                <input type="email" placeholder="Work email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} required style={inputStyle} />
              </div>
              <input type="text" placeholder="Company / solar farm name" value={form.company} onChange={e => setForm(f => ({ ...f, company: e.target.value }))} style={inputStyle} />
              <textarea placeholder="Site size, location, or any questions..." value={form.message} onChange={e => setForm(f => ({ ...f, message: e.target.value }))} rows={3} style={{ ...inputStyle, resize: 'none', lineHeight: 1.6 }} />
              <button type="submit" disabled={formState === 'sending'} style={{
                padding: '0.72rem 1.5rem',
                background: formState === 'sending' ? 'rgba(0,240,200,0.1)' : `linear-gradient(135deg, ${C.teal} 0%, ${C.purple} 100%)`,
                border: formState === 'sending' ? `1px solid rgba(0,240,200,0.2)` : 'none',
                borderRadius: '4px',
                color: formState === 'sending' ? C.teal : '#020208',
                fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700, fontSize: '0.82rem', letterSpacing: '0.08em', textTransform: 'uppercase' as const,
                cursor: formState === 'sending' ? 'default' : 'pointer',
                boxShadow: formState !== 'sending' ? '0 0 24px rgba(0,240,200,0.28)' : 'none',
                width: '100%', transition: 'opacity 0.2s',
              }}>
                {formState === 'sending' ? 'Sending...' : 'Request demo flight →'}
              </button>
              <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.58rem', color: C.muted, textAlign: 'center' as const }}>
                Or email{' '}
                <a href="mailto:contact@axalonsystems.com" style={{ color: C.teal, textDecoration: 'none' }}>contact@axalonsystems.com</a>
              </p>
            </motion.form>
          )}
        </AnimatePresence>
      </motion.div>

      <motion.div
        initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: false }} transition={{ delay: 0.4 }}
        style={{ display: 'flex', gap: '1.8rem', marginTop: '2.5rem' }}
      >
        {[{ v: '99.7%', l: 'Accuracy' }, { v: '10×', l: 'Faster' }, { v: '50MW+', l: 'Inspected' }].map(s => (
          <div key={s.l}>
            <p style={{ fontFamily: 'Syne, sans-serif', fontWeight: 800, fontSize: '1.5rem', background: `linear-gradient(135deg, ${C.teal}, ${C.purple})`, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text', lineHeight: 1, marginBottom: '0.2rem' }}>{s.v}</p>
            <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.58rem', color: C.muted, letterSpacing: '0.08em' }}>{s.l}</p>
          </div>
        ))}
      </motion.div>

      {/* Footer strip */}
      <div style={{ marginTop: '3rem', paddingTop: '1.5rem', borderTop: '1px solid rgba(255,255,255,0.04)', display: 'flex', gap: '1.5rem', flexWrap: 'wrap' as const }}>
        {['Privacy', 'Terms', 'IIT Bombay Incubated', '© 2026 Axalon Systems'].map(item => (
          <span key={item} style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.56rem', color: C.muted, letterSpacing: '0.06em' }}>{item}</span>
        ))}
      </div>
    </Section>
  )
}

// ─── ROOT EXPORT — sections 2-5 only (hero + CTA are full-width zones) ───────
export default function LeftPanel() {
  return (
    <div id="left-panel-inner">
      <ThermalSection />
      <DetectionSection />
      <FleetSection />
      <ReportSection />
    </div>
  )
}
