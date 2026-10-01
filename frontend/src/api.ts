export type Step = { action: string; expected: string }

export type StepIssue = { index: number; severity: 'error' | 'warning' | 'info'; issue: string; suggestion: string }
export type Review = { score: number; runnable: boolean; summary: string; issues: StepIssue[] }

export type Requirement = { id: number; ref: string; feature: string; text: string; acceptance: string; priority: string }

export type Project = {
  id: number
  name: string
  base_url: string
  repo_url: string | null
  requirements_file: string | null
  gen_status: 'idle' | 'running' | 'done' | 'error'
  gen_message: string | null
  created_at: string
  case_count?: number
  approved_count?: number
  passed_count?: number
  failed_count?: number
  requirements?: Requirement[]
}

export type CaseStatus = 'draft' | 'approved' | 'rejected'
export type RunStatus = 'queued' | 'running' | 'passed' | 'failed' | 'error' | 'cancelled' | 'skipped'
export const ACTIVE: RunStatus[] = ['queued', 'running']
export const isActive = (s?: string | null) => s === 'queued' || s === 'running'

export type TestCase = {
  id: number
  project_id: number
  key: string
  title: string
  kind: 'ui' | 'api'
  priority: 'P1' | 'P2' | 'P3'
  category: string
  objective: string
  preconditions: string
  steps: Step[]
  requirement_refs: string[]
  status: CaseStatus
  source: string
  review: Review | null
  last_run_status: RunStatus | null
  runs?: { id: number; status: RunStatus; error: string | null; created_at: string; finished_at: string | null }[]
}

export type SubAction = {
  n: number
  action: Record<string, unknown> & { type: string }
  label?: string
  reasoning: string
  ok: boolean
  error?: string | null
  data?: { status?: number; url?: string; body?: string } | null
  screenshot?: string
  screen_changed?: boolean
  verifier?: { success: boolean; reasoning: string; is_app_error: boolean }
}

export type RunStep = {
  index: number
  action: string
  expected: string
  status: 'pending' | 'running' | 'passed' | 'failed' | 'skipped'
  sub_actions: SubAction[]
  heal_count: number
  error: string | null
  reasoning: string | null
  final_screenshot: string | null
  duration_ms: number | null
}

export type Run = {
  id: number
  project_id: number
  test_case_id: number
  flow_run_id: number | null
  status: RunStatus
  error: string | null
  case_snapshot: { key: string; title: string; kind: string; objective: string }
  steps: RunStep[]
  usage: { input_tokens?: number; output_tokens?: number; requests?: number }
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export type RunSummary = {
  id: number
  test_case_id: number
  flow_run_id: number | null
  status: RunStatus
  error: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  usage: Run['usage']
  case_key: string
  case_title: string
  step_count: number
  passed_steps: number
}

export type Flow = {
  id: number
  project_id: number
  name: string
  description: string
  case_ids: number[]
  shared_session: boolean
  stop_on_fail: boolean
  created_at: string
  last_run: { id: number; status: RunStatus; created_at: string } | null
  runs?: FlowRunBase[]
}

export type FlowRunItem = {
  run_id: number
  case_id: number
  key: string
  title: string
  kind: string
  status: RunStatus
  error: string | null
  step_count: number
  done_steps: number
  passed_steps: number
  current_step: number | null
  started_at: string | null
  finished_at: string | null
}

type FlowRunBase = {
  id: number
  project_id: number
  flow_id: number
  flow_name: string
  status: RunStatus
  run_ids: number[]
  current_index: number | null
  error: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}
export type FlowRun = FlowRunBase & { runs: FlowRunItem[] }

export type Health = {
  ok: boolean
  llm_ready: boolean
  provider: string
  missing_keys: string[]
  model: string
  verifier_model: string
  testteller_installed: boolean
}

// Messages on /api/live/{run|flow}/{id}
export type LiveMsg =
  | { type: 'frame'; data: string; w: number; h: number }
  | { type: 'url'; url: string }
  | { type: 'case'; key: string; title: string; run_id: number }
  | {
      type: 'phase'
      phase: 'navigate' | 'observe' | 'plan' | 'act' | 'verify' | 'gave_up' | 'done'
      step: number | null
      label?: string
      reasoning?: string
      box?: { x: number; y: number; width: number; height: number } | null
      run_id?: number
    }
  | { type: 'result'; step: number; ok: boolean; label: string; error: string | null }
  | { type: 'verdict'; step: number; success: boolean; reasoning: string; is_app_error: boolean }
  | { type: 'step_done'; step: number; ok: boolean; reason: string }
  | { type: 'ping' }

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = init?.body && !(init.body instanceof FormData) ? { 'content-type': 'application/json' } : undefined
  const r = await fetch(path, { ...init, headers })
  if (!r.ok) {
    let msg = r.statusText
    try {
      const j = await r.json()
      msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch {
      /* not json */
    }
    throw new Error(msg)
  }
  return r.json()
}

const json = (body: unknown) => JSON.stringify(body)
const post = <T>(path: string, body?: unknown) => req<T>(path, { method: 'POST', body: body === undefined ? undefined : json(body) })
const put = <T>(path: string, body: unknown) => req<T>(path, { method: 'PUT', body: json(body) })
const del = (path: string) => req<{ ok: boolean }>(path, { method: 'DELETE' })

export const api = {
  health: () => req<Health>('/api/health'),

  projects: () => req<Project[]>('/api/projects'),
  project: (id: number) => req<Project>(`/api/projects/${id}`),
  createProject: (form: FormData) => req<Project>('/api/projects', { method: 'POST', body: form }),
  deleteProject: (id: number) => del(`/api/projects/${id}`),
  generate: (id: number, generator: string, max_cases: number) => post(`/api/projects/${id}/generate`, { generator, max_cases }),

  cases: (projectId: number) => req<TestCase[]>(`/api/projects/${projectId}/cases`),
  createCase: (projectId: number, body: Partial<TestCase>) => post<TestCase>(`/api/projects/${projectId}/cases`, body),
  case: (id: number) => req<TestCase>(`/api/cases/${id}`),
  updateCase: (id: number, body: Partial<TestCase>) => put<TestCase>(`/api/cases/${id}`, body),
  deleteCase: (id: number) => del(`/api/cases/${id}`),
  review: (id: number) => post<Review>(`/api/cases/${id}/review`),

  runCase: (id: number) => post<Run>(`/api/cases/${id}/run`),
  runMany: (projectId: number, case_ids?: number[]) => post<Run[]>(`/api/projects/${projectId}/runs`, { case_ids: case_ids ?? null }),
  runs: (projectId: number) => req<RunSummary[]>(`/api/projects/${projectId}/runs`),
  run: (id: number) => req<Run>(`/api/runs/${id}`),
  cancelRun: (id: number) => post(`/api/runs/${id}/cancel`),

  flows: (projectId: number) => req<Flow[]>(`/api/projects/${projectId}/flows`),
  flow: (id: number) => req<Flow>(`/api/flows/${id}`),
  createFlow: (projectId: number, body: Partial<Flow>) => post<Flow>(`/api/projects/${projectId}/flows`, body),
  updateFlow: (id: number, body: Partial<Flow>) => put<Flow>(`/api/flows/${id}`, body),
  deleteFlow: (id: number) => del(`/api/flows/${id}`),
  runFlow: (id: number) => post<FlowRun>(`/api/flows/${id}/run`),
  flowRuns: (projectId: number) => req<FlowRun[]>(`/api/projects/${projectId}/flow-runs`),
  flowRun: (id: number) => req<FlowRun>(`/api/flow-runs/${id}`),
  cancelFlowRun: (id: number) => post(`/api/flow-runs/${id}/cancel`),
}

export function wsUrl(path: string) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}${path}`
}
