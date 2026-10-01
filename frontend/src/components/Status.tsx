import { Badge, Loader, ThemeIcon, type MantineColor } from '@mantine/core'
import {
  IconCheck, IconClock, IconExclamationMark, IconPlayerSkipForward, IconPlayerStop, IconX,
} from '@tabler/icons-react'

export const statusColor: Record<string, MantineColor> = {
  passed: 'teal',
  approved: 'teal',
  failed: 'red',
  error: 'red',
  rejected: 'red',
  running: 'blue',
  queued: 'indigo',
  draft: 'yellow',
  pending: 'gray',
  skipped: 'gray',
  cancelled: 'orange',
}

export function StatusBadge({ value, size = 'sm' }: { value?: string | null; size?: 'xs' | 'sm' | 'md' | 'lg' }) {
  if (!value) return <Badge variant="light" color="gray" size={size}>—</Badge>
  return (
    <Badge
      variant="light"
      color={statusColor[value] ?? 'gray'}
      size={size}
      leftSection={value === 'running' ? <Loader size={10} color="blue" /> : undefined}
    >
      {value}
    </Badge>
  )
}

export function StatusIcon({ status, size = 26 }: { status: string; size?: number }) {
  const s = size * 0.6
  const icon =
    status === 'passed' ? <IconCheck size={s} stroke={3} /> :
    status === 'failed' ? <IconX size={s} stroke={3} /> :
    status === 'error' ? <IconExclamationMark size={s} stroke={3} /> :
    status === 'running' ? <Loader size={s} color="white" type="oval" /> :
    status === 'skipped' ? <IconPlayerSkipForward size={s} /> :
    status === 'cancelled' ? <IconPlayerStop size={s} /> :
    <IconClock size={s} />
  return (
    <ThemeIcon
      radius="xl"
      size={size}
      color={statusColor[status] ?? 'gray'}
      variant={status === 'pending' || status === 'queued' || status === 'skipped' ? 'light' : 'filled'}
    >
      {icon}
    </ThemeIcon>
  )
}

export function fmtDuration(ms: number | null | undefined) {
  if (ms == null) return ''
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`
}

export function fmtDate(iso: string | null | undefined) {
  if (!iso) return ''
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + 'Z')
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function elapsed(start?: string | null, end?: string | null) {
  if (!start) return ''
  const s = new Date(start.endsWith('Z') ? start : start + 'Z').getTime()
  const e = end ? new Date(end.endsWith('Z') ? end : end + 'Z').getTime() : Date.now()
  return fmtDuration(Math.max(0, e - s))
}
