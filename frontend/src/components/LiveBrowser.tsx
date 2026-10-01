/**
 * The sandbox viewer: a fake browser window showing the real headless browser via CDP
 * screencast frames, with an overlay of what the agent is doing (phase, target element).
 */
import { Badge, Box, Group, Loader, Text, Tooltip } from '@mantine/core'
import {
  IconBrain, IconCheck, IconEye, IconHandFinger, IconLock, IconRoute, IconShieldCheck, IconX,
} from '@tabler/icons-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'

import { wsUrl, type LiveMsg } from '../api'

type Phase = Extract<LiveMsg, { type: 'phase' }>
type Box4 = { x: number; y: number; width: number; height: number }

const PHASES: Record<string, { label: string; color: string; icon: ReactNode }> = {
  navigate: { label: 'Opening', color: 'indigo', icon: <IconRoute size={14} /> },
  observe: { label: 'Observing', color: 'cyan', icon: <IconEye size={14} /> },
  plan: { label: 'Thinking', color: 'violet', icon: <IconBrain size={14} /> },
  act: { label: 'Acting', color: 'blue', icon: <IconHandFinger size={14} /> },
  verify: { label: 'Verifying', color: 'grape', icon: <IconShieldCheck size={14} /> },
  gave_up: { label: 'Gave up', color: 'red', icon: <IconX size={14} /> },
  done: { label: 'Finished', color: 'gray', icon: <IconCheck size={14} /> },
}

export function LiveBrowser({
  channel,
  active,
  fallbackImage,
  caption,
}: {
  channel: string // e.g. "run/12" or "flow/3"
  active: boolean
  fallbackImage?: string | null
  caption?: ReactNode
}) {
  const imgRef = useRef<HTMLImageElement>(null)
  const [hasFrame, setHasFrame] = useState(false)
  const [size, setSize] = useState({ w: 1280, h: 800 })
  const [url, setUrl] = useState('')
  const [phase, setPhase] = useState<Phase | null>(null)
  const [box, setBox] = useState<Box4 | null>(null)
  const [flash, setFlash] = useState<{ ok: boolean; text: string } | null>(null)
  const [caseTitle, setCaseTitle] = useState<string | null>(null)
  const [lastFrameAt, setLastFrameAt] = useState(0)
  const [, tick] = useState(0)

  useEffect(() => {
    setHasFrame(false)
    setPhase(null)
    setBox(null)
    const ws = new WebSocket(wsUrl(`/api/live/${channel}`))
    let flashTimer: ReturnType<typeof setTimeout>
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data) as LiveMsg
      switch (m.type) {
        case 'frame':
          // Set src directly: no React re-render per frame.
          if (imgRef.current) imgRef.current.src = `data:image/jpeg;base64,${m.data}`
          if (m.w && m.h) setSize((s) => (s.w === m.w && s.h === m.h ? s : { w: m.w, h: m.h }))
          setHasFrame(true)
          setLastFrameAt(Date.now())
          break
        case 'url':
          setUrl(m.url)
          break
        case 'case':
          setCaseTitle(`${m.key} · ${m.title}`)
          break
        case 'phase':
          setPhase(m)
          setBox(m.phase === 'act' && m.box ? m.box : null)
          break
        case 'result':
          setBox(null)
          if (!m.ok) {
            setFlash({ ok: false, text: m.error ?? 'Action failed' })
            clearTimeout(flashTimer)
            flashTimer = setTimeout(() => setFlash(null), 2500)
          }
          break
        case 'verdict':
          setFlash({ ok: m.success, text: m.reasoning })
          clearTimeout(flashTimer)
          flashTimer = setTimeout(() => setFlash(null), 2500)
          break
      }
    }
    return () => {
      ws.close()
      clearTimeout(flashTimer)
    }
  }, [channel])

  // Re-render every second so the LIVE badge goes stale when frames stop.
  useEffect(() => {
    if (!active) return
    const t = setInterval(() => tick((n) => n + 1), 1000)
    return () => clearInterval(t)
  }, [active])

  const live = active && Date.now() - lastFrameAt < 4000
  const p = phase ? PHASES[phase.phase] : null
  const showFallback = !hasFrame || (!active && fallbackImage)

  return (
    <Box className="browser">
      <Group className="browser-bar" gap={8} wrap="nowrap">
        <Group gap={6} wrap="nowrap">
          <span className="dot red" /><span className="dot yellow" /><span className="dot green" />
        </Group>
        <Group className="url-pill" gap={6} wrap="nowrap">
          <IconLock size={12} />
          <Text size="xs" truncate>{url || 'about:blank'}</Text>
        </Group>
        {live ? (
          <Badge color="red" variant="filled" size="sm" leftSection={<span className="rec" />}>LIVE</Badge>
        ) : (
          <Badge color="gray" variant="light" size="sm">{active ? 'connecting' : 'replay'}</Badge>
        )}
      </Group>

      <Box className="browser-view" style={{ aspectRatio: `${size.w} / ${size.h}` }}>
        <img ref={imgRef} alt="" className="frame" style={{ display: showFallback ? 'none' : 'block' }} />
        {showFallback && (
          fallbackImage
            ? <img src={fallbackImage} alt="screenshot" className="frame" />
            : <div className="frame empty">{active ? <Loader color="violet" type="dots" /> : <Text c="dimmed" size="sm">No screen yet</Text>}</div>
        )}
        {box && !showFallback && (
          <div
            className="target-box"
            style={{
              left: `${(box.x / size.w) * 100}%`,
              top: `${(box.y / size.h) * 100}%`,
              width: `${(box.width / size.w) * 100}%`,
              height: `${(box.height / size.h) * 100}%`,
            }}
          />
        )}
        {flash && (
          <div className={`flash ${flash.ok ? 'ok' : 'bad'}`}>
            {flash.ok ? <IconCheck size={14} /> : <IconX size={14} />}
            <span>{flash.text}</span>
          </div>
        )}
      </Box>

      <Group className="browser-status" gap={10} wrap="nowrap">
        {active && p ? (
          <Badge color={p.color} variant="light" leftSection={p.icon} style={{ flex: 'none' }}>
            {p.label}{phase?.step != null ? ` · step ${phase.step + 1}` : ''}
          </Badge>
        ) : (
          <Badge color="gray" variant="light" style={{ flex: 'none' }}>{active ? 'Waiting' : 'Idle'}</Badge>
        )}
        <Tooltip label={phase?.reasoning} disabled={!phase?.reasoning} multiline w={360} withArrow>
          <Text size="sm" truncate fw={500}>
            {active ? (phase?.label ?? caseTitle ?? '') : caption}
          </Text>
        </Tooltip>
      </Group>
    </Box>
  )
}
