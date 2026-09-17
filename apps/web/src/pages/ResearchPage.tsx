import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import { useApp } from '../app-context'
import { Badge, Modal } from '../components'
import {
  ACTIVE_PHASES,
  CONTRACT_LABELS,
  eventLabel,
  eventText,
  formatTime,
  PHASE_LABELS,
  PHASE_TONES,
  SOURCE_LABELS,
  TRIAL_STATUS_LABELS,
} from '../labels'
import type {
  ChallengeDetail,
  ChallengeSummary,
  Checkpoint,
  RunDetail,
  RunEvent,
  RunSummary,
} from '../types'
import { useRunEventStream } from '../useRunEventStream'

type Tab = 'events' | 'trials' | 'checkpoints' | 'submission'

const TABS: { key: Tab; label: string }[] = [
  { key: 'events', label: '事件流' },
  { key: 'trials', label: 'Trials' },
  { key: 'checkpoints', label: '检查点' },
  { key: 'submission', label: '提交与评分' },
]

const SOURCE_AVATAR: Record<string, string> = {
  brain: 'B',
  prime: 'P',
  user: 'U',
  controller: 'CS',
  demo: 'D',
}

export default function ResearchPage() {
  const { toast, setCurrentChallengeId, demoMode, setPage } = useApp()

  const [challenges, setChallenges] = useState<ChallengeSummary[]>([])
  const [challengeId, setChallengeId] = useState<string | null>(null)
  const [challenge, setChallenge] = useState<ChallengeDetail | null>(null)
  const [runs, setRuns] = useState<RunSummary[]>([])

  const [events, setEvents] = useState<RunEvent[]>([])
  const [tab, setTab] = useState<Tab>('events')
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([])
  const [importOpen, setImportOpen] = useState(false)
  const [startOpen, setStartOpen] = useState(false)
  const [terminateOpen, setTerminateOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [steerText, setSteerText] = useState('')
  const [steerState, setSteerState] = useState<{ opId: string; state: 'queued' | 'consumed' } | null>(null)

  const eventsRef = useRef<HTMLDivElement>(null)
  const atBottomRef = useRef(true)
  const [showJump, setShowJump] = useState(false)

  const refreshChallenges = useCallback(async () => {
    try {
      const data = await api.get<{ items: ChallengeSummary[] }>('/api/v1/challenges')
      setChallenges(data.items)
    } catch (err) {
      if (!(err instanceof ApiError && err.code === 'PAIRING_REQUIRED')) {
        toast('加载题目列表失败：' + (err instanceof Error ? err.message : String(err)))
      }
    }
  }, [toast])

  const refreshRuns = useCallback(async () => {
    try {
      const data = await api.get<{ items: RunSummary[] }>('/api/v1/runs')
      setRuns(data.items)
    } catch (err) {
      if (!(err instanceof ApiError && err.code === 'PAIRING_REQUIRED')) {
        toast('加载 Run 列表失败：' + (err instanceof Error ? err.message : String(err)))
      }
    }
  }, [toast])

  useEffect(() => {
    void refreshChallenges()
    void refreshRuns()
  }, [refreshChallenges, refreshRuns])

  // 默认选中最近的题目
  useEffect(() => {
    if (!challengeId && challenges.length) {
      setChallengeId(challenges[0].id)
    }
  }, [challenges, challengeId])

  useEffect(() => {
    setCurrentChallengeId(challengeId)
    if (!challengeId) {
      setChallenge(null)
      return
    }
    api
      .get<ChallengeDetail>(`/api/v1/challenges/${challengeId}`)
      .then(setChallenge)
      .catch(() => setChallenge(null))
  }, [challengeId, setCurrentChallengeId])

  const currentRun: RunSummary | null = useMemo(() => {
    if (!challengeId) return null
    const forChallenge = runs
      .filter((r) => r.challenge_id === challengeId)
      .sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''))
    return forChallenge[0] ?? null
  }, [runs, challengeId])

  const active = currentRun ? ACTIVE_PHASES.includes(currentRun.phase) : false

  const [runDetail, setRunDetail] = useState<RunDetail | null>(null)

  useEffect(() => {
    setRunDetail(null)
    setEvents([])
    setSteerState(null)
  }, [currentRun?.id])

  const refreshRunDetail = useCallback(async () => {
    if (!currentRun) return
    try {
      const detail = await api.get<RunDetail>(`/api/v1/runs/${currentRun.id}`)
      setRunDetail(detail)
    } catch {
      // 轮询失败不打扰用户；事件流断线提示会覆盖连接问题
    }
  }, [currentRun])

  useEffect(() => {
    if (!currentRun) return
    void refreshRunDetail()
    const phase = runDetail?.phase ?? currentRun.phase
    if (ACTIVE_PHASES.includes(phase)) {
      const timer = window.setInterval(() => void refreshRunDetail(), 3000)
      return () => window.clearInterval(timer)
    }
  }, [currentRun, refreshRunDetail, runDetail?.phase])

  const refreshCheckpoints = useCallback(async () => {
    if (!currentRun) return
    try {
      const data = await api.get<{ items?: Checkpoint[] } | Checkpoint[]>(
        `/api/v1/runs/${currentRun.id}/checkpoints`,
      )
      setCheckpoints(Array.isArray(data) ? data : (data.items ?? []))
    } catch {
      setCheckpoints([])
    }
  }, [currentRun])

  useEffect(() => {
    if (tab === 'checkpoints') void refreshCheckpoints()
  }, [tab, refreshCheckpoints])

  const steerStateRef = useRef<{ opId: string; state: 'queued' | 'consumed' } | null>(null)
  useEffect(() => {
    steerStateRef.current = steerState
  }, [steerState])

  const handleEvent = useCallback(
    (event: RunEvent) => {
      setEvents((list) => [...list, event])
      if (event.type === 'prime.steer.consumed' && steerStateRef.current) {
        const op = event.payload?.operation_id
        if (!op || op === steerStateRef.current.opId) {
          setSteerState({ opId: steerStateRef.current.opId, state: 'consumed' })
        }
      }
      if (event.type.startsWith('run.')) {
        void refreshRunDetail()
        void refreshRuns()
      }
      if (event.type === 'prime.checkpoint.created' || event.type === 'checkpoint.created') {
        void refreshCheckpoints()
      }
    },
    [refreshRunDetail, refreshRuns, refreshCheckpoints],
  )

  useRunEventStream(active ? (currentRun?.id ?? null) : null, handleEvent)

  // 自动滚动：用户停留在底部时跟随新事件；上翻阅读时不强制滚动。
  useEffect(() => {
    const el = eventsRef.current
    if (el && atBottomRef.current) {
      el.scrollTop = el.scrollHeight
    }
    const el2 = eventsRef.current
    if (el2) setShowJump(!atBottomRef.current && el2.scrollHeight > el2.clientHeight)
  }, [events])

  function onEventsScroll() {
    const el = eventsRef.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40
    atBottomRef.current = nearBottom
    setShowJump(!nearBottom && el.scrollHeight > el.clientHeight)
  }

  function jumpToLatest() {
    const el = eventsRef.current
    if (el) {
      el.scrollTop = el.scrollHeight
      atBottomRef.current = true
      setShowJump(false)
    }
  }

  async function sendSteer() {
    const text = steerText.trim()
    if (!text || !currentRun) return
    const opId = crypto.randomUUID()
    setBusy(true)
    try {
      await api.post(`/api/v1/runs/${currentRun.id}/control`, {
        action: 'steer',
        text,
        operation_id: opId,
      })
      setSteerText('')
      setSteerState({ opId, state: 'queued' })
      toast('指导已排队。')
    } catch (err) {
      toast('发送指导失败：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setBusy(false)
    }
  }

  async function pauseRun() {
    if (!currentRun) return
    try {
      await api.post(`/api/v1/runs/${currentRun.id}/control`, {
        action: 'pause',
        operation_id: crypto.randomUUID(),
      })
      toast('正在暂停；已有远程任务可能继续运行/计费。')
      void refreshRunDetail()
    } catch (err) {
      toast('暂停失败：' + (err instanceof Error ? err.message : String(err)))
    }
  }

  async function resumeRun() {
    if (!currentRun) return
    try {
      await api.post(`/api/v1/runs/${currentRun.id}/control`, {
        action: 'resume',
        operation_id: crypto.randomUUID(),
      })
      toast('已请求恢复研究。')
      void refreshRunDetail()
    } catch (err) {
      toast('恢复失败：' + (err instanceof Error ? err.message : String(err)))
    }
  }

  async function terminateRun() {
    if (!currentRun) return
    setBusy(true)
    try {
      await api.post(`/api/v1/runs/${currentRun.id}/control`, {
        action: 'terminate',
        operation_id: crypto.randomUUID(),
      })
      setTerminateOpen(false)
      toast('已请求终止；证据与检查点保留。')
      void refreshRunDetail()
      void refreshRuns()
    } catch (err) {
      toast('终止失败：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setBusy(false)
    }
  }

  const phase = runDetail?.phase ?? currentRun?.phase ?? null
  const paused = phase === 'paused'
  const pausing = phase === 'pausing'

  return (
    <section aria-label="研究工作台">
      <div className="page-head">
        <div>
          <div className="eyebrow">RESEARCH / OVERVIEW</div>
          <h1>研究工作台</h1>
          <p className="sub">看清当前证据，决定下一次实验。</p>
        </div>
        <div className="actions">
          <button type="button" className="btn" onClick={() => setImportOpen(true)}>
            导入题目
          </button>
          {challengeId && (
            <button type="button" className="btn primary" onClick={() => setStartOpen(true)}>
              {active && paused ? '恢复研究' : active ? '查看研究' : '开始研究'}
            </button>
          )}
        </div>
      </div>

      {challenge ? (
        <div className="challenge-bar">
          <div>
            <div className="challenge-label">
              {challenge.is_demo ? 'DEMO_CHALLENGE · 非真实竞赛题' : (challenge.platform_challenge_id ?? '本地题目')}
            </div>
            <div className="challenge-title">{challenge.title}</div>
          </div>
          <div className="actions">
            <Badge tone={challenge.contract_status === 'verified' ? 'green' : 'neutral'}>
              {CONTRACT_LABELS[challenge.contract_status] ?? challenge.contract_status ?? '契约未验证'}
            </Badge>
            {phase && (
              <Badge tone={PHASE_TONES[phase as keyof typeof PHASE_TONES] ?? 'neutral'}>
                {PHASE_LABELS[phase as keyof typeof PHASE_LABELS] ?? phase}
                {pausing && '；已有远程任务可能继续运行/计费'}
              </Badge>
            )}
          </div>
        </div>
      ) : (
        <div className="empty">
          <strong>还没有题目</strong>
          <p>导入一个演示题目，或手动粘贴题面开始研究。</p>
          <div className="actions" style={{ marginTop: 12 }}>
            <button type="button" className="btn primary" onClick={() => setImportOpen(true)}>
              导入题目
            </button>
          </div>
        </div>
      )}

      {challenges.length > 1 && (
        <div className="challenge-picker">
          <label htmlFor="challenge-picker">切换题目</label>
          <select
            id="challenge-picker"
            value={challengeId ?? ''}
            onChange={(e) => setChallengeId(e.target.value)}
          >
            {challenges.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
                {c.is_demo ? '（演示）' : ''}
              </option>
            ))}
          </select>
        </div>
      )}

      {phase === 'blocked' && runDetail?.block_reason && (
        <div className="callout danger" role="alert">
          <strong>研究被阻塞：</strong>
          {runDetail.block_reason}
          <button type="button" className="btn small" onClick={() => setPage('settings')}>
            去连接设置
          </button>
        </div>
      )}

      <div className="work-grid">
        <div className="stack">
          <article className="card">
            <div className="card-head">
              <h2>当前研究意图</h2>
              <Badge tone="green">大脑的判断窗口</Badge>
            </div>
            <div className="card-body">
              <div className="intent">
                <p>{runDetail?.intention ?? '尚未开始研究。开始后会显示大脑当前的研究意图。'}</p>
              </div>
            </div>
          </article>

          <article className="card">
            <div className="card-head">
              <h2>研究活动</h2>
              <div className="actions">
                {phase === 'running' && (
                  <button type="button" className="btn" onClick={() => void pauseRun()}>
                    暂停研究
                  </button>
                )}
                {paused && (
                  <button type="button" className="btn" onClick={() => void resumeRun()}>
                    恢复研究
                  </button>
                )}
                {active && !paused && !pausing && (
                  <button type="button" className="btn danger" onClick={() => setTerminateOpen(true)}>
                    终止研究
                  </button>
                )}
              </div>
            </div>
            <div className="tabs" role="tablist" aria-label="研究活动标签">
              {TABS.map((t) => (
                <button
                  key={t.key}
                  role="tab"
                  aria-selected={tab === t.key}
                  className={tab === t.key ? 'tab active' : 'tab'}
                  onClick={() => setTab(t.key)}
                >
                  {t.label}
                </button>
              ))}
            </div>
            <div className="card-body">
              {tab === 'events' && (
                <div className="events-wrap">
                  <div
                    className="events"
                    ref={eventsRef}
                    onScroll={onEventsScroll}
                    aria-label="研究事件流"
                  >
                    {events.length === 0 ? (
                      <div className="empty">
                        <strong>还没有研究事件</strong>
                        <p>开始研究后，大脑、执行器与控制器的交接会显示在这里。</p>
                      </div>
                    ) : (
                      events.map((e) => (
                        <div className="event" key={e.event_id ?? e.seq}>
                          <div
                            className={`avatar src-${e.source}`}
                            aria-hidden="true"
                          >
                            {SOURCE_AVATAR[e.source] ?? '?'}
                          </div>
                          <div className="event-body">
                            <div className="event-top">
                              <span className="event-role">
                                {SOURCE_LABELS[e.source] ?? e.source} · {eventLabel(e.type)}
                              </span>
                              <time>{formatTime(e.occurred_at)}</time>
                            </div>
                            {eventText(e) && <p>{eventText(e)}</p>}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                  {showJump && (
                    <button type="button" className="btn small jump-latest" onClick={jumpToLatest}>
                      回到最新
                    </button>
                  )}
                </div>
              )}

              {tab === 'trials' && (
                <div>
                  {runDetail?.trials?.length ? (
                    <ul className="plain-list">
                      {runDetail.trials.map((t) => (
                        <li key={t.id} className="row-item">
                          <div>
                            <strong>{t.goal || t.id}</strong>
                            <div className="small-text">
                              创建 {formatTime(t.created_at)}
                              {runDetail.current_trial_id === t.id && ' · 当前 Trial'}
                            </div>
                          </div>
                          <Badge
                            tone={
                              t.status === 'done' || t.status === 'completed'
                                ? 'green'
                                : t.status === 'failed'
                                  ? 'danger'
                                  : 'blue'
                            }
                          >
                            {TRIAL_STATUS_LABELS[t.status] ?? t.status}
                          </Badge>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="empty">
                      <strong>还没有 Trial</strong>
                      <p>执行器接受任务后会创建 Trial。</p>
                    </div>
                  )}
                </div>
              )}

              {tab === 'checkpoints' && (
                <div>
                  <CheckpointForm
                    runId={currentRun?.id ?? null}
                    trials={runDetail?.trials ?? []}
                    onCreated={() => void refreshCheckpoints()}
                  />
                  {checkpoints.length > 0 && (
                    <ul className="plain-list">
                      {checkpoints.map((c, i) => (
                        <li key={c.id ?? i} className="row-item block">
                          <div className="small-text">记录于 {formatTime(c.created_at)}</div>
                          <p className="pre-wrap">{c.report}</p>
                          {c.evidence_refs?.length > 0 && (
                            <div className="small-text">证据引用：{c.evidence_refs.join('、')}</div>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {tab === 'submission' && (
                <div className="empty">
                  <strong>提交与评分：阶段 2 接入，当前不可用</strong>
                  <p>正式提交前会分别核对提交包清单与 hash、远程 Attempt 与上传、官方反馈与参赛资格。</p>
                </div>
              )}
            </div>
          </article>
        </div>

        <div className="stack right">
          <article className="card">
            <div className="card-head">
              <h2>运行摘要</h2>
              {currentRun && <Badge tone="neutral">模式 {currentRun.mode}</Badge>}
            </div>
            <div className="card-body">
              <div className="meta-row">
                <span>Run</span>
                <span>{currentRun ? currentRun.id.slice(0, 8) + '…' : '尚未创建'}</span>
              </div>
              <div className="meta-row">
                <span>大脑状态</span>
                <span>{lastSourceEvent(events, 'brain')}</span>
              </div>
              <div className="meta-row">
                <span>Prime 状态</span>
                <span>{lastSourceEvent(events, 'prime')}</span>
              </div>
              <div className="meta-row">
                <span>预算 · 大脑判断</span>
                <span>
                  {runDetail?.budget
                    ? `${runDetail.budget.brain_reviews_used} / ${runDetail.budget.max_brain_reviews}`
                    : '—'}
                </span>
              </div>
              <div className="meta-row">
                <span>预算 · 模型调用上限</span>
                <span>{runDetail?.budget ? String(runDetail.budget.model_turns.limit) : '—'}</span>
              </div>
              <div className="meta-row">
                <span>费用 · 已知部分</span>
                <span>
                  {runDetail?.budget
                    ? runDetail.budget.model_turns.known_cost === null
                      ? '未知'
                      : String(runDetail.budget.model_turns.known_cost)
                    : '—'}
                </span>
              </div>
              <div className="meta-row">
                <span>费用 · 未知部分</span>
                <span>
                  {runDetail?.budget
                    ? runDetail.budget.model_turns.unknown_cost
                      ? '未知（存在未计费的模型调用）'
                      : '无'
                    : '—'}
                </span>
              </div>
              <div className="meta-row">
                <span>提交上限</span>
                <span>{runDetail?.budget ? runDetail.budget.max_submissions : '—'}</span>
              </div>
              {currentRun && (
                <details className="snapshot">
                  <summary>本轮配置快照</summary>
                  <pre>{JSON.stringify(runDetail?.config_snapshot ?? null, null, 2)}</pre>
                </details>
              )}
              <button type="button" className="btn" style={{ width: '100%', marginTop: 13 }} onClick={() => setPage('settings')}>
                查看连接与授权
              </button>
            </div>
          </article>

          <article className="card">
            <div className="card-head">
              <h2>人工指导</h2>
              <Badge tone="blue">保留执行自主权</Badge>
            </div>
            <div className="card-body">
              <p className="sub">告诉大脑或 Prime 需要区分什么、保留什么。</p>
              <label htmlFor="steer-text">指导内容</label>
              <textarea
                id="steer-text"
                className="editor"
                rows={3}
                value={steerText}
                onChange={(e) => setSteerText(e.target.value)}
                placeholder="例如：先区分环境错误和算法局限，再决定是否重跑。"
                disabled={!active || paused || pausing}
              />
              {steerState && (
                <p className="small-text" role="status">
                  {steerState.state === 'queued'
                    ? '已排队，尚未生效。'
                    : '指导已被执行器接收并生效。'}
                </p>
              )}
              <button
                type="button"
                className="btn primary"
                style={{ width: '100%', marginTop: 10 }}
                disabled={!active || paused || pausing || !steerText.trim() || busy}
                onClick={() => void sendSteer()}
              >
                发送指导
              </button>
              <div className="callout" style={{ marginTop: 12 }}>
                暂停研究不等于取消远程 Job，已有远程任务可能继续运行或计费。
              </div>
            </div>
          </article>
        </div>
      </div>

      <ImportDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        demoMode={demoMode}
        onImported={(id) => {
          setImportOpen(false)
          void refreshChallenges().then(() => setChallengeId(id))
        }}
      />

      <StartDialog
        open={startOpen}
        onClose={() => setStartOpen(false)}
        challengeId={challengeId}
        challengeTitle={challenge?.title ?? ''}
        activePhase={active ? phase : null}
        demoMode={demoMode}
        onStarted={() => {
          setStartOpen(false)
          void refreshRuns()
          if (currentRun) void refreshRunDetail()
        }}
        onResume={() => {
          setStartOpen(false)
          void resumeRun()
        }}
      />

      <Modal open={terminateOpen} onClose={() => setTerminateOpen(false)} title="终止研究">
        <p>
          终止后本 Run 不再继续，已产生的证据、检查点和事件记录都会保留。
          已运行的远程任务是否取消由后端按当前授权处理。
        </p>
        <div className="modal-actions">
          <button type="button" className="btn" onClick={() => setTerminateOpen(false)}>
            取消
          </button>
          <button type="button" className="btn danger" disabled={busy} onClick={() => void terminateRun()}>
            确认终止
          </button>
        </div>
      </Modal>
    </section>
  )
}

function lastSourceEvent(events: RunEvent[], source: string): string {
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].source === source) return eventLabel(events[i].type)
  }
  return '尚无事件'
}

function ImportDialog({
  open,
  onClose,
  demoMode,
  onImported,
}: {
  open: boolean
  onClose: () => void
  demoMode: boolean
  onImported: (challengeId: string) => void
}) {
  const { toast } = useApp()
  const [mode, setMode] = useState<'demo' | 'manual' | 'url'>('demo')
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit() {
    setBusy(true)
    try {
      const body: Record<string, string> = { mode }
      if (mode === 'manual') {
        if (!title.trim() || !content.trim()) {
          toast('手动导入需要标题和题面。')
          return
        }
        body.title = title.trim()
        body.content = content
      }
      if (mode === 'url') {
        if (!url.trim()) {
          toast('请填写题目 URL。')
          return
        }
        body.url = url.trim()
        if (title.trim()) body.title = title.trim()
      }
      const res = await api.post<{ challenge: { id: string } }>('/api/v1/challenges/import', body)
      toast('题目已导入。')
      onImported(res.challenge.id)
    } catch (err) {
      toast('导入失败：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="导入题目">
      <div className="filter" role="group" aria-label="导入方式">
        <button type="button" className={mode === 'demo' ? 'active' : ''} onClick={() => setMode('demo')}>
          导入演示题目
        </button>
        <button type="button" className={mode === 'manual' ? 'active' : ''} onClick={() => setMode('manual')}>
          手动导入（标题+题面）
        </button>
        <button type="button" className={mode === 'url' ? 'active' : ''} onClick={() => setMode('url')}>
          从 URL 导入
        </button>
      </div>
      {mode === 'demo' && (
        <p className="sub">使用后端内置的虚构演示题目（DEMO_* ID），不访问真实平台。</p>
      )}
      {mode !== 'demo' && (
        <div className="field">
          <label htmlFor="import-title">标题</label>
          <input id="import-title" value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
      )}
      {mode === 'manual' && (
        <div className="field">
          <label htmlFor="import-content">题面（Markdown）</label>
          <textarea
            id="import-content"
            className="editor"
            rows={6}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            spellCheck={false}
          />
        </div>
      )}
      {mode === 'url' && (
        <div className="field">
          <label htmlFor="import-url">题目 URL</label>
          <input
            id="import-url"
            inputMode="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://…"
          />
          <p className="inline-note">后端会验证来源并解析题目与提交契约。</p>
        </div>
      )}
      {demoMode && (
        <p className="inline-note">当前为演示模式，建议优先使用演示题目。</p>
      )}
      <div className="modal-actions">
        <button type="button" className="btn" onClick={onClose}>
          取消
        </button>
        <button type="button" className="btn primary" disabled={busy} onClick={() => void submit()}>
          {busy ? '导入中…' : '导入'}
        </button>
      </div>
    </Modal>
  )
}

function StartDialog({
  open,
  onClose,
  challengeId,
  challengeTitle,
  activePhase,
  demoMode,
  onStarted,
  onResume,
}: {
  open: boolean
  onClose: () => void
  challengeId: string | null
  challengeTitle: string
  activePhase: string | null
  demoMode: boolean
  onStarted: () => void
  onResume: () => void
}) {
  const { toast } = useApp()
  const [allowModelCalls, setAllowModelCalls] = useState(false)
  const [maxModelTurns, setMaxModelTurns] = useState(0)
  const [maxRunMinutes, setMaxRunMinutes] = useState(30)
  const [maxSubmissions, setMaxSubmissions] = useState(0)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (open) {
      setAllowModelCalls(false)
      setNote('')
      api
        .get<{ run_defaults: { max_model_turns: number; max_run_minutes: number; max_submissions: number } }>(
          '/api/v1/settings',
        )
        .then((s) => {
          setMaxModelTurns(s.run_defaults.max_model_turns)
          setMaxRunMinutes(s.run_defaults.max_run_minutes)
          setMaxSubmissions(s.run_defaults.max_submissions)
        })
        .catch(() => undefined)
    }
  }, [open])

  async function start() {
    if (!challengeId) return
    setBusy(true)
    try {
      const run = await api.post<{ id: string }>('/api/v1/runs', { challenge_id: challengeId })
      await api.post(`/api/v1/runs/${run.id}/authorize`, {
        scope: 'demo',
        allow_model_calls: allowModelCalls,
        max_model_turns: maxModelTurns,
        max_run_minutes: maxRunMinutes,
        max_submissions: maxSubmissions,
        note: note.trim() || undefined,
      })
      await api.post(`/api/v1/runs/${run.id}/start`)
      toast('研究已开始。')
      onStarted()
    } catch (err) {
      toast('开始研究失败：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setBusy(false)
    }
  }

  if (activePhase === 'paused') {
    return (
      <Modal open={open} onClose={onClose} title="恢复研究">
        <p>
          当前 Run 处于已暂停状态。恢复前会先核对已有进程、远程任务与快照，不会从头重跑。
        </p>
        <div className="modal-actions">
          <button type="button" className="btn" onClick={onClose}>
            取消
          </button>
          <button type="button" className="btn primary" onClick={onResume}>
            恢复研究
          </button>
        </div>
      </Modal>
    )
  }

  if (activePhase) {
    return (
      <Modal open={open} onClose={onClose} title="研究进行中">
        <p>当前题目已有进行中的 Run（{PHASE_LABELS[activePhase as keyof typeof PHASE_LABELS] ?? activePhase}）。</p>
        <div className="modal-actions">
          <button type="button" className="btn primary" onClick={onClose}>
            知道了
          </button>
        </div>
      </Modal>
    )
  }

  return (
    <Modal open={open} onClose={onClose} title="开始研究 · 预检与授权">
      <p className="sub">题目：{challengeTitle || '—'}</p>
      <p>开始研究前，请确认本轮授权范围。授权只对本 Run 生效。</p>
      <div className="field checkbox">
        <input
          id="auth-model-calls"
          type="checkbox"
          checked={allowModelCalls}
          onChange={(e) => setAllowModelCalls(e.target.checked)}
        />
        <label htmlFor="auth-model-calls">允许模型调用（会消耗模型额度）</label>
      </div>
      <div className="fields triple">
        <div className="field">
          <label htmlFor="auth-turns">模型调用上限</label>
          <input
            id="auth-turns"
            type="number"
            min={0}
            value={maxModelTurns}
            onChange={(e) => setMaxModelTurns(Number(e.target.value))}
          />
        </div>
        <div className="field">
          <label htmlFor="auth-minutes">运行时长上限（分钟）</label>
          <input
            id="auth-minutes"
            type="number"
            min={1}
            value={maxRunMinutes}
            onChange={(e) => setMaxRunMinutes(Number(e.target.value))}
          />
        </div>
        <div className="field">
          <label htmlFor="auth-submissions">提交次数上限</label>
          <input
            id="auth-submissions"
            type="number"
            min={0}
            value={maxSubmissions}
            onChange={(e) => setMaxSubmissions(Number(e.target.value))}
          />
        </div>
      </div>
      <div className="field">
        <label htmlFor="auth-note">备注（可选）</label>
        <input id="auth-note" value={note} onChange={(e) => setNote(e.target.value)} />
      </div>
      {demoMode && !allowModelCalls && (
        <p className="inline-note">演示模式默认不勾选模型调用；不授权模型调用时大脑只能做本地判断。</p>
      )}
      <div className="modal-actions">
        <button type="button" className="btn" onClick={onClose}>
          取消
        </button>
        <button type="button" className="btn primary" disabled={busy} onClick={() => void start()}>
          {busy ? '启动中…' : '确认并开始'}
        </button>
      </div>
    </Modal>
  )
}

function CheckpointForm({
  runId,
  trials,
  onCreated,
}: {
  runId: string | null
  trials: { id: string; goal: string }[]
  onCreated: () => void
}) {
  const { toast } = useApp()
  const [report, setReport] = useState('')
  const [evidence, setEvidence] = useState('')
  const [trialId, setTrialId] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit() {
    if (!runId) return
    if (!report.trim()) {
      toast('请填写检查点内容。')
      return
    }
    setBusy(true)
    try {
      await api.post(`/api/v1/runs/${runId}/checkpoints`, {
        trial_id: trialId || undefined,
        report: report.trim(),
        evidence_refs: evidence
          .split('\n')
          .map((s) => s.trim())
          .filter(Boolean),
      })
      setReport('')
      setEvidence('')
      toast('检查点已创建。')
      onCreated()
    } catch (err) {
      toast('创建检查点失败：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="checkpoint-form">
      <div className="field">
        <label htmlFor="cp-trial">关联 Trial（可选）</label>
        <select id="cp-trial" value={trialId} onChange={(e) => setTrialId(e.target.value)}>
          <option value="">不关联</option>
          {trials.map((t) => (
            <option key={t.id} value={t.id}>
              {t.goal || t.id}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="cp-report">检查点内容</label>
        <textarea
          id="cp-report"
          className="editor"
          rows={3}
          value={report}
          onChange={(e) => setReport(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="cp-evidence">证据引用（每行一个）</label>
        <textarea
          id="cp-evidence"
          className="editor"
          rows={2}
          value={evidence}
          onChange={(e) => setEvidence(e.target.value)}
          spellCheck={false}
        />
      </div>
      <button type="button" className="btn" disabled={!runId || busy} onClick={() => void submit()}>
        创建检查点
      </button>
    </div>
  )
}
