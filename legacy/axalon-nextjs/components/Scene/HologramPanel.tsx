'use client'

import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { scrollStore } from '../../scrollStore'
import { computeFaultySet } from './SolarField'

const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi)
const lerp  = (a: number, b: number, t: number) => a + (b - a) * t

// ── Chip data ────────────────────────────────────────────────────────────────
const CHIPS = [
  { label: 'mAP50',     value: '0.734',      color: '#00f0c8', angle: 0     },
  { label: 'PANELS',    value: '396',         color: '#60a5fa', angle: 1.57  },
  { label: 'FAULTS',    value: '67',          color: '#ff6b35', angle: 3.14  },
  { label: 'FLIGHT',    value: '4.2 min',     color: '#6c63ff', angle: 4.71  },
]

function buildChipTexture(label: string, value: string, color: string): THREE.CanvasTexture {
  const W = 160, H = 64
  const cv = document.createElement('canvas')
  cv.width = W; cv.height = H
  const ctx = cv.getContext('2d')!

  ctx.fillStyle = 'rgba(2,2,8,0.92)'
  ctx.fillRect(0, 0, W, H)

  ctx.strokeStyle = color + '55'
  ctx.lineWidth = 1
  ctx.strokeRect(0.5, 0.5, W - 1, H - 1)

  // Corner accents
  const cs = 8
  ctx.strokeStyle = color
  ctx.lineWidth = 1.5
  ctx.beginPath()
  ctx.moveTo(0, cs); ctx.lineTo(0, 0); ctx.lineTo(cs, 0)
  ctx.moveTo(W - cs, 0); ctx.lineTo(W, 0); ctx.lineTo(W, cs)
  ctx.moveTo(0, H - cs); ctx.lineTo(0, H); ctx.lineTo(cs, H)
  ctx.moveTo(W - cs, H); ctx.lineTo(W, H); ctx.lineTo(W, H - cs)
  ctx.stroke()

  ctx.fillStyle = color + 'cc'
  ctx.font = 'bold 9px monospace'
  ctx.textAlign = 'center'
  ctx.fillText(label, W / 2, 22)

  ctx.fillStyle = '#e8e8f0'
  ctx.font = 'bold 18px monospace'
  ctx.fillText(value, W / 2, 46)

  return new THREE.CanvasTexture(cv)
}

// ── Main report canvas (redrawn every frame) ─────────────────────────────────
function buildBaseCanvas(): HTMLCanvasElement {
  const W = 512, H = 330
  const cv = document.createElement('canvas')
  cv.width = W; cv.height = H
  return cv
}

const GCOLS = 22, GROWS = 18
const CELL_W = 19, CELL_H = 7, GAP_X = 2, GAP_Y = 2
const GRID_X = 14, GRID_Y = 48
const TOTAL_PANELS = GCOLS * GROWS

function drawReport(ctx: CanvasRenderingContext2D, W: number, H: number, revealCount: number, scanLine: number) {
  // Base
  ctx.fillStyle = '#020208'
  ctx.fillRect(0, 0, W, H)

  // Header band
  const hdr = ctx.createLinearGradient(0, 0, W, 0)
  hdr.addColorStop(0, 'rgba(0,240,200,0.12)')
  hdr.addColorStop(1, 'rgba(0,32,32,0.04)')
  ctx.fillStyle = hdr
  ctx.fillRect(0, 0, W, 38)

  ctx.fillStyle = '#00f0c8'
  ctx.font = 'bold 10px monospace'
  ctx.textAlign = 'left'
  ctx.fillText('AXALON · INSPECTION REPORT', 12, 14)

  ctx.fillStyle = '#6b6b80'
  ctx.font = '8px monospace'
  ctx.fillText('SOLAR FARM DELTA  ·  SECTOR 7  ·  2026-04-17', 12, 29)

  // Revealed count indicator
  const pct = Math.round((revealCount / TOTAL_PANELS) * 100)
  ctx.fillStyle = '#00f0c8'
  ctx.font = 'bold 10px monospace'
  ctx.textAlign = 'right'
  ctx.fillText(`${pct}%`, W - 12, 14)
  ctx.fillStyle = '#6b6b80'
  ctx.font = '7px monospace'
  ctx.fillText('SCANNED', W - 12, 25)
  ctx.textAlign = 'left'

  ctx.strokeStyle = 'rgba(0,240,200,0.18)'
  ctx.lineWidth = 1
  ctx.beginPath(); ctx.moveTo(0, 38); ctx.lineTo(W, 38); ctx.stroke()

  // Panel grid
  const faultySet = computeFaultySet()
  for (let idx = 0; idx < TOTAL_PANELS; idx++) {
    const r = Math.floor(idx / GCOLS)
    const c = idx % GCOLS
    const x = GRID_X + c * (CELL_W + GAP_X)
    const y = GRID_Y + r * (CELL_H + GAP_Y)
    const revealed = idx < revealCount
    const faulty = faultySet.has(idx % 176)  // map to SolarField panel indices

    if (!revealed) {
      ctx.fillStyle = 'rgba(13,13,25,0.4)'
      ctx.strokeStyle = 'rgba(0,240,200,0.04)'
    } else if (faulty) {
      const sinVal = Math.sin(idx * 137.5)
      if (sinVal > 0.85)      { ctx.fillStyle = 'rgba(255,26,0,0.45)';  ctx.strokeStyle = '#ff1a0055' }
      else if (sinVal > 0.78) { ctx.fillStyle = 'rgba(255,107,53,0.4)'; ctx.strokeStyle = '#ff6b3555' }
      else                    { ctx.fillStyle = 'rgba(255,200,0,0.30)'; ctx.strokeStyle = '#ffc80055' }
    } else {
      ctx.fillStyle  = '#0d1a3a'
      ctx.strokeStyle = 'rgba(0,240,200,0.12)'
    }

    ctx.lineWidth = 0.5
    ctx.fillRect(x, y, CELL_W, CELL_H)
    ctx.strokeRect(x, y, CELL_W, CELL_H)

    // Fault dot
    if (revealed && faulty) {
      const sinVal = Math.sin(idx * 137.5)
      ctx.fillStyle = sinVal > 0.85 ? '#ff1a00' : sinVal > 0.78 ? '#ff6b35' : '#ffc800'
      ctx.beginPath()
      ctx.arc(x + CELL_W / 2, y + CELL_H / 2, 1.8, 0, Math.PI * 2)
      ctx.fill()
    }
  }

  // Animated scanline highlight
  const slY = GRID_Y + (scanLine % (GROWS * (CELL_H + GAP_Y)))
  const slGrad = ctx.createLinearGradient(0, slY - 3, 0, slY + 3)
  slGrad.addColorStop(0, 'transparent')
  slGrad.addColorStop(0.5, 'rgba(0,240,200,0.15)')
  slGrad.addColorStop(1, 'transparent')
  ctx.fillStyle = slGrad
  ctx.fillRect(GRID_X, slY - 3, GCOLS * (CELL_W + GAP_X), 6)

  // Stats footer
  const statsY = GRID_Y + GROWS * (CELL_H + GAP_Y) + 10
  ctx.strokeStyle = 'rgba(0,240,200,0.10)'
  ctx.beginPath(); ctx.moveTo(0, statsY - 4); ctx.lineTo(W, statsY - 4); ctx.stroke()

  const STATS = [
    { label: 'CRITICAL', val: '12', col: '#ff1a00' },
    { label: 'HIGH',     val: '19', col: '#ff6b35' },
    { label: 'MEDIUM',   val: '28', col: '#ffc800' },
    { label: 'LOW',      val: '8',  col: '#00f0c8' },
    { label: 'TOTAL',    val: '67', col: '#e8e8f0' },
  ]
  STATS.forEach(({ label, val, col }, i) => {
    const sx = 14 + i * 96
    ctx.fillStyle = col
    ctx.font = 'bold 13px monospace'
    ctx.fillText(val, sx, statsY + 12)
    ctx.fillStyle = '#6b6b80'
    ctx.font = '6.5px monospace'
    ctx.fillText(label, sx, statsY + 23)
  })

  // CRT scanline overlay
  for (let sy = 0; sy < H; sy += 3) {
    ctx.fillStyle = 'rgba(0,0,0,0.06)'
    ctx.fillRect(0, sy, W, 1)
  }

  // Footer
  ctx.strokeStyle = 'rgba(0,240,200,0.08)'
  ctx.beginPath(); ctx.moveTo(0, H - 14); ctx.lineTo(W, H - 14); ctx.stroke()
  ctx.fillStyle = 'rgba(0,240,200,0.25)'
  ctx.font = '6.5px monospace'
  ctx.fillText('YOLO11m v3.2  ·  CONF ≥ 0.25  ·  AXL-FLEET-3  ·  2026-04-17T09:42:11Z', 10, H - 4)
}

// ── Outward particles ─────────────────────────────────────────────────────────
const PARTICLE_COUNT = 50

function buildParticleSystem() {
  const positions  = new Float32Array(PARTICLE_COUNT * 3)
  const velocities = new Float32Array(PARTICLE_COUNT * 3)
  const ages       = new Float32Array(PARTICLE_COUNT)

  for (let i = 0; i < PARTICLE_COUNT; i++) {
    const θ = Math.random() * Math.PI * 2
    const φ = Math.acos(2 * Math.random() - 1)
    const spd = 0.008 + Math.random() * 0.012
    velocities[i * 3    ] = spd * Math.sin(φ) * Math.cos(θ)
    velocities[i * 3 + 1] = spd * Math.sin(φ) * Math.sin(θ) * 0.5
    velocities[i * 3 + 2] = spd * Math.cos(φ) * 0.4
    ages[i] = Math.random() // stagger start ages
  }

  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  return { geo, velocities, ages, positions }
}

// ── Main component ────────────────────────────────────────────────────────────
export default function HologramPanel() {
  const groupRef    = useRef<THREE.Group>(null)
  const panelRef    = useRef<THREE.Mesh>(null)
  const glowRef     = useRef<THREE.Mesh>(null)
  const particleRef = useRef<THREE.Points>(null)
  const lightRef    = useRef<THREE.PointLight>(null)
  const panelMatRef = useRef<THREE.MeshBasicMaterial>(null)
  const chipRefs    = useRef<(THREE.Mesh | null)[]>([])
  const revealRef   = useRef(0)

  const { reportCanvas, reportTex } = useMemo(() => {
    const cv  = buildBaseCanvas()
    const tex = new THREE.CanvasTexture(cv)
    tex.minFilter = THREE.LinearFilter
    tex.magFilter = THREE.LinearFilter
    return { reportCanvas: cv, reportTex: tex }
  }, [])

  const chipTextures = useMemo(() =>
    CHIPS.map(c => buildChipTexture(c.label, c.value, c.color)),
  [])

  const { geo: particleGeo, velocities, ages, positions } = useMemo(() => buildParticleSystem(), [])

  const frameEdgesGeo = useMemo(() => new THREE.EdgesGeometry(new THREE.PlaneGeometry(4.2, 2.8)), [])

  useFrame(({ clock }) => {
    const t = scrollStore.progress
    const reportP = clamp((t - 4 / 6) / (1 / 6), 0, 1)
    const active  = reportP > 0.005

    if (groupRef.current) groupRef.current.visible = active
    if (!active) return

    const elapsed = clock.elapsedTime

    // Hologram float + gentle tilt
    if (groupRef.current) {
      groupRef.current.position.y = 2.5 + Math.sin(elapsed * 0.7) * 0.18
      groupRef.current.rotation.y = Math.sin(elapsed * 0.35) * 0.06
      groupRef.current.rotation.x = Math.sin(elapsed * 0.5 + 1) * 0.03
    }

    // Panel reveal — count up with scroll
    const targetReveal = Math.floor(reportP * TOTAL_PANELS)
    if (revealRef.current < targetReveal) {
      revealRef.current = Math.min(revealRef.current + 6, targetReveal)
    }

    // Redraw canvas each frame
    const ctx = reportCanvas.getContext('2d')!
    const scanLine = (elapsed * 60) % (GROWS * (CELL_H + GAP_Y))
    drawReport(ctx, reportCanvas.width, reportCanvas.height, revealRef.current, scanLine)
    reportTex.needsUpdate = true

    // Fade in panel material
    if (panelMatRef.current) {
      panelMatRef.current.opacity = lerp(panelMatRef.current.opacity, reportP * 0.94, 0.04)
    }

    // Glow shimmer
    if (glowRef.current) {
      const mat = glowRef.current.material as THREE.MeshBasicMaterial
      mat.opacity = (0.06 + Math.sin(elapsed * 1.8) * 0.02) * reportP
    }

    // Orbiting chips
    chipRefs.current.forEach((chip, i) => {
      if (!chip) return
      const baseAngle = CHIPS[i].angle + elapsed * 0.4
      const r = 2.8
      chip.position.x = Math.cos(baseAngle) * r
      chip.position.y = Math.sin(baseAngle * 0.7) * 0.5
      chip.position.z = Math.sin(baseAngle) * 0.6
      chip.lookAt(0, chip.position.y, 0)
      chip.visible = reportP > 0.25 + i * 0.08
      const mat = chip.material as THREE.MeshBasicMaterial
      mat.opacity = Math.min((reportP - 0.25 - i * 0.08) * 4, 0.9)
    })

    // Outward particles
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      ages[i] += 0.005
      if (ages[i] > 1) {
        // Reset at center
        ages[i] = 0
        positions[i * 3]     = (Math.random() - 0.5) * 0.4
        positions[i * 3 + 1] = (Math.random() - 0.5) * 0.2
        positions[i * 3 + 2] = (Math.random() - 0.5) * 0.2
      } else {
        positions[i * 3]     += velocities[i * 3]
        positions[i * 3 + 1] += velocities[i * 3 + 1]
        positions[i * 3 + 2] += velocities[i * 3 + 2]
      }
    }
    const posAttr = particleGeo.getAttribute('position') as THREE.BufferAttribute
    posAttr.needsUpdate = true

    if (particleRef.current) {
      particleRef.current.rotation.y = elapsed * 0.08
      const mat = particleRef.current.material as THREE.PointsMaterial
      mat.opacity = Math.min(reportP * 1.8, 0.6)
    }

    // Light pulse
    if (lightRef.current) {
      lightRef.current.intensity = reportP * (3 + Math.sin(elapsed * 2.2) * 0.6)
    }
  })

  return (
    <group ref={groupRef} position={[0, 2.5, 6]} visible={false}>

      {/* ── Main report panel ── */}
      <mesh ref={panelRef}>
        <planeGeometry args={[4.2, 2.8]} />
        <meshBasicMaterial
          ref={panelMatRef}
          map={reportTex}
          transparent
          opacity={0}
          side={THREE.DoubleSide}
        />
      </mesh>

      {/* ── Glow plane behind panel ── */}
      <mesh ref={glowRef} position={[0, 0, -0.05]}>
        <planeGeometry args={[4.6, 3.1]} />
        <meshBasicMaterial
          color="#00f0c8"
          transparent
          opacity={0}
          side={THREE.DoubleSide}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </mesh>

      {/* ── Hologram frame ── */}
      <lineSegments geometry={frameEdgesGeo}>
        <lineBasicMaterial color="#00f0c8" transparent opacity={0.45} />
      </lineSegments>

      {/* ── Corner brackets ── */}
      {([[-1, 1], [1, 1], [-1, -1], [1, -1]] as [number,number][]).map(([sx, sy], i) => (
        <group key={i} position={[sx * 2.1, sy * 1.4, 0.01]}>
          <mesh>
            <boxGeometry args={[0.22, 0.018, 0.01]} />
            <meshBasicMaterial color="#00f0c8" transparent opacity={0.8} />
          </mesh>
          <mesh>
            <boxGeometry args={[0.018, 0.22, 0.01]} />
            <meshBasicMaterial color="#00f0c8" transparent opacity={0.8} />
          </mesh>
        </group>
      ))}

      {/* ── Orbiting chip planes (CanvasTexture) ── */}
      {CHIPS.map((chip, i) => (
        <mesh
          key={i}
          ref={el => { chipRefs.current[i] = el }}
          visible={false}
        >
          <planeGeometry args={[0.8, 0.32]} />
          <meshBasicMaterial
            map={chipTextures[i]}
            transparent
            opacity={0}
            side={THREE.DoubleSide}
            depthWrite={false}
          />
        </mesh>
      ))}

      {/* ── Outward particles ── */}
      <points ref={particleRef} geometry={particleGeo}>
        <pointsMaterial
          color="#00f0c8"
          size={0.05}
          transparent
          opacity={0}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          sizeAttenuation
        />
      </points>

      {/* ── Hologram point light ── */}
      <pointLight
        ref={lightRef}
        position={[0, 0, 1]}
        color="#00f0c8"
        intensity={0}
        distance={14}
        decay={2}
      />
    </group>
  )
}
