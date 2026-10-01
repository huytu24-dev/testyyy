import { Badge, Card, Grid, Group, Progress, ScrollArea, Stack, Text } from '@mantine/core'
import { IconBolt, IconRefresh } from '@tabler/icons-react'
import { useState } from 'react'

import { isActive, type Run } from '../api'
import { LiveBrowser } from './LiveBrowser'
import { elapsed } from './Status'
import { StepTimeline } from './StepTimeline'

/** Live browser on the left, step timeline on the right. `channel` decides which live stream to watch. */
export function RunSandbox({ run, channel, liveActive }: { run: Run; channel: string; liveActive: boolean }) {
  const [pinned, setPinned] = useState<string | null>(null)
  const active = isActive(run.status)

  const done = run.steps.filter((s) => s.status === 'passed' || s.status === 'failed').length
  const passed = run.steps.filter((s) => s.status === 'passed').length
  const heals = run.steps.reduce((n, s) => n + s.heal_count, 0)
  const tokens = (run.usage?.input_tokens ?? 0) + (run.usage?.output_tokens ?? 0)
  const lastShot = [...run.steps].reverse().map((s) => s.final_screenshot ?? s.sub_actions.at(-1)?.screenshot).find(Boolean) ?? null

  return (
    <Grid gap="lg">
      <Grid.Col span={{ base: 12, lg: 7 }}>
        <Stack gap="sm" className="sticky-top">
          <LiveBrowser
            channel={channel}
            active={liveActive}
            fallbackImage={pinned ?? (active ? null : lastShot)}
            caption={pinned ? 'Screenshot from the timeline' : run.error ?? (run.status === 'passed' ? 'All steps passed' : '')}
          />
          <Group gap="lg">
            <Metric label="progress" value={`${done}/${run.steps.length}`} />
            <Metric label="passed" value={String(passed)} color="teal" />
            <Metric label="self-heals" value={String(heals)} color="grape" icon={<IconRefresh size={12} />} />
            <Metric label="duration" value={elapsed(run.started_at, run.finished_at) || '—'} />
            {tokens > 0 && <Metric label="tokens" value={`${(tokens / 1000).toFixed(1)}k`} icon={<IconBolt size={12} />} />}
          </Group>
          <Progress.Root size="md" radius="xl">
            <Progress.Section value={(passed / Math.max(1, run.steps.length)) * 100} color="teal" />
            <Progress.Section value={((done - passed) / Math.max(1, run.steps.length)) * 100} color="red" />
            {active && <Progress.Section value={100 / Math.max(1, run.steps.length)} color="blue" striped animated />}
          </Progress.Root>
        </Stack>
      </Grid.Col>
      <Grid.Col span={{ base: 12, lg: 5 }}>
        <Card className="glass" p="md">
          <Group justify="space-between" mb="sm">
            <Text fw={700}>Steps</Text>
            {pinned && <Badge variant="light" style={{ cursor: 'pointer' }} onClick={() => setPinned(null)}>back to live ✕</Badge>}
          </Group>
          <ScrollArea.Autosize mah="calc(100vh - 260px)" offsetScrollbars>
            <StepTimeline steps={run.steps} onShowImage={setPinned} />
          </ScrollArea.Autosize>
        </Card>
      </Grid.Col>
    </Grid>
  )
}

function Metric({ label, value, color, icon }: { label: string; value: string; color?: string; icon?: React.ReactNode }) {
  return (
    <Stack gap={0}>
      <Group gap={4}>{icon}<Text fw={700} c={color}>{value}</Text></Group>
      <Text size="xs" c="dimmed">{label}</Text>
    </Stack>
  )
}
