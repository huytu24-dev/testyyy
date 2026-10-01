import { Alert, Anchor, Button, Group, Loader, Stack, Text, Title } from '@mantine/core'
import { IconPlayerPlay, IconPlayerStop } from '@tabler/icons-react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { api, isActive } from '../api'
import { RunSandbox } from '../components/RunSandbox'
import { StatusBadge } from '../components/Status'
import { useAction, useRun } from '../queries'

export default function RunPage() {
  const id = Number(useParams().id)
  const navigate = useNavigate()
  const { data: run } = useRun(id)
  const cancel = useAction(() => api.cancelRun(id), { success: 'Cancelling…' })
  const rerun = useAction(() => api.runCase(run!.test_case_id), { invalidate: ['runs'] })

  if (!run) return <Loader m="xl" />
  const active = isActive(run.status)

  return (
    <Stack gap="md" maw={1500} mx="auto">
      <Group justify="space-between" align="flex-end">
        <div>
          <Group gap="xs">
            <Anchor component={Link} to={`/cases/${run.test_case_id}`} size="xs" c="dimmed">← Test case</Anchor>
            {run.flow_run_id && <Anchor component={Link} to={`/flow-runs/${run.flow_run_id}`} size="xs">part of flow run #{run.flow_run_id}</Anchor>}
          </Group>
          <Group gap="sm">
            <Title order={2}>Run #{run.id}</Title>
            <Text ff="monospace" c="dimmed">{run.case_snapshot.key}</Text>
            <Text fw={600} size="lg">{run.case_snapshot.title}</Text>
            <StatusBadge value={run.status} size="lg" />
          </Group>
        </div>
        <Group gap="xs">
          {active
            ? <Button color="red" variant="light" leftSection={<IconPlayerStop size={14} />} loading={cancel.isPending} onClick={() => cancel.mutate(undefined)}>Stop</Button>
            : <Button variant="light" leftSection={<IconPlayerPlay size={14} />} loading={rerun.isPending} onClick={async () => {
                const r = await rerun.mutateAsync(undefined).catch(() => null)
                if (r) navigate(`/runs/${r.id}`)
              }}>Run again</Button>}
        </Group>
      </Group>
      {run.error && !active && <Alert color={run.status === 'cancelled' ? 'orange' : 'red'} variant="light">{run.error}</Alert>}
      <RunSandbox run={run} channel={`run/${run.id}`} liveActive={active} />
    </Stack>
  )
}
