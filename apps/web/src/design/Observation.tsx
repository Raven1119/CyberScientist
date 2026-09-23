import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import { Badge } from '../components'
import { PHASE_LABELS, TERMINAL_PHASES } from '../labels'
import type { SupervisionStatus } from '../types'
import { cancelPixels, pixelTransition } from './motion'
import { createField } from './observation-field'
import type { FieldMode } from './observation-field'
import { usePresentation } from './presentation'

export function Observation({ runId, phase, connected, supervision, demo }: {
  runId?: string; phase?: string | null; connected: boolean; supervision: SupervisionStatus | null; demo: boolean
}) {
  const { theme, motion, reduced, ambient, writing, setPreference } = usePresentation()
  const [mode, setMode] = useState<FieldMode>('threads'), [selected, setSelected] = useState<FieldMode>('threads')
  const [error, setError] = useState('')
  const aperture = useRef<HTMLDivElement>(null), field = useRef<HTMLDivElement>(null)
  const scene = useRef<ReturnType<typeof createField>>()
  // Only backend-confirmed activity drives ambient motion; no synthetic progress.
  const active = phase === 'running' && connected && !!(supervision?.brain_busy || supervision?.executor_busy)
  const running = active && motion && !reduced && ambient && !writing
  // Read tokens after PresentationProvider has committed the root theme attribute.
  useEffect(() => {
    const host = field.current
    if (!host) return
    setError('')
    try {
      const style = getComputedStyle(document.documentElement)
      const created = createField(host, mode, style.getPropertyValue('--ril-field-ink'), style.getPropertyValue('--ril-field-base'))
      scene.current = created
      return () => { created.dispose(); scene.current = undefined }
    } catch (e) { setError(e instanceof Error ? e.message : '观测图形不可用。') }
  }, [mode, theme])
  useEffect(() => { scene.current?.setRunning(running) }, [running, mode, theme])
  useLayoutEffect(() => {
    const host = aperture.current
    return () => { if (host) cancelPixels(host) }
  }, [])
  const choose = (next: FieldMode) => {
    setSelected(next)
    if (aperture.current) pixelTransition(aperture.current, () => flushSync(() => setMode(next)))
  }
  const label = phase ? (PHASE_LABELS[phase as keyof typeof PHASE_LABELS] ?? phase) : '尚未开始'
  const agentLabel = (busy: boolean | undefined, busyLabel: string) => {
    if (!runId) return '未启动'
    if (TERMINAL_PHASES.some(p => p === phase)) return '已归档'
    if (phase === 'paused') return '已暂停'
    if (phase !== 'running') return label
    if (!connected || !supervision) return '状态待确认'
    return busy ? busyLabel : '空闲'
  }
  const motionLabel = !active ? '静态观测' : reduced ? '系统已减少动态' : !motion ? '动效已关闭'
    : !ambient ? '画面已暂停' : writing ? '书写中 · 画面暂停' : mode === 'dots' ? '点阵可响应指针' : '活动信号'
  return <article className="observation" aria-label="运行观测">
    <div className="section-heading"><h2>运行观测 <span>OBSERVATORY</span></h2><Badge tone={active ? 'green' : 'neutral'}>{label}</Badge></div>
    <div className="observation-frame">
      <div className="observation-toolbar"><span className="instrument-label">{demo ? 'DEMO / ' : ''}{runId ? `RUN / ${runId.slice(0, 8)}` : 'AWAITING RUN'}</span>
        <button type="button" className="btn small" aria-pressed={!ambient} onClick={() => setPreference('ambient', !ambient)} title="仅暂停观测画面，不暂停研究">{ambient ? '暂停画面' : '恢复画面'}</button>
      </div>
      <div className="observation-aperture" ref={aperture} data-mode={mode} data-activity={active}>
        <div ref={field} className="observation-field" />
        <span className="field-code" aria-hidden="true">{mode === 'threads' ? 'RB–01 / THREADS' : 'RB–08 / DOT GRID'}</span>
        <span className="field-caption">{motionLabel}</span>
        {error && <p className="field-error" role="status">{error}</p>}
      </div>
      <div className="observation-modes" role="group" aria-label="观测图形">
        <button type="button" className="btn" aria-pressed={selected === 'threads'} onClick={() => choose('threads')}>01 线束</button>
        <button type="button" className="btn" aria-pressed={selected === 'dots'} onClick={() => choose('dots')}>02 点阵</button>
      </div>
      <p className="observation-note">{demo ? '演示运行信号' : '后端活动信号'} · 图形不代表计算进度。书写时自动静止。</p>
    </div>
    <div className="agent-status"><span>大脑 <b>{agentLabel(supervision?.brain_busy, '审阅中')}</b></span>
      <span>执行器 <b>{agentLabel(supervision?.executor_busy, '执行中')}</b></span></div>
  </article>
}
