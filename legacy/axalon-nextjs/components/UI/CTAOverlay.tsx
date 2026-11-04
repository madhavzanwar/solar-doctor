'use client'

import { useRef, useEffect, useState } from 'react'
import { motion, useInView, AnimatePresence } from 'framer-motion'
import { scrollStore } from '../../scrollStore'

const C = {
  teal:   '#00f0c8',
  purple: '#6c63ff',
  text:   '#e8e8f0',
  muted:  '#6b6b80',
  bg:     'rgba(2,2,8,0.92)',
}

const STATS = [
  { value: '99.7%',  label: 'Detection accuracy' },
  { value: '10×',    label: 'Faster than manual' },
  { value: '50MW+',  label: 'Sites inspected'    },
]

type FormState = 'idle' | 'sending' | 'sent'

export default function CTAOverlay() {
  const [ctaP,   setCtaP]   = useState(0)
  const [form, setForm] = useState({ name: '', email: '', company: '', message: '' })
  const [formState, setFormState] = useState<FormState>('idle')

  const ref    = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: false, margin: '-10%' })
  const rafRef = useRef<number>(0)

  useEffect(() => {
    if (!inView) { cancelAnimationFrame(rafRef.current); return }
    const update = () => {
      const t = scrollStore.progress
      const p = Math.min(Math.max((t - 5 / 6) / (1 / 6), 0), 1)
      setCtaP(p)
      rafRef.current = requestAnimationFrame(update)
    }
    rafRef.current = requestAnimationFrame(update)
    return () => cancelAnimationFrame(rafRef.current)
  }, [inView])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.email || !form.name) return
    setFormState('sending')
    setTimeout(() => setFormState('sent'), 1400)
  }

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
    transition: 'border-color 0.2s, box-shadow 0.2s',
  }

  return (
    <div
      ref={ref}
      style={{ position: 'absolute', inset: 0, pointerEvents: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
    >
      <div style={{
        width: '100%',
        maxWidth: '1000px',
        padding: '0 4vw',
        pointerEvents: 'auto',
        display: 'grid',
        gridTemplateColumns: '3fr 2fr',
        gap: '3rem',
        alignItems: 'center',
      }}>

        {/* ── Left: CTA copy ── */}
        <div style={{
          zIndex: 20,
          background: 'rgba(5,5,8,0.7)',
          backdropFilter: 'blur(12px)',
          borderRadius: '16px',
          padding: '2rem',
        }}>
          <motion.p
            initial={{ opacity: 0, x: -20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: false }}
            style={{
              fontFamily: 'Space Grotesk, sans-serif',
              fontSize: '0.7rem',
              letterSpacing: '0.25em',
              textTransform: 'uppercase',
              color: C.teal,
              opacity: 0.8,
              marginBottom: '1rem',
            }}
          >
            06 — Ready to inspect?
          </motion.p>

          <motion.h2
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: false }}
            transition={{ delay: 0.1, duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
            style={{
              fontFamily: 'Syne, sans-serif',
              fontWeight: 800,
              fontSize: 'clamp(2.2rem, 5vw, 4rem)',
              color: C.text,
              lineHeight: 1.05,
              letterSpacing: '-0.02em',
              marginBottom: '1.2rem',
            }}
          >
            Request a<br />
            <span style={{
              background: `linear-gradient(135deg, ${C.teal} 0%, ${C.purple} 100%)`,
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
              textShadow: '0 0 40px rgba(0,240,200,0.3)',
            }}>
              demo flight.
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
              marginBottom: '2.2rem',
            }}
          >
            Let us inspect your solar farm — no commitment.
            We'll deliver a full fault report within 48 hours of the flight.
          </motion.p>

          {/* Stats */}
          <motion.div
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: false }}
            transition={{ delay: 0.3 }}
            style={{ display: 'flex', gap: '1.5rem' }}
          >
            {STATS.map(({ value, label }) => (
              <div key={label}>
                <p style={{
                  fontFamily: 'Syne, sans-serif',
                  fontWeight: 800,
                  fontSize: '1.6rem',
                  background: `linear-gradient(135deg, ${C.teal}, ${C.purple})`,
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  backgroundClip: 'text',
                  lineHeight: 1,
                  marginBottom: '0.2rem',
                }}>
                  {value}
                </p>
                <p style={{
                  fontFamily: 'Space Grotesk, sans-serif',
                  fontSize: '0.62rem',
                  color: C.muted,
                  letterSpacing: '0.08em',
                }}>
                  {label}
                </p>
              </div>
            ))}
          </motion.div>
        </div>

        {/* ── Right: contact form ── */}
        <motion.div
          initial={{ opacity: 0, x: 30 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: false }}
          transition={{ delay: 0.2, duration: 0.6 }}
          style={{
            background: C.bg,
            border: '1px solid rgba(0,240,200,0.14)',
            backdropFilter: 'blur(24px)',
            padding: '2rem',
          }}
        >
          <AnimatePresence mode="wait">
            {formState === 'sent' ? (
              <motion.div
                key="sent"
                initial={{ opacity: 0, scale: 0.96 }}
                animate={{ opacity: 1, scale: 1 }}
                style={{ textAlign: 'center', padding: '2rem 0' }}
              >
                <div style={{
                  width: '48px', height: '48px',
                  border: `2px solid ${C.teal}`,
                  borderRadius: '50%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto 1rem',
                }}>
                  <span style={{ color: C.teal, fontSize: '1.2rem' }}>✓</span>
                </div>
                <p style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '1.1rem', color: C.text, marginBottom: '0.5rem' }}>
                  Request received.
                </p>
                <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.8rem', color: C.muted, lineHeight: 1.6 }}>
                  We'll reach out within 24 hours to schedule your demo flight.
                </p>
              </motion.div>
            ) : (
              <motion.form
                key="form"
                initial={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onSubmit={handleSubmit}
                style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}
              >
                <p style={{
                  fontFamily: 'Space Grotesk, sans-serif',
                  fontSize: '0.6rem',
                  letterSpacing: '0.2em',
                  textTransform: 'uppercase',
                  color: C.muted,
                  marginBottom: '0.25rem',
                }}>
                  Get in touch
                </p>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                  <input
                    type="text"
                    placeholder="Full name"
                    value={form.name}
                    onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                    required
                    style={inputStyle}
                  />
                  <input
                    type="email"
                    placeholder="Work email"
                    value={form.email}
                    onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                    required
                    style={inputStyle}
                  />
                </div>

                <input
                  type="text"
                  placeholder="Company / solar farm name"
                  value={form.company}
                  onChange={e => setForm(f => ({ ...f, company: e.target.value }))}
                  style={inputStyle}
                />

                <textarea
                  placeholder="Site size, location, or any questions..."
                  value={form.message}
                  onChange={e => setForm(f => ({ ...f, message: e.target.value }))}
                  rows={3}
                  style={{ ...inputStyle, resize: 'none', lineHeight: 1.6 }}
                />

                <button
                  type="submit"
                  disabled={formState === 'sending'}
                  style={{
                    padding: '0.75rem 1.5rem',
                    background: formState === 'sending'
                      ? 'rgba(0,240,200,0.12)'
                      : `linear-gradient(135deg, ${C.teal} 0%, ${C.purple} 100%)`,
                    border: formState === 'sending' ? `1px solid rgba(0,240,200,0.25)` : 'none',
                    borderRadius: '4px',
                    color: formState === 'sending' ? C.teal : '#020208',
                    fontFamily: 'Space Grotesk, sans-serif',
                    fontWeight: 700,
                    fontSize: '0.82rem',
                    letterSpacing: '0.08em',
                    textTransform: 'uppercase',
                    cursor: formState === 'sending' ? 'default' : 'pointer',
                    marginTop: '0.25rem',
                    transition: 'opacity 0.2s, box-shadow 0.2s',
                    boxShadow: formState !== 'sending' ? '0 0 24px rgba(0,240,200,0.3)' : 'none',
                    width: '100%',
                  }}
                >
                  {formState === 'sending' ? 'Sending...' : 'Request demo flight →'}
                </button>

                <p style={{
                  fontFamily: 'Space Grotesk, sans-serif',
                  fontSize: '0.6rem',
                  color: C.muted,
                  textAlign: 'center',
                }}>
                  Or email us directly at{' '}
                  <a href="mailto:contact@axalonsystems.com" style={{ color: C.teal, textDecoration: 'none' }}>
                    contact@axalonsystems.com
                  </a>
                </p>
              </motion.form>
            )}
          </AnimatePresence>
        </motion.div>
      </div>

      {/* ── Bottom footer strip ── */}
      <div style={{
        position: 'absolute',
        bottom: '3vh',
        left: 0,
        right: 0,
        display: 'flex',
        justifyContent: 'center',
        gap: '2rem',
        opacity: ctaP * 0.6,
        transition: 'opacity 0.3s',
        pointerEvents: 'auto',
      }}>
        {['Privacy', 'Terms', 'IIT Bombay Incubated', '© 2026 Axalon Systems'].map(item => (
          <span key={item} style={{
            fontFamily: 'Space Grotesk, sans-serif',
            fontSize: '0.58rem',
            color: C.muted,
            letterSpacing: '0.06em',
          }}>
            {item}
          </span>
        ))}
      </div>
    </div>
  )
}
