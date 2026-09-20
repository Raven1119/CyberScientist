import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, api, bindChallengeSkill, listSkills, unbindChallengeSkill, updateRunBudget } from '../api'
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
  SCORE_STATUS_LABELS,
  SOURCE_LABELS,
  TERMINAL_PHASES,
  TRIAL_STATUS_LABELS,
} from '../labels'
import type {
  ChallengeDetail,
  ChallengeSummary,
  Checkpoint,
  RunBudget,
  RunDetail,
  RunEvent,
  RunSummary,
  ReviewRequestResult,
  SkillCatalogResponse,
  Submission,
  SupervisionGuidance,
  SupervisionStatus,
} from '../types'
import { useRunEventStream, type StreamStatus } from '../useRunEventStream'

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
  executor: 'P',
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
  const [budgetOpen, setBudgetOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [steerText, setSteerText] = useState('')
  const [steerState, setSteerState] = useState<{
    opId: string
    sentAt: number
    state: 'queued' | 'consumed'
  } | null>(null)
  const [supervision, setSupervision] = useState<SupervisionStatus | null>(null)
  const [subRefresh, setSubRefresh] = useState(0)
  const [streamStatus, setStreamStatus] = useState<StreamStatus>('idle')

  const eventsRef = useRef<HTMLDivElement>(null)
  const atBottomRef = useRef(true)
  const [showJump, setShowJump] = useState(false)

  const refreshChallenges = useCallback(async () => {
    try {
      const data = await api.get<{ items: ChallengeSummary[] }>('/api/v1/challenges')
      setChallenges(data.items)
    } catch (err) {
      toast('加载题目列表失败：' + (err instanceof Error ? err.message : String(err)))
    }
  }, [toast])

  const refreshRuns = useCallback(async () => {
    try {
      const data = await api.get<{ items: RunSummary[] }>('/api/v1/runs')
      setRuns(data.items)
    } catch (err) {
      toast('加载 Run 列表失败：' + (err instanceof Error ? err.message : String(err)))
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

  const phase = runDetail?.phase ?? currentRun?.phase ?? null
  const paused = phase === 'paused'
  const pausing = phase === 'pausing'
  const recovering = phase === 'recovering'
  const terminal = phase !== null && TERMINAL_PHASES.includes(phase)

  useEffect(() => {
    setRunDetail(null)
    setEvents([])
    setSteerState(null)
    setSupervision(null)
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

  const refreshSupervision = useCallback(async () => {
    if (!currentRun) return
    try {
      const data = await api.get<SupervisionStatus>(`/api/v1/runs/${currentRun.id}/supervision`)
      setSupervision(data)
    } catch {
      // 监督接口失败不打扰用户；下次轮询或事件会重试
    }
  }, [currentRun])

  // 挂载即拉取一次，另保留 10s 轮询兜底；SSE 事件另行触发即时刷新
  useEffect(() => {
    if (!currentRun) return
    void refreshSupervision()
    const timer = window.setInterval(() => void refreshSupervision(), 10000)
    return () => window.clearInterval(timer)
  }, [currentRun, refreshSupervision])

  useEffect(() => {
    if (tab === 'checkpoints') void refreshCheckpoints()
  }, [tab, refreshCheckpoints])

  const steerStateRef = useRef<{ opId: string; sentAt: number; state: 'queued' | 'consumed' } | null>(null)
  useEffect(() => {
    steerStateRef.current = steerState
  }, [steerState])

  const handleEvent = useCallback(
    (event: RunEvent) => {
      setEvents((list) => [...list, event])
      const pendingSteer = steerStateRef.current
      if (pendingSteer && pendingSteer.state === 'queued') {
        // 后端不把前端的 operation_id 带回事件（guidance.sent 里是执行器回执 id），
        // 改为时间序匹配：只认发送之后到达的消费信号，避免历史回放误判
        const at = Date.parse(event.occurred_at)
        const afterSend = Number.isNaN(at) || at >= pendingSteer.sentAt - 1000
        const consumed =
          event.type === 'prime.steer.consumed' ||
          event.type === 'guidance.sent' ||
          event.type === 'guidance.acknowledged' ||
          (event.type === 'guidance.queued' && event.payload?.kind === 'steer')
        if (consumed && afterSend) {
          setSteerState({ ...pendingSteer, state: 'consumed' })
        }
      }
      if (event.type.startsWith('run.')) {
        void refreshRunDetail()
        void refreshRuns()
      }
      if (event.type === 'prime.checkpoint.created' || event.type === 'checkpoint.created') {
        void refreshCheckpoints()
      }
      if (event.type.startsWith('submission.')) {
        setSubRefresh((n) => n + 1)
      }
      if (
        event.type === 'brain.review_done' ||
        event.type === 'review.requested' ||
        event.type.startsWith('guidance.') ||
        event.type.startsWith('shadow.') ||
        event.type.startsWith('run.')
      ) {
        void refreshSupervision()
      }
    },
    [refreshRunDetail, refreshRuns, refreshCheckpoints, refreshSupervision],
  )

  // 只要选中了 Run 就订阅事件流：进行中的 Run 持续推送，
  // 已结束的 Run 由服务端一次性回放历史事件后归档（closed），不再重连。
  useRunEventStream(currentRun?.id ?? null, handleEvent, {
    onStatus: setStreamStatus,
    terminal,
  })

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
    const sentAt = Date.now()
    setBusy(true)
    try {
      await api.post(`/api/v1/runs/${currentRun.id}/control`, {
        action: 'steer',
        text,
        operation_id: opId,
      })
      setSteerText('')
      setSteerState({ opId, sentAt, state: 'queued' })
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

      {challengeId && <ChallengeSkills key={challengeId} challengeId={challengeId} />}

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
                {streamStatus === 'open' && <Badge tone="green">事件流已连接</Badge>}
                {(streamStatus === 'connecting' || streamStatus === 'reconnecting') && (
                  <Badge tone="amber">事件流已断开，正在重连…</Badge>
                )}
                {streamStatus === 'closed' && <Badge tone="neutral">事件流已归档</Badge>}
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
                {recovering && (
                  <button type="button" className="btn" onClick={() => void resumeRun()}>
                    恢复研究（后端重启后）
                  </button>
                )}
                {(active || recovering) && !paused && (
                  <button type="button" className="btn danger" onClick={() => setTerminateOpen(true)}>
                    {pausing ? '终止研究（不等暂停确认）' : '终止研究'}
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
                      events.map((e) => <EventItem key={e.event_id ?? e.seq} event={e} />)
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

              {tab === 'submission' && challengeId && (
                <SubmissionsPanel
                  challengeId={challengeId}
                  runId={currentRun?.id ?? null}
                  refreshKey={subRefresh}
                />
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
                <span>{terminal && phase ? PHASE_LABELS[phase] : lastSourceEvent(events, 'brain')}</span>
              </div>
              <div className="meta-row">
                <span>执行器状态</span>
                <span>
                  {terminal && phase ? PHASE_LABELS[phase] : lastSourceEvent(events, 'prime', 'executor')}
                </span>
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
              <div className="meta-row">
                <span>算力上限</span>
                <span>{runDetail?.budget ? runDetail.budget.max_jobs : '—'}</span>
              </div>
              {currentRun && runDetail?.budget && (
                <button
                  type="button"
                  className="btn small"
                  style={{ width: '100%', marginTop: 8 }}
                  onClick={() => setBudgetOpen(true)}
                >
                  调整预算（运行中生效）
                </button>
              )}
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

          {currentRun && (
            <SupervisionPanel
              runId={currentRun.id}
              supervision={supervision}
              runEnded={terminal}
              onChanged={(s) => setSupervision(s)}
              onRefresh={() => void refreshSupervision()}
            />
          )}

          <article className="card">
            <div className="card-head">
              <h2>人工指导</h2>
              <Badge tone="blue">保留执行自主权</Badge>
            </div>
            <div className="card-body">
              <p className="sub">告诉大脑或执行器需要区分什么、保留什么。</p>
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
              {steerState && !terminal && (
                <p className="small-text" role="status">
                  {steerState.state === 'queued'
                    ? '已排队，等待大脑审阅后投递。'
                    : '指导已被 Run 消费（转为正式指导或已投递执行器）。'}
                </p>
              )}
              {terminal && (
                <p className="small-text" role="status">
                  Run 已结束{phase ? `（${PHASE_LABELS[phase]}）` : ''}，不能再发送指导。
                </p>
              )}
              <button
                type="button"
                className="btn primary"
                style={{ width: '100%', marginTop: 10 }}
                disabled={!active || paused || pausing || !steerText.trim() || busy}
                title={terminal ? 'Run 已结束，不能发送指导' : undefined}
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

      {currentRun && runDetail?.budget && (
        <BudgetDialog
          open={budgetOpen}
          onClose={() => setBudgetOpen(false)}
          runId={currentRun.id}
          budget={runDetail.budget}
          onSaved={() => {
            setBudgetOpen(false)
            void refreshRunDetail()
          }}
        />
      )}
    </section>
  )
}

function BudgetDialog({
  open,
  onClose,
  runId,
  budget,
  onSaved,
}: {
  open: boolean
  onClose: () => void
  runId: string
  budget: RunBudget
  onSaved: () => void
}) {
  const { toast } = useApp()
  const [form, setForm] = useState({
    max_brain_reviews: 0,
    max_trials: 0,
    max_model_turns: 0,
    max_run_minutes: 0,
    max_submissions: 0,
    max_jobs: 0,
  })
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (open) {
      setForm({
        max_brain_reviews: budget.max_brain_reviews,
        max_trials: budget.max_trials,
        max_model_turns: budget.model_turns.limit,
        max_run_minutes: budget.run_minutes_limit,
        max_submissions: budget.max_submissions,
        max_jobs: budget.max_jobs,
      })
    }
  }, [open, budget])

  // 语义核对：max_model_turns/max_submissions 为 0 表示不再授权；max_run_minutes 为 0 表示不设限；
  // 大脑判断与 Trial 上限作用于全局设置，为 0 会锁死后续研究，故最小为 1。
  const FIELDS: { key: keyof typeof form; label: string; min: number }[] = [
    { key: 'max_brain_reviews', label: '大脑判断上限', min: 1 },
    { key: 'max_trials', label: 'Trial 上限', min: 1 },
    { key: 'max_model_turns', label: '模型调用上限（0 = 不再授权）', min: 0 },
    { key: 'max_run_minutes', label: '运行时长（分钟，0 = 不设限）', min: 0 },
    { key: 'max_submissions', label: '提交上限（0 = 不再授权）', min: 0 },
    { key: 'max_jobs', label: '算力上限（Bohrium Job 数）', min: 1 },
  ]

  async function save() {
    const current = {
      max_brain_reviews: budget.max_brain_reviews,
      max_trials: budget.max_trials,
      max_model_turns: budget.model_turns.limit,
      max_run_minutes: budget.run_minutes_limit,
      max_submissions: budget.max_submissions,
      max_jobs: budget.max_jobs,
    }
    const body: Record<string, number> = {}
    for (const { key } of FIELDS) {
      if (form[key] !== current[key]) body[key] = form[key]
    }
    if (Object.keys(body).length === 0) {
      onClose()
      return
    }
    setBusy(true)
    try {
      await updateRunBudget(runId, body)
      toast('预算已更新，立即生效。')
      onSaved()
    } catch (err) {
      toast('预算更新失败：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="调整预算">
      <p className="sub">
        保存后立即生效，无需重启或中断当前 Run。大脑判断与 Trial 上限作用于全局设置；模型调用、运行时长与提交上限作用于本 Run 的授权。
      </p>
      {FIELDS.map(({ key, label, min }) => (
        <div className="field" key={key}>
          <label htmlFor={`budget-${key}`}>{label}</label>
          <input
            id={`budget-${key}`}
            type="number"
            min={min}
            value={form[key]}
            onChange={(e) =>
              setForm((prev) => ({ ...prev, [key]: Number(e.target.value) }))
            }
          />
        </div>
      ))}
      <div className="modal-actions">
        <button type="button" className="btn" onClick={onClose}>
          取消
        </button>
        <button
          type="button"
          className="btn primary"
          disabled={busy}
          onClick={() => void save()}
        >
          {busy ? '保存中…' : '保存'}
        </button>
      </div>
    </Modal>
  )
}

function lastSourceEvent(events: RunEvent[], ...sources: string[]): string {
  for (let i = events.length - 1; i >= 0; i--) {
    if (sources.includes(events[i].source)) return eventLabel(events[i].type)
  }
  return '尚无事件'
}

function ChallengeSkills({ challengeId }: { challengeId: string }) {
  const { toast } = useApp()
  const [data, setData] = useState<SkillCatalogResponse | null>(null)
  const [manageOpen, setManageOpen] = useState(false)

  const reload = useCallback(async () => {
    try {
      setData(await listSkills(challengeId))
    } catch (err) {
      toast('加载技能失败：' + (err instanceof Error ? err.message : String(err)))
    }
  }, [challengeId, toast])

  useEffect(() => {
    void reload()
  }, [reload])

  async function remove(skillId: string) {
    try {
      await unbindChallengeSkill(challengeId, skillId)
      toast('已移除本题技能。')
      await reload()
    } catch (err) {
      toast('移除技能失败：' + (err instanceof Error ? err.message : String(err)))
    }
  }

  const boundSkills = data?.skills.filter((s) => s.bound) ?? []

  return (
    <div className="skill-bar">
      <span className="skill-bar-label">本题技能</span>
      {data === null ? (
        <span className="small-text">加载中…</span>
      ) : boundSkills.length === 0 ? (
        <span className="small-text">未绑定技能</span>
      ) : (
        <span className="skill-chips">
          {boundSkills.map((s) => (
            <span key={s.id} className="skill-chip" title={s.description || s.id}>
              {s.name}
              <button
                type="button"
                className="skill-chip-remove"
                aria-label={`移除技能 ${s.name}`}
                onClick={() => void remove(s.id)}
              >
                ×
              </button>
            </span>
          ))}
        </span>
      )}
      <button type="button" className="btn small" onClick={() => setManageOpen(true)}>
        管理技能
      </button>
      <SkillManageDialog
        open={manageOpen}
        onClose={() => setManageOpen(false)}
        challengeId={challengeId}
        data={data}
        onSaved={() => {
          setManageOpen(false)
          void reload()
        }}
      />
    </div>
  )
}

function SkillManageDialog({
  open,
  onClose,
  challengeId,
  data,
  onSaved,
}: {
  open: boolean
  onClose: () => void
  challengeId: string
  data: SkillCatalogResponse | null
  onSaved: () => void
}) {
  const { toast } = useApp()
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (open) setChecked(new Set(data?.bound ?? []))
  }, [open, data])

  function toggle(id: string) {
    setChecked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function save() {
    if (!data) return
    setBusy(true)
    try {
      const before = new Set(data.bound)
      for (const id of checked) {
        if (!before.has(id)) await bindChallengeSkill(challengeId, id)
      }
      for (const id of before) {
        if (!checked.has(id)) await unbindChallengeSkill(challengeId, id)
      }
      toast('本题技能已保存；下一个 Trial 启动时生效。')
      onSaved()
    } catch (err) {
      toast('保存技能失败：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="管理本题技能">
      {!data || data.skills.length === 0 ? (
        <p className="sub">
          未在技能目录发现技能（~/.kimi-code/skills、~/.agents/skills、~/.codex/skills 下含 SKILL.md 的子目录）。
        </p>
      ) : (
        <ul className="plain-list">
          {data.skills.map((s) => (
            <li key={s.id} className="row-item">
              <div>
                <strong>{s.name}</strong>
                {s.always_on && <Badge tone="blue">常驻</Badge>}
                {s.description && <div className="small-text">{s.description}</div>}
                <div className="small-text">{s.source}</div>
              </div>
              <div className="field checkbox">
                <input
                  id={`skill-bind-${s.id}`}
                  type="checkbox"
                  checked={checked.has(s.id)}
                  onChange={() => toggle(s.id)}
                />
                <label htmlFor={`skill-bind-${s.id}`}>本题启用</label>
              </div>
            </li>
          ))}
        </ul>
      )}
      <div className="modal-actions">
        <button type="button" className="btn" onClick={onClose}>
          取消
        </button>
        <button
          type="button"
          className="btn primary"
          disabled={busy || !data}
          onClick={() => void save()}
        >
          {busy ? '保存中…' : '保存'}
        </button>
      </div>
    </Modal>
  )
}

const SOURCE_BADGE_TONE: Record<string, 'purple' | 'blue' | 'neutral' | 'green' | 'neutral'> = {
  brain: 'purple',
  prime: 'blue',
  controller: 'neutral',
  user: 'green',
  demo: 'neutral',
}

const COLLAPSE_LIMIT = 300

function EventItem({ event }: { event: RunEvent }) {
  const [expanded, setExpanded] = useState(false)
  const rawText = eventText(event)
  const isStalled =
    event.type === 'prime.trial.stalled' ||
    event.type === 'controller.trial.stalled' ||
    event.type === 'trial.stalled'
  const isApproval = event.type === 'prime.approval.granted'
  const isRawOutput = event.type === 'brain.raw_output'
  const longText = !isRawOutput && rawText.length > COLLAPSE_LIMIT
  const shownText =
    isRawOutput && !expanded
      ? `（大脑原始输出，共 ${rawText.length} 字，已折叠）`
      : longText && !expanded
        ? rawText.slice(0, COLLAPSE_LIMIT) + '…'
        : rawText

  const rowClass = ['event']
  if (isApproval) rowClass.push('event-approval')
  if (isStalled) rowClass.push('event-stalled')

  return (
    <div className={rowClass.join(' ')}>
      <div className={`avatar src-${event.source}`} aria-hidden="true">
        {SOURCE_AVATAR[event.source] ?? '?'}
      </div>
      <div className="event-body">
        <div className="event-top">
          <span className="event-role">
            <Badge tone={SOURCE_BADGE_TONE[event.source] ?? 'neutral'}>
              {SOURCE_LABELS[event.source] ?? event.source}
            </Badge>
            <span className="event-type">{eventLabel(event.type)}</span>
          </span>
          <time>{formatTime(event.occurred_at)}</time>
        </div>
        {isApproval && <p className="event-approval-text">执行器工具已自动批准：{shownText}</p>}
        {isStalled && <p className="event-stalled-text">执行器挂起已处置：{shownText}</p>}
        {!isApproval && !isStalled && rawText && (
          <p className={isRawOutput ? 'event-raw' : undefined}>{shownText}</p>
        )}
        {(longText || isRawOutput) && (
          <button
            type="button"
            className="btn small link-btn"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
          >
            {expanded ? '收起' : isRawOutput ? '展开原始输出' : '展开'}
          </button>
        )}
      </div>
    </div>
  )
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
  const [shadowEnabled, setShadowEnabled] = useState(false)
  const [maxModelTurns, setMaxModelTurns] = useState(0)
  const [maxRunMinutes, setMaxRunMinutes] = useState(30)
  const [maxSubmissions, setMaxSubmissions] = useState(0)
  const [maxJobs, setMaxJobs] = useState(0)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (open) {
      setAllowModelCalls(false)
      setShadowEnabled(false)
      setNote('')
      api
        .get<{ run_defaults: { max_model_turns: number; max_run_minutes: number; max_submissions: number; max_jobs: number } }>(
          '/api/v1/settings',
        )
        .then((s) => {
          setMaxModelTurns(s.run_defaults.max_model_turns)
          setMaxRunMinutes(s.run_defaults.max_run_minutes)
          setMaxSubmissions(s.run_defaults.max_submissions)
          setMaxJobs(s.run_defaults.max_jobs)
        })
        .catch(() => undefined)
    }
  }, [open])

  async function start() {
    if (!challengeId) return
    setBusy(true)
    try {
      const run = await api.post<{ id: string }>('/api/v1/runs', {
        challenge_id: challengeId,
        shadow_enabled: shadowEnabled,
      })
      await api.post(`/api/v1/runs/${run.id}/authorize`, {
        scope: demoMode ? 'demo' : 'model_roundtrip',
        allow_model_calls: allowModelCalls,
        max_model_turns: maxModelTurns,
        max_run_minutes: maxRunMinutes,
        max_submissions: maxSubmissions,
        max_jobs: maxJobs,
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
      <div className="field checkbox">
        <input
          id="auth-shadow-enabled"
          type="checkbox"
          checked={shadowEnabled}
          onChange={(e) => setShadowEnabled(e.target.checked)}
        />
        <label htmlFor="auth-shadow-enabled">开启静默监督（大脑后台观察，有独立观察额度）</label>
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
        <div className="field">
          <label htmlFor="auth-jobs">算力上限（Bohrium Job 数）</label>
          <input
            id="auth-jobs"
            type="number"
            min={0}
            value={maxJobs}
            onChange={(e) => setMaxJobs(Number(e.target.value))}
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

function SubmissionsPanel({
  challengeId,
  runId,
  refreshKey,
}: {
  challengeId: string
  runId: string | null
  refreshKey: number
}) {
  const { toast } = useApp()
  const [items, setItems] = useState<Submission[] | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      // 按题聚合所有 Run 的提交；后端题级端点未就绪时回退到当前 Run 级端点
      const res = await api.get<{ items: Submission[] }>(
        `/api/v1/challenges/${encodeURIComponent(challengeId)}/submissions`,
      )
      setItems(res.items)
    } catch (err) {
      if (runId && err instanceof ApiError && err.status === 404) {
        try {
          const res = await api.get<{ items: Submission[] }>(`/api/v1/runs/${runId}/submissions`)
          setItems(res.items)
          return
        } catch (fallbackErr) {
          toast('加载提交记录失败：' + (fallbackErr instanceof Error ? fallbackErr.message : String(fallbackErr)))
          setItems([])
          return
        }
      }
      toast('加载提交记录失败：' + (err instanceof Error ? err.message : String(err)))
      setItems([])
    }
  }, [challengeId, runId, toast])

  useEffect(() => {
    void load()
  }, [load, refreshKey])

  async function poll() {
    setBusy(true)
    try {
      const res = await api.post<{ polled: number; updated: number; still_unknown: number }>(
        '/api/v1/submissions/poll', runId ? { run_id: runId } : {})
      toast(`评分轮询：检查 ${res.polled}，新出分 ${res.updated}，等待中 ${res.still_unknown}。`)
      await load()
    } catch (err) {
      toast('轮询失败：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setBusy(false)
    }
  }

  if (items === null) return <p className="small-text">加载中…</p>
  return (
    <div>
      <div className="actions" style={{ marginBottom: 10 }}>
        <button type="button" className="btn" disabled={busy} onClick={() => void poll()}>
          轮询评分
        </button>
        <span className="small-text">
          服务端每 45 秒自动轮询；评分器排队时保持「未知」，不编造分数。实验邮箱提交由大脑 submit 指导自动发起，收割提交在「邮箱与提交」页手动确认。
        </span>
      </div>
      {items.length === 0 ? (
        <div className="empty">
          <strong>本题还没有提交</strong>
          <p>这里聚合本题所有 Run 的提交记录；结果包就绪后大脑会发出 submit 指导自动提交，或在「邮箱与提交」页手动提交现成包。</p>
        </div>
      ) : (
        <ul className="plain-list">
          {items.map((s) => (
            <li key={s.id} className="row-item block">
              <div className="meta-row">
                <span>
                  {s.is_harvest ? '收割' : '实验'} · {s.mailbox_email ?? s.mailbox_id}
                  {s.platform_ref ? ` · 平台 #${s.platform_ref}` : ''}
                </span>
                <Badge
                  tone={
                    s.status === 'failed'
                      ? 'danger'
                      : s.score_status === 'scored'
                        ? 'green'
                        : 'amber'
                  }
                >
                  {s.status === 'failed'
                    ? '提交失败'
                    : s.score_status === 'scored'
                      ? `得分 ${s.score}`
                      : `分数${SCORE_STATUS_LABELS[s.score_status] ?? '未知'}`}
                </Badge>
              </div>
              <div className="small-text">
                {s.package_path} · 提交于 {formatTime(s.submitted_at ?? s.created_at)}
                {s.scored_at ? ` · 出分于 ${formatTime(s.scored_at)}` : ''}
              </div>
              {s.error && <p className="form-error">{s.error}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
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
  const [busy, setBusy] = useState(false)

  async function submit() {
    if (!runId) return
    if (!report.trim()) {
      toast('请填写检查点内容。')
      return
    }
    setBusy(true)
    try {
      // 后端按当前活跃 Trial 绑定身份，请求里的 trial_id 会被忽略，故不传
      await api.post(`/api/v1/runs/${runId}/checkpoints`, {
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
      <p className="small-text">
        检查点由后端自动关联当前活跃 Trial{trials.length > 0 ? `（当前 ${trials.length} 个）` : ''}。
      </p>
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

const GATE_LABELS: Record<string, string> = {
  open: '开放',
  yielding: '执行器交棒中',
  waiting_brain: '等待大脑',
  stopped: '已停止新工作',
}

const GATE_TONES: Record<string, 'green' | 'amber' | 'danger'> = {
  open: 'green',
  yielding: 'amber',
  waiting_brain: 'amber',
  stopped: 'danger',
}

const GUIDANCE_STATUS_LABELS: Record<string, string> = {
  queued: '排队中',
  sending: '发送中',
  sent: '已发送',
  acknowledged: '已确认',
  unknown: '未知',
  rejected: '被拒绝',
  superseded: '已被取代',
  invalidated: '已失效',
}

const GUIDANCE_STATUS_TONES: Record<string, 'green' | 'blue' | 'neutral' | 'danger'> = {
  queued: 'neutral',
  sending: 'blue',
  sent: 'blue',
  acknowledged: 'green',
  unknown: 'neutral',
  rejected: 'danger',
  superseded: 'neutral',
  invalidated: 'neutral',
}

const GUIDANCE_TEXT_LIMIT = 200

function GuidanceItem({ item }: { item: SupervisionGuidance }) {
  const [expanded, setExpanded] = useState(false)
  const stale = item.status === 'invalidated' || item.status === 'superseded'
  const text = item.text_md ?? ''
  const long = text.length > GUIDANCE_TEXT_LIMIT
  const shown = long && !expanded ? text.slice(0, GUIDANCE_TEXT_LIMIT) + '…' : text
  return (
    <li className="row-item block">
      <div className="actions" style={{ marginBottom: 4 }}>
        <Badge tone="purple">{item.kind}</Badge>
        <Badge tone="neutral">{item.intent}</Badge>
        <span className={stale ? 'struck' : undefined}>
          <Badge tone={GUIDANCE_STATUS_TONES[item.status] ?? 'neutral'}>
            {GUIDANCE_STATUS_LABELS[item.status] ?? item.status}
          </Badge>
        </span>
      </div>
      <p className={stale ? 'pre-wrap struck' : 'pre-wrap'}>{shown || '（无内容）'}</p>
      {long && (
        <button
          type="button"
          className="btn small link-btn"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
        >
          {expanded ? '收起' : '展开'}
        </button>
      )}
      <div className="small-text">
        {formatTime(item.created_at)}
        {item.target_trial_id ? ` · 目标 Trial ${item.target_trial_id.slice(0, 8)}…` : ''}
        {item.ack_disposition ? ` · 确认结论：${item.ack_disposition}` : ''}
      </div>
    </li>
  )
}

function SupervisionPanel({
  runId,
  supervision,
  runEnded,
  onChanged,
  onRefresh,
}: {
  runId: string
  supervision: SupervisionStatus | null
  runEnded: boolean
  onChanged: (s: SupervisionStatus) => void
  onRefresh: () => void
}) {
  const { toast } = useApp()
  const [busy, setBusy] = useState(false)

  const enabled = Boolean(supervision?.enabled)

  async function requestReview() {
    setBusy(true)
    try {
      const res = await api.post<ReviewRequestResult>(`/api/v1/runs/${runId}/review_requests`, {
        blocking: false,
      })
      toast(`已请求大脑审阅（${res.review_id}）。`)
      onRefresh()
    } catch (err) {
      toast('请求审阅失败：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setBusy(false)
    }
  }

  async function toggleSupervision() {
    if (enabled && !window.confirm('关闭只停止被动观察；已发布的指导仍可能有效。确定关闭静默监督吗？')) {
      return
    }
    setBusy(true)
    try {
      const res = await api.post<SupervisionStatus>(`/api/v1/runs/${runId}/supervision`, {
        enabled: !enabled,
      })
      onChanged(res)
      toast(!enabled ? '静默监督已开启。' : '静默监督已关闭；已发布的指导仍可能有效。')
    } catch (err) {
      toast('切换静默监督失败：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setBusy(false)
    }
  }

  let brainBadge: { tone: 'neutral' | 'amber' | 'purple' | 'green'; label: string }
  if (!enabled) {
    brainBadge = { tone: 'neutral', label: '未开启监督' }
  } else if (supervision?.degraded) {
    brainBadge = { tone: 'amber', label: `降级：${supervision.degrade_reason ?? '原因未知'}` }
  } else if (supervision?.brain_busy) {
    brainBadge = { tone: 'purple', label: '审阅中' }
  } else {
    brainBadge = { tone: 'green', label: '空闲' }
  }

  return (
    <article className="card">
      <div className="card-head">
        <h2>协作监督</h2>
        <Badge tone={enabled ? 'purple' : 'neutral'}>{enabled ? '静默监督开启' : '静默监督关闭'}</Badge>
      </div>
      <div className="card-body">
        <div className="actions" style={{ flexWrap: 'wrap', marginBottom: 10 }}>
          <Badge tone={brainBadge.tone}>大脑 · {brainBadge.label}</Badge>
          <Badge tone={supervision?.executor_busy ? 'blue' : 'neutral'}>
            执行器 · {supervision?.executor_busy ? '执行中' : '空闲'}
          </Badge>
          <Badge tone={GATE_TONES[supervision?.gate ?? ''] ?? 'neutral'}>
            门禁 · {GATE_LABELS[supervision?.gate ?? ''] ?? (supervision?.gate ?? '—')}
          </Badge>
        </div>
        <div className="meta-row">
          <span>观察覆盖</span>
          <span>{supervision ? `${supervision.covered_seq} / ${supervision.latest_seq}` : '—'}</span>
        </div>
        <div className="meta-row">
          <span>观察用量</span>
          <span>{supervision ? `${supervision.reviews_used} / ${supervision.max_reviews}` : '—'}</span>
        </div>
        <div className="meta-row">
          <span>上次审阅</span>
          <span>{supervision?.last_review_at ? formatTime(supervision.last_review_at) : '尚无'}</span>
        </div>
        {supervision && supervision.pending_requests.length > 0 && (
          <div className="meta-row">
            <span>待处理审阅请求</span>
            <span>{supervision.pending_requests.length}</span>
          </div>
        )}
        <div className="actions" style={{ marginTop: 10 }}>
          <button
            type="button"
            className="btn"
            disabled={busy || !enabled || runEnded}
            title={runEnded ? 'Run 已结束，不能再请求审阅' : undefined}
            onClick={() => void requestReview()}
          >
            请大脑现在审阅
          </button>
          <button
            type="button"
            className="btn"
            disabled={busy || runEnded}
            title={runEnded ? 'Run 已结束，监督状态不再变更' : undefined}
            onClick={() => void toggleSupervision()}
          >
            {enabled ? '关闭静默监督' : '开启静默监督'}
          </button>
        </div>

        <details className="snapshot" style={{ marginTop: 12 }}>
          <summary>指导记录（{supervision?.guidance.length ?? 0}）</summary>
          {supervision && supervision.guidance.length > 0 ? (
            <ul className="plain-list" style={{ marginTop: 8 }}>
              {supervision.guidance.map((g) => (
                <GuidanceItem key={g.id} item={g} />
              ))}
            </ul>
          ) : (
            <p className="small-text">尚无指导。</p>
          )}
        </details>

        <details className="snapshot" style={{ marginTop: 8 }}>
          <summary>大脑研究笔记（仅用户可见，不发送给执行器）</summary>
          {supervision?.private_note_md ? (
            <p className="pre-wrap" style={{ marginTop: 8 }}>{supervision.private_note_md}</p>
          ) : (
            <p className="small-text" style={{ marginTop: 8 }}>暂无笔记。</p>
          )}
          {supervision && supervision.watchlist.length > 0 && (
            <ul className="plain-list" style={{ marginTop: 8 }}>
              {supervision.watchlist.map((w) => (
                <li key={w.id} className="row-item block">
                  <strong>{w.hypothesis_md}</strong>
                  <div className="small-text">需要证据：{w.evidence_needed_md}</div>
                  <div className="small-text">介入条件：{w.intervene_when_md}</div>
                  {w.evidence_refs.length > 0 && (
                    <div className="small-text">证据引用：{w.evidence_refs.join('、')}</div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </details>
      </div>
    </article>
  )
}
