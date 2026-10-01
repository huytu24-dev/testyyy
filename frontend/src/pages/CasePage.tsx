import {
  ActionIcon, Alert, Anchor, Badge, Button, Card, Grid, Group, Loader, Paper, RingProgress, Select, Stack, Text,
  TextInput, Textarea, Title, Tooltip,
} from '@mantine/core'
import { modals } from '@mantine/modals'
import {
  IconArrowDown, IconArrowUp, IconCheck, IconDeviceFloppy, IconPlayerPlay, IconPlus, IconSparkles, IconTrash, IconWand, IconX,
} from '@tabler/icons-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { api, type Step, type StepIssue, type TestCase } from '../api'
import { StatusBadge, fmtDate } from '../components/Status'
import { useAction, useCase } from '../queries'

const pick = (c: TestCase) => {
  const { title, kind, priority, category, objective, preconditions, steps } = c
  return { title, kind, priority, category, objective, preconditions, steps }
}

export default function CasePage() {
  const id = Number(useParams().id)
  const navigate = useNavigate()
  const { data: saved } = useCase(id)
  const [draft, setDraft] = useState<TestCase | null>(null)
  useEffect(() => { if (saved) setDraft(saved) }, [saved])

  const save = useAction((extra: Partial<TestCase>) => api.updateCase(id, { ...pick(draft!), ...extra }), {
    invalidate: ['case', 'cases', 'projects'], success: 'Saved',
  })
  const review = useAction(async () => {
    if (dirty) await api.updateCase(id, pick(draft!))
    return api.review(id)
  }, { invalidate: ['case', 'cases'] })
  const run = useAction(async () => {
    if (dirty) await api.updateCase(id, pick(draft!))
    return api.runCase(id)
  }, { invalidate: ['runs', 'cases'] })
  const remove = useAction(() => api.deleteCase(id), { invalidate: ['cases', 'projects'] })

  if (!draft || !saved) return <Loader m="xl" />
  const dirty = JSON.stringify(pick(draft)) !== JSON.stringify(pick(saved))
  const set = <K extends keyof TestCase>(k: K, v: TestCase[K]) => setDraft({ ...draft, [k]: v })
  const setStep = (i: number, patch: Partial<Step>) => set('steps', draft.steps.map((s, j) => (j === i ? { ...s, ...patch } : s)))
  const move = (i: number, d: -1 | 1) => {
    const j = i + d
    if (j < 0 || j >= draft.steps.length) return
    const steps = [...draft.steps]
    ;[steps[i], steps[j]] = [steps[j], steps[i]]
    set('steps', steps)
  }
  const rv = draft.review
  const issuesFor = (i: number): StepIssue[] => rv?.issues.filter((x) => x.index === i) ?? []

  return (
    <Stack gap="md" maw={1300} mx="auto">
      <div>
        <Anchor component={Link} to={`/projects/${draft.project_id}`} size="xs" c="dimmed">← Project</Anchor>
        <Group justify="space-between" align="flex-end">
          <Group gap="sm">
            <Text ff="monospace" c="dimmed">{draft.key}</Text>
            <Title order={2}>{saved.title}</Title>
            <StatusBadge value={draft.status} size="md" />
            <Badge variant="outline" color="gray">{draft.source}</Badge>
          </Group>
        </Group>
      </div>

      <Paper className="glass" p="xs" radius="lg" style={{ position: 'sticky', top: 64, zIndex: 5 }}>
        <Group justify="space-between">
          <Group gap="xs">
            <Button size="xs" leftSection={<IconDeviceFloppy size={14} />} disabled={!dirty} loading={save.isPending} onClick={() => save.mutate({})}>
              {dirty ? 'Save' : 'Saved'}
            </Button>
            <Button size="xs" variant="light" color="grape" leftSection={<IconSparkles size={14} />} loading={review.isPending} onClick={() => review.mutate(undefined)}>
              AI review
            </Button>
            {draft.status !== 'approved'
              ? <Button size="xs" variant="light" color="teal" leftSection={<IconCheck size={14} />} onClick={() => save.mutate({ status: 'approved' })}>Approve</Button>
              : <Button size="xs" variant="default" onClick={() => save.mutate({ status: 'draft' })}>Unapprove</Button>}
            {draft.status !== 'rejected' && (
              <Button size="xs" variant="subtle" color="red" leftSection={<IconX size={14} />} onClick={() => save.mutate({ status: 'rejected' })}>Reject</Button>
            )}
          </Group>
          <Group gap="xs">
            <Button size="xs" variant="gradient" gradient={{ from: 'violet', to: 'blue' }} leftSection={<IconPlayerPlay size={14} />}
              loading={run.isPending} onClick={async () => {
                const r = await run.mutateAsync(undefined).catch(() => null)
                if (r) navigate(`/runs/${r.id}`)
              }}>Run in sandbox</Button>
            <ActionIcon variant="subtle" color="red" onClick={() => modals.openConfirmModal({
              title: 'Delete test case?', labels: { confirm: 'Delete', cancel: 'Cancel' }, confirmProps: { color: 'red' },
              onConfirm: async () => { await remove.mutateAsync(undefined); navigate(`/projects/${draft.project_id}`) },
            })}><IconTrash size={16} /></ActionIcon>
          </Group>
        </Group>
      </Paper>

      <Grid>
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Card className="glass" p="md">
            <Stack gap="sm">
              <TextInput label="Title" value={draft.title} onChange={(e) => set('title', e.currentTarget.value)} />
              <Group grow>
                <Select label="Kind" value={draft.kind} data={[{ value: 'ui', label: 'UI journey' }, { value: 'api', label: 'API' }]}
                  onChange={(v) => v && set('kind', v as TestCase['kind'])} allowDeselect={false} />
                <Select label="Priority" value={draft.priority} data={['P1', 'P2', 'P3']} onChange={(v) => v && set('priority', v as TestCase['priority'])} allowDeselect={false} />
                <TextInput label="Category" value={draft.category} onChange={(e) => set('category', e.currentTarget.value)} />
              </Group>
              <Textarea label="Objective" autosize minRows={1} value={draft.objective} onChange={(e) => set('objective', e.currentTarget.value)} />
              <Textarea label="Preconditions" autosize minRows={1} value={draft.preconditions} onChange={(e) => set('preconditions', e.currentTarget.value)} />
              {draft.requirement_refs.length > 0 && (
                <Group gap={4}><Text size="xs" c="dimmed">Covers</Text>{draft.requirement_refs.map((r) => <Badge key={r} size="xs" variant="light">{r}</Badge>)}</Group>
              )}
            </Stack>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Card className="glass" p="md" h="100%">
            <Text size="xs" tt="uppercase" fw={700} c="dimmed">AI review</Text>
            {!rv && <Text size="sm" c="dimmed" mt="xs">Not reviewed yet. The reviewer checks that each step is one unambiguous action with an observable expected result.</Text>}
            {rv && (
              <Group mt="xs" wrap="nowrap" align="flex-start">
                <RingProgress size={84} thickness={8} roundCaps
                  sections={[{ value: rv.score * 10, color: rv.score >= 8 ? 'teal' : rv.score >= 5 ? 'yellow' : 'red' }]}
                  label={<Text ta="center" fw={800}>{rv.score}</Text>} />
                <Stack gap={4}>
                  <Badge color={rv.runnable ? 'teal' : 'red'} variant="light">{rv.runnable ? 'runnable' : 'not runnable'}</Badge>
                  <Text size="sm">{rv.summary}</Text>
                </Stack>
              </Group>
            )}
            {issuesFor(-1).map((x, k) => <Issue key={k} issue={x} />)}
            {saved.runs && saved.runs.length > 0 && (
              <Stack gap={4} mt="md">
                <Text size="xs" tt="uppercase" fw={700} c="dimmed">Recent runs</Text>
                {saved.runs.slice(0, 5).map((r) => (
                  <Group key={r.id} gap="xs">
                    <Anchor component={Link} to={`/runs/${r.id}`} size="sm">#{r.id}</Anchor>
                    <StatusBadge value={r.status} size="xs" />
                    <Text size="xs" c="dimmed">{fmtDate(r.created_at)}</Text>
                  </Group>
                ))}
              </Stack>
            )}
          </Card>
        </Grid.Col>
      </Grid>

      <Card className="glass" p="md">
        <Group justify="space-between" mb="sm">
          <Text fw={700}>Steps</Text>
          <Text size="xs" c="dimmed">Action = what the agent does · Expected = what the verifier checks</Text>
        </Group>
        <Stack gap="xs">
          {draft.steps.map((s, i) => {
            const issues = issuesFor(i)
            return (
              <Paper key={i} p="sm" radius="md" withBorder className={issues.some((x) => x.severity === 'error') ? 'step-row has-error' : 'step-row'}>
                <Group align="flex-start" wrap="nowrap" gap="sm">
                  <Badge circle size="lg" variant="light">{i + 1}</Badge>
                  <Stack gap={6} style={{ flex: 1 }}>
                    <Group grow align="flex-start">
                      <Textarea placeholder="Click the “Sign in” button" autosize minRows={1} value={s.action} onChange={(e) => setStep(i, { action: e.currentTarget.value })} />
                      <Textarea placeholder="Expected result (optional)" autosize minRows={1} value={s.expected} onChange={(e) => setStep(i, { expected: e.currentTarget.value })} />
                    </Group>
                    {issues.map((x, k) => <Issue key={k} issue={x} onApply={() => x.suggestion && setStep(i, { action: x.suggestion })} />)}
                  </Stack>
                  <Group gap={2} wrap="nowrap">
                    <ActionIcon variant="subtle" color="gray" onClick={() => move(i, -1)}><IconArrowUp size={14} /></ActionIcon>
                    <ActionIcon variant="subtle" color="gray" onClick={() => move(i, 1)}><IconArrowDown size={14} /></ActionIcon>
                    <ActionIcon variant="subtle" color="red" onClick={() => set('steps', draft.steps.filter((_, j) => j !== i))}><IconTrash size={14} /></ActionIcon>
                  </Group>
                </Group>
              </Paper>
            )
          })}
        </Stack>
        <Group justify="space-between" mt="sm">
          <Button size="xs" variant="default" leftSection={<IconPlus size={14} />} onClick={() => set('steps', [...draft.steps, { action: '', expected: '' }])}>Add step</Button>
          <Text size="xs" c="dimmed">Use <code>{'{{env:TEST_PASSWORD}}'}</code> for secrets from .env — injected in the browser, masked for the LLM.</Text>
        </Group>
      </Card>
    </Stack>
  )
}

function Issue({ issue, onApply }: { issue: StepIssue; onApply?: () => void }) {
  const color = issue.severity === 'error' ? 'red' : issue.severity === 'warning' ? 'yellow' : 'blue'
  return (
    <Alert color={color} variant="light" p={8} mt={6} title={<Text size="xs" fw={700} tt="uppercase">{issue.severity}</Text>}>
      <Text size="xs">{issue.issue}</Text>
      {issue.suggestion && (
        <Group gap={6} mt={4} wrap="nowrap">
          <Text size="xs" c="dimmed" style={{ flex: 1 }}>→ {issue.suggestion}</Text>
          {onApply && (
            <Tooltip label="Replace the step action with this suggestion">
              <Button size="compact-xs" variant="light" color={color} leftSection={<IconWand size={12} />} onClick={onApply}>apply</Button>
            </Tooltip>
          )}
        </Group>
      )}
    </Alert>
  )
}
