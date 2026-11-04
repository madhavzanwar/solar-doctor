'use client'

import { useEffect, useState, useRef } from 'react'

const SECTION_NUMS = ['01', '02', '03', '04', '05', '06']
const SECTION_IDS = ['hero', 'thermal', 'detection', 'fleet', 'report', 'contact']

export default function SplitLayout({
  leftContent,
  rightContent,
}: {
  leftContent: React.ReactNode
  rightContent: React.ReactNode
}) {
  const [progress, setProgress] = useState(0)
  const [activeSection, setActiveSection] = useState(0)
  const leftRef = useRef<HTMLDivElement>(null)

  // Scroll progress for the indicator fill line
  useEffect(() => {
    const onScroll = () => {
      const maxScroll = Math.max(1, document.documentElement.scrollHeight - window.innerHeight)
      setProgress(window.scrollY / maxScroll)
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // IntersectionObserver: fire when each section is 40% visible
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const idx = SECTION_IDS.indexOf(entry.target.getAttribute('data-section') ?? '')
            if (idx !== -1) setActiveSection(idx)
          }
        })
      },
      { threshold: 0.4 },
    )

    // Wait one tick for leftContent to mount, then observe its sections
    const timer = setTimeout(() => {
      if (!leftRef.current) return
      leftRef.current.querySelectorAll('[data-section]').forEach((el) => observer.observe(el))
    }, 100)

    return () => {
      clearTimeout(timer)
      observer.disconnect()
    }
  }, [leftContent])
  // Dot moves from top to bottom of the indicator track (40vh centred)
  const dotPct = progress * 100

  return (
    // align-items: flex-start is critical — without it, flex stretches the right
    // panel to match the left panel's full height, breaking position: sticky
    <div style={{ display: 'flex', alignItems: 'flex-start', minHeight: '100vh' }}>

      {/* ── LEFT: scrollable content (40%) ── */}
      <div ref={leftRef} style={{
        width: '40%',
        background: '#050508',
        position: 'relative',
        zIndex: 20,
        // Right border separates panels
        borderRight: '1px solid rgba(255,255,255,0.04)',
      }}>

        {/* ── Scroll progress indicator (fixed within left panel) ── */}
        <div
          aria-hidden
          style={{
            position: 'fixed',
            left: '1.5rem',
            top: '50%',
            transform: 'translateY(-50%)',
            height: '42vh',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            zIndex: 50,
            pointerEvents: 'none',
          }}
        >
          {/* Background track */}
          <div style={{
            position: 'absolute',
            top: 0,
            bottom: 0,
            width: '1px',
            background: 'rgba(255,255,255,0.08)',
          }} />

          {/* Filled portion */}
          <div style={{
            position: 'absolute',
            top: 0,
            width: '1px',
            height: `${dotPct}%`,
            background: 'linear-gradient(180deg, rgba(0,240,200,0.6) 0%, #00f0c8 100%)',
            transition: 'height 0.1s linear',
          }} />

          {/* Section markers */}
          {SECTION_NUMS.map((num, i) => {
            const sectionTop = (i / 6) * 100
            const isActive = activeSection === i
            return (
              <div
                key={num}
                style={{
                  position: 'absolute',
                  top: `${sectionTop}%`,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  transform: 'translateY(-50%)',
                }}
              >
                <div style={{
                  width: isActive ? '6px' : '4px',
                  height: isActive ? '6px' : '4px',
                  borderRadius: '50%',
                  background: isActive ? '#00f0c8' : 'rgba(255,255,255,0.2)',
                  boxShadow: isActive ? '0 0 8px rgba(0,240,200,0.8)' : 'none',
                  transition: 'all 0.3s',
                  flexShrink: 0,
                }} />
                <span style={{
                  fontFamily: 'Space Grotesk, monospace',
                  fontSize: '0.55rem',
                  letterSpacing: '0.12em',
                  color: isActive ? '#00f0c8' : 'rgba(255,255,255,0.2)',
                  transition: 'color 0.3s',
                  userSelect: 'none',
                }}>
                  {num}
                </span>
              </div>
            )
          })}
        </div>

        {leftContent}
      </div>

      {/* ── RIGHT: sticky 3D panel (60%) ── */}
      <div style={{
        width: '60%',
        height: '100vh',
        position: 'sticky',
        top: 0,
        overflow: 'hidden',
        // background fills when Canvas isn't mounted
        background: '#020208',
        flexShrink: 0,
      }}>
        {rightContent}
      </div>

    </div>
  )
}
