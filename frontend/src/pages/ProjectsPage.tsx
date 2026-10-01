import { Button, Card, Group, Modal, RingProgress, SimpleGrid, Stack, Text, TextInput, ThemeIcon, Title } from '@mantine/core'
import { Dropzone } from '@mantine/dropzone'
import { useDisclosure } from '@mantine/hooks'
import { IconBrandGithub, IconFileSpreadsheet, IconPlus, IconUpload, IconWorld, IconX } from '@tabler/icons-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { api } from '../api'
import { useAction, useProjects } from '../queries'

export default function ProjectsPage() {
  const { data: projects = [], isLoading } = useProjects()
  const [opened, { open, close }] = useDisclosure(false)

  return (
    <Stack gap="lg" maw={1200} mx="auto">
      <Group justify="space-between" align="flex-end">
        <div>
          <Title order={2}>Projects</Title>
          <Text c="dimmed" size="sm">Requirements + repo → AI-generated test cases → an agent runs them in a sandboxed browser.</Text>
        </div>
        <Button leftSection={<IconPlus size={16} />} variant="gradient" gradient={{ from: 'violet', to: 'cyan', deg: 135 }} onClick={open}>
          New project
        </Button>
      </Group>

      {!isLoading && projects.length === 0 && (
        <Card className="glass" p="xl" ta="center">
          <Text c="dimmed">No projects yet. Create one with your app URL, a GitHub repo and an Excel of requirements.</Text>
        </Card>
      )}

      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
        {projects.map((p) => {
          const total = p.case_count ?? 0
          const pass = total ? ((p.passed_count ?? 0) / total) * 100 : 0
          const fail = total ? ((p.failed_count ?? 0) / total) * 100 : 0
          return (
            <Card key={p.id} component={Link} to={`/projects/${p.id}`} className="glass hover-lift" padding="lg">
              <Group justify="space-between" wrap="nowrap" align="flex-start">
                <Stack gap={4} style={{ minWidth: 0 }}>
                  <Text fw={700} size="lg" truncate>{p.name}</Text>
                  <Group gap={6} c="dimmed"><IconWorld size={14} /><Text size="xs" truncate>{p.base_url}</Text></Group>
                  {p.repo_url && <Group gap={6} c="dimmed"><IconBrandGithub size={14} /><Text size="xs" truncate>{p.repo_url}</Text></Group>}
                </Stack>
                <RingProgress
                  size={74}
                  thickness={7}
                  roundCaps
                  sections={[{ value: pass, color: 'teal' }, { value: fail, color: 'red' }]}
                  label={<Text ta="center" size="xs" fw={700}>{Math.round(pass)}%</Text>}
                />
              </Group>
              <Group gap="lg" mt="md">
                <Stat label="cases" value={total} />
                <Stat label="approved" value={p.approved_count ?? 0} color="violet" />
                <Stat label="passed" value={p.passed_count ?? 0} color="teal" />
                <Stat label="failed" value={p.failed_count ?? 0} color="red" />
              </Group>
            </Card>
          )
        })}
      </SimpleGrid>

      <NewProjectModal opened={opened} onClose={close} />
    </Stack>
  )
}

function Stat({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <div>
      <Text fw={700} c={color}>{value}</Text>
      <Text size="xs" c="dimmed">{label}</Text>
    </div>
  )
}

function NewProjectModal({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const navigate = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const create = useAction((form: FormData) => api.createProject(form), {
    invalidate: ['projects'],
    success: 'Project created',
  })

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = new FormData(e.currentTarget)
    if (file) form.set('requirements', file)
    const p = await create.mutateAsync(form).catch(() => null)
    if (p) {
      onClose()
      navigate(`/projects/${p.id}`)
    }
  }

  return (
    <Modal opened={opened} onClose={onClose} title={<Text fw={700}>New project</Text>} size="lg" centered>
      <form onSubmit={onSubmit}>
        <Stack>
          <TextInput name="name" label="Name" placeholder="Todo app" required data-autofocus />
          <TextInput name="base_url" label="App URL" description="The running app the agent will test" placeholder="http://localhost:8001" required leftSection={<IconWorld size={16} />} />
          <TextInput name="repo_url" label="GitHub repo" description="URL or local path — used to understand routes and UI labels" placeholder="https://github.com/org/repo" leftSection={<IconBrandGithub size={16} />} />
          <Dropzone
            onDrop={(files) => setFile(files[0] ?? null)}
            maxFiles={1}
            accept={['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/vnd.ms-excel.sheet.macroEnabled.12']}
          >
            <Group justify="center" gap="md" mih={90} style={{ pointerEvents: 'none' }}>
              <Dropzone.Accept><IconUpload size={36} /></Dropzone.Accept>
              <Dropzone.Reject><IconX size={36} /></Dropzone.Reject>
              <Dropzone.Idle>
                <ThemeIcon size={44} variant="light" color="teal"><IconFileSpreadsheet size={26} /></ThemeIcon>
              </Dropzone.Idle>
              <div>
                <Text fw={600}>{file ? file.name : 'Drop requirements Excel here'}</Text>
                <Text size="xs" c="dimmed">{file ? `${(file.size / 1024).toFixed(1)} KB` : '.xlsx — columns like ID, Feature, Requirement, Acceptance (EN or VI)'}</Text>
              </div>
            </Group>
          </Dropzone>
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={create.isPending}>Create project</Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}
