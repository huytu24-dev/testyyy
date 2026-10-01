/** Test cases as connected nodes; edges animate into the case that is running. */
import { Badge, Group, Progress, Text } from '@mantine/core'
import { Background, Handle, Position, ReactFlow, type Edge, type Node, type NodeProps } from '@xyflow/react'
import { useMemo } from 'react'

import type { RunStatus } from '../api'
import { StatusIcon, statusColor } from './Status'

export type FlowNodeData = {
  key: string
  title: string
  kind?: string
  status?: RunStatus | 'pending'
  done?: number
  total?: number
  currentStep?: number | null
  selected?: boolean
}

function CaseNode({ data }: NodeProps<Node<FlowNodeData>>) {
  const status = data.status ?? 'pending'
  const pct = data.total ? ((data.done ?? 0) / data.total) * 100 : 0
  return (
    <div className={`case-node ${status} ${data.selected ? 'selected' : ''}`}>
      <Handle type="target" position={Position.Left} />
      <Group justify="space-between" wrap="nowrap" gap={6}>
        <Group gap={6} wrap="nowrap">
          <StatusIcon status={status} size={22} />
          <Text ff="monospace" size="xs" c="dimmed">{data.key}</Text>
        </Group>
        {data.kind && <Badge size="xs" variant="outline" color="gray">{data.kind}</Badge>}
      </Group>
      <Text size="sm" fw={600} mt={6} lineClamp={2}>{data.title}</Text>
      {data.total != null && (
        <>
          <Progress
            mt={8}
            size="sm"
            radius="xl"
            value={pct}
            color={statusColor[status] ?? 'violet'}
            striped={status === 'running'}
            animated={status === 'running'}
          />
          <Text size="xs" c="dimmed" mt={4}>
            {data.done ?? 0}/{data.total} steps
            {status === 'running' && data.currentStep != null ? ` · on step ${data.currentStep + 1}` : ''}
          </Text>
        </>
      )}
      <Handle type="source" position={Position.Right} />
    </div>
  )
}

const nodeTypes = { case: CaseNode }

export function FlowGraph({
  items,
  height = 190,
  onSelect,
}: {
  items: FlowNodeData[]
  height?: number
  onSelect?: (index: number) => void
}) {
  const { nodes, edges } = useMemo(() => {
    const nodes: Node<FlowNodeData>[] = items.map((d, i) => ({
      id: String(i),
      type: 'case',
      position: { x: i * 290, y: 0 },
      data: d,
      draggable: false,
    }))
    const edges: Edge[] = items.slice(1).map((d, i) => {
      const prev = items[i].status
      const color =
        prev === 'passed' ? 'var(--mantine-color-teal-6)' :
        prev === 'failed' || prev === 'error' ? 'var(--mantine-color-red-6)' :
        'var(--mantine-color-dark-3)'
      return {
        id: `${i}-${i + 1}`,
        source: String(i),
        target: String(i + 1),
        animated: d.status === 'running' || (prev === 'running'),
        style: { stroke: color, strokeWidth: 2 },
      }
    })
    return { nodes, edges }
  }, [items])

  return (
    <div style={{ height }} className="flow-graph">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.15, maxZoom: 1 }}
        proOptions={{ hideAttribution: true }}
        nodesConnectable={false}
        panOnScroll
        zoomOnScroll={false}
        onNodeClick={(_, n) => onSelect?.(Number(n.id))}
        colorMode="dark"
      >
        <Background gap={18} size={1} />
      </ReactFlow>
    </div>
  )
}
