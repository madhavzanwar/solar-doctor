'use client'

import { motion, AnimatePresence } from 'framer-motion'
import { useEffect, useMemo, useState } from 'react'
import type { ANOMALIES } from './PlatformScene'

type Anomaly = (typeof ANOMALIES)[number]

const SEV_COLOR: Record<string, string> = {
  CRITICAL: '#ff2a4d',
  HIGH: '#ff8a1f',
  MEDIUM: '#ffd23f',
  LOW: '#3aa6ff',
}

export default function PlatformHUD({
  anomalies,
  selected,
  onSelect,
}: {
  anomalies: Anomaly[]
  selected: Anomaly | null
  onSelect: (a: Anomaly | null) => void
}) {
  const summary = useMemo(() => {
    const s = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 }
    for (const a of anomalies) s[a.severity]++
    return s
  }, [anomalies])

  const total = anomalies.length

  // Live "scan progress" %
  const [progress, setProgress] = useState(0)
  useEffect(() => {
    const id = setInterval(() => {
      setProgress((p) => (p + 0.7) % 100)
    }, 80)
    return () => clearInterval(id)
  }, [])

  // Rolling detection feed
  const [feedIdx, setFeedIdx] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setFeedIdx((i) => (i + 1) % anomalies.length), 1400)
    return () => clearInterval(id)
  }, [anomalies.length])

  return (
    <>
      {/* Top-left: title + status */}
      <motion.div
        initial={{ opacity: 0, x: -24 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        style={panelStyle({ top: 92, left: 24, width: 320 })}
      >
        <div style={labelStyle}>
          <span style={dotStyle('#00f0c8')} />
          ACTIVE INSPECTION
        </div>
        <div style={{ fontFamily: 'Syne, sans-serif', fontSize: 22, fontWeight: 700, marginTop: 6 }}>
          PARK_07 · Maharashtra
        </div>
        <div style={{ fontSize: 11, color: '#7a8aa0', marginTop: 4, letterSpacing: '0.05em' }}>
          MISSION ID · MX-2026-0429-A · ALT 42m
        </div>

        <div style={{ marginTop: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: '#7a8aa0' }}>
            <span>SCAN PROGRESS</span>
            <span style={{ color: '#00f0c8' }}>{Math.round(progress)}%</span>
          </div>
          <div style={progressBarStyle}>
            <div
              style={{
                width: `${progress}%`,
                height: '100%',
                background: 'linear-gradient(90deg, #00f0c8, #6c63ff)',
                transition: 'width 80ms linear',
              }}
            />
          </div>
        </div>
      </motion.div>

      {/* Top-right: severity stats */}
      <motion.div
        initial={{ opacity: 0, x: 24 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.6, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
        style={panelStyle({ top: 92, right: 24, width: 280 })}
      >
        <div style={labelStyle}>
          <span style={dotStyle('#ff2a4d')} />
          ANOMALY TELEMETRY
        </div>
        <div style={{ fontFamily: 'Syne, sans-serif', fontSize: 38, fontWeight: 700, marginTop: 4 }}>
          {total}
        </div>
        <div style={{ fontSize: 10, color: '#7a8aa0', letterSpacing: '0.08em' }}>
          DETECTIONS · LIVE
        </div>

        <div style={{ marginTop: 14, display: 'grid', gap: 8 }}>
          {(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as const).map((sev) => {
            const n = summary[sev]
            const pct = total ? (n / total) * 100 : 0
            return (
              <div key={sev}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10 }}>
                  <span style={{ color: SEV_COLOR[sev], letterSpacing: '0.06em', fontWeight: 600 }}>
                    {sev}
                  </span>
                  <span style={{ color: '#a3b1c5' }}>{n}</span>
                </div>
                <div style={{ height: 4, background: 'rgba(255,255,255,0.05)', borderRadius: 2, marginTop: 3 }}>
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${pct}%` }}
                    transition={{ duration: 0.8, ease: 'easeOut' }}
                    style={{
                      height: '100%',
                      background: SEV_COLOR[sev],
                      borderRadius: 2,
                      boxShadow: `0 0 8px ${SEV_COLOR[sev]}`,
                    }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      </motion.div>

      {/* Bottom-left: live feed */}
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
        style={panelStyle({ bottom: 24, left: 24, width: 360 })}
      >
        <div style={labelStyle}>
          <span style={dotStyle('#6c63ff')} />
          DETECTION FEED
        </div>
        <div
          style={{
            marginTop: 10,
            height: 132,
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 11,
          }}
        >
          {anomalies
            .slice(feedIdx, feedIdx + 5)
            .concat(anomalies.slice(0, Math.max(0, feedIdx + 5 - anomalies.length)))
            .map((a, i) => (
              <motion.div
                key={`${a.id}-${feedIdx}-${i}`}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1 - i * 0.18, x: 0 }}
                transition={{ duration: 0.35 }}
                style={{
                  display: 'flex',
                  gap: 10,
                  alignItems: 'center',
                  padding: '4px 8px',
                  borderLeft: `2px solid ${SEV_COLOR[a.severity]}`,
                  background: 'rgba(255,255,255,0.02)',
                  borderRadius: 3,
                }}
              >
                <span style={{ color: SEV_COLOR[a.severity], width: 60, fontWeight: 600 }}>
                  {a.severity}
                </span>
                <span style={{ color: '#a3b1c5', width: 90 }}>R{a.row + 1}-C{a.col + 1}</span>
                <span style={{ color: '#7a8aa0' }}>{a.cls}</span>
              </motion.div>
            ))}
        </div>
      </motion.div>

      {/* Bottom-right: stack info */}
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.25, ease: [0.22, 1, 0.36, 1] }}
        style={panelStyle({ bottom: 24, right: 24, width: 240 })}
      >
        <div style={labelStyle}>
          <span style={dotStyle('#00f0c8')} />
          INFERENCE STACK
        </div>
        <div style={{ marginTop: 10, display: 'grid', gap: 6, fontSize: 11, color: '#a3b1c5' }}>
          <Row k="MODEL" v="YOLO11m · best.pt" />
          <Row k="CLASSES" v="11" />
          <Row k="CONF" v="0.25" />
          <Row k="DEVICE" v="CUDA:0" />
          <Row k="LATENCY" v="14ms" color="#00f0c8" />
        </div>
      </motion.div>

      {/* Selected anomaly card (center-top, dismissable) */}
      <AnimatePresence>
        {selected && (
          <motion.div
            key={selected.id}
            initial={{ opacity: 0, y: -12, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.97 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            style={{
              position: 'fixed',
              top: 92,
              left: '50%',
              transform: 'translateX(-50%)',
              width: 360,
              padding: '16px 18px',
              background: 'rgba(8, 12, 22, 0.85)',
              border: `1px solid ${SEV_COLOR[selected.severity]}55`,
              borderRadius: 10,
              backdropFilter: 'blur(20px)',
              boxShadow: `0 0 40px ${SEV_COLOR[selected.severity]}33`,
              zIndex: 60,
              color: '#e8e8f0',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <div style={{ fontSize: 10, color: SEV_COLOR[selected.severity], letterSpacing: '0.1em', fontWeight: 700 }}>
                  ▶ {selected.severity}
                </div>
                <div style={{ fontFamily: 'Syne, sans-serif', fontSize: 20, fontWeight: 700, marginTop: 4 }}>
                  {selected.cls.toUpperCase()}
                </div>
                <div style={{ fontSize: 12, color: '#7a8aa0', marginTop: 2 }}>
                  Panel R{selected.row + 1}-C{selected.col + 1}
                </div>
              </div>
              <button
                onClick={() => onSelect(null)}
                style={{
                  background: 'transparent',
                  color: '#7a8aa0',
                  border: 'none',
                  fontSize: 16,
                  cursor: 'pointer',
                  padding: 0,
                }}
                aria-label="Close"
              >
                ✕
              </button>
            </div>
            <div style={{ marginTop: 12, display: 'flex', gap: 14, fontSize: 11, color: '#a3b1c5' }}>
              <span>conf <strong style={{ color: '#e8e8f0' }}>0.{Math.floor(60 + Math.random() * 39)}</strong></span>
              <span>ID <strong style={{ color: '#e8e8f0' }}>{selected.id}</strong></span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}

function Row({ k, v, color }: { k: string; v: string; color?: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
      <span style={{ color: '#7a8aa0', letterSpacing: '0.05em' }}>{k}</span>
      <span style={{ color: color || '#e8e8f0', fontFamily: 'JetBrains Mono, monospace' }}>{v}</span>
    </div>
  )
}

function panelStyle(pos: { top?: number; left?: number; right?: number; bottom?: number; width: number }): React.CSSProperties {
  return {
    position: 'fixed',
    ...pos,
    padding: '14px 16px',
    background: 'rgba(6, 10, 20, 0.72)',
    border: '1px solid rgba(0,240,200,0.12)',
    borderRadius: 10,
    backdropFilter: 'blur(18px)',
    color: '#e8e8f0',
    zIndex: 50,
    boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
  }
}

const labelStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  fontSize: 10,
  color: '#7a8aa0',
  letterSpacing: '0.12em',
  fontWeight: 600,
}

const dotStyle = (color: string): React.CSSProperties => ({
  width: 6,
  height: 6,
  borderRadius: '50%',
  background: color,
  boxShadow: `0 0 8px ${color}`,
  display: 'inline-block',
  animation: 'platformPulse 1.6s ease-in-out infinite',
})

const progressBarStyle: React.CSSProperties = {
  marginTop: 6,
  height: 4,
  background: 'rgba(255,255,255,0.05)',
  borderRadius: 2,
  overflow: 'hidden',
}
