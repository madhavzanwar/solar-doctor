'use client'

import { useState } from 'react'
import { motion, useInView } from 'framer-motion'
import { useRef } from 'react'
import { Mail, MapPin, Phone, CheckCircle, Loader, ArrowRight } from 'lucide-react'

const C = {
  teal: '#00f0c8',
  purple: '#6c63ff',
  bg: '#050508',
  surface: '#0d0d14',
  text: '#e8e8f0',
  muted: '#6b6b80',
}

const contactInfo = [
  { icon: Mail,   label: 'Email',  value: 'contact@axalonsystems.com' },
  { icon: MapPin, label: 'Office', value: 'Mumbai, India' },
  { icon: Phone,  label: 'Phone',  value: 'Available upon request' },
]

const initialForm = { name: '', email: '', company: '', role: '', message: '' }

const inputStyle: React.CSSProperties = {
  width: '100%',
  background: '#0d0d14',
  border: '1px solid rgba(255,255,255,0.08)',
  color: C.text,
  fontFamily: 'Space Grotesk, sans-serif',
  fontSize: '0.875rem',
  padding: '0.75rem 1rem',
  outline: 'none',
  transition: 'border-color 0.2s',
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontFamily: 'Space Grotesk, sans-serif',
  fontSize: '0.65rem',
  fontWeight: 500,
  letterSpacing: '0.15em',
  textTransform: 'uppercase',
  color: C.muted,
  marginBottom: '0.5rem',
}

export default function ContactSection() {
  const [form, setForm] = useState(initialForm)
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle')
  const [errorMsg, setErrorMsg] = useState('')

  const headerRef = useRef<HTMLDivElement>(null)
  const headerInView = useInView(headerRef, { once: true, margin: '-80px' })

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setStatus('loading')
    setErrorMsg('')
    try {
      const res = await fetch('http://localhost:8000/api/demo-requests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      if (!res.ok) throw new Error('Request failed')
      setStatus('success')
      setForm(initialForm)
    } catch {
      setStatus('error')
      setErrorMsg('Something went wrong. Please try again or email us directly.')
    }
  }

  return (
    <>
      {/* CTA Banner */}
      <section style={{
        position: 'relative',
        padding: '7rem 0',
        background: C.bg,
        overflow: 'hidden',
        textAlign: 'center',
      }}>
        {/* Radial glow */}
        <div style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          pointerEvents: 'none',
        }}>
          <div style={{
            width: '700px',
            height: '350px',
            background: 'rgba(0,240,200,0.04)',
            borderRadius: '50%',
            filter: 'blur(120px)',
          }} />
        </div>

        {/* Top separator */}
        <div style={{
          position: 'absolute',
          top: 0,
          left: '50%',
          transform: 'translateX(-50%)',
          width: '400px',
          height: '1px',
          background: `linear-gradient(90deg, transparent, rgba(0,240,200,0.3), transparent)`,
        }} />

        <div style={{ position: 'relative', maxWidth: '900px', margin: '0 auto', padding: '0 2rem' }}>
          <motion.p
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            style={{
              fontFamily: 'Space Grotesk, sans-serif',
              fontSize: '0.68rem',
              fontWeight: 500,
              letterSpacing: '0.28em',
              textTransform: 'uppercase' as const,
              color: C.teal,
              marginBottom: '1.5rem',
            }}
          >
            Ready to transform inspections?
          </motion.p>

          <motion.h2
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.1 }}
            style={{
              fontFamily: 'Syne, sans-serif',
              fontWeight: 800,
              fontSize: 'clamp(2rem, 5vw, 3.8rem)',
              color: C.text,
              lineHeight: 1.05,
              marginBottom: '1.5rem',
            }}
          >
            See Axalon in action<br /> on your solar assets
          </motion.h2>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.2 }}
            style={{
              fontFamily: 'Space Grotesk, sans-serif',
              fontSize: '1rem',
              lineHeight: 1.65,
              color: C.muted,
              marginBottom: '3rem',
              maxWidth: '500px',
              margin: '0 auto 3rem',
            }}
          >
            Get in touch with our team to learn about autonomous flight,
            real-time AI processing, and automated reporting.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.3 }}
            style={{ display: 'flex', gap: '1rem', justifyContent: 'center', flexWrap: 'wrap' }}
          >
            <motion.a
              href="#contact"
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.9rem 2rem',
                background: 'linear-gradient(135deg, #00f0c8, #6c63ff)',
                color: '#050508',
                fontFamily: 'Space Grotesk, sans-serif',
                fontWeight: 600,
                fontSize: '0.875rem',
                textDecoration: 'none',
                borderRadius: '4px',
                boxShadow: '0 0 30px rgba(0,240,200,0.2)',
              }}
            >
              Contact us <ArrowRight size={16} />
            </motion.a>
            <motion.a
              href="#technology"
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.9rem 2rem',
                background: 'rgba(255,255,255,0.04)',
                border: '1px solid rgba(255,255,255,0.1)',
                color: C.text,
                fontFamily: 'Space Grotesk, sans-serif',
                fontWeight: 600,
                fontSize: '0.875rem',
                textDecoration: 'none',
                borderRadius: '4px',
              }}
            >
              View capabilities
            </motion.a>
          </motion.div>
        </div>
      </section>

      {/* Contact Form */}
      <section
        id="contact"
        style={{
          padding: '7rem 0',
          background: C.surface,
          borderTop: '1px solid rgba(255,255,255,0.05)',
        }}
      >
        <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '0 2rem' }}>
          <div className="contact-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '5rem', alignItems: 'start' }}>

            {/* Left — info */}
            <motion.div
              ref={headerRef}
              initial={{ opacity: 0, y: 24 }}
              animate={headerInView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.6 }}
            >
              <p style={{
                fontFamily: 'Space Grotesk, sans-serif',
                fontSize: '0.68rem',
                fontWeight: 500,
                letterSpacing: '0.28em',
                textTransform: 'uppercase' as const,
                color: C.teal,
                marginBottom: '1rem',
              }}>
                Contact
              </p>
              <h2 style={{
                fontFamily: 'Syne, sans-serif',
                fontWeight: 800,
                fontSize: 'clamp(1.8rem, 3vw, 2.5rem)',
                color: C.text,
                lineHeight: 1.1,
                marginBottom: '1.5rem',
              }}>
                Let&apos;s discuss your inspection needs
              </h2>
              <p style={{
                fontFamily: 'Space Grotesk, sans-serif',
                fontSize: '1rem',
                lineHeight: 1.65,
                color: C.muted,
                marginBottom: '3rem',
                maxWidth: '400px',
              }}>
                Reach out to learn how Axalon&apos;s autonomous inspection platform
                can work for your infrastructure.
              </p>

              <div style={{ display: 'flex', flexDirection: 'column' as const, gap: '1.25rem' }}>
                {contactInfo.map(({ icon: Icon, label, value }) => (
                  <div key={label} style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem' }}>
                    <div style={{
                      width: '40px',
                      height: '40px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      background: 'rgba(0,240,200,0.08)',
                      border: '1px solid rgba(255,255,255,0.05)',
                      flexShrink: 0,
                    }}>
                      <Icon size={16} color={C.teal} />
                    </div>
                    <div>
                      <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.875rem', fontWeight: 600, color: C.text }}>
                        {label}
                      </p>
                      <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.875rem', color: C.muted }}>
                        {value}
                      </p>
                    </div>
                  </div>
                ))}
              </div>

              {/* Pulse indicator */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '3rem' }}>
                <span style={{
                  display: 'inline-block',
                  width: '6px',
                  height: '6px',
                  borderRadius: '50%',
                  background: C.teal,
                  animation: 'pulse-glow 2s ease-in-out infinite',
                }} />
                <span style={{
                  fontFamily: 'Space Grotesk, sans-serif',
                  fontSize: '0.65rem',
                  letterSpacing: '0.15em',
                  textTransform: 'uppercase' as const,
                  color: 'rgba(0,240,200,0.5)',
                }}>
                  Systems nominal
                </span>
              </div>
            </motion.div>

            {/* Right — form */}
            <motion.div
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.6, delay: 0.15 }}
            >
              {status === 'success' ? (
                <motion.div
                  key="success"
                  initial={{ opacity: 0, scale: 0.96 }}
                  animate={{ opacity: 1, scale: 1 }}
                  style={{
                    display: 'flex',
                    flexDirection: 'column' as const,
                    alignItems: 'center',
                    justifyContent: 'center',
                    padding: '5rem 2rem',
                    textAlign: 'center',
                  }}
                >
                  <CheckCircle size={48} color={C.teal} style={{ marginBottom: '1.25rem' }} />
                  <h3 style={{ fontFamily: 'Syne, sans-serif', fontWeight: 700, fontSize: '1.3rem', color: C.text, marginBottom: '0.75rem' }}>
                    Message received
                  </h3>
                  <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.875rem', color: C.muted, maxWidth: '280px' }}>
                    We&apos;ll be in touch within one business day.
                  </p>
                  <button
                    onClick={() => setStatus('idle')}
                    style={{
                      marginTop: '2rem',
                      fontFamily: 'Space Grotesk, sans-serif',
                      fontSize: '0.875rem',
                      color: C.teal,
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                    }}
                  >
                    Send another message →
                  </button>
                </motion.div>
              ) : (
                <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column' as const, gap: '1.25rem' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem' }}>
                    <div>
                      <label style={labelStyle} htmlFor="name">
                        Full name <span style={{ color: C.teal }}>*</span>
                      </label>
                      <input
                        id="name" name="name" type="text" required
                        value={form.name} onChange={handleChange}
                        placeholder="Jane Smith"
                        style={inputStyle}
                        onFocus={(e) => e.target.style.borderColor = C.teal}
                        onBlur={(e) => e.target.style.borderColor = 'rgba(255,255,255,0.08)'}
                      />
                    </div>
                    <div>
                      <label style={labelStyle} htmlFor="email">
                        Work email <span style={{ color: C.teal }}>*</span>
                      </label>
                      <input
                        id="email" name="email" type="email" required
                        value={form.email} onChange={handleChange}
                        placeholder="jane@company.com"
                        style={inputStyle}
                        onFocus={(e) => e.target.style.borderColor = C.teal}
                        onBlur={(e) => e.target.style.borderColor = 'rgba(255,255,255,0.08)'}
                      />
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem' }}>
                    <div>
                      <label style={labelStyle} htmlFor="company">
                        Company <span style={{ color: C.teal }}>*</span>
                      </label>
                      <input
                        id="company" name="company" type="text" required
                        value={form.company} onChange={handleChange}
                        placeholder="Acme Solar Ltd."
                        style={inputStyle}
                        onFocus={(e) => e.target.style.borderColor = C.teal}
                        onBlur={(e) => e.target.style.borderColor = 'rgba(255,255,255,0.08)'}
                      />
                    </div>
                    <div>
                      <label style={labelStyle} htmlFor="role">Role</label>
                      <input
                        id="role" name="role" type="text"
                        value={form.role} onChange={handleChange}
                        placeholder="Operations Manager"
                        style={inputStyle}
                        onFocus={(e) => e.target.style.borderColor = C.teal}
                        onBlur={(e) => e.target.style.borderColor = 'rgba(255,255,255,0.08)'}
                      />
                    </div>
                  </div>

                  <div>
                    <label style={labelStyle} htmlFor="message">Message</label>
                    <textarea
                      id="message" name="message" rows={5}
                      value={form.message} onChange={handleChange}
                      placeholder="Tell us about your inspection requirements — site size, assets, timelines..."
                      style={{ ...inputStyle, resize: 'none' }}
                      onFocus={(e) => e.target.style.borderColor = C.teal}
                      onBlur={(e) => e.target.style.borderColor = 'rgba(255,255,255,0.08)'}
                    />
                  </div>

                  {status === 'error' && (
                    <p style={{ fontFamily: 'Space Grotesk, sans-serif', fontSize: '0.875rem', color: '#ef4444' }}>
                      {errorMsg}
                    </p>
                  )}

                  <motion.button
                    type="submit"
                    disabled={status === 'loading'}
                    whileHover={{ scale: status === 'loading' ? 1 : 1.02 }}
                    whileTap={{ scale: 0.97 }}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      alignSelf: 'flex-start',
                      padding: '0.9rem 2rem',
                      background: `linear-gradient(135deg, ${C.teal}, ${C.purple})`,
                      color: '#050508',
                      fontFamily: 'Space Grotesk, sans-serif',
                      fontWeight: 600,
                      fontSize: '0.875rem',
                      border: 'none',
                      borderRadius: '4px',
                      cursor: status === 'loading' ? 'not-allowed' : 'pointer',
                      opacity: status === 'loading' ? 0.7 : 1,
                      boxShadow: '0 0 20px rgba(0,240,200,0.2)',
                    }}
                  >
                    {status === 'loading' ? (
                      <><Loader size={16} style={{ animation: 'spin 1s linear infinite' }} /> Sending...</>
                    ) : (
                      'Send message'
                    )}
                  </motion.button>
                </form>
              )}
            </motion.div>

          </div>
        </div>
      </section>
    </>
  )
}
