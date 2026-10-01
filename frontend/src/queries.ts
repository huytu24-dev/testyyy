/** React Query hooks. Live state (runs, flow runs) is pushed over WebSocket into the cache. */
import { notifications } from '@mantine/notifications'
import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { useEffect } from 'react'

import { api, isActive, wsUrl, type FlowRun, type Run } from './api'

export const keys = {
  health: ['health'] as const,
  projects: ['projects'] as const,
  project: (id: number) => ['project', id] as const,
  cases: (pid: number) => ['cases', pid] as const,
  case: (id: number) => ['case', id] as const,
  runs: (pid: number) => ['runs', pid] as const,
  run: (id: number) => ['run', id] as const,
  flows: (pid: number) => ['flows', pid] as const,
  flow: (id: number) => ['flow', id] as const,
  flowRuns: (pid: number) => ['flowRuns', pid] as const,
  flowRun: (id: number) => ['flowRun', id] as const,
}

export const notifyError = (e: unknown) =>
  notifications.show({ color: 'red', title: 'Error', message: e instanceof Error ? e.message : String(e) })

export const useHealth = () => useQuery({ queryKey: keys.health, queryFn: api.health, refetchInterval: 30_000 })
export const useProjects = () => useQuery({ queryKey: keys.projects, queryFn: api.projects })

export const useProject = (id: number) =>
  useQuery({
    queryKey: keys.project(id),
    queryFn: () => api.project(id),
    refetchInterval: (q) => (q.state.data?.gen_status === 'running' ? 1500 : false),
  })

export const useCases = (pid: number, poll = false) =>
  useQuery({ queryKey: keys.cases(pid), queryFn: () => api.cases(pid), refetchInterval: poll ? 2000 : false })

export const useCase = (id: number) => useQuery({ queryKey: keys.case(id), queryFn: () => api.case(id) })

export const useRuns = (pid: number) =>
  useQuery({
    queryKey: keys.runs(pid),
    queryFn: () => api.runs(pid),
    refetchInterval: (q) => (q.state.data?.some((r) => isActive(r.status)) ? 2000 : false),
  })

export const useFlows = (pid: number) => useQuery({ queryKey: keys.flows(pid), queryFn: () => api.flows(pid) })
export const useFlow = (id: number) => useQuery({ queryKey: keys.flow(id), queryFn: () => api.flow(id) })

export const useFlowRuns = (pid: number) =>
  useQuery({
    queryKey: keys.flowRuns(pid),
    queryFn: () => api.flowRuns(pid),
    refetchInterval: (q) => (q.state.data?.some((r) => isActive(r.status)) ? 2000 : false),
  })

/** Subscribe a state WebSocket and write each message into the query cache. */
function useStateSocket<T extends { status: string }>(path: string | null, key: QueryKey, onFinish?: () => void) {
  const qc = useQueryClient()
  useEffect(() => {
    if (!path) return
    let closed = false
    let ws: WebSocket | null = null
    let retry: ReturnType<typeof setTimeout>
    const connect = () => {
      ws = new WebSocket(wsUrl(path))
      ws.onmessage = (e) => {
        const data = JSON.parse(e.data) as T
        const prev = qc.getQueryData<T>(key)
        qc.setQueryData(key, data)
        if (prev && isActive(prev.status) && !isActive(data.status)) onFinish?.()
      }
      ws.onclose = () => {
        const cur = qc.getQueryData<T>(key)
        if (!closed && (!cur || isActive(cur.status))) retry = setTimeout(connect, 1500)
      }
    }
    connect()
    return () => {
      closed = true
      clearTimeout(retry)
      ws?.close()
    }
  }, [path])
}

export function useRun(id: number | null) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: keys.run(id ?? -1), queryFn: () => api.run(id!), enabled: id != null })
  useStateSocket<Run>(id != null ? `/api/runs/${id}/ws` : null, keys.run(id ?? -1), () => {
    qc.invalidateQueries({ queryKey: ['runs'] })
    qc.invalidateQueries({ queryKey: ['cases'] })
    qc.invalidateQueries({ queryKey: ['projects'] })
  })
  return q
}

export function useFlowRun(id: number) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: keys.flowRun(id), queryFn: () => api.flowRun(id) })
  useStateSocket<FlowRun>(`/api/flow-runs/${id}/ws`, keys.flowRun(id), () => {
    qc.invalidateQueries({ queryKey: ['flowRuns'] })
    qc.invalidateQueries({ queryKey: ['flows'] })
    qc.invalidateQueries({ queryKey: ['cases'] })
    qc.invalidateQueries({ queryKey: ['projects'] })
  })
  return q
}

/** useMutation + error toast + invalidation of the given key prefixes on success. */
export function useAction<TArgs, TResult>(
  fn: (args: TArgs) => Promise<TResult>,
  opts: { invalidate?: string[]; success?: string | ((r: TResult) => string) } = {},
) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onError: notifyError,
    onSuccess: (r) => {
      for (const k of opts.invalidate ?? []) qc.invalidateQueries({ queryKey: [k] })
      if (opts.success) {
        notifications.show({ color: 'teal', message: typeof opts.success === 'function' ? opts.success(r) : opts.success })
      }
    },
  })
}
