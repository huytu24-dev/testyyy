import { Badge, Box, Code, Collapse, Group, Paper, Stack, Text, Timeline, UnstyledButton } from '@mantine/core'
import { IconCheck, IconChevronDown, IconChevronRight, IconRefresh, IconX } from '@tabler/icons-react'
import { useState } from 'react'

import type { RunStep, SubAction } from '../api'
import { StatusIcon, fmtDuration } from './Status'

export function StepTimeline({ steps, onShowImage }: { steps: RunStep[]; onShowImage?: (src: string | null) => void }) {
  const [open, setOpen] = useState<Set<number>>(new Set())
  const running = steps.findIndex((s) => s.status === 'running')
  const lastDone = steps.reduce((acc, s, i) => (s.status === 'passed' || s.status === 'failed' ? i : acc), -1)
  const toggle = (i: number) =>
    setOpen((o) => {
      const n = new Set(o)
      n.has(i) ? n.delete(i) : n.add(i)
      return n
    })

  return (
    <Timeline active={running >= 0 ? running : lastDone} bulletSize={28} lineWidth={2} color="violet">
      {steps.map((s) => {
        const expanded = open.has(s.index) || s.status === 'running'
        return (
          <Timeline.Item
            key={s.index}
            bullet={<StatusIcon status={s.status} size={28} />}
            lineVariant={s.status === 'pending' || s.status === 'skipped' ? 'dashed' : 'solid'}
            title={
              <UnstyledButton onClick={() => toggle(s.index)} w="100%">
                <Group justify="space-between" wrap="nowrap" gap="xs">
                  <Group gap={6} wrap="nowrap">
                    {expanded ? <IconChevronDown size={14} /> : <IconChevronRight size={14} />}
                    <Text fw={600} size="sm" c={s.status === 'skipped' ? 'dimmed' : undefined}>
                      {s.index + 1}. {s.action}
                    </Text>
                  </Group>
                  <Group gap={6} wrap="nowrap">
                    {s.heal_count > 0 && (
                      <Badge size="xs" color="grape" variant="light" leftSection={<IconRefresh size={10} />}>
                        healed {s.heal_count}
                      </Badge>
                    )}
                    <Text size="xs" c="dimmed">{fmtDuration(s.duration_ms)}</Text>
                  </Group>
                </Group>
              </UnstyledButton>
            }
          >
            {s.expected && <Text size="xs" c="dimmed">expect: {s.expected}</Text>}
            {(s.error || s.reasoning) && (
              <Text size="xs" c={s.status === 'failed' ? 'red.4' : 'teal.4'} mt={4}>
                {s.error ?? s.reasoning}
              </Text>
            )}
            <Collapse expanded={expanded}>
              <Stack gap={6} mt={8}>
                {s.status === 'running' && s.sub_actions.length === 0 && (
                  <Text size="xs" c="dimmed">Observing the page…</Text>
                )}
                {s.sub_actions.map((a) => (
                  <SubActionCard key={a.n} a={a} onShow={() => onShowImage?.(a.screenshot ?? null)} />
                ))}
                {s.final_screenshot && (
                  <UnstyledButton onClick={() => onShowImage?.(s.final_screenshot)}>
                    <Text size="xs" c="violet.4">▸ screen after step</Text>
                  </UnstyledButton>
                )}
              </Stack>
            </Collapse>
          </Timeline.Item>
        )
      })}
    </Timeline>
  )
}

function SubActionCard({ a, onShow }: { a: SubAction; onShow: () => void }) {
  const { type, ...args } = a.action
  return (
    <Paper
      p={8}
      radius="md"
      withBorder
      className={`sub-card ${a.ok ? 'ok' : 'bad'}`}
      onClick={onShow}
      style={{ cursor: a.screenshot ? 'pointer' : undefined }}
    >
      <Group gap={6} wrap="nowrap">
        {a.ok ? <IconCheck size={14} color="var(--mantine-color-teal-5)" /> : <IconX size={14} color="var(--mantine-color-red-5)" />}
        <Text size="xs" fw={600} truncate>{a.label ?? type}</Text>
        {a.label == null && <Code fz={10}>{JSON.stringify(args)}</Code>}
        {a.screen_changed === false && <Badge size="xs" color="gray" variant="light">no change</Badge>}
      </Group>
      <Text size="xs" c="dimmed" mt={2}>{a.reasoning}</Text>
      {a.error && <Text size="xs" c="red.4" mt={2}>{a.error}</Text>}
      {a.data && (
        <Box mt={4}>
          <Code block fz={10} mah={140} style={{ overflow: 'auto' }}>{`HTTP ${a.data.status} ${a.data.url}\n${a.data.body}`}</Code>
        </Box>
      )}
      {a.verifier && (
        <Text size="xs" mt={4} c={a.verifier.success ? 'teal.4' : 'red.4'}>
          verifier · {a.verifier.success ? 'pass' : a.verifier.is_app_error ? 'app error' : 'rejected'} — {a.verifier.reasoning}
        </Text>
      )}
    </Paper>
  )
}
