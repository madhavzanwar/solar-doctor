/**
 * Central query-key registry.
 *
 * Keys live here rather than inline so an invalidation can never silently miss
 * a cache entry because of a typo'd string. Keys are hierarchical: invalidating
 * a prefix (e.g. `projects.all`) refreshes every entry beneath it.
 */
export const queryKeys = {
  ops: {
    health: ['ops', 'health'] as const,
    orthos: (parkId: string) => ['ops', 'orthos', parkId] as const,
  },
  inventory: {
    components: ['inventory', 'components'] as const,
    prototypes: ['inventory', 'prototypes'] as const,
    orders: ['inventory', 'orders'] as const,
    /** Everything under the inventory namespace — used after any mutation. */
    all: ['inventory'] as const,
  },
  faults: {
    park: (parkId: string) => ['faults', 'park', parkId] as const,
    photos: (faultId: number) => ['faults', 'photos', faultId] as const,
  },
  parks: {
    list: ['parks', 'list'] as const,
    /** GET /park/{id} — summary including the inspection list. */
    summary: (parkId: string) => ['parks', 'summary', parkId] as const,
    grid: (parkId: string, inspectionId: string) => ['parks', 'grid', parkId, inspectionId] as const,
    trend: (parkId: string) => ['parks', 'trend', parkId] as const,
    recurring: (parkId: string) => ['parks', 'recurring', parkId] as const,
    diff: (parkId: string, a: string, b: string) => ['parks', 'diff', parkId, a, b] as const,
    layout: (parkId: string) => ['parks', 'layout', parkId] as const,
  },
  analytics: {
    overview: (parkIds: string[]) => ['analytics', 'overview', parkIds] as const,
  },
  jobs: {
    status: (jobId: string) => ['jobs', 'status', jobId] as const,
    mapData: (jobId: string) => ['jobs', 'map', jobId] as const,
    corrections: (jobId: string) => ['jobs', 'corrections', jobId] as const,
  },
  odm: {
    jobs: (parkId: string) => ['odm', 'jobs', parkId] as const,
    job: (parkId: string, jobId: string) => ['odm', 'job', parkId, jobId] as const,
  },
  projects: {
    all: ['projects'] as const,
    list: ['projects', 'list'] as const,
    detail: (id: number) => ['projects', 'detail', id] as const,
  },
  missions: {
    all: ['missions'] as const,
    list: (parkId: string) => ['missions', 'list', parkId] as const,
  },
  settings: {
    blob: ['settings', 'blob'] as const,
    fusionCalibration: ['settings', 'fusion-calibration'] as const,
  },
  accounts: {
    users: ['accounts', 'users'] as const,
    shareLinks: ['accounts', 'share-links'] as const,
  },
  track: {
    notesAll: ['track', 'notes'] as const,
    notes: (kind: string) => ['track', 'notes', kind] as const,
    files: ['track', 'files'] as const,
  },
} as const
