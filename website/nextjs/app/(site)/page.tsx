'use client'

import { useEffect, useRef, useState, type ReactNode } from 'react'
import Image from 'next/image'
import { API_BASE } from '@/lib/api'
import {
  ArrowRight,
  Wind,
  ScanEye,
  Timer,
  ClipboardX,
  Cpu,
  ShieldCheck,
  Layers,
  MapPin,
  FileText,
  Lock,
  KeyRound,
  Satellite,
  RadioTower,
  Gauge,
  Menu,
  X,
  type LucideIcon,
} from 'lucide-react'

/* ============================================================
   REVEAL ON SCROLL
   ============================================================ */
const Reveal = ({
  children,
  delay = 0,
  className = '',
}: {
  children: ReactNode
  delay?: number
  className?: string
}) => {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            setTimeout(() => el.classList.add('in'), delay)
            io.unobserve(el)
          }
        })
      },
      { threshold: 0.12 },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [delay])
  return (
    <div ref={ref} className={`reveal ${className}`}>
      {children}
    </div>
  )
}

/* ============================================================
   NAV
   ============================================================ */
const NAV_LINKS = [
  { label: 'Technology', href: '#technology' },
  { label: 'Mission', href: '#mission' },
  { label: 'Security', href: '#security' },
  { label: 'Contact', href: '#cta' },
]

const Nav = () => {
  const [scrolled, setScrolled] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header className={`fixed top-0 inset-x-0 z-50 transition-colors ${scrolled || menuOpen ? 'navblur' : ''}`}>
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        <a href="#" className="flex items-center gap-2.5">
          <Image
            src="/logo.png"
            alt="Axalon Systems"
            width={28}
            height={28}
            className="w-7 h-7 rounded-md object-contain"
            priority
          />
          <span className="text-[17px] font-semibold tracking-tight font-display">Axalon Systems</span>
        </a>
        <nav className="hidden md:flex items-center gap-7 text-[13.5px] text-white/65">
          {NAV_LINKS.map((l) => (
            <a key={l.href} href={l.href} className="hover:text-white transition">{l.label}</a>
          ))}
        </nav>
        <div className="hidden sm:flex items-center gap-2.5">
          <a href="#cta" className="btn-primary text-[13.5px] font-medium px-3.5 py-2 rounded-md text-[#020208]">Request a demo flight</a>
        </div>
        <button
          type="button"
          onClick={() => setMenuOpen((v) => !v)}
          aria-label={menuOpen ? 'Close menu' : 'Open menu'}
          className="sm:hidden w-9 h-9 grid place-items-center rounded-md border border-white/10 text-white/80"
        >
          {menuOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
        </button>
      </div>
      {menuOpen && (
        <div className="sm:hidden navblur border-t border-white/5 px-6 py-4 flex flex-col gap-3">
          {NAV_LINKS.map((l) => (
            <a key={l.href} href={l.href} onClick={() => setMenuOpen(false)} className="text-[14px] text-white/75">{l.label}</a>
          ))}
          <a href="#cta" onClick={() => setMenuOpen(false)} className="btn-primary text-center text-[13.5px] font-medium px-3.5 py-2 rounded-md text-[#020208] mt-1">Request a demo flight</a>
        </div>
      )}
    </header>
  )
}

/* ============================================================
   HERO
   ============================================================ */
const HERO_STATS: [string, string][] = [
  ['99.7%', 'Defect detection rate'],
  ['3×', 'Faster than manual'],
  ['50MW+', 'Solar capacity inspected'],
  ['<2hr', 'Flight to report'],
]

const FlightReportMock = () => {
  const findings: [string, string, 'CRITICAL' | 'HIGH' | 'MEDIUM'][] = [
    ['String 14, Row 6', 'Hot-spot — cell level', 'CRITICAL'],
    ['String 22, Row 2', 'Bypass diode failure', 'HIGH'],
    ['String 3, Row 11', 'Vegetation shading', 'MEDIUM'],
    ['String 9, Row 4', 'Junction box heating', 'HIGH'],
  ]
  const tone: Record<string, string> = {
    CRITICAL: 'border-rose-400/25 text-rose-300/90',
    HIGH: 'border-amber-400/25 text-amber-300/90',
    MEDIUM: 'border-[#00f0c8]/25 text-[#5eead4]',
  }
  return (
    <div className="relative rounded-2xl grad-border bg-[#0d0d14]/80 backdrop-blur-xl shadow-[0_50px_120px_-30px_rgba(0,240,200,.22)] overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-white/15" />
          <span className="w-2.5 h-2.5 rounded-full bg-white/15" />
          <span className="w-2.5 h-2.5 rounded-full bg-white/15" />
        </div>
        <div className="font-mono text-[11px] text-white/40 tracking-wide hidden sm:block">flight #2291 / sunfield-solar-40mw</div>
        <div className="flex items-center gap-1.5 text-[10px] text-white/40 font-mono">
          <span className="w-1.5 h-1.5 bg-[#00f0c8] rounded-full pulse-dot" /> ALT 35M
        </div>
      </div>
      <div className="grid grid-cols-12">
        <div className="col-span-4 hidden md:block border-r border-white/5 p-4 space-y-3">
          <div className="text-[10px] uppercase tracking-widest text-white/30 font-mono mb-2">Mission</div>
          <div className="space-y-2 text-[11.5px] text-white/55">
            <div className="flex items-center gap-2"><Satellite className="w-3.5 h-3.5 text-[#00f0c8]" strokeWidth={1.6} /> 18°55′N 72°49′E</div>
            <div className="flex items-center gap-2"><Gauge className="w-3.5 h-3.5 text-[#00f0c8]" strokeWidth={1.6} /> 9.4 m/s ground speed</div>
            <div className="flex items-center gap-2"><RadioTower className="w-3.5 h-3.5 text-[#00f0c8]" strokeWidth={1.6} /> Thermal IR + RGB fused</div>
          </div>
          <div className="pt-4 mt-2 border-t border-white/5">
            <div className="text-[10px] uppercase tracking-widest text-white/30 font-mono mb-2">Coverage</div>
            <div className="px-2.5 py-2 rounded-md bg-gradient-to-br from-[#00f0c8]/10 to-[#6c63ff]/10 border border-white/5">
              <div className="text-[12.5px] font-medium leading-snug">40 MW block, 12,400 panels</div>
              <div className="mt-2 h-1 bg-white/5 rounded-full overflow-hidden">
                <div className="h-full w-[100%] bg-gradient-to-r from-[#00f0c8] to-[#6c63ff]" />
              </div>
              <div className="flex items-center justify-between mt-1.5 font-mono text-[10px] text-white/45">
                <span>Inspection complete</span><span>41 min</span>
              </div>
            </div>
          </div>
        </div>
        <div className="col-span-12 md:col-span-8 p-4">
          <div className="text-[10px] uppercase tracking-widest text-white/30 font-mono mb-2">Detected anomalies · 4</div>
          <div className="space-y-1.5">
            {findings.map(([loc, desc, sev]) => (
              <div key={loc} className="flex items-center justify-between px-2.5 py-2 rounded-lg bg-white/[.02] border border-white/5">
                <div>
                  <div className="text-[12.5px] text-white/85">{loc}</div>
                  <div className="text-[11px] text-white/45">{desc}</div>
                </div>
                <span className={`font-mono text-[10px] px-1.5 py-0.5 rounded chip border ${tone[sev]}`}>{sev}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

const Hero = () => (
  <section className="relative overflow-hidden">
    <div className="absolute inset-0 bg-grid" />
    <div className="absolute inset-0 spotlight" />
    <div className="orb-vio absolute -top-40 -left-40 w-[560px] h-[560px] rounded-full blur-3xl opacity-40 drift" />
    <div className="orb-blue absolute top-1/3 -right-40 w-[520px] h-[520px] rounded-full blur-3xl opacity-30 drift" style={{ animationDelay: '-6s' }} />

    <div className="relative max-w-7xl mx-auto px-6 pt-40 pb-24 grid lg:grid-cols-12 gap-12 items-center">
      <div className="lg:col-span-6">
        <Reveal>
          <div className="inline-flex items-center gap-2 chip rounded-full px-3 py-1.5 mb-6">
            <span className="w-1.5 h-1.5 rounded-full bg-[#00f0c8] pulse-dot" />
            <span className="font-mono text-[11px] uppercase tracking-widest text-white/55">Autonomous inspection platform</span>
          </div>
        </Reveal>
        <Reveal delay={80}>
          <h1 className="font-display text-[42px] sm:text-[54px] leading-[1.03] font-extrabold tracking-tight">
            Solar inspection, done by drones<br className="hidden sm:block" />
            that see <span className="grad-text">what eyes can&apos;t.</span>
          </h1>
        </Reveal>
        <Reveal delay={140}>
          <p className="mt-6 text-[16.5px] text-white/60 leading-relaxed max-w-lg">
            AI-enabled drone systems for precise solar asset inspection. Thermal + RGB fusion, 11-class fault
            detection, and a GPS-tagged report within hours of the flight.
          </p>
        </Reveal>
        <Reveal delay={200}>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <a href="#cta" className="btn-primary inline-flex items-center gap-2 text-[14.5px] font-medium px-5 py-3 rounded-lg text-[#020208]">
              Request a demo flight <ArrowRight className="w-4 h-4" />
            </a>
            <a href="#technology" className="inline-flex items-center gap-2 text-[14.5px] font-medium px-5 py-3 rounded-lg border border-white/10 text-white/75 hover:text-white hover:border-white/20 transition">
              See the technology
            </a>
          </div>
        </Reveal>
        <Reveal delay={260}>
          <div className="mt-14 grid grid-cols-4 gap-4 max-w-lg">
            {HERO_STATS.map(([v, l]) => (
              <div key={l}>
                <div className="font-display text-[20px] sm:text-[24px] font-extrabold grad-text leading-none">{v}</div>
                <div className="mt-1.5 font-mono text-[10px] uppercase tracking-wide text-white/40 leading-tight">{l}</div>
              </div>
            ))}
          </div>
        </Reveal>
      </div>

      <div className="lg:col-span-6">
        <Reveal delay={160} className="relative">
          <div className="relative grad-border rounded-2xl overflow-hidden">
            <FlightReportMock />
          </div>
        </Reveal>
      </div>
    </div>
  </section>
)

/* ============================================================
   PROBLEM
   ============================================================ */
const PROBLEMS: [LucideIcon, string, string][] = [
  [ClipboardX, 'Ground crews don’t scale', 'Manual thermal scans need trained operators walking rows of panels — slow, expensive, and dangerous on live utility-scale sites.'],
  [Wind, 'Weather-dependent, error-prone', 'Handheld thermal cameras miss the sun-angle and altitude consistency automated flights hold to for every panel, every pass.'],
  [ScanEye, 'Subtle faults get missed', 'Cell-level hot-spots and early bypass-diode failures are easy for a human reviewer to overlook across thousands of panels.'],
  [Timer, 'Reports take weeks, not hours', 'By the time a manual report reaches the asset owner, degraded panels have already cost weeks of lost generation.'],
]

const Problem = () => (
  <section className="relative py-24 border-t border-white/5">
    <div className="absolute inset-0 bg-grid opacity-40" />
    <div className="relative max-w-7xl mx-auto px-6">
      <Reveal>
        <div className="max-w-xl">
          <div className="font-mono text-[11px] uppercase tracking-widest text-[#00f0c8] mb-3">Why it matters</div>
          <h2 className="font-display text-[30px] sm:text-[38px] font-extrabold tracking-tight leading-tight">
            Manual solar inspection wasn&apos;t built for utility-scale fleets.
          </h2>
        </div>
      </Reveal>
      <div className="mt-12 grid sm:grid-cols-2 gap-5">
        {PROBLEMS.map(([Icon, title, desc], i) => (
          <Reveal key={title} delay={i * 70}>
            <div className="h-full rounded-xl chip p-5">
              <Icon className="w-5 h-5 text-[#00f0c8]" strokeWidth={1.6} />
              <div className="mt-3.5 font-display font-semibold text-[15.5px]">{title}</div>
              <p className="mt-1.5 text-[13.5px] text-white/55 leading-relaxed">{desc}</p>
            </div>
          </Reveal>
        ))}
      </div>
    </div>
  </section>
)

/* ============================================================
   WORKFLOW ("Mission")
   ============================================================ */
const STEPS: [LucideIcon, string, string, string][] = [
  [MapPin, '01', 'Plan the mission', 'Define inspection boundaries and parameters. The platform auto-generates optimized flight paths with full terrain awareness and no-fly-zone avoidance.'],
  [Cpu, '02', 'Autonomous capture', 'The drone flies the mission unattended. Thermal IR and RGB sensors capture synchronized, multi-layer datasets at 35m altitude.'],
  [FileText, '03', 'AI-powered report', 'YOLO11m processes the dataset. You get an automated report with detected anomalies, severity classification, and GPS-tagged findings.'],
]

const WorkflowSection = () => (
  <section id="mission" className="relative py-24 border-t border-white/5">
    <div className="absolute inset-0 bg-grid opacity-30" />
    <div className="relative max-w-7xl mx-auto px-6">
      <Reveal>
        <div className="max-w-xl">
          <div className="font-mono text-[11px] uppercase tracking-widest text-[#00f0c8] mb-3">How it works</div>
          <h2 className="font-display text-[30px] sm:text-[38px] font-extrabold tracking-tight leading-tight">
            From deployment to decisions in minutes.
          </h2>
        </div>
      </Reveal>
      <div className="mt-12 relative grad-border rounded-2xl overflow-hidden">
        <div className="grid sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-white/5 bg-[#0d0d14]/60 backdrop-blur">
          {STEPS.map(([Icon, num, title, desc], i) => (
            <Reveal key={num} delay={i * 100} className="p-7">
              <div className="flex items-center gap-3">
                <span className="font-display text-[34px] font-extrabold text-[#00f0c8]/15 leading-none">{num}</span>
                <span className="w-8 h-8 rounded-md grid place-items-center bg-[#00f0c8]/8">
                  <Icon className="w-4 h-4 text-[#00f0c8]" strokeWidth={1.6} />
                </span>
              </div>
              <div className="mt-5 font-display font-semibold text-[15.5px]">{title}</div>
              <p className="mt-1.5 text-[13.5px] text-white/55 leading-relaxed">{desc}</p>
            </Reveal>
          ))}
        </div>
      </div>
    </div>
  </section>
)

/* ============================================================
   CAPABILITIES ("Technology")
   ============================================================ */
const CAPABILITIES: [LucideIcon, string, string][] = [
  [Wind, 'Autonomous flight', 'Fully autonomous mission planning and execution, with intelligent path optimization and obstacle avoidance across complex terrain.'],
  [ScanEye, 'Thermal detection', 'YOLO11m trained on 20,000 thermal IR images. Detects 11 fault classes, from cell-level hot-spots to vegetation shading.'],
  [Lock, 'Telemetry security', 'End-to-end encrypted communication with AES-256 protection for every mission and inspection dataset.'],
  [Cpu, 'Onboard AI', 'Edge-compute inference for real-time anomaly detection, CRITICAL / HIGH / MEDIUM / LOW severity classification, and automated reporting.'],
  [Layers, 'Modular payload', 'Hot-swappable sensor bays — thermal IR, RGB, LiDAR, and multispectral. One platform, every inspection use case.'],
]

const Capabilities = () => (
  <section id="technology" className="relative py-24 border-t border-white/5">
    <div className="relative max-w-7xl mx-auto px-6">
      <Reveal>
        <div className="max-w-xl">
          <div className="font-mono text-[11px] uppercase tracking-widest text-[#00f0c8] mb-3">Capabilities</div>
          <h2 className="font-display text-[30px] sm:text-[38px] font-extrabold tracking-tight leading-tight">
            Engineering precision at every layer.
          </h2>
        </div>
      </Reveal>
      <div className="mt-12 grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {CAPABILITIES.map(([Icon, title, desc], i) => (
          <Reveal key={title} delay={i * 70}>
            <div className="h-full rounded-xl chip p-6 hover:bg-white/[.03] transition">
              <span className="inline-flex w-9 h-9 rounded-md items-center justify-center bg-[#00f0c8]/8">
                <Icon className="w-4 h-4 text-[#00f0c8]" strokeWidth={1.6} />
              </span>
              <div className="mt-4 font-display font-semibold text-[15.5px]">{title}</div>
              <p className="mt-1.5 text-[13.5px] text-white/55 leading-relaxed">{desc}</p>
            </div>
          </Reveal>
        ))}
      </div>
    </div>
  </section>
)

/* ============================================================
   SECURITY
   ============================================================ */
const SECURITY_POINTS: [LucideIcon, string, string][] = [
  [KeyRound, 'AES-256 everywhere', 'Every telemetry link and stored dataset is encrypted end-to-end — flight logs, thermal imagery, and generated reports alike.'],
  [ShieldCheck, 'Auditable findings', 'Every detected anomaly carries a GPS tag, timestamp, and confidence score, so findings hold up in a maintenance audit.'],
  [Satellite, 'Isolated mission data', 'Mission and inspection data stay scoped per site — no cross-tenant access, ever.'],
]

const Security = () => (
  <section id="security" className="relative py-24 border-t border-white/5">
    <div className="absolute inset-0 bg-grid opacity-30" />
    <div className="relative max-w-7xl mx-auto px-6">
      <div className="grid lg:grid-cols-12 gap-12 items-center">
        <div className="lg:col-span-5">
          <Reveal>
            <div className="font-mono text-[11px] uppercase tracking-widest text-[#00f0c8] mb-3">Security</div>
            <h2 className="font-display text-[30px] sm:text-[38px] font-extrabold tracking-tight leading-tight">
              Built for utility-grade trust.
            </h2>
            <p className="mt-4 text-[14.5px] text-white/55 leading-relaxed">
              Inspection data drives real maintenance decisions on live assets — it has to be handled like it.
            </p>
          </Reveal>
        </div>
        <div className="lg:col-span-7 grid sm:grid-cols-3 gap-5">
          {SECURITY_POINTS.map(([Icon, title, desc], i) => (
            <Reveal key={title} delay={i * 90}>
              <div className="h-full rounded-xl chip p-5">
                <Icon className="w-5 h-5 text-[#00f0c8]" strokeWidth={1.6} />
                <div className="mt-3.5 font-display font-semibold text-[14.5px]">{title}</div>
                <p className="mt-1.5 text-[12.5px] text-white/55 leading-relaxed">{desc}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </div>
  </section>
)

/* ============================================================
   FAQ
   ============================================================ */
const FAQS: [string, string][] = [
  ['What kind of solar sites can you inspect?', 'Utility-scale and commercial solar farms. Missions are planned per site — terrain, panel layout, and no-fly zones are accounted for before the first flight.'],
  ['How long does a flight take?', 'Depends on site size — a 40 MW block typically clears in under an hour of flight time, with the full report following within a couple of hours.'],
  ['What’s in the report?', 'Every detected anomaly with its severity (CRITICAL / HIGH / MEDIUM / LOW), GPS tag, thermal + RGB imagery, and a confidence score.'],
  ['Do we need our own drone hardware?', 'No — Axalon operates the flight. You get the report; the sensor and flight-ops side is handled end-to-end.'],
  ['Is our inspection data secure?', 'Yes — AES-256 encryption end-to-end, and mission data stays scoped to your site only.'],
]

const FAQ = () => (
  <section className="relative py-24 border-t border-white/5">
    <div className="relative max-w-3xl mx-auto px-6">
      <Reveal>
        <div className="text-center mb-12">
          <div className="font-mono text-[11px] uppercase tracking-widest text-[#00f0c8] mb-3">FAQ</div>
          <h2 className="font-display text-[30px] sm:text-[38px] font-extrabold tracking-tight">Questions, answered.</h2>
        </div>
      </Reveal>
      <div className="space-y-2.5">
        {FAQS.map(([q, a], i) => (
          <Reveal key={q} delay={i * 50}>
            <details className="group chip rounded-xl px-5 py-4">
              <summary className="flex items-center justify-between cursor-pointer list-none text-[14.5px] font-medium text-white/85">
                {q}
                <span className="acc-icon text-white/40 text-lg leading-none">+</span>
              </summary>
              <p className="mt-3 text-[13.5px] text-white/55 leading-relaxed">{a}</p>
            </details>
          </Reveal>
        ))}
      </div>
    </div>
  </section>
)

/* ============================================================
   DEMO REQUEST FORM
   ============================================================ */
function DemoRequestForm() {
  const [form, setForm] = useState({ name: '', email: '', company: '', message: '' })
  const [status, setStatus] = useState<'idle' | 'submitting' | 'success' | 'error'>('idle')

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.name.trim() || !form.email.trim() || !form.company.trim()) return
    setStatus('submitting')
    try {
      const res = await fetch(`${API_BASE}/api/demo-requests`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      if (!res.ok) throw new Error('Request failed')
      setStatus('success')
    } catch (err) {
      console.error('[DemoRequestForm] submit failed:', err)
      setStatus('error')
    }
  }

  if (status === 'success') {
    return (
      <div className="rounded-2xl border border-white/15 bg-[#0d0d14]/60 backdrop-blur p-6 md:p-7 text-center">
        <div className="text-4xl mb-3">✓</div>
        <div className="text-white font-semibold text-lg">Request received</div>
        <div className="mt-2 text-white/55 text-sm">We&apos;ll reach out within one business day to schedule your flight.</div>
      </div>
    )
  }

  const fieldBase = 'w-full rounded-lg border border-white/10 bg-white/[.04] px-3 py-2 text-[14px] text-white placeholder:text-white/25 focus:outline-none focus:border-[#00f0c8]/60 transition'

  return (
    <div className="rounded-2xl border border-white/15 bg-[#0d0d14]/60 backdrop-blur p-6 md:p-7">
      <div className="font-mono text-[10.5px] uppercase tracking-widest text-white/50 mb-5">Request a demo flight</div>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block font-mono text-[10px] uppercase tracking-widest text-white/45 mb-1">Full name *</label>
            <input type="text" required value={form.name} onChange={set('name')} className={fieldBase} />
          </div>
          <div>
            <label className="block font-mono text-[10px] uppercase tracking-widest text-white/45 mb-1">Company *</label>
            <input type="text" required value={form.company} onChange={set('company')} className={fieldBase} />
          </div>
        </div>
        <div>
          <label className="block font-mono text-[10px] uppercase tracking-widest text-white/45 mb-1">Work email *</label>
          <input type="email" required value={form.email} onChange={set('email')} className={fieldBase} />
        </div>
        <div>
          <label className="block font-mono text-[10px] uppercase tracking-widest text-white/45 mb-1">Site size / location</label>
          <textarea rows={3} value={form.message} onChange={set('message')} className={`${fieldBase} resize-none`} />
        </div>
        {status === 'error' && (
          <p className="text-red-400 text-sm">Something went wrong — email us at contact@axalonsystems.com</p>
        )}
        <button
          type="submit"
          disabled={status === 'submitting'}
          className="w-full rounded-lg btn-primary disabled:opacity-60 px-4 py-2.5 text-[14px] font-semibold text-[#020208] transition"
        >
          {status === 'submitting' ? 'Sending…' : 'Request a demo flight'}
        </button>
        <p className="text-center font-mono text-[10.5px] text-white/35">
          Or email{' '}
          <a href="mailto:contact@axalonsystems.com" className="underline text-white/55">contact@axalonsystems.com</a>
        </p>
      </form>
    </div>
  )
}

/* ============================================================
   FOOTER CTA
   ============================================================ */
const FooterCTA = () => (
  <section id="cta" className="relative py-24 border-t border-white/5">
    <div className="absolute inset-0 bg-grid opacity-50" />
    <div className="relative max-w-7xl mx-auto px-6 grid lg:grid-cols-12 gap-12 items-center">
      <div className="lg:col-span-6">
        <Reveal>
          <div className="font-mono text-[11px] uppercase tracking-widest text-[#00f0c8] mb-3">Ready to inspect?</div>
          <h2 className="font-display text-[30px] sm:text-[40px] font-extrabold tracking-tight leading-tight">
            Let us fly your site — <span className="grad-text">no commitment.</span>
          </h2>
          <p className="mt-4 text-[15px] text-white/55 leading-relaxed max-w-md">
            Full fault report within hours of the flight. See exactly what the platform finds before you decide anything.
          </p>
          <div className="mt-8 grid grid-cols-3 gap-6 max-w-sm">
            {HERO_STATS.slice(0, 3).map(([v, l]) => (
              <div key={l}>
                <div className="font-display text-[18px] font-extrabold grad-text leading-none">{v}</div>
                <div className="mt-1.5 font-mono text-[9.5px] uppercase tracking-wide text-white/40 leading-tight">{l}</div>
              </div>
            ))}
          </div>
        </Reveal>
      </div>
      <div className="lg:col-span-6">
        <Reveal delay={100}>
          <DemoRequestForm />
        </Reveal>
      </div>
    </div>
  </section>
)

/* ============================================================
   FOOTER
   ============================================================ */
const SiteFooter = () => (
  <footer className="relative border-t border-white/5 py-10">
    <div className="max-w-7xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
      <div className="flex items-center gap-2.5">
        <Image src="/logo.png" alt="Axalon Systems" width={22} height={22} className="w-[22px] h-[22px] object-contain" />
        <span className="text-[13.5px] font-medium text-white/60 font-display">Axalon Systems</span>
      </div>
      <div className="font-mono text-[11.5px] text-white/35">Mumbai, India</div>
      <div className="text-[12.5px] text-white/35">© {new Date().getFullYear()} Axalon Systems. All rights reserved.</div>
    </div>
  </footer>
)

/* ============================================================
   SCOPED STYLES
   ============================================================ */
const MarketingStyles = () => (
  <style>{`
    .axalon-root {
      background: #050508;
      color: #e8e8f0;
      font-family: 'Space Grotesk', ui-sans-serif, system-ui, sans-serif;
      -webkit-font-smoothing: antialiased;
      scroll-behavior: smooth;
    }
    .axalon-root .font-display { font-family: 'Syne', ui-sans-serif, sans-serif; }
    .axalon-root .font-mono { font-family: 'Space Grotesk', ui-monospace, monospace; }

    .axalon-root .bg-grid {
      background-image:
        linear-gradient(rgba(108,99,255,.05) 1px, transparent 1px),
        linear-gradient(90deg, rgba(0,240,200,.05) 1px, transparent 1px);
      background-size: 72px 72px;
    }

    .axalon-root .orb-vio  { background: radial-gradient(circle, rgba(108,99,255,.25), rgba(108,99,255,0) 70%); }
    .axalon-root .orb-blue { background: radial-gradient(circle, rgba(0,240,200,.20), rgba(0,240,200,0) 70%); }

    .axalon-root .spotlight {
      background:
        radial-gradient(55% 50% at 15% 0%, rgba(0,240,200,.10), transparent 60%),
        radial-gradient(45% 45% at 85% 10%, rgba(108,99,255,.14), transparent 60%);
    }

    @keyframes ax-drift { 0%,100% { transform: translate(0,0); } 50% { transform: translate(20px,-14px); } }
    .axalon-root .drift { animation: ax-drift 16s ease-in-out infinite; }

    @keyframes ax-pulseDot { 0%,100% { opacity:.5; } 50% { opacity:1; } }
    .axalon-root .pulse-dot { animation: ax-pulseDot 2.4s ease-in-out infinite; }

    .axalon-root .reveal { opacity:0; transform:translateY(12px); transition: opacity .7s cubic-bezier(.2,.7,.2,1), transform .7s cubic-bezier(.2,.7,.2,1); }
    .axalon-root .reveal.in { opacity:1; transform:none; }

    .axalon-root .grad-text {
      background: linear-gradient(90deg,#5eead4 0%, #a5a1ff 70%);
      -webkit-background-clip:text; background-clip:text; color:transparent;
    }

    .axalon-root .grad-border { position:relative; }
    .axalon-root .grad-border::before {
      content:""; position:absolute; inset:0; padding:1px; border-radius:inherit;
      background: linear-gradient(135deg, rgba(0,240,200,.5), rgba(108,99,255,.45) 40%, rgba(255,255,255,.04) 80%);
      -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
      -webkit-mask-composite: xor; mask-composite: exclude;
      pointer-events:none;
    }

    .axalon-root .btn-primary {
      background: linear-gradient(135deg, #00f0c8 0%, #6c63ff 100%);
      box-shadow: inset 0 1px 0 rgba(255,255,255,.22), 0 8px 30px -10px rgba(0,240,200,.4);
    }
    .axalon-root .btn-primary:hover { filter: brightness(1.08); }

    .axalon-root .chip { border:1px solid rgba(255,255,255,.08); background:rgba(255,255,255,.02); }
    .axalon-root .navblur { backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px); background:rgba(5,5,8,.75); border-bottom:1px solid rgba(255,255,255,.06); }

    .axalon-root details[open] .acc-icon { transform: rotate(45deg); }
    .axalon-root .acc-icon { transition: transform .2s ease; }
  `}</style>
)

/* ============================================================
   ROOT
   ============================================================ */
export default function Home() {
  return (
    <div className="axalon-root min-h-screen relative">
      <MarketingStyles />
      <Nav />
      <Hero />
      <Problem />
      <WorkflowSection />
      <Capabilities />
      <Security />
      <FAQ />
      <FooterCTA />
      <SiteFooter />
    </div>
  )
}
