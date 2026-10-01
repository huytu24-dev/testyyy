import {
  ActionIcon, Anchor, Badge, Button, Card, Checkbox, Group, Loader, Menu, NumberInput, Paper, SegmentedControl,
  SimpleGrid, Stack, Table, Tabs, Text, ThemeIcon, Title, Tooltip,
} from '@mantine/core'
import { modals } from '@mantine/modals'
import {
  IconArrowRight, IconBrandGithub, IconChecks, IconDots, IconFlask2, IconGitBranch, IconListCheck, IconPlayerPlay,
  IconPlus, IconRoute, IconSparkles, IconTrash, IconWorld, IconX,
} from '@tabler/icons-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { api, isActive, type TestCase } from '../api'
import { StatusBadge, fmtDate, elapsed } from '../components/Status'
import { useAction, useCases, useFlowRuns, useFlows, useProject, useRuns } from '../queries'

export default function ProjectPage() {
  const id = Number(useParams().id)
  const navigate = useNavigate()
  const { data: project } = useProject(id)
  const generating = project?.gen_status === 'running'
  const { data: cases = [] } = useCases(id, generating)
  const { data: flows = [] } = useFlows(id)
  const { data: runs = [] } = useRuns(id)
  const { data: flowRuns = [] } = useFlowRuns(id)
  const [tab, setTab] = useState<string | null>('cases')

  const del = useAction(() => api.deleteProject(id), { invalidate: ['projects'] })

  if (!project) return <Loader m="xl" />

  const approved = cases.filter((c) => c.status === 'approved')
  const reviewed = cases.filter((c) => c.review).length
  const passed = cases.filter((c) => c.last_run_status === 'passed').length

  return (
    <Stack gap="lg" maw={1300} mx="auto">
      <Group justify="space-between" align="flex-start">
        <div>
          <Anchor component={Link} to="/" size="xs" c="dimmed">← Projects</Anchor>
          <Title order={2}>{project.name}</Title>
          <Group gap="md" mt={4} c="dimmed">
            <Group gap={4}><IconWorld size={14} /><Anchor href={project.base_url} target="_blank" size="xs">{project.base_url}</Anchor></Group>
            {project.repo_url && <Group gap={4}><IconBrandGithub size={14} /><Text size="xs">{project.repo_url}</Text></Group>}
          </Group>
        </div>
        <Menu position="bottom-end">
          <Menu.Target><ActionIcon variant="subtle" color="gray"><IconDots size={18} /></ActionIcon></Menu.Target>
          <Menu.Dropdown>
            <Menu.Item color="red" leftSection={<IconTrash size={14} />} onClick={() =>
              modals.openConfirmModal({
                title: 'Delete project?',
                children: <Text size="sm">All test cases, flows and runs of “{project.name}” will be deleted.</Text>,
                labels: { confirm: 'Delete', cancel: 'Cancel' },
                confirmProps: { color: 'red' },
                onConfirm: async () => { await del.mutateAsync(undefined); navigate('/') },
              })}>Delete project</Menu.Item>
          </Menu.Dropdown>
        </Menu>
      </Group>

      <SimpleGrid cols={{ base: 2, md: 4 }}>
        <PipelineCard n={1} icon={<IconSparkles size={18} />} title="Generate" value={`${cases.length} cases`}
          sub={`${project.requirements?.length ?? 0} requirements`} color="violet" />
        <PipelineCard n={2} icon={<IconListCheck size={18} />} title="Review" value={`${approved.length} approved`}
          sub={`${reviewed} AI-reviewed`} color="indigo" />
        <PipelineCard n={3} icon={<IconGitBranch size={18} />} title="Flow" value={`${flows.length} flows`}
          sub="cases chained together" color="cyan" />
        <PipelineCard n={4} icon={<IconPlayerPlay size={18} />} title="Run" value={`${passed}/${cases.length} passing`}
          sub={`${runs.filter((r) => isActive(r.status)).length} running now`} color="teal" />
      </SimpleGrid>

      <GenerateBar projectId={id} status={project.gen_status} message={project.gen_message} />

      <Tabs value={tab} onChange={setTab} variant="pills" radius="xl">
        <Tabs.List>
          <Tabs.Tab value="cases" leftSection={<IconFlask2 size={14} />}>Test cases <Badge size="xs" ml={4} variant="light">{cases.length}</Badge></Tabs.Tab>
          <Tabs.Tab value="flows" leftSection={<IconRoute size={14} />}>Flows <Badge size="xs" ml={4} variant="light">{flows.length}</Badge></Tabs.Tab>
          <Tabs.Tab value="requirements">Requirements <Badge size="xs" ml={4} variant="light">{project.requirements?.length ?? 0}</Badge></Tabs.Tab>
          <Tabs.Tab value="runs">Runs <Badge size="xs" ml={4} variant="light">{runs.length + flowRuns.length}</Badge></Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="cases" pt="md"><CasesTab projectId={id} cases={cases} onFlowCreated={(fid) => navigate(`/flows/${fid}`)} /></Tabs.Panel>
        <Tabs.Panel value="flows" pt="md"><FlowsTab projectId={id} cases={cases} /></Tabs.Panel>
        <Tabs.Panel value="requirements" pt="md">
          <Card className="glass" p={0}>
            <Table verticalSpacing="sm" highlightOnHover>
              <Table.Thead><Table.Tr><Table.Th>ID</Table.Th><Table.Th>Feature</Table.Th><Table.Th>Requirement</Table.Th><Table.Th>Acceptance</Table.Th><Table.Th>Priority</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>
                {project.requirements?.map((r) => (
                  <Table.Tr key={r.id}>
                    <Table.Td><Text ff="monospace" size="xs">{r.ref}</Text></Table.Td>
                    <Table.Td>{r.feature}</Table.Td><Table.Td>{r.text}</Table.Td>
                    <Table.Td><Text size="sm" c="dimmed">{r.acceptance}</Text></Table.Td>
                    <Table.Td>{r.priority && <Badge variant="light" size="sm">{r.priority}</Badge>}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
            {!project.requirements?.length && <Text c="dimmed" ta="center" p="lg">No Excel uploaded.</Text>}
          </Card>
        </Tabs.Panel>
        <Tabs.Panel value="runs" pt="md">
          <Stack>
            {flowRuns.length > 0 && (
              <Card className="glass" p={0}>
                <Text fw={700} p="sm">Flow runs</Text>
                <Table highlightOnHover>
                  <Table.Tbody>
                    {flowRuns.map((fr) => (
                      <Table.Tr key={fr.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/flow-runs/${fr.id}`)}>
                        <Table.Td w={70}><Text ff="monospace" size="xs">#{fr.id}</Text></Table.Td>
                        <Table.Td><Text fw={600} size="sm">{fr.flow_name}</Text></Table.Td>
                        <Table.Td><ChainChips items={fr.runs.map((r) => ({ key: r.key, status: r.status }))} /></Table.Td>
                        <Table.Td><StatusBadge value={fr.status} /></Table.Td>
                        <Table.Td><Text size="xs" c="dimmed">{fmtDate(fr.created_at)} · {elapsed(fr.started_at, fr.finished_at)}</Text></Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Card>
            )}
            <Card className="glass" p={0}>
              <Text fw={700} p="sm">Case runs</Text>
              <Table highlightOnHover>
                <Table.Tbody>
                  {runs.map((r) => (
                    <Table.Tr key={r.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/runs/${r.id}`)}>
                      <Table.Td w={70}><Text ff="monospace" size="xs">#{r.id}</Text></Table.Td>
                      <Table.Td><Text ff="monospace" size="xs" c="dimmed" span>{r.case_key}</Text> <Text span size="sm">{r.case_title}</Text></Table.Td>
                      <Table.Td>{r.flow_run_id && <Badge size="xs" variant="outline" color="cyan">flow #{r.flow_run_id}</Badge>}</Table.Td>
                      <Table.Td><StatusBadge value={r.status} /></Table.Td>
                      <Table.Td><Text size="xs">{r.passed_steps}/{r.step_count} steps</Text></Table.Td>
                      <Table.Td><Text size="xs" c="dimmed">{fmtDate(r.started_at ?? r.created_at)}</Text></Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
              {runs.length === 0 && <Text c="dimmed" ta="center" p="lg">No runs yet.</Text>}
            </Card>
          </Stack>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  )
}

function PipelineCard({ n, icon, title, value, sub, color }: { n: number; icon: React.ReactNode; title: string; value: string; sub: string; color: string }) {
  return (
    <Paper className="glass" p="md" radius="lg">
      <Group gap="sm" wrap="nowrap">
        <ThemeIcon size={38} radius="md" variant="light" color={color}>{icon}</ThemeIcon>
        <div style={{ minWidth: 0 }}>
          <Text size="xs" c="dimmed" tt="uppercase" fw={700}>{n} · {title}</Text>
          <Text fw={700}>{value}</Text>
          <Text size="xs" c="dimmed" truncate>{sub}</Text>
        </div>
      </Group>
    </Paper>
  )
}

function GenerateBar({ projectId, status, message }: { projectId: number; status: string; message: string | null }) {
  const [generator, setGenerator] = useState('builtin')
  const [max, setMax] = useState<number | string>(8)
  const gen = useAction(() => api.generate(projectId, generator, Number(max) || 8), { invalidate: ['project'] })
  const running = status === 'running'
  return (
    <Paper className="glass" p="sm" radius="lg">
      <Group justify="space-between" wrap="wrap">
        <Group gap="sm">
          <SegmentedControl size="xs" value={generator} onChange={setGenerator} data={[
            { label: 'Builtin · Claude', value: 'builtin' }, { label: 'TestTeller', value: 'testteller' },
          ]} />
          <NumberInput size="xs" w={110} min={1} max={30} value={max} onChange={setMax} leftSection={<Text size="xs" c="dimmed">max</Text>} />
          <Button size="xs" leftSection={<IconSparkles size={14} />} variant="gradient" gradient={{ from: 'violet', to: 'cyan', deg: 135 }}
            loading={running || gen.isPending} onClick={() => gen.mutate(undefined)}>
            Generate test cases
          </Button>
        </Group>
        {message && (
          <Group gap={6}>
            {running && <Loader size="xs" />}
            <Text size="xs" c={status === 'error' ? 'red.4' : 'dimmed'}>{message}</Text>
          </Group>
        )}
      </Group>
    </Paper>
  )
}

function CasesTab({ projectId, cases, onFlowCreated }: { projectId: number; cases: TestCase[]; onFlowCreated: (id: number) => void }) {
  const navigate = useNavigate()
  const [selected, setSelected] = useState<number[]>([])
  const sel = new Set(selected)
  const setStatus = useAction(
    (status: TestCase['status']) => Promise.all(selected.map((cid) => api.updateCase(cid, { status }))),
    { invalidate: ['cases', 'projects'] },
  )
  const runMany = useAction((ids: number[] | undefined) => api.runMany(projectId, ids), { invalidate: ['runs', 'cases'], success: (r) => `Started ${r.length} run(s)` })
  const addCase = useAction(() => api.createCase(projectId, { title: 'New test case', steps: [{ action: 'Open the home page', expected: '' }] }), { invalidate: ['cases'] })
  const newFlow = useAction(
    (ids: number[]) => api.createFlow(projectId, { name: `Flow ${new Date().toLocaleTimeString()}`, case_ids: ids, shared_session: true, stop_on_fail: true }),
    { invalidate: ['flows'] },
  )
  // keep the selection in table order (that becomes the flow order)
  const ordered = cases.filter((c) => sel.has(c.id)).map((c) => c.id)

  return (
    <Stack gap="sm">
      <Group justify="space-between">
        <Group gap="xs">
          <Button size="xs" variant="default" leftSection={<IconPlus size={14} />} onClick={async () => {
            const c = await addCase.mutateAsync(undefined).catch(() => null)
            if (c) navigate(`/cases/${c.id}`)
          }}>Add case</Button>
          {selected.length > 0 && (
            <>
              <Badge variant="light">{selected.length} selected</Badge>
              <Button size="xs" variant="light" color="teal" leftSection={<IconChecks size={14} />} onClick={() => setStatus.mutate('approved')}>Approve</Button>
              <Button size="xs" variant="light" color="red" leftSection={<IconX size={14} />} onClick={() => setStatus.mutate('rejected')}>Reject</Button>
              <Button size="xs" variant="light" color="cyan" leftSection={<IconRoute size={14} />} onClick={async () => {
                const f = await newFlow.mutateAsync(ordered).catch(() => null)
                if (f) onFlowCreated(f.id)
              }}>Chain into flow</Button>
              <Button size="xs" variant="light" leftSection={<IconPlayerPlay size={14} />} onClick={() => runMany.mutate(ordered)}>Run each</Button>
            </>
          )}
        </Group>
        <Button size="xs" leftSection={<IconPlayerPlay size={14} />} disabled={!cases.some((c) => c.status === 'approved')}
          loading={runMany.isPending} onClick={() => runMany.mutate(undefined)}>
          Run all approved
        </Button>
      </Group>
      <Card className="glass" p={0}>
        <Table highlightOnHover verticalSpacing="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th w={40}><Checkbox size="xs" checked={cases.length > 0 && selected.length === cases.length}
                indeterminate={selected.length > 0 && selected.length < cases.length}
                onChange={(e) => setSelected(e.currentTarget.checked ? cases.map((c) => c.id) : [])} /></Table.Th>
              <Table.Th>Key</Table.Th><Table.Th>Test case</Table.Th><Table.Th>Kind</Table.Th><Table.Th>Steps</Table.Th>
              <Table.Th>Review</Table.Th><Table.Th>Status</Table.Th><Table.Th>Last run</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {cases.map((c) => (
              <Table.Tr key={c.id} opacity={c.status === 'rejected' ? 0.5 : 1}>
                <Table.Td><Checkbox size="xs" checked={sel.has(c.id)} onChange={() =>
                  setSelected((s) => (s.includes(c.id) ? s.filter((x) => x !== c.id) : [...s, c.id]))} /></Table.Td>
                <Table.Td><Text ff="monospace" size="xs" c="dimmed">{c.key}</Text></Table.Td>
                <Table.Td>
                  <Anchor component={Link} to={`/cases/${c.id}`} fw={600} size="sm">{c.title}</Anchor>
                  <Group gap={4} mt={2}>
                    <Badge size="xs" variant="dot" color={c.priority === 'P1' ? 'red' : c.priority === 'P2' ? 'yellow' : 'gray'}>{c.priority}</Badge>
                    {c.category && <Text size="xs" c="dimmed">{c.category}</Text>}
                  </Group>
                </Table.Td>
                <Table.Td><Badge size="xs" variant="outline" color={c.kind === 'api' ? 'cyan' : 'violet'}>{c.kind}</Badge></Table.Td>
                <Table.Td><Text size="sm">{c.steps.length}</Text></Table.Td>
                <Table.Td>{c.review
                  ? <Badge variant="light" color={c.review.score >= 8 ? 'teal' : c.review.score >= 5 ? 'yellow' : 'red'}>{c.review.score}/10</Badge>
                  : <Text c="dimmed" size="xs">—</Text>}</Table.Td>
                <Table.Td><StatusBadge value={c.status} /></Table.Td>
                <Table.Td><StatusBadge value={c.last_run_status} /></Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
        {cases.length === 0 && <Text c="dimmed" ta="center" p="xl">No test cases yet — generate some or add one.</Text>}
      </Card>
    </Stack>
  )
}

function ChainChips({ items }: { items: { key: string; status?: string }[] }) {
  return (
    <Group gap={4} wrap="nowrap">
      {items.map((it, i) => (
        <Group key={i} gap={4} wrap="nowrap">
          {i > 0 && <IconArrowRight size={12} color="var(--mantine-color-dark-2)" />}
          <StatusBadge value={it.status ?? 'pending'} size="xs" />
          <Text ff="monospace" size="xs">{it.key}</Text>
        </Group>
      ))}
    </Group>
  )
}

function FlowsTab({ projectId, cases }: { projectId: number; cases: TestCase[] }) {
  const navigate = useNavigate()
  const { data: flows = [] } = useFlows(projectId)
  const byId = new Map(cases.map((c) => [c.id, c]))
  const create = useAction(
    () => api.createFlow(projectId, {
      name: 'Main user journey',
      case_ids: cases.filter((c) => c.status === 'approved').map((c) => c.id),
      shared_session: true, stop_on_fail: true,
    }),
    { invalidate: ['flows'] },
  )
  const runFlow = useAction((fid: number) => api.runFlow(fid), { invalidate: ['flows', 'flowRuns'] })

  return (
    <Stack>
      <Group justify="space-between">
        <Text size="sm" c="dimmed">A flow runs test cases one after another — optionally in the same browser session, so case 2 continues where case 1 ended.</Text>
        <Button size="xs" leftSection={<IconPlus size={14} />} onClick={async () => {
          const f = await create.mutateAsync(undefined).catch(() => null)
          if (f) navigate(`/flows/${f.id}`)
        }}>New flow</Button>
      </Group>
      {flows.map((f) => (
        <Card key={f.id} className="glass hover-lift" p="md">
          <Group justify="space-between" wrap="nowrap">
            <Stack gap={6} style={{ minWidth: 0 }}>
              <Group gap="xs">
                <Anchor component={Link} to={`/flows/${f.id}`} fw={700}>{f.name}</Anchor>
                {f.shared_session && <Badge size="xs" variant="light" color="cyan">shared session</Badge>}
                {f.stop_on_fail && <Badge size="xs" variant="light" color="orange">stop on fail</Badge>}
              </Group>
              <ChainChips items={f.case_ids.map((cid) => ({ key: byId.get(cid)?.key ?? `#${cid}`, status: byId.get(cid)?.last_run_status ?? undefined }))} />
            </Stack>
            <Group gap="xs" wrap="nowrap">
              {f.last_run && (
                <Tooltip label="Last run">
                  <Anchor component={Link} to={`/flow-runs/${f.last_run.id}`}><StatusBadge value={f.last_run.status} /></Anchor>
                </Tooltip>
              )}
              <Button size="xs" leftSection={<IconPlayerPlay size={14} />} loading={runFlow.isPending && runFlow.variables === f.id}
                onClick={async () => {
                  const fr = await runFlow.mutateAsync(f.id).catch(() => null)
                  if (fr) navigate(`/flow-runs/${fr.id}`)
                }}>Run flow</Button>
            </Group>
          </Group>
        </Card>
      ))}
      {flows.length === 0 && <Card className="glass" p="xl"><Text c="dimmed" ta="center">No flows yet. Select cases in the Test cases tab and click “Chain into flow”, or create one here from all approved cases.</Text></Card>}
    </Stack>
  )
}
