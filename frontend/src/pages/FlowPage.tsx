import {
  ActionIcon, Anchor, Button, Card, Grid, Group, Loader, Paper, Select, Stack, Switch, Text, TextInput, Textarea, Title,
} from '@mantine/core'
import { modals } from '@mantine/modals'
import { IconArrowDown, IconArrowUp, IconDeviceFloppy, IconPlayerPlay, IconPlus, IconTrash } from '@tabler/icons-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { api, type Flow } from '../api'
import { FlowGraph } from '../components/FlowGraph'
import { StatusBadge, elapsed, fmtDate } from '../components/Status'
import { useAction, useCases, useFlow } from '../queries'

export default function FlowPage() {
  const id = Number(useParams().id)
  const navigate = useNavigate()
  const { data: saved } = useFlow(id)
  const { data: cases = [] } = useCases(saved?.project_id ?? -1)
  const [draft, setDraft] = useState<Flow | null>(null)
  const [adding, setAdding] = useState<string | null>(null)
  useEffect(() => { if (saved) setDraft(saved) }, [saved])

  const save = useAction(() => api.updateFlow(id, draft!), { invalidate: ['flow', 'flows'], success: 'Flow saved' })
  const run = useAction(async () => {
    await api.updateFlow(id, draft!)
    return api.runFlow(id)
  }, { invalidate: ['flowRuns', 'flows'] })
  const remove = useAction(() => api.deleteFlow(id), { invalidate: ['flows'] })

  if (!draft || !saved) return <Loader m="xl" />
  const byId = new Map(cases.map((c) => [c.id, c]))
  const set = <K extends keyof Flow>(k: K, v: Flow[K]) => setDraft({ ...draft, [k]: v })
  const move = (i: number, d: -1 | 1) => {
    const j = i + d
    if (j < 0 || j >= draft.case_ids.length) return
    const ids = [...draft.case_ids]
    ;[ids[i], ids[j]] = [ids[j], ids[i]]
    set('case_ids', ids)
  }
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved)

  return (
    <Stack gap="md" maw={1300} mx="auto">
      <div>
        <Anchor component={Link} to={`/projects/${draft.project_id}`} size="xs" c="dimmed">← Project</Anchor>
        <Group justify="space-between" align="flex-end">
          <Title order={2}>{saved.name}</Title>
          <Group gap="xs">
            <Button size="xs" variant="default" leftSection={<IconDeviceFloppy size={14} />} disabled={!dirty} loading={save.isPending} onClick={() => save.mutate(undefined)}>Save</Button>
            <Button size="xs" variant="gradient" gradient={{ from: 'violet', to: 'cyan', deg: 135 }} leftSection={<IconPlayerPlay size={14} />}
              disabled={draft.case_ids.length === 0} loading={run.isPending} onClick={async () => {
                const fr = await run.mutateAsync(undefined).catch(() => null)
                if (fr) navigate(`/flow-runs/${fr.id}`)
              }}>Run flow in sandbox</Button>
            <ActionIcon variant="subtle" color="red" onClick={() => modals.openConfirmModal({
              title: 'Delete flow?', labels: { confirm: 'Delete', cancel: 'Cancel' }, confirmProps: { color: 'red' },
              onConfirm: async () => { await remove.mutateAsync(undefined); navigate(`/projects/${draft.project_id}`) },
            })}><IconTrash size={16} /></ActionIcon>
          </Group>
        </Group>
      </div>

      <Card className="glass" p="md">
        <FlowGraph height={170} items={draft.case_ids.map((cid) => {
          const c = byId.get(cid)
          return { key: c?.key ?? `#${cid}`, title: c?.title ?? 'missing case', kind: c?.kind, status: c?.last_run_status ?? 'pending', total: c?.steps.length }
        })} />
      </Card>

      <Grid>
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Card className="glass" p="md">
            <Text fw={700} mb="sm">Cases in order</Text>
            <Stack gap="xs">
              {draft.case_ids.map((cid, i) => {
                const c = byId.get(cid)
                return (
                  <Paper key={`${cid}-${i}`} withBorder p="xs" radius="md">
                    <Group justify="space-between" wrap="nowrap">
                      <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
                        <Text fw={800} c="violet.4" w={22}>{i + 1}</Text>
                        <Text ff="monospace" size="xs" c="dimmed">{c?.key}</Text>
                        <Anchor component={Link} to={`/cases/${cid}`} size="sm" fw={600} truncate>{c?.title ?? `missing case #${cid}`}</Anchor>
                        <StatusBadge value={c?.status} size="xs" />
                      </Group>
                      <Group gap={2} wrap="nowrap">
                        <ActionIcon variant="subtle" color="gray" onClick={() => move(i, -1)}><IconArrowUp size={14} /></ActionIcon>
                        <ActionIcon variant="subtle" color="gray" onClick={() => move(i, 1)}><IconArrowDown size={14} /></ActionIcon>
                        <ActionIcon variant="subtle" color="red" onClick={() => set('case_ids', draft.case_ids.filter((_, j) => j !== i))}><IconTrash size={14} /></ActionIcon>
                      </Group>
                    </Group>
                  </Paper>
                )
              })}
            </Stack>
            <Group mt="sm" gap="xs">
              <Select placeholder="Add a test case…" searchable value={adding} onChange={setAdding} style={{ flex: 1 }}
                data={cases.map((c) => ({ value: String(c.id), label: `${c.key} · ${c.title}` }))} />
              <Button variant="default" leftSection={<IconPlus size={14} />} disabled={!adding} onClick={() => {
                set('case_ids', [...draft.case_ids, Number(adding)])
                setAdding(null)
              }}>Add</Button>
            </Group>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Stack>
            <Card className="glass" p="md">
              <Stack gap="sm">
                <TextInput label="Name" value={draft.name} onChange={(e) => set('name', e.currentTarget.value)} />
                <Textarea label="Description" autosize minRows={1} value={draft.description} onChange={(e) => set('description', e.currentTarget.value)} />
                <Switch checked={draft.shared_session} onChange={(e) => set('shared_session', e.currentTarget.checked)}
                  label="Shared browser session" description="Case N+1 continues in the same page/cookies where case N ended (e.g. login once)." />
                <Switch checked={draft.stop_on_fail} onChange={(e) => set('stop_on_fail', e.currentTarget.checked)}
                  label="Stop on first failure" description="Skip the remaining cases when one fails." />
              </Stack>
            </Card>
            <Card className="glass" p="md">
              <Text fw={700} mb="xs">Run history</Text>
              <Stack gap={6}>
                {saved.runs?.map((r) => (
                  <Group key={r.id} gap="xs">
                    <Anchor component={Link} to={`/flow-runs/${r.id}`} size="sm">#{r.id}</Anchor>
                    <StatusBadge value={r.status} size="xs" />
                    <Text size="xs" c="dimmed">{fmtDate(r.created_at)} · {elapsed(r.started_at, r.finished_at)}</Text>
                  </Group>
                ))}
                {!saved.runs?.length && <Text size="sm" c="dimmed">Not run yet.</Text>}
              </Stack>
            </Card>
          </Stack>
        </Grid.Col>
      </Grid>
    </Stack>
  )
}
