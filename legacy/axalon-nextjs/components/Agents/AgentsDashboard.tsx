'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { API_BASE } from '@/lib/api'

// ── Types ─────────────────────────────────────────────────────────────────────

type SessionStatus  = 'running' | 'done' | 'stopped' | 'limit' | 'unknown'
type TaskStatus     = 'pending' | 'running' | 'done' | 'failed' | 'stopped'
type PhaseStatus    = 'pending' | 'running' | 'done' | 'failed'
type SidebarTab     = 'sessions' | 'pipelines'
type RunMode        = 'agent' | 'pipeline'

type AgentType  = { id: string; name: string; icon: string; description: string; model: string; color: string }
type Session    = { id: string; status: SessionStatus; model: string; task: string; started_at: string; size_bytes: number }
type PlanTask   = { id: string; name: string; priority: string; effort: string; status: TaskStatus; session_id: string | null; started_at: string | null; completed_at: string | null }
type PlanState  = { auto_run: boolean; current_session_id: string | null; tasks: PlanTask[] }

type PipelinePhase = {
  id: string; name: string; icon: string; color: string
  agent_type: string; description: string
  status: PhaseStatus; session_id: string | null
  started_at: string | null; completed_at: string | null
}
type Pipeline = {
  id: string; task: string; model: string
  status: 'running' | 'done' | 'failed'
  current_phase: string | null
  created_at: string
  phases: PipelinePhase[]
}

// ── Static fallback agent types ───────────────────────────────────────────────

const FALLBACK_TYPES: AgentType[] = [
  { id: 'coder',       name: 'Coder',       icon: '⚡', description: 'Feature dev, refactoring',   model: 'qwen2.5-coder:7b', color: '#00d4b8' },
  { id: 'reviewer',    name: 'Reviewer',    icon: '🔍', description: 'Code review, security',       model: 'qwen2.5-coder:7b', color: '#f0883e' },
  { id: 'tester',      name: 'Tester',      icon: '🧪', description: 'Tests, 80% coverage',         model: 'qwen2.5-coder:7b', color: '#3fb950' },
  { id: 'ml-engineer', name: 'ML Engineer', icon: '🤖', description: 'YOLO eval, augmentation',     model: 'qwen2.5-coder:7b', color: '#d2a8ff' },
  { id: 'frontend',    name: 'Frontend',    icon: '🎨', description: 'Next.js, React, CSS',         model: 'qwen2.5-coder:7b', color: '#58a6ff' },
  { id: 'planner',     name: 'Planner',     icon: '📋', description: 'Task breakdown, roadmap',     model: 'qwen2.5-coder:7b', color: '#d29922' },
  { id: 'devops',      name: 'DevOps',      icon: '🚀', description: 'Deploy, CI/CD, scripts',      model: 'qwen2.5-coder:7b', color: '#f85149' },
]

const FALLBACK_PHASES = [
  { id: 'think',     name: 'Think',     icon: '🧠', color: '#d2a8ff' },
  { id: 'plan',      name: 'Plan',      icon: '📋', color: '#d29922' },
  { id: 'implement', name: 'Implement', icon: '⚡', color: '#00d4b8' },
  { id: 'review',    name: 'Review',    icon: '🔍', color: '#f0883e' },
  { id: 'test',      name: 'Test',      icon: '🧪', color: '#3fb950' },
  { id: 'refine',    name: 'Refine',    icon: '✨', color: '#58a6ff' },
]

// ── Helpers ───────────────────────────────────────────────────────────────────

function lineStyle(line: string): React.CSSProperties {
  if (/^\[iter \d+\/\d+\]/.test(line)) return { color: '#484f58' }
  if (/^Thought:/.test(line))           return { color: '#c9d1d9' }
  if (/^Action:/.test(line))            return { color: '#58a6ff', fontWeight: '600' }
  if (/^Input:/.test(line))             return { color: '#79c0ff' }
  if (/^Observation/.test(line))        return { color: '#8b949e' }
  if (/✓/.test(line))                   return { color: '#3fb950', fontWeight: '600' }
  if (/⚠/.test(line))                   return { color: '#d29922' }
  if (/ERROR|error/.test(line))         return { color: '#f85149' }
  if (/^\s+\$/.test(line))             return { color: '#00d4b8' }
  if (/\[loop-break\]/.test(line))     return { color: '#f85149', fontWeight: '600' }
  if (/\[auto-yes\]/.test(line))       return { color: '#484f58', fontStyle: 'italic' }
  return { color: '#8b949e' }
}

function timeSince(iso: string): string {
  const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  return `${Math.floor(m / 60)}h ${m % 60}m ago`
}

function agentTypeFromId(id: string, types: AgentType[]): AgentType | null {
  return types.find(t => t.id === (id.split('_').pop() ?? '')) ?? null
}

const PRIORITY_COLOR: Record<string, string> = { P0: '#f85149', P1: '#d29922', P2: '#58a6ff', P3: '#484f58' }
const TASK_STATUS_CLASS: Record<TaskStatus, string> = { pending: 'pending', running: 'running', done: 'done', failed: 'failed', stopped: 'stopped' }

// ── Plan Board ────────────────────────────────────────────────────────────────

function PlanBoard({ plan, model, onRunNext, onToggleAuto, onReset, onDone, onOpenSession }: {
  plan: PlanState | null; model: string
  onRunNext: () => void; onToggleAuto: () => void
  onReset: (id: string) => void; onDone: (id: string) => void
  onOpenSession: (id: string) => void
}) {
  if (!plan) return null
  const done  = plan.tasks.filter(t => t.status === 'done').length
  const total = plan.tasks.length
  return (
    <div className="ac-plan-board">
      <div className="ac-plan-header">
        <div className="ac-plan-progress-wrap">
          <span className="ac-plan-label">Plan</span>
          <span className="ac-plan-count">{done}/{total}</span>
          <div className="ac-progress-bar"><div className="ac-progress-fill" style={{ width: `${(done / total) * 100}%` }} /></div>
        </div>
        <div className="ac-plan-actions">
          <button className="ac-btn" disabled={plan.tasks.some(t => t.status === 'running') || done === total} onClick={onRunNext}>▶ Run Next</button>
          <button className={`ac-btn${plan.auto_run ? ' primary' : ''}`} onClick={onToggleAuto}>{plan.auto_run ? '⏹ Auto ON' : '⬡ Auto'}</button>
        </div>
      </div>
      <div className="ac-tasks">
        {plan.tasks.map(t => (
          <div key={t.id} className={`ac-task-chip${t.status === 'running' ? ' running' : ''}${t.session_id ? ' clickable' : ''}`} onClick={() => t.session_id && onOpenSession(t.session_id)} title={t.name}>
            <span className={`ac-task-dot ${TASK_STATUS_CLASS[t.status]}`} />
            <span className="ac-task-priority" style={{ color: PRIORITY_COLOR[t.priority] }}>{t.priority}</span>
            <span className="ac-task-name">{t.name}</span>
            {t.status === 'done'    && <button className="ac-task-btn" onClick={e => { e.stopPropagation(); onReset(t.id) }}>↺</button>}
            {t.status === 'pending' && <button className="ac-task-btn" onClick={e => { e.stopPropagation(); onDone(t.id) }}>✓</button>}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Pipeline Phase Track ──────────────────────────────────────────────────────

function PhaseTrack({ pipeline, onSelectPhase, activePhaseId }: {
  pipeline: Pipeline; onSelectPhase: (phaseId: string, sid: string) => void; activePhaseId: string | null
}) {
  return (
    <div style={{ padding: '12px 18px', background: '#0d1117', borderBottom: '1px solid #1c2128' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
        <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: '0.1em', color: '#484f58', textTransform: 'uppercase' }}>Pipeline</span>
        <span style={{ fontSize: 11, color: '#8b949e', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{pipeline.task}</span>
        <span style={{ fontSize: 10, fontWeight: 700, color: pipeline.status === 'done' ? '#3fb950' : pipeline.status === 'failed' ? '#f85149' : '#00d4b8' }}>
          {pipeline.status.toUpperCase()}
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center' }}>
        {pipeline.phases.map((phase, i) => (
          <div key={phase.id} style={{ display: 'flex', alignItems: 'center', flex: 1 }}>
            <button
              onClick={() => phase.session_id && onSelectPhase(phase.id, phase.session_id)}
              disabled={!phase.session_id}
              style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
                padding: '6px 10px', borderRadius: 8, border: '1px solid',
                borderColor: activePhaseId === phase.id ? phase.color : phase.status === 'pending' ? '#21262d' : phase.color + '66',
                background: phase.status === 'running' ? phase.color + '15' : phase.status === 'done' ? phase.color + '10' : '#0d1117',
                cursor: phase.session_id ? 'pointer' : 'default',
                transition: 'all 0.15s', flex: 1,
                boxShadow: phase.status === 'running' ? `0 0 12px ${phase.color}30` : 'none',
              }}
              title={phase.description}
            >
              <span style={{ fontSize: 16, filter: phase.status === 'pending' ? 'grayscale(1) opacity(0.3)' : 'none' }}>{phase.icon}</span>
              <span style={{ fontSize: 10, fontWeight: 700, color: phase.status === 'pending' ? '#484f58' : phase.color }}>{phase.name}</span>
              <span style={{
                width: 6, height: 6, borderRadius: '50%',
                background: phase.status === 'done' ? '#3fb950' : phase.status === 'failed' ? '#f85149' : phase.status === 'running' ? phase.color : '#21262d',
                boxShadow: phase.status === 'running' ? `0 0 6px ${phase.color}` : 'none',
                animation: phase.status === 'running' ? 'pulse 1.5s ease-in-out infinite' : 'none',
              }} />
            </button>
            {i < pipeline.phases.length - 1 && (
              <div style={{ width: 20, height: 1, flexShrink: 0, background: pipeline.phases[i + 1].status !== 'pending' ? '#30363d' : '#1c2128' }} />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main Dashboard ────────────────────────────────────────────────────────────

export function AgentsDashboard() {
  const [sessions, setSessions]               = useState<Session[]>([])
  const [pipelines, setPipelines]             = useState<Pipeline[]>([])
  const [plan, setPlan]                       = useState<PlanState | null>(null)
  const [activeId, setActiveId]               = useState<string | null>(null)
  const [activePipeline, setActivePipeline]   = useState<Pipeline | null>(null)
  const [activePhaseId, setActivePhaseId]     = useState<string | null>(null)
  const [logLines, setLogLines]               = useState<string[]>([])
  const [models, setModels]                   = useState<string[]>(['qwen2.5-coder:7b', 'qwen2.5-coder:1.5b'])
  const [agentTypes, setAgentTypes]           = useState<AgentType[]>(FALLBACK_TYPES)
  const [agentType, setAgentType]             = useState('coder')
  const [task, setTask]                       = useState('')
  const [model, setModel]                     = useState('qwen2.5-coder:7b')
  const [launching, setLaunching]             = useState(false)
  const [autoScroll, setAutoScroll]           = useState(true)
  const [sidebarTab, setSidebarTab]           = useState<SidebarTab>('sessions')
  const [runMode, setRunMode]                 = useState<RunMode>('agent')

  const logRef  = useRef<HTMLDivElement>(null)
  const sseRef  = useRef<EventSource | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── Fetchers ──────────────────────────────────────────────────────────────

  const fetchSessions  = useCallback(async () => { try { const r = await fetch(`${API_BASE}/agents/sessions`); if (r.ok) setSessions(await r.json()) } catch {} }, [])
  const fetchPlan      = useCallback(async () => { try { const r = await fetch(`${API_BASE}/agents/plan`); if (r.ok) setPlan(await r.json()) } catch {} }, [])
  const fetchPipelines = useCallback(async () => { try { const r = await fetch(`${API_BASE}/agents/pipelines`); if (r.ok) setPipelines(await r.json()) } catch {} }, [])

  const fetchModels = useCallback(async () => {
    try { const r = await fetch(`${API_BASE}/agents/models`); if (r.ok) { const d = await r.json(); if (d.models?.length) setModels(d.models) } } catch {}
  }, [])

  const fetchAgentTypes = useCallback(async () => {
    try { const r = await fetch(`${API_BASE}/agents/types`); if (r.ok) { const d: AgentType[] = await r.json(); if (d.length) setAgentTypes(d) } } catch {}
  }, [])

  useEffect(() => {
    fetchSessions(); fetchPlan(); fetchPipelines(); fetchModels(); fetchAgentTypes()
    pollRef.current = setInterval(() => { fetchSessions(); fetchPlan(); fetchPipelines() }, 3000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [fetchSessions, fetchPlan, fetchPipelines, fetchModels, fetchAgentTypes])

  // Keep activePipeline in sync with polled data
  useEffect(() => {
    if (!activePipeline) return
    const updated = pipelines.find(p => p.id === activePipeline.id)
    if (updated) setActivePipeline(updated)
  }, [pipelines, activePipeline])

  // ── Auto-scroll ───────────────────────────────────────────────────────────

  useEffect(() => {
    if (autoScroll && logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [logLines, autoScroll])

  // ── Log streaming ─────────────────────────────────────────────────────────

  const openSession = useCallback((id: string) => {
    setActiveId(id)
    setLogLines([])
    setAutoScroll(true)
    if (sseRef.current) { sseRef.current.close(); sseRef.current = null }
    const es = new EventSource(`${API_BASE}/agents/sessions/${encodeURIComponent(id)}/log`)
    sseRef.current = es
    es.onmessage = e => { try { setLogLines(prev => [...prev, JSON.parse(e.data)]) } catch {} }
    es.addEventListener('done', () => { es.close(); sseRef.current = null; fetchSessions(); fetchPlan(); fetchPipelines() })
    es.onerror = () => { es.close(); sseRef.current = null }
  }, [fetchSessions, fetchPlan, fetchPipelines])

  const hasAutoOpened = useRef(false)
  useEffect(() => {
    if (!hasAutoOpened.current && sessions.length > 0) {
      hasAutoOpened.current = true
      const s = sessions.find(s => s.status === 'running') ?? sessions[0]
      openSession(s.id)
    }
  }, [sessions, openSession])

  useEffect(() => {
    if (!plan?.current_session_id) return
    const planSess = sessions.find(s => s.id === plan.current_session_id)
    if (planSess?.status === 'running' && plan.current_session_id !== activeId)
      openSession(plan.current_session_id)
  }, [plan?.current_session_id, sessions, activeId, openSession])

  const handleScroll = () => {
    const el = logRef.current
    if (el) setAutoScroll(el.scrollHeight - el.scrollTop - el.clientHeight < 40)
  }

  // ── Actions ───────────────────────────────────────────────────────────────

  const launchAgent = async () => {
    if (!task.trim() || launching) return
    setLaunching(true)
    try {
      const r = await fetch(`${API_BASE}/agents/run`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: task.trim(), model, agent_type: agentType, auto_yes: true }),
      })
      if (r.ok) { const d = await r.json(); setTask(''); await fetchSessions(); openSession(d.session_id); setSidebarTab('sessions') }
    } finally { setLaunching(false) }
  }

  const launchPipeline = async () => {
    if (!task.trim() || launching) return
    setLaunching(true)
    try {
      const r = await fetch(`${API_BASE}/agents/pipeline`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: task.trim(), model }),
      })
      if (r.ok) {
        const pl: Pipeline = await r.json()
        setTask('')
        await fetchPipelines()
        setActivePipeline(pl)
        setSidebarTab('pipelines')
        const first = pl.phases.find(p => p.session_id)
        if (first?.session_id) { openSession(first.session_id); setActivePhaseId(first.id) }
      }
    } finally { setLaunching(false) }
  }

  const launchTask = runMode === 'pipeline' ? launchPipeline : launchAgent

  const killSession  = async (id: string) => { await fetch(`${API_BASE}/agents/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' }); fetchSessions(); fetchPlan() }
  const runNextPlan  = async () => { await fetch(`${API_BASE}/agents/plan/run-next`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model }) }); fetchPlan(); fetchSessions() }
  const toggleAuto   = async () => { await fetch(`${API_BASE}/agents/plan/toggle-auto`, { method: 'POST' }); fetchPlan() }
  const resetTask    = async (id: string) => { await fetch(`${API_BASE}/agents/plan/${id}/reset`, { method: 'POST' }); fetchPlan() }
  const markDone     = async (id: string) => { await fetch(`${API_BASE}/agents/plan/${id}/done`, { method: 'POST' }); fetchPlan() }

  const rerunPhase = async (pipelineId: string, phaseId: string) => {
    const r = await fetch(`${API_BASE}/agents/pipeline/${pipelineId}/phase/${phaseId}/rerun`, { method: 'POST' })
    if (r.ok) { const pl: Pipeline = await r.json(); setActivePipeline(pl); fetchPipelines() }
  }

  const activeSession = sessions.find(s => s.id === activeId)
  const activeType    = activeSession ? agentTypeFromId(activeSession.id, agentTypes) : null

  const placeholder = runMode === 'pipeline'
    ? 'Describe the task to chain through all 6 phases… (🧠→📋→⚡→🔍→🧪→✨)'
    : `Task for ${agentTypes.find(t => t.id === agentType)?.name ?? 'Agent'}… (Enter to run)`

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <PlanBoard plan={plan} model={model} onRunNext={runNextPlan} onToggleAuto={toggleAuto} onReset={resetTask} onDone={markDone} onOpenSession={openSession} />

      <div className="ac-body" style={{ flex: 1, overflow: 'hidden' }}>

        {/* ── Sidebar ── */}
        <aside className="ac-sidebar">
          <div style={{ display: 'flex', borderBottom: '1px solid #1c2128' }}>
            {(['sessions', 'pipelines'] as SidebarTab[]).map(tab => (
              <button key={tab} onClick={() => setSidebarTab(tab)} style={{
                flex: 1, padding: '10px 0', fontSize: 10, fontWeight: 800, letterSpacing: '0.08em',
                textTransform: 'uppercase', border: 'none', cursor: 'pointer', transition: 'all 0.15s',
                background: sidebarTab === tab ? '#161b22' : 'transparent',
                color: sidebarTab === tab ? '#00d4b8' : '#484f58',
                borderBottom: sidebarTab === tab ? '2px solid #00d4b8' : '2px solid transparent',
                fontFamily: 'inherit',
              }}>
                {tab === 'sessions' ? `Sessions ${sessions.length}` : `Pipelines ${pipelines.length}`}
              </button>
            ))}
          </div>

          <div className="ac-sessions">
            {sidebarTab === 'sessions' && (
              sessions.length === 0
                ? <div className="ac-no-sessions">No sessions yet.<br />Pick an agent type and run a task.</div>
                : sessions.map(s => {
                    const sType = agentTypeFromId(s.id, agentTypes)
                    return (
                      <div key={s.id}
                        className={`ac-session status-${s.status}${activeId === s.id ? ' active' : ''}`}
                        onClick={() => { openSession(s.id); setActivePipeline(null) }}
                      >
                        <div className="ac-session-top">
                          <span className={`ac-status-dot ${s.status}`} />
                          <span className="ac-session-id">{s.id}</span>
                          {sType && <span className="ac-type-tag" style={{ color: sType.color }}>{sType.icon}</span>}
                        </div>
                        <div className="ac-session-meta">{s.model} · {timeSince(s.started_at)}</div>
                        {s.task && <div className="ac-session-task">{s.task}</div>}
                      </div>
                    )
                  })
            )}

            {sidebarTab === 'pipelines' && (
              pipelines.length === 0
                ? <div className="ac-no-sessions">No pipelines yet.<br />Switch to Pipeline mode and run a task.</div>
                : pipelines.map(pl => (
                    <div key={pl.id}
                      className={`ac-session${activePipeline?.id === pl.id ? ' active' : ''}`}
                      onClick={() => {
                        setActivePipeline(pl)
                        const running = pl.phases.find(p => p.status === 'running') ?? pl.phases.find(p => p.session_id)
                        if (running) { openSession(running.session_id!); setActivePhaseId(running.id) }
                      }}
                    >
                      <div className="ac-session-top">
                        <span className={`ac-status-dot ${pl.status === 'running' ? 'running' : pl.status === 'done' ? 'done' : 'stopped'}`} />
                        <span className="ac-session-id">{pl.id}</span>
                        <span className="ac-type-tag">🔄</span>
                      </div>
                      <div className="ac-session-meta">{timeSince(pl.created_at)}</div>
                      <div className="ac-session-task">{pl.task}</div>
                      <div style={{ display: 'flex', gap: 3, marginTop: 6, paddingLeft: 14 }}>
                        {pl.phases.map(ph => (
                          <span key={ph.id} title={ph.name} style={{
                            width: 18, height: 18, borderRadius: 4, fontSize: 9,
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            background: ph.status === 'done' ? ph.color + '22' : ph.status === 'running' ? ph.color + '33' : '#21262d',
                            border: `1px solid ${ph.status !== 'pending' ? ph.color + '66' : '#21262d'}`,
                            color: ph.status === 'pending' ? '#484f58' : ph.color,
                            boxShadow: ph.status === 'running' ? `0 0 6px ${ph.color}50` : 'none',
                          }}>{ph.icon}</span>
                        ))}
                      </div>
                    </div>
                  ))
            )}
          </div>
        </aside>

        {/* ── Main panel ── */}
        <div className="ac-main">

          {/* Phase track — shown when a pipeline is selected */}
          {activePipeline && (
            <PhaseTrack
              pipeline={activePipeline}
              activePhaseId={activePhaseId}
              onSelectPhase={(phaseId, sid) => { openSession(sid); setActivePhaseId(phaseId) }}
            />
          )}

          {/* Log header */}
          <div className="ac-log-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
              <span className="ac-log-title">{activeSession ? activeSession.id : 'No session selected'}</span>
              {activeType && <span className="ac-log-type" style={{ color: activeType.color }}>{activeType.icon} {activeType.name}</span>}
              {activePipeline && activePhaseId && (() => {
                const ph = activePipeline.phases.find(p => p.id === activePhaseId)
                return ph ? <span style={{ fontSize: 10, color: ph.color, fontWeight: 700, background: ph.color + '15', padding: '2px 8px', borderRadius: 4, border: `1px solid ${ph.color}40` }}>{ph.icon} {ph.name}</span> : null
              })()}
            </div>
            <div className="ac-log-actions">
              {!autoScroll && (
                <button className="ac-btn" onClick={() => { setAutoScroll(true); logRef.current?.scrollTo(0, logRef.current.scrollHeight) }}>↓ Bottom</button>
              )}
              {activePipeline && activePhaseId && (
                <button className="ac-btn" onClick={() => rerunPhase(activePipeline.id, activePhaseId)}>↺ Rerun Phase</button>
              )}
              {activeSession?.status === 'running' && (
                <button className="ac-btn danger" onClick={() => killSession(activeSession.id)}>■ Kill</button>
              )}
            </div>
          </div>

          {/* Log body */}
          {!activeSession
            ? <div className="ac-log-empty"><div className="ac-log-empty-icon">⬡</div><div>Select a session or launch a task below</div></div>
            : <div ref={logRef} className="ac-log-body" onScroll={handleScroll}>
                {logLines.map((line, i) => <div key={i} className="ac-log-line" style={lineStyle(line)}>{line || ' '}</div>)}
              </div>
          }

          {/* Runner */}
          <div className="ac-runner">
            {/* Mode toggle */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ display: 'flex', background: '#080c10', border: '1px solid #21262d', borderRadius: 8, overflow: 'hidden', flexShrink: 0 }}>
                {(['agent', 'pipeline'] as RunMode[]).map(m => (
                  <button key={m} onClick={() => setRunMode(m)} style={{
                    padding: '5px 14px', border: 'none', cursor: 'pointer', fontSize: 11, fontWeight: 700,
                    fontFamily: 'inherit', transition: 'all 0.15s',
                    background: runMode === m ? (m === 'pipeline' ? '#d2a8ff22' : '#00d4b822') : 'transparent',
                    color: runMode === m ? (m === 'pipeline' ? '#d2a8ff' : '#00d4b8') : '#484f58',
                  }}>
                    {m === 'agent' ? '⚡ Agent' : '🔄 Pipeline'}
                  </button>
                ))}
              </div>
              {runMode === 'pipeline' && (
                <span style={{ fontSize: 10, color: '#484f58', lineHeight: 1.4 }}>
                  Chains 6 phases: Think → Plan → Implement → Review → Test → Refine
                </span>
              )}
            </div>

            {/* Agent type cards — agent mode */}
            {runMode === 'agent' && (
              <div className="ac-type-row">
                {agentTypes.map(t => (
                  <button key={t.id}
                    className={`ac-type-card${agentType === t.id ? ' active' : ''}`}
                    style={{ '--tc': t.color } as React.CSSProperties}
                    onClick={() => setAgentType(t.id)}
                    title={t.description}
                  >
                    <span className="ac-type-card-icon">{t.icon}</span>
                    <span className="ac-type-card-name">{t.name}</span>
                    <span className="ac-type-card-desc">{t.description}</span>
                  </button>
                ))}
              </div>
            )}

            {/* Phase preview — pipeline mode */}
            {runMode === 'pipeline' && (
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                {FALLBACK_PHASES.map((ph, i) => (
                  <div key={ph.id} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div style={{
                      display: 'flex', alignItems: 'center', gap: 5,
                      padding: '4px 10px', borderRadius: 6,
                      border: `1px solid ${ph.color}44`, background: ph.color + '0d',
                      fontSize: 11,
                    }}>
                      <span>{ph.icon}</span>
                      <span style={{ color: ph.color, fontWeight: 600 }}>{ph.name}</span>
                    </div>
                    {i < FALLBACK_PHASES.length - 1 && <span style={{ color: '#30363d', fontSize: 10 }}>→</span>}
                  </div>
                ))}
              </div>
            )}

            {/* Command input */}
            <div className="ac-runner-controls">
              <textarea className="ac-runner-input" placeholder={placeholder} value={task}
                onChange={e => setTask(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); launchTask() } }}
                rows={1}
              />
              <select className="ac-runner-select" value={model} onChange={e => setModel(e.target.value)}>
                {models.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
              <button className="ac-btn primary" onClick={launchTask} disabled={!task.trim() || launching}>
                {launching ? '…' : runMode === 'pipeline' ? '🔄 Run Pipeline' : '▶ Run'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
