import { Alert, Anchor, Badge, Button, Card, Group, Loader, Progress, Stack, Text, Title } from '@mantine/core'
import { IconPlayerPlay, IconPlayerStop, IconRoute } from '@tabler/icons-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { api, isActive } from '../api'
import { FlowGraph } from '../components/FlowGraph'
import { RunSandbox } from '../components/RunSandbox'
import { StatusBadge, elapsed } from '../components/Status'
import { useAction, useFlowRun, useRun } from '../queries'

export default function FlowRunPage() {
  const id = Number(useParams().id)
  const navigate = useNavigate()
  const { data: fr } = useFlowRun(id)
  const [selected, setSelected] = useState<number | null>(null)
  const [follow, setFollow] = useState(true)

  // Follow the running case unless the user picked one.
  const runningIdx = fr?.runs.findIndex((r) => r.status === 'running') ?? -1
  const autoIdx = runningIdx >= 0 ? runningIdx : (fr?.current_index ?? 0)
  const idx = follow ? autoIdx : (selected ?? autoIdx)
  useEffect(() => { if (follow) setSelected(null) }, [follow])

  const item = fr?.runs[idx]
  const { data: run } = useRun(item?.run_id ?? null)
  const cancel = useAction(() => api.cancelFlowRun(id), { success: 'Cancelling flow…' })
  const rerun = useAction(() => api.runFlow(fr!.flow_id), { invalidate: ['flowRuns'] })

  if (!fr) return <Loader m="xl" />
  const active = isActive(fr.status)
  const totalSteps = fr.runs.reduce((n, r) => n + r.step_count, 0)
  const doneSteps = fr.runs.reduce((n, r) => n + r.done_steps, 0)
  const passedCases = fr.runs.filter((r) => r.status === 'passed').length

  return (
    <Stack gap="md" maw={1500} mx="auto">
      <Group justify="space-between" align="flex-end">
        <div>
          <Anchor component={Link} to={`/flows/${fr.flow_id}`} size="xs" c="dimmed">← Flow</Anchor>
          <Group gap="sm">
            <IconRoute size={22} />
            <Title order={2}>{fr.flow_name}</Title>
            <Text c="dimmed">run #{fr.id}</Text>
            <StatusBadge value={fr.status} size="lg" />
          </Group>
        </div>
        <Group gap="xs">
          <Badge variant="light" color="gray">{elapsed(fr.started_at, fr.finished_at) || 'queued'}</Badge>
          {active
            ? <Button color="red" variant="light" leftSection={<IconPlayerStop size={14} />} loading={cancel.isPending} onClick={() => cancel.mutate(undefined)}>Stop flow</Button>
            : <Button variant="light" leftSection={<IconPlayerPlay size={14} />} loading={rerun.isPending} onClick={async () => {
                const r = await rerun.mutateAsync(undefined).catch(() => null)
                if (r) navigate(`/flow-runs/${r.id}`)
              }}>Run again</Button>}
        </Group>
      </Group>

      <Card className="glass" p="md">
        <Group justify="space-between" mb="xs">
          <Group gap="xs">
            <Text fw={700}>Flow progress</Text>
            <Text size="sm" c="dimmed">{passedCases}/{fr.runs.length} cases passed · {doneSteps}/{totalSteps} steps</Text>
          </Group>
          <Badge variant={follow ? 'filled' : 'light'} style={{ cursor: 'pointer' }} onClick={() => setFollow((f) => !f)}>
            {follow ? 'following live case' : 'click to follow live'}
          </Badge>
        </Group>
        <Progress value={(doneSteps / Math.max(1, totalSteps)) * 100} size="sm" radius="xl" mb="sm"
          color={fr.status === 'failed' ? 'red' : 'violet'} striped={active} animated={active} />
        <FlowGraph
          items={fr.runs.map((r, i) => ({
            key: r.key, title: r.title, kind: r.kind, status: r.status,
            done: r.done_steps, total: r.step_count, currentStep: r.current_step, selected: i === idx,
          }))}
          onSelect={(i) => { setSelected(i); setFollow(false) }}
        />
      </Card>

      {fr.error && !active && <Alert color="red" variant="light">{fr.error}</Alert>}
      {item?.error && item.status === 'skipped' && <Alert color="gray" variant="light">{item.key}: {item.error}</Alert>}

      {run && (
        <>
          <Group gap="xs">
            <Text fw={700}>Case {idx + 1}/{fr.runs.length}:</Text>
            <Anchor component={Link} to={`/runs/${run.id}`} fw={600}>{run.case_snapshot.key} · {run.case_snapshot.title}</Anchor>
            <StatusBadge value={run.status} />
          </Group>
          {/* The flow channel streams whichever case is running, so the browser never disconnects between cases. */}
          <RunSandbox
            run={run}
            channel={follow || isActive(run.status) ? `flow/${fr.id}` : `run/${run.id}`}
            liveActive={active && (follow || isActive(run.status))}
          />
        </>
      )}
    </Stack>
  )
}
