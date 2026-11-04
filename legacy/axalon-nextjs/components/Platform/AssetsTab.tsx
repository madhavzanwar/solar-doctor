'use client'

import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, FolderKanban, Plus, Trash2 } from 'lucide-react'
import { api, ApiError, type Project, type ProjectDetail } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'
import { useParks } from '@/components/Platform/hooks/useParks'
import { useErrorToast } from '@/components/Platform/hooks/useErrorToast'
import { useToast } from '@/components/Platform/Toast'
import { useAuth } from '@/components/Platform/AuthGate'
import { ErrorBanner } from '@/components/Platform/ErrorBanner'
import { SkeletonLine } from '@/components/Platform/Skeleton'

const NO_PROJECTS: Project[] = []

function errMessage(err: unknown): string {
  return err instanceof ApiError || err instanceof Error ? err.message : String(err)
}

function ProjectCard({ project }: { project: Project }) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const { canWrite, canManageProjects } = useAssetPermissions()
  const { parks } = useParks()
  const [isOpen, setIsOpen] = useState(false)
  const [assignParkId, setAssignParkId] = useState('')

  const detailQuery = useQuery({
    queryKey: queryKeys.projects.detail(project.id),
    queryFn: () => api.project(project.id),
    enabled: isOpen,
  })
  useErrorToast(detailQuery.error, errMessage)
  const detail: ProjectDetail | null = detailQuery.data ?? null

  const assignedIds = new Set((detail?.sites ?? []).map((s) => s.id))
  const assignable = parks.filter((p) => !assignedIds.has(p.id))

  // Any project change can move site counts, statuses or membership: refresh
  // the whole projects namespace (list + every open detail).
  const refreshProjects = () => void queryClient.invalidateQueries({ queryKey: queryKeys.projects.all })
  const onError = (err: unknown) => toast.error(errMessage(err))

  const assignMutation = useMutation({
    mutationFn: ({ parkId, projectId }: { parkId: string; projectId: number | null }) =>
      api.updatePark(parkId, { project_id: projectId }),
    onSuccess: (_res, { projectId }) => {
      if (projectId !== null) setAssignParkId('')
      refreshProjects()
    },
    onError,
  })

  const statusMutation = useMutation({
    mutationFn: () =>
      api.updateProject(project.id, { status: project.status === 'active' ? 'archived' : 'active' }),
    onSuccess: refreshProjects,
    onError,
  })

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteProject(project.id),
    onSuccess: refreshProjects,
    onError,
  })

  function assign() {
    if (!assignParkId) return
    assignMutation.mutate({ parkId: assignParkId, projectId: project.id })
  }

  function unassign(parkId: string) {
    assignMutation.mutate({ parkId, projectId: null })
  }

  function toggleStatus() {
    statusMutation.mutate()
  }

  function remove() {
    if (!window.confirm(`Delete project "${project.name}"? Sites stay but become unassigned.`)) return
    deleteMutation.mutate()
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }} onClick={() => setIsOpen((v) => !v)}>
          {isOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
          <div>
            <div className="panel-title">{project.name}</div>
            <p>
              {project.client || 'No client'} · {project.site_count ?? 0} site(s)
              {project.description ? ` · ${project.description}` : ''}
            </p>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <button
            type="button"
            className={`inv-status inv-status-${project.status === 'active' ? 'active' : 'retired'}`}
            onClick={canManageProjects ? toggleStatus : undefined}
            disabled={!canManageProjects}
            title={canManageProjects ? 'Toggle status' : project.status}
          >
            {project.status}
          </button>
          {canManageProjects && (
            <button type="button" className="inv-icon-btn" onClick={remove} title="Delete project">
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>

      {isOpen && (
        <div style={{ marginTop: 10 }}>
          {detail === null && <div className="empty">Loading sites…</div>}
          {detail && detail.sites.length === 0 && (
            <div className="inv-bom-empty">No sites assigned yet.</div>
          )}
          {detail && detail.sites.length > 0 && (
            <div className="table">
              <div className="table-head asset-site-head">
                <span>Site</span>
                <span>Panels</span>
                <span>Inspections</span>
                <span>Missions</span>
                <span>Last flight</span>
                <span />
              </div>
              {detail.sites.map((s) => (
                <div className="asset-site-row" key={s.id}>
                  <span className="inv-part">
                    <strong>{s.name}</strong>
                    <small>{s.id}</small>
                  </span>
                  <span>{s.total_panels ?? '—'}</span>
                  <span>{s.inspection_count}</span>
                  <span>{s.mission_count}</span>
                  <span>{s.last_inspection_date ?? '—'}</span>
                  {canManageProjects ? (
                    <button type="button" className="inv-icon-btn" onClick={() => unassign(s.id)} title="Remove from project">
                      <Trash2 size={13} />
                    </button>
                  ) : (
                    <span />
                  )}
                </div>
              ))}
            </div>
          )}

          {canWrite && assignable.length > 0 && (
            <div className="inv-assign-form" style={{ marginTop: 8 }}>
              <select value={assignParkId} onChange={(e) => setAssignParkId(e.target.value)}>
                <option value="">Add a site to this project…</option>
                {assignable.map((p) => (
                  <option key={p.id} value={p.id}>{p.name ?? p.id}</option>
                ))}
              </select>
              <button type="button" className="secondary" disabled={!assignParkId} onClick={assign}>
                <Plus size={13} /> Assign
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  )
}

/** Project create/delete/status are admin-only once accounts are on; moving a
 * site between a user's own projects is an operator action. */
function useAssetPermissions() {
  const { canWrite, mode, isAdmin } = useAuth()
  return { canWrite, canManageProjects: mode !== 'users' || isAdmin }
}

export function AssetsTab() {
  const toast = useToast()
  const { canManageProjects } = useAssetPermissions()
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [client, setClient] = useState('')
  const [description, setDescription] = useState('')

  const projectsQuery = useQuery({ queryKey: queryKeys.projects.list, queryFn: () => api.projects() })
  useErrorToast(projectsQuery.error, errMessage)
  const projects = projectsQuery.data ?? NO_PROJECTS
  const isLoading = projectsQuery.isPending
  const loadError = projectsQuery.error ? errMessage(projectsQuery.error) : null
  const { refetch } = projectsQuery
  const reload = useCallback(() => void refetch(), [refetch])

  const createMutation = useMutation({
    mutationFn: () =>
      api.createProject({
        name: name.trim(),
        client: client.trim() || null,
        description: description.trim() || null,
      }),
    onSuccess: () => {
      setName(''); setClient(''); setDescription('')
      void queryClient.invalidateQueries({ queryKey: queryKeys.projects.all })
    },
    onError: (err) => toast.error(errMessage(err)),
  })

  function create() {
    if (!name.trim()) {
      toast.error('Project name is required')
      return
    }
    createMutation.mutate()
  }

  return (
    <section className="tab-section">
      <header className="cmdbar">
        <div className="cmdbar-titles">
          <div className="eyebrow">
            <FolderKanban size={13} />
            projects · sites · missions
          </div>
          <h1>Assets</h1>
        </div>
      </header>

      {canManageProjects && (
        <div className="inv-form">
          <input placeholder="New project name *" value={name} onChange={(e) => setName(e.target.value)} />
          <input placeholder="Client" value={client} onChange={(e) => setClient(e.target.value)} />
          <input placeholder="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
          <div className="inv-form-actions">
            <button type="button" className="primary" onClick={create}><Plus size={14} /> Create project</button>
          </div>
        </div>
      )}

      {loadError && !isLoading && <ErrorBanner message={loadError} onRetry={reload} />}
      {isLoading && (
        <div className="table" style={{ marginTop: 14 }}>
          {[0, 1, 2].map((i) => (
            <div className="panel" key={i} style={{ marginBottom: 10 }}>
              <SkeletonLine width={200} height={16} />
              <div style={{ marginTop: 8 }}>
                <SkeletonLine width="60%" />
              </div>
            </div>
          ))}
        </div>
      )}
      {!isLoading && !loadError && projects.length === 0 && (
        <div className="empty">No projects yet — group your parks into client projects above.</div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 14 }}>
        {projects.map((p) => (
          <ProjectCard key={p.id} project={p} />
        ))}
      </div>
    </section>
  )
}
