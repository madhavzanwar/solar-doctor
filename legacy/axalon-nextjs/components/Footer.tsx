'use client'

import { motion } from 'framer-motion'

const C = {
  teal: '#00f0c8',
  bg: '#050508',
  text: '#e8e8f0',
  muted: '#6b6b80',
}

const footerLinks: Record<string, { label: string; href: string }[]> = {
  Product: [
    { label: 'Overview', href: '#technology' },
    { label: 'Capabilities', href: '#technology' },
    { label: 'How it works', href: '#mission' },
  ],
  Resources: [
    { label: 'Case Studies', href: '#' },
    { label: 'Documentation', href: '#' },
    { label: 'API Reference', href: '#' },
  ],
  Company: [
    { label: 'About', href: '#contact' },
    { label: 'Contact', href: '#contact' },
    { label: 'Careers', href: '#contact' },
  ],
}

export default function Footer() {
  return (
    <footer style={{
      background: C.bg,
      borderTop: '1px solid rgba(255,255,255,0.05)',
    }}>
      <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '4rem 2rem' }}>
        <div className="footer-grid" style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 1fr 1fr', gap: '3rem' }}>

          {/* Brand */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
          >
            <p style={{
              fontFamily: 'Syne, sans-serif',
              fontWeight: 800,
              fontSize: '1rem',
              letterSpacing: '0.12em',
              background: 'linear-gradient(135deg, #00f0c8 0%, #6c63ff 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
              marginBottom: '1rem',
            }}>
              AXALON SYSTEMS
            </p>
            <p style={{
              fontFamily: 'Space Grotesk, sans-serif',
              fontSize: '0.875rem',
              color: C.muted,
              lineHeight: 1.65,
              maxWidth: '240px',
            }}>
              Autonomous inspection drones for reliable solar asset decisions.
            </p>

            {/* Pulse indicator */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '1.25rem' }}>
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

          {/* Link columns */}
          {Object.entries(footerLinks).map(([title, links], colIdx) => (
            <motion.div
              key={title}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: (colIdx + 1) * 0.08 }}
            >
              <h4 style={{
                fontFamily: 'Space Grotesk, sans-serif',
                fontSize: '0.65rem',
                fontWeight: 600,
                letterSpacing: '0.2em',
                textTransform: 'uppercase' as const,
                color: C.muted,
                marginBottom: '1rem',
              }}>
                {title}
              </h4>
              <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column' as const, gap: '0.75rem' }}>
                {links.map(({ label, href }) => (
                  <li key={label}>
                    <a
                      href={href}
                      style={{
                        fontFamily: 'Space Grotesk, sans-serif',
                        fontSize: '0.875rem',
                        color: '#4a4a5a',
                        textDecoration: 'none',
                        transition: 'color 0.2s',
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.color = C.text)}
                      onMouseLeave={(e) => (e.currentTarget.style.color = '#4a4a5a')}
                    >
                      {label}
                    </a>
                  </li>
                ))}
              </ul>
            </motion.div>
          ))}
        </div>

        {/* Bottom bar */}
        <div style={{
          marginTop: '4rem',
          paddingTop: '2rem',
          borderTop: '1px solid rgba(255,255,255,0.05)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '1rem',
          flexWrap: 'wrap',
        }}>
          <p style={{
            fontFamily: 'Space Grotesk, sans-serif',
            fontSize: '0.75rem',
            color: '#2a2a3a',
          }}>
            © {new Date().getFullYear()} Axalon Systems. All rights reserved.
          </p>
          <div style={{ display: 'flex', gap: '1.5rem' }}>
            {['Privacy Policy', 'Terms of Service'].map((t) => (
              <span
                key={t}
                style={{
                  fontFamily: 'Space Grotesk, sans-serif',
                  fontSize: '0.75rem',
                  color: '#2a2a3a',
                  cursor: 'pointer',
                  transition: 'color 0.2s',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.color = C.muted)}
                onMouseLeave={(e) => (e.currentTarget.style.color = '#2a2a3a')}
              >
                {t}
              </span>
            ))}
          </div>
        </div>
      </div>
    </footer>
  )
}
