'use client'

import Image from 'next/image'
import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Menu, X } from 'lucide-react'

const links: { label: string; href: string }[] = [
  { label: 'Technology', href: '#technology' },
  { label: 'Mission', href: '#mission' },
  { label: 'Contact', href: '#contact' },
]

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20)
    const onResize = () => {
      const mobile = window.innerWidth <= 900
      setIsMobile(mobile)
      if (!mobile) setMenuOpen(false)
    }

    onScroll()
    onResize()
    window.addEventListener('scroll', onScroll)
    window.addEventListener('resize', onResize)

    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onResize)
    }
  }, [])

  return (
    <>
      <motion.nav
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          zIndex: 100,
          padding: isMobile ? '0 1rem' : '0 2rem',
          height: isMobile ? '72px' : '64px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: scrolled || menuOpen
            ? 'rgba(5, 5, 8, 0.88)'
            : 'transparent',
          backdropFilter: scrolled || menuOpen ? 'blur(20px)' : 'none',
          borderBottom: scrolled || menuOpen
            ? '1px solid rgba(0,240,200,0.08)'
            : '1px solid transparent',
          transition: 'background 0.3s ease, border-color 0.3s ease, height 0.3s ease',
        }}
      >
        <motion.a
          href="#hero"
          style={{ textDecoration: 'none', minWidth: 0 }}
          whileHover={{ scale: 1.02 }}
        >
          <Image
            src="/LogoWithName.png"
            alt="Axalon Systems"
            width={160}
            height={48}
            style={{
              height: isMobile ? '32px' : '38px',
              width: 'auto',
              objectFit: 'contain',
              filter: 'invert(1)',
              opacity: 0.92,
            }}
            priority
          />
        </motion.a>

        <div
          className="nav-links"
          style={{ display: isMobile ? 'none' : 'flex', gap: '2.5rem', alignItems: 'center' }}
        >
          {links.map((link, i) => (
            <NavLink key={link.label} label={link.label} href={link.href} delay={i * 0.08} />
          ))}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: isMobile ? '0.6rem' : '0.85rem' }}>
          {!isMobile && (
            <motion.a
              href="#contact"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.5 }}
              style={{
                padding: '0.45rem 1.1rem',
                border: '1px solid rgba(0,240,200,0.4)',
                borderRadius: '4px',
                color: '#00f0c8',
                fontFamily: 'Space Grotesk, sans-serif',
                fontWeight: 500,
                fontSize: '0.82rem',
                letterSpacing: '0.06em',
                textDecoration: 'none',
                background: 'rgba(0,240,200,0.04)',
                transition: 'all 0.2s ease',
              }}
              whileHover={{
                background: 'rgba(0,240,200,0.1)',
                boxShadow: '0 0 20px rgba(0,240,200,0.2)',
              }}
            >
              REQUEST DEMO
            </motion.a>
          )}

          <motion.a
            href="#hero"
            whileHover={{ scale: 1.03 }}
            style={{
              width: isMobile ? '42px' : '48px',
              height: isMobile ? '42px' : '48px',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: '8px',
              border: '1px solid rgba(255,255,255,0.08)',
              background: 'rgba(255,255,255,0.03)',
              overflow: 'hidden',
              flexShrink: 0,
            }}
            aria-label="Axalon Systems home"
          >
            <Image
              src="/logo.png"
              alt="Axalon Systems logo"
              width={40}
              height={40}
              style={{
                width: isMobile ? '30px' : '34px',
                height: isMobile ? '30px' : '34px',
                objectFit: 'contain',
              }}
              priority
            />
          </motion.a>

          {isMobile && (
            <button
              type="button"
              onClick={() => setMenuOpen((prev) => !prev)}
              aria-label={menuOpen ? 'Close navigation menu' : 'Open navigation menu'}
              aria-expanded={menuOpen}
              style={{
                width: '42px',
                height: '42px',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: '8px',
                border: '1px solid rgba(255,255,255,0.08)',
                background: 'rgba(255,255,255,0.03)',
                color: '#e8e8f0',
                cursor: 'pointer',
              }}
            >
              {menuOpen ? <X size={18} /> : <Menu size={18} />}
            </button>
          )}
        </div>
      </motion.nav>

      <AnimatePresence>
        {isMobile && menuOpen && (
          <motion.div
            initial={{ opacity: 0, y: -16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
            style={{
              position: 'fixed',
              top: '72px',
              left: '1rem',
              right: '1rem',
              zIndex: 99,
              padding: '1rem',
              background: 'rgba(8, 8, 14, 0.94)',
              border: '1px solid rgba(0,240,200,0.08)',
              borderRadius: '10px',
              backdropFilter: 'blur(24px)',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.5rem',
            }}
          >
            {links.map((link) => (
              <a
                key={link.label}
                href={link.href}
                onClick={() => setMenuOpen(false)}
                style={{
                  padding: '0.9rem 0.95rem',
                  borderRadius: '8px',
                  background: 'rgba(255,255,255,0.02)',
                  color: '#e8e8f0',
                  textDecoration: 'none',
                  fontFamily: 'Space Grotesk, sans-serif',
                  fontSize: '0.92rem',
                  letterSpacing: '0.04em',
                }}
              >
                {link.label}
              </a>
            ))}
            <a
              href="#contact"
              onClick={() => setMenuOpen(false)}
              style={{
                marginTop: '0.35rem',
                padding: '0.95rem 1rem',
                borderRadius: '8px',
                background: 'linear-gradient(135deg, #00f0c8 0%, #6c63ff 100%)',
                color: '#020208',
                textDecoration: 'none',
                fontFamily: 'Space Grotesk, sans-serif',
                fontWeight: 700,
                fontSize: '0.84rem',
                letterSpacing: '0.08em',
                textAlign: 'center',
              }}
            >
              REQUEST DEMO
            </a>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}

function NavLink({ label, href, delay }: { label: string; href: string; delay: number }) {
  const [hovered, setHovered] = useState(false)

  return (
    <motion.a
      href={href}
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 + delay, duration: 0.5 }}
      onHoverStart={() => setHovered(true)}
      onHoverEnd={() => setHovered(false)}
      style={{
        position: 'relative',
        textDecoration: 'none',
        color: hovered ? '#e8e8f0' : '#6b6b80',
        fontFamily: 'Space Grotesk, sans-serif',
        fontWeight: 500,
        fontSize: '0.85rem',
        letterSpacing: '0.05em',
        transition: 'color 0.2s ease',
        paddingBottom: '2px',
      }}
    >
      {label}
      <motion.span
        style={{
          position: 'absolute',
          bottom: -2,
          left: 0,
          right: 0,
          height: '1px',
          background: 'linear-gradient(90deg, #00f0c8, #6c63ff)',
          transformOrigin: 'left',
        }}
        initial={{ scaleX: 0 }}
        animate={{ scaleX: hovered ? 1 : 0 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
      />
    </motion.a>
  )
}
