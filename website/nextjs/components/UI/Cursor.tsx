'use client'

import { useEffect, useRef } from 'react'

export default function Cursor() {
  const dotRef  = useRef<HTMLDivElement>(null)
  const ringRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const dot  = dotRef.current
    const ring = ringRef.current
    if (!dot || !ring) return

    let mx = window.innerWidth / 2
    let my = window.innerHeight / 2
    let rx = mx, ry = my   // ring lags behind

    const onMove = (e: MouseEvent) => {
      mx = e.clientX
      my = e.clientY
    }
    window.addEventListener('mousemove', onMove)

    let raf: number
    const animate = () => {
      // dot: instant
      dot.style.transform  = `translate(${mx - 3}px, ${my - 3}px)`
      // ring: lerp for inertia
      rx += (mx - rx) * 0.12
      ry += (my - ry) * 0.12
      ring.style.transform = `translate(${rx - 16}px, ${ry - 16}px)`
      raf = requestAnimationFrame(animate)
    }
    raf = requestAnimationFrame(animate)

    // Scale ring on hoverable elements
    const onEnter = () => ring.style.transform += ' scale(1.8)'
    const onLeave = () => {}

    const links = document.querySelectorAll('a, button, input, textarea, [data-hover]')
    links.forEach(el => {
      el.addEventListener('mouseenter', onEnter)
      el.addEventListener('mouseleave', onLeave)
    })

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('mousemove', onMove)
      links.forEach(el => {
        el.removeEventListener('mouseenter', onEnter)
        el.removeEventListener('mouseleave', onLeave)
      })
    }
  }, [])

  return (
    <>
      {/* Inner dot */}
      <div
        ref={dotRef}
        style={{
          position: 'fixed',
          top: 0, left: 0,
          width: '6px', height: '6px',
          borderRadius: '50%',
          background: '#00f0c8',
          pointerEvents: 'none',
          zIndex: 9999,
          boxShadow: '0 0 8px rgba(0,240,200,0.8)',
          willChange: 'transform',
        }}
      />
      {/* Outer ring */}
      <div
        ref={ringRef}
        style={{
          position: 'fixed',
          top: 0, left: 0,
          width: '32px', height: '32px',
          borderRadius: '50%',
          border: '1px solid rgba(0,240,200,0.45)',
          pointerEvents: 'none',
          zIndex: 9998,
          willChange: 'transform',
          transition: 'border-color 0.2s',
        }}
      />
    </>
  )
}
