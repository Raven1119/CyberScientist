import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { ApiError, api, bindChallengeSkill, listSkills, unbindChallengeSkill, updateRunBudget } from '../api'
import { useApp } from '../app-context'
import { Badge, Modal, LoadingState } from '../components'
import { RunOperations } from './RunOperations'
import { Observation } from '../design/Observation'
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
  trialStatusLabel,
} from '../labels'
import type {
  ChallengeDetail,
  ChallengeSummary,
  Checkpoint,
  ModelChoice,
  RunOverview,
  RunBudget,
  RunDetail,
  RunEvent,
  RunSummary,
  Settings,
  ReviewRequestResult,
  SkillCatalogResponse,
  Submission,
  SupervisionGuidance,
  SupervisionStatus,
} from '../types'
import { useRunEventStream, type StreamStatus } from '../useRunEventStream'

type Tab = 'events' | 'trials' | 'checkpoints' | 'data' | 'submission'

const TABS: { key: Tab; label: string }[] = [
  { key: 'events', label: '事件流' },
  { key: 'trials', label: 'Trials' },
  { key: 'checkpoints', label: '检查点' },
  { key: 'data', label: '公开数据' },
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
  const { toast, currentChallengeId, setCurrentChallengeId, demoMode, setPage } = useApp()

  const [challenges, setChallenges] = useState<ChallengeSummary[]>([])
  const [challengeId, setChallengeId] = useState<string | null>(currentChallengeId)
  const [challengeSnapshot, setChallenge] = useState<ChallengeDetail | null>(null)
  const challenge = challengeSnapshot?.id === challengeId ? challengeSnapshot : null
  const selectedChallengeId = useRef(challengeId)
  selectedChallengeId.current = challengeId
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [overview, setOverview] = useState<RunOverview[]>([])
  const [preferredRunId, setPreferredRunId] = useState<string | null>(null)
  const [editModelsOpen, setEditModelsOpen] = useState(false)

  const [events, setEvents] = useState<RunEvent[]>([])
  const [tab, setTab] = useState<Tab>('events')
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([])
  const [importOpen, setImportOpen] = useState(false)
  const [startOpen, setStartOpen] = useState(false)
  const [terminateOpen, setTerminateOpen] = useState(false)
  const [budgetOpen, setBudgetOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [steerDrafts, setSteerDrafts] = useState<Record<string, string>>({})
  const [steerState, setSteerState] = useState<{
    opId: string
    state: 'queued' | 'review_queued'
  } | null>(null)
  const [supervisionSnapshot, setSupervisionSnapshot] = useState<{ runId: string; data: SupervisionStatus } | null>(null)
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
      const active = await api.get<{ items: RunOverview[] }>('/api/v1/runs/overview')
      setOverview(active.items)
    } catch (err) {
      toast('加载 Run 列表失败：' + (err instanceof Error ? err.message : String(err)))
    }
  }, [toast])

  useEffect(() => {
    const timer = window.setInterval(() => void refreshRuns(), 10000)
    return () => window.clearInterval(timer)
  }, [refreshRuns])

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
    let cancelled = false
    setCurrentChallengeId(challengeId)
    if (!challengeId) {
      setChallenge(null)
      return
    }
    api
      .get<ChallengeDetail>(`/api/v1/challenges/${challengeId}`)
      .then((value) => { if (!cancelled) setChallenge(value) })
      .catch(() => { if (!cancelled) setChallenge(null) })
    return () => { cancelled = true }
  }, [challengeId, setCurrentChallengeId])

  const currentRun: RunSummary | null = useMemo(() => {
    if (!challengeId) return null
    const forChallenge = runs
      .filter((r) => r.challenge_id === challengeId)
      .sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''))
    return forChallenge.find((run) => run.id === preferredRunId)
      ?? forChallenge.find((run) => ACTIVE_PHASES.includes(run.phase))
      ?? forChallenge[0] ?? null
  }, [runs, challengeId, preferredRunId])

  // A delayed response from a previous selection must never animate this Run.
  const selectedRunId = useRef<string | null>(null)
  selectedRunId.current = currentRun?.id ?? null
  const steerText = currentRun ? steerDrafts[currentRun.id] ?? '' : ''
  function setSteerText(text: string) {
    if (currentRun) setSteerDrafts((drafts) => ({ ...drafts, [currentRun.id]: text }))
  }
  const supervision = supervisionSnapshot?.runId === currentRun?.id ? supervisionSnapshot?.data ?? null : null

  const active = currentRun ? ACTIVE_PHASES.includes(currentRun.phase) : false

  const [runSnapshot, setRunDetail] = useState<RunDetail | null>(null)
  const runDetail = runSnapshot?.id === currentRun?.id ? runSnapshot : null
  const detailRequest = useRef(0)
  const checkpointRequest = useRef(0)
  const lifecycleV2 = (runDetail?.config_snapshot as { lifecycle_version?: number } | undefined)?.lifecycle_version === 2

  const phase = runDetail?.phase ?? currentRun?.phase ?? null
  const paused = phase === 'paused'
  const pausing = phase === 'pausing'
  const recovering = phase === 'recovering'
  const terminal = phase !== null && TERMINAL_PHASES.includes(phase)

  useEffect(() => {
    setRunDetail(null)
    setEvents([])
    setCheckpoints([])
    setSteerState(null)
    setSupervisionSnapshot(null)
  }, [currentRun?.id])

  const refreshRunDetail = useCallback(async () => {
    if (!currentRun) return
    const request = ++detailRequest.current
    try {
      const detail = await api.get<RunDetail>(`/api/v1/runs/${currentRun.id}`)
      if (request === detailRequest.current && selectedRunId.current === currentRun.id) setRunDetail(detail)
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
    const request = ++checkpointRequest.current
    try {
      const data = await api.get<{ items?: Checkpoint[] } | Checkpoint[]>(
        `/api/v1/runs/${currentRun.id}/checkpoints`,
      )
      if (request === checkpointRequest.current && selectedRunId.current === currentRun.id) {
        setCheckpoints(Array.isArray(data) ? data : (data.items ?? []))
      }
    } catch {
      if (request === checkpointRequest.current && selectedRunId.current === currentRun.id) setCheckpoints([])
    }
  }, [currentRun])

  const refreshSupervision = useCallback(async () => {
    if (!currentRun) return
    try {
      const data = await api.get<SupervisionStatus>(`/api/v1/runs/${currentRun.id}/supervision`)
      if (selectedRunId.current === currentRun.id) setSupervisionSnapshot({ runId: currentRun.id, data })
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

  const steerStateRef = useRef<typeof steerState>(null)
  useEffect(() => {
    steerStateRef.current = steerState
  }, [steerState])

  const handleEvent = useCallback(
    (event: RunEvent) => {
      setEvents((list) => [...list, event])
      const pendingSteer = steerStateRef.current
      if (pendingSteer && pendingSteer.state === 'queued') {
        if (event.type === 'user.steer.review_queued' && event.payload.operation_id === pendingSteer.opId) {
          setSteerState({ ...pendingSteer, state: 'review_queued' })
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
    setBusy(true)
    // Subscribe to a correlated receipt before POST; SSE can arrive first.
    const pending = { opId, state: 'queued' as const }
    steerStateRef.current = pending
    setSteerState(pending)
    try {
      await api.post(`/api/v1/runs/${currentRun.id}/control`, {
        action: 'steer',
        text,
        operation_id: opId,
      })
      setSteerText('')
      toast('指导已排队。')
    } catch (err) {
      if (selectedRunId.current === currentRun.id) { steerStateRef.current = null; setSteerState(null) }
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

      <RunOverviewPanel items={overview} onSelect={(item) => {
        setChallengeId(item.challenge_id)
        setPreferredRunId(item.id)
      }} />

      {challenge ? (
        <div className="challenge-bar">
          <div>
            <div className="challenge-label">
              {challenge.is_demo ? 'DEMO_CHALLENGE · 非真实竞赛题' : (challenge.platform_challenge_id ?? '本地题目')}
            </div>
            <div className="challenge-title">{challenge.title}</div>
            <p className="small-text">大脑 {challenge.model_config?.brain.runtime ?? '未配置'} / {challenge.model_config?.brain.model_id ?? '未知'} · 执行器 {challenge.model_config?.executor.runtime ?? '未配置'} / {challenge.model_config?.executor.model_id ?? '未知'}</p>
            {challenge.platform_snapshot && (
              <p className="small-text">
                平台状态：{challenge.platform_snapshot.status ?? '未知'}
                {challenge.platform_snapshot.roundEndAt && ` · 截止 ${formatTime(challenge.platform_snapshot.roundEndAt)}`}
                {challenge.platform_snapshot.scoring && ` · 评分策略 ${challenge.platform_snapshot.scoring.strategy ?? '未知'}`}
                {challenge.platform_snapshot.scoring?.grader_name === null && ' · 未注册题目专属评分器'}
                {' · 参赛有效性待平台确认'}
              </p>
            )}
          </div>
          <div className="actions">
            <button type="button" className="btn small" onClick={() => setEditModelsOpen(true)}>编辑本题模型</button>
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

      {(phase === 'blocked' || phase === 'paused' || phase === 'pausing') && runDetail?.block_reason && (
        <div className="callout danger" role="alert">
          <strong>{phase === 'blocked' ? '研究被阻塞：' : '运行需要关注：'}</strong>
          {runDetail.block_reason}
          <button type="button" className="btn small" onClick={() => setPage('settings')}>
            去连接设置
          </button>
        </div>
      )}

      {runDetail?.gate === 'awaiting_budget' && (
        <div className="callout" role="alert">
          <strong>Trial 已达本 Run 上限，待处理意图已保存。</strong>
          <div className="actions" style={{ marginTop: 8 }}>
            <button type="button" className="btn" onClick={() => setBudgetOpen(true)}>提高 Trial 上限</button>
            <button type="button" className="btn" onClick={() => {
              if (!currentRun) return
              void api.post(`/api/v1/runs/${currentRun.id}/pending-intent/drop`, { reason: '用户在前端放弃意图' })
                .then(() => void refreshRunDetail())
                .catch((err: unknown) => toast('放弃意图失败：' + (err instanceof Error ? err.message : String(err))))
            }}>放弃该意图</button>
            <button type="button" className="btn danger" onClick={() => setTerminateOpen(true)}>结束 Run</button>
          </div>
        </div>
      )}

      <div className="work-grid">
        <div className="stack">
          <article className="card intention-card">
            <div className="card-head">
              <h2>{lifecycleV2 ? '用户目标与当前 Trial' : '当前研究意图'}</h2>
              <span className="instrument-label">THINKING SPACE</span>
            </div>
            <div className="card-body">
              {lifecycleV2 && runDetail ? (
                <div>
                  <p className="pre-wrap">{runDetail.objective_md || '用户目标未填写'}</p>
                  <p className="small-text">用户目标状态：{runDetail.objective_status || 'open'}</p>
                  <p className="small-text">当前 Trial：{runDetail.trials.find((t) => t.id === runDetail.current_trial_id)?.goal || '尚无'}</p>
                  {runDetail.end_reason && <p className="small-text">结束原因：{runDetail.end_reason}</p>}
                </div>
              ) : (
                <ResearchIntention key={currentRun?.id}
                  text={runDetail?.intention ?? '尚未开始研究。开始后会显示大脑当前的研究意图。'} />
              )}
            </div>
          </article>

          <article className="card guidance-card">
            <div className="card-head">
              <h2>人工指导</h2>
              <span className="instrument-label">WORKING NOTE</span>
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
                    : '已进入大脑审阅队列；尚未确认执行器接收。'}
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
                style={{ marginTop: 10 }}
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

          {currentRun && <RunOperations key={currentRun.id} runId={currentRun.id} phase={phase ?? currentRun.phase} />}

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
                {(active || recovering) && (
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
                            {trialStatusLabel(t.status, t.delivered)}
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
                    key={currentRun?.id ?? 'none'}
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
                  key={`${challengeId}:${currentRun?.id}:${runDetail?.current_trial_id}`}
                  challengeId={challengeId}
                  runId={currentRun?.id ?? null}
                  trialId={runDetail?.current_trial_id ?? null}
                  refreshKey={subRefresh}
                />
              )}
              {tab === 'data' && challengeId && (
                <DataPanel key={`${challengeId}:${currentRun?.id}`} challengeId={challengeId} runId={currentRun?.id ?? null} />
              )}
            </div>
          </article>
        </div>

        <div className="stack right">
          <Observation key={currentRun?.id ?? challengeId ?? 'idle'} runId={currentRun?.id}
            phase={runDetail?.id === currentRun?.id ? runDetail?.phase : currentRun?.phase}
            connected={streamStatus === 'open'} supervision={supervision} demo={demoMode} />
          <details className="card runtime-summary">
            <summary className="card-head">
              <span className="small-title">运行摘要与预算</span>
              {currentRun && <Badge tone="neutral">模式 {currentRun.mode}</Badge>}
            </summary>
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
          </details>

          {currentRun && (
            <SupervisionPanel
              runId={currentRun.id}
              supervision={supervision}
              runEnded={terminal}
              onChanged={(s) => {
                if (selectedRunId.current === currentRun.id) setSupervisionSnapshot({ runId: currentRun.id, data: s })
              }}
              onRefresh={() => void refreshSupervision()}
            />
          )}
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

      <ChallengeModelDialog key={`models:${challengeId}`} open={editModelsOpen} challenge={challenge}
        onClose={() => setEditModelsOpen(false)}
        onSaved={(updated) => {
          if (selectedChallengeId.current === updated.id) { setChallenge(updated); setEditModelsOpen(false) }
        }} />

      <StartDialog
        key={`start:${challengeId}`}
        open={startOpen}
        onClose={() => setStartOpen(false)}
        challengeId={challengeId}
        challengeTitle={challenge?.title ?? ''}
        activePhase={active ? phase : null}
        existingRunId={currentRun?.phase === 'created' ? currentRun.id : null}
        demoMode={demoMode}
        onCreated={() => void refreshRuns()}
        onStarted={() => {
          if (selectedChallengeId.current !== challengeId) return
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

function ResearchIntention({ text }: { text: string }) {
  const id = useId()
  const content = useRef<HTMLParagraphElement>(null)
  const [expanded, setExpanded] = useState(false)
  const [overflows, setOverflows] = useState(false)

  useEffect(() => setExpanded(false), [text])

  useEffect(() => {
    const element = content.current
    if (!element) return
    const measure = () => {
      const lineHeight = Number.parseFloat(window.getComputedStyle(element).lineHeight)
      setOverflows(element.scrollHeight > lineHeight * 6 + 1)
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [text])

  return (
    <div className="intent">
      <p id={id} ref={content} className={expanded ? '' : 'intent-collapsed'}>{text}</p>
      {overflows && (
        <button
          type="button"
          className="link-btn intent-toggle"
          aria-expanded={expanded}
          aria-controls={id}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? '收起' : '展开全文'}
        </button>
      )}
    </div>
  )
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
  const alwaysOnCount = data?.skills.filter((s) => s.always_on).length ?? 0

  return (
    <div className="skill-bar">
      {data && <span className="small-text">常驻技能 {alwaysOnCount} 项</span>}
      <span className="skill-bar-label">本题额外技能</span>
      {data === null ? (
        <LoadingState />
      ) : boundSkills.length === 0 ? (
        <span className="small-text">未绑定</span>
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

type SelectedModels = { brain: ModelChoice; executor: ModelChoice }

export function RunOverviewPanel({ items, onSelect }: {
  items: RunOverview[]
  onSelect: (item: RunOverview) => void
}) {
  return <article className="card" aria-label="本轮总览">
    <div className="card-head"><h2>本轮总览</h2><span className="small-text">活跃 Run {items.length}</span></div>
    <div className="card-body">
      {items.length === 0 ? <p className="sub">当前没有活跃 Run。</p> : <ul className="plain-list">
        {items.map((item) => <li key={item.id} className="row-item">
          <button type="button" className="btn" onClick={() => onSelect(item)}>
            {item.challenge_title} · {item.id.slice(0, 8)}
          </button>
          <span>{PHASE_LABELS[item.phase] ?? item.phase} · 门禁 {item.gate ?? '开放'}</span>
          <span>Trial {item.current_trial_id ?? '无'} · Job {item.job_count} · 沙箱 {item.sandbox_count}</span>
          <span>最近得分 {item.latest_score ?? '未知'}
            {item.latest_score !== null && `（${item.score_confidence === 'confirmed' ? '已确认' : '暂定'}）`}</span>
          {item.needs_attention && <Badge tone="amber">需关注：{item.attention_reason ?? '门禁待处理'}</Badge>}
        </li>)}
      </ul>}
    </div>
  </article>
}

function ModelChoicesEditor({ value, onChange, prefix }: {
  value: SelectedModels
  onChange: (next: SelectedModels) => void
  prefix: string
}) {
  const { toast } = useApp()
  const [checking, setChecking] = useState<string | null>(null)
  async function check(role: 'brain' | 'executor') {
    setChecking(role)
    try {
      const result = await api.post<{ status: string; detail: string }>(
        `/api/v1/connections/${role}/test`, { kind: 'model_selection', model_choice: value[role] })
      toast(result.status === 'ok' ? `模型会话可用：${result.detail}` : `模型尚不可用：${result.detail}`)
    } catch (err) {
      toast('模型检查失败：' + (err instanceof Error ? err.message : String(err)))
    } finally { setChecking(null) }
  }
  return <div className="fields">
    {(['brain', 'executor'] as const).map((role) => (
      <div key={role} className="field">
        <strong>{role === 'brain' ? '大脑' : '执行器'}模型</strong>
        <label htmlFor={`${prefix}-${role}-runtime`}>原生运行时</label>
        <select id={`${prefix}-${role}-runtime`} value={value[role].runtime}
          onChange={(event) => onChange({ ...value, [role]: {
            ...value[role], runtime: event.target.value, model_id: '',
          } })}>
          <option value="codex">Codex</option><option value="kimi">Kimi Code</option>
          {role === 'executor' && <option value="prime">Prime Agent</option>}
        </select>
        <label htmlFor={`${prefix}-${role}-model`}>模型 ID</label>
        <input id={`${prefix}-${role}-model`} value={value[role].model_id}
          onChange={(event) => onChange({ ...value, [role]: {
            ...value[role], model_id: event.target.value,
          } })} placeholder="手动填写；连接检查可验证可用性" />
        <label htmlFor={`${prefix}-${role}-effort`}>思考强度</label>
        <select id={`${prefix}-${role}-effort`} value={value[role].reasoning_effort}
          onChange={(event) => onChange({ ...value, [role]: {
            ...value[role], reasoning_effort: event.target.value as ModelChoice['reasoning_effort'],
          } })}>
          {['low', 'medium', 'high', 'xhigh', 'max'].map((effort) =>
            <option key={effort} value={effort}>{effort}</option>)}
        </select>
        <button type="button" className="btn small" disabled={checking !== null || !value[role].model_id.trim()}
          onClick={() => void check(role)}>检查所选模型会话</button>
      </div>
    ))}
  </div>
}

function ChallengeModelDialog({ open, challenge, onClose, onSaved }: {
  open: boolean
  challenge: ChallengeDetail | null
  onClose: () => void
  onSaved: (updated: ChallengeDetail) => void
}) {
  const { toast } = useApp()
  const [models, setModels] = useState<SelectedModels | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (open) setModels(challenge?.model_config ?? null)
  }, [open, challenge?.id])
  async function save() {
    if (!challenge || !models) return
    setBusy(true)
    try {
      const updated = await api.put<ChallengeDetail>(`/api/v1/challenges/${challenge.id}/models`,
        { model_config: models })
      toast('本题模型已保存；只影响之后创建的 Run。')
      onSaved(updated)
    } catch (err) {
      toast('保存本题模型失败：' + (err instanceof Error ? err.message : String(err)))
    } finally { setBusy(false) }
  }
  return <Modal open={open} onClose={onClose} title="编辑本题模型">
    <p className="sub">已有 Run 使用创建时冻结的模型配置。</p>
    {models && <ModelChoicesEditor value={models} onChange={setModels} prefix="challenge-model" />}
    <div className="modal-actions">
      <button type="button" className="btn" onClick={onClose}>取消</button>
      <button type="button" className="btn primary" disabled={busy || !models} onClick={() => void save()}>保存</button>
    </div>
  </Modal>
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
  const [models, setModels] = useState<SelectedModels | null>(null)

  useEffect(() => {
    if (!open) return
    api.get<Settings>('/api/v1/settings').then((settings) => setModels({
      brain: { runtime: settings.brain.runtime, model_id: settings.brain.model_id,
        reasoning_effort: settings.brain.reasoning_effort },
      executor: { runtime: settings.executor.runtime, model_id: settings.executor.model_id,
        reasoning_effort: settings.executor.reasoning_effort },
    })).catch(() => setModels(null))
  }, [open])

  async function submit() {
    setBusy(true)
    try {
      const body: Record<string, unknown> = { mode }
      if (!models || !models.brain.model_id.trim() || !models.executor.model_id.trim()) {
        toast('请先填写大脑和执行器的模型 ID。')
        return
      }
      body.model_config = models
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
      {models ? <ModelChoicesEditor value={models} onChange={setModels} prefix="import-model" />
        : <LoadingState>正在加载模型默认配置…</LoadingState>}
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
  existingRunId,
  demoMode,
  onCreated,
  onStarted,
  onResume,
}: {
  open: boolean
  onClose: () => void
  challengeId: string | null
  challengeTitle: string
  activePhase: string | null
  existingRunId: string | null
  demoMode: boolean
  onCreated: () => void
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
  const [maxSandboxes, setMaxSandboxes] = useState(0)
  const [maxSandboxMinutes, setMaxSandboxMinutes] = useState(0)
  const [allowSandboxGpu, setAllowSandboxGpu] = useState(false)
  const [note, setNote] = useState('')
  const [objective, setObjective] = useState('')
  const [allowDataDownload, setAllowDataDownload] = useState(false)
  const [busy, setBusy] = useState(false)
  const pendingRun = useRef<string | null>(null)
  const [creationUncertain, setCreationUncertain] = useState(false)
  const [error, setError] = useState('')
  const [defaultsLoading, setDefaultsLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    if (open) {
      setDefaultsLoading(true)
      setMaxModelTurns(0); setMaxRunMinutes(30); setMaxSubmissions(0); setMaxJobs(0)
      setAllowModelCalls(false)
      setShadowEnabled(false)
      setNote('')
      setObjective('')
      setAllowDataDownload(false)
      setMaxSandboxes(0)
      setMaxSandboxMinutes(0)
      setAllowSandboxGpu(false)
      api
        .get<{ run_defaults: { max_model_turns: number; max_run_minutes: number; max_submissions: number; max_jobs: number } }>(
          '/api/v1/settings',
        )
        .then((s) => {
          if (cancelled) return
          setMaxModelTurns(s.run_defaults.max_model_turns)
          setMaxRunMinutes(s.run_defaults.max_run_minutes)
          setMaxSubmissions(s.run_defaults.max_submissions)
          setMaxJobs(s.run_defaults.max_jobs)
        })
        .catch(() => { if (!cancelled) setError('未能加载默认预算，请核对并手动填写本轮授权。') })
        .finally(() => { if (!cancelled) setDefaultsLoading(false) })
    }
    return () => { cancelled = true }
  }, [open])

  async function start() {
    if (!challengeId || busy || defaultsLoading || creationUncertain) return
    setBusy(true)
    setError('')
    let stage = 'prepare'
    try {
      let runId = pendingRun.current ?? existingRunId
      if (runId) {
        const status = await api.get<{ phase: string }>(`/api/v1/runs/${runId}`)
        if (status.phase === 'running') {
          pendingRun.current = null
          toast('Run 已在运行，已重新读取状态。')
          onStarted()
          return
        }
        if (status.phase !== 'created') throw new Error(`Run ${runId} 当前为 ${status.phase}，请在研究页处理已有 Run。`)
      } else {
        stage = 'create'
        const run = await api.post<{ id: string }>('/api/v1/runs', {
          challenge_id: challengeId, shadow_enabled: shadowEnabled,
        })
        runId = run.id
        pendingRun.current = run.id
        onCreated()
      }
      stage = 'authorize'
      await api.post(`/api/v1/runs/${runId}/authorize`, {
        scope: demoMode ? 'demo' : 'model_roundtrip',
        allow_model_calls: allowModelCalls,
        max_model_turns: maxModelTurns,
        max_run_minutes: maxRunMinutes,
        max_submissions: maxSubmissions,
        max_jobs: maxJobs,
        max_sandboxes: maxSandboxes,
        max_sandbox_minutes: maxSandboxMinutes,
        allow_sandbox_gpu: allowSandboxGpu,
        job_limits: { max_concurrent_jobs: 2, max_cpu: 16, max_memory_gb: 16, max_disk_gb: 10, allow_gpu: false },
        note: note.trim() || undefined,
        objective: objective.trim() || note.trim() || undefined,
        allow_data_download: allowDataDownload,
      })
      stage = 'start'
      await api.post(`/api/v1/runs/${runId}/start`)
      pendingRun.current = null
      toast('研究已开始。')
      onStarted()
    } catch (err) {
      if (stage === 'create' && (!(err instanceof ApiError) || err.status >= 500)) setCreationUncertain(true)
      const message = '开始研究失败：' + (err instanceof Error ? err.message : String(err))
      setError(message)
      toast(message)
      onCreated()
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

  if (activePhase && activePhase !== 'created') {
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
      {(pendingRun.current || existingRunId) && <p className="inline-note">继续配置已有 Run：{pendingRun.current ?? existingRunId}，不会重复创建。</p>}
      {error && <p role="alert" className="form-error">{error}</p>}
      {creationUncertain && <p role="alert">创建结果未知，已停止重试创建。请关闭此窗口并刷新研究页，核对已有 Run。</p>}
      {defaultsLoading && <LoadingState>正在加载默认预算…</LoadingState>}
      <fieldset className="settings-fields" disabled={busy || defaultsLoading}>
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
      <p className="inline-note">算力授权：最多同时 2 个任务，每个最多 16 核 CPU、16 GB 内存、10 GB 磁盘，无 GPU。失败和未知创建计入 Job 总数，每个 Job 必须设置本轮剩余时长内的超时。</p>
      <div className="field"><label htmlFor="auth-sandboxes">同时存在的沙箱上限</label>
        <input id="auth-sandboxes" type="number" min={0} value={maxSandboxes}
          onChange={(e) => setMaxSandboxes(Number(e.target.value))} /></div>
      <div className="field"><label htmlFor="auth-sandbox-minutes">沙箱累计存活分钟上限</label>
        <input id="auth-sandbox-minutes" type="number" min={0} value={maxSandboxMinutes}
          onChange={(e) => setMaxSandboxMinutes(Number(e.target.value))} /></div>
      <div className="field checkbox"><input id="auth-sandbox-gpu" type="checkbox"
        checked={allowSandboxGpu} onChange={(e) => setAllowSandboxGpu(e.target.checked)} />
        <label htmlFor="auth-sandbox-gpu">单独授权沙箱 GPU</label></div>
      <div className="field checkbox">
        <input id="auth-data-download" type="checkbox" checked={allowDataDownload}
          onChange={(e) => setAllowDataDownload(e.target.checked)} />
        <label htmlFor="auth-data-download">允许用本账号下载题目公开数据</label>
      </div>
      <div className="field">
        <label htmlFor="auth-objective">本 Run 的用户目标</label>
        <textarea id="auth-objective" value={objective} onChange={(e) => setObjective(e.target.value)} />
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
        <button type="button" className="btn primary" disabled={busy || creationUncertain} onClick={() => void start()}>
          {busy ? '启动中…' : (pendingRun.current || existingRunId) ? '授权并启动现有 Run' : '确认并开始'}
        </button>
      </div>
      </fieldset>
    </Modal>
  )
}

type DataItem = {
  materialization_id: string
  resource_key: string
  status: string
  error_code?: string | null
  content_sha256?: string
  workspace_path?: string
  hash_semantics: string
}

function DataPanel({ challengeId, runId }: { challengeId: string; runId: string | null }) {
  const { toast } = useApp()
  const [items, setItems] = useState<DataItem[]>([])
  const [busy, setBusy] = useState(false)
  const load = useCallback(async () => {
    try {
      const result = await api.get<{ items: DataItem[] }>(`/api/v1/challenges/${encodeURIComponent(challengeId)}/data`)
      setItems(result.items)
    } catch (err) {
      toast('读取公开数据状态失败：' + (err instanceof Error ? err.message : String(err)))
    }
  }, [challengeId, toast])
  useEffect(() => { void load() }, [load])
  async function request(item: DataItem) {
    if (!runId) return
    setBusy(true)
    try {
      await api.post(`/api/v1/runs/${runId}/data/materialize`, {
        resource_key: item.resource_key, operation_id: `data-${crypto.randomUUID()}`,
      })
      await load()
    } catch (err) {
      toast('数据物化失败：' + (err instanceof Error ? err.message : String(err)))
      await load()
    } finally { setBusy(false) }
  }
  return <div>
    <p className="inline-note">公开数据下载需在本 Run 单独授权。Wenyon 公开清单及所列文件校验通过时显示 verified；缺少可核对的登记哈希时显示 unverified。</p>
    <button type="button" className="btn small" onClick={() => void load()}>刷新数据状态</button>
    {items.length === 0 ? <p className="small-text">该题未登记可物化数据。</p> :
      <ul className="plain-list">{items.map((item) => <li key={item.materialization_id} className="row-item block">
        <strong>{item.resource_key}</strong>
        <div className="small-text">状态：{item.status} · 哈希语义：{item.hash_semantics}
          {item.error_code && ` · ${item.error_code}`}</div>
        {item.error_code === 'AUTH_REQUIRED' && <div className="small-text">
          Wenyon 未通过认证。请检查其隔离 HOME 中的原生 CLI 登录状态；AccessKey 已配置不等于 Wenyon 会话有效。
        </div>}
        {item.content_sha256 && <div className="small-text">SHA-256：{item.content_sha256}</div>}
        {item.workspace_path && <div className="small-text">工作区：{item.workspace_path}</div>}
        {runId && item.status !== 'unsupported' && <button type="button" className="btn small" disabled={busy}
          onClick={() => void request(item)}>请求物化</button>}
      </li>)}</ul>}
  </div>
}

function SubmissionsPanel({
  challengeId,
  runId,
  trialId,
  refreshKey,
}: {
  challengeId: string
  runId: string | null
  trialId: string | null
  refreshKey: number
}) {
  const { toast } = useApp()
  const [items, setItems] = useState<Submission[] | null>(null)
  const [localScoring, setLocalScoring] = useState<{
    scorer: { scorer_version: string; version: string; image: string } | null
    local_scores?: { id: string; run_id: string; science_score: number | null;
      score_source: 'system' | 'executor_verified'; package_sha256: string }[]
    calibrations: { submission_id: string; predicted_display_score: number | null;
      platform_display_score: number | null; display_delta: number | null;
      science_delta: number | null; trace_delta: number | null; valid: number;
      source: 'realtime' | 'historical' }[]
  } | null>(null)
  const [busy, setBusy] = useState(false)
  const [packagePath, setPackagePath] = useState('')
  const preflightRequest = useRef(0)
  const [preflight, setPreflight] = useState<{
    sealed_package_sha256: string
    error_code: string | null
    admission: { verdict: string; signals: Record<string, { ok: boolean | null; detail: string }> }
    trace_diagnostics: {
      status: 'ready' | 'unavailable'
      reason?: string
      checklist_cap: number | null
      advisories: { code: string; grade: string; reason: string; action: string; implied_cap: number | null }[]
      details: { code: string; grade: string; reason: string; implied_cap: number | null }[]
    }
  } | null>(null)

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

  useEffect(() => {
    void api.get<typeof localScoring>(
      `/api/v1/challenges/${encodeURIComponent(challengeId)}/local-scores`,
    ).then(setLocalScoring).catch(() => setLocalScoring(null))
  }, [challengeId, refreshKey])

  async function poll() {
    setBusy(true)
    try {
      const res = await api.post<{ polled: number; updated: number; still_unknown: number }>(
        '/api/v1/submissions/poll', runId ? { run_id: runId } : {})
      toast(`评分轮询：检查 ${res.polled}，新出分 ${res.updated}，等待中 ${res.still_unknown}。`)
      await load()
      setLocalScoring(await api.get<typeof localScoring>(
        `/api/v1/challenges/${encodeURIComponent(challengeId)}/local-scores`))
    } catch (err) {
      toast('轮询失败：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setBusy(false)
    }
  }

  async function checkPackage() {
    if (!runId) return
    const requestId = ++preflightRequest.current
    setPreflight(null)
    setBusy(true)
    try {
      const result = await api.post<typeof preflight>(`/api/v1/runs/${runId}/submissions/preflight`, {
        trial_id: trialId, package_path: packagePath.trim() || undefined,
      })
      if (requestId === preflightRequest.current) setPreflight(result)
    } catch (err) {
      if (requestId === preflightRequest.current) {
        toast('提交预检失败：' + (err instanceof Error ? err.message : String(err)))
      }
    } finally { setBusy(false) }
  }

  if (items === null) return <LoadingState />
  return (
    <div>
      <div className="callout" style={{ marginBottom: 12 }}>
        <strong>本地评分器</strong>
        <p className="small-text">{localScoring?.scorer
          ? `版本 ${localScoring.scorer.version} (${localScoring.scorer.scorer_version.slice(0, 12)}) · 镜像 ${localScoring.scorer.image}`
          : '本题尚未配置本地科学评分器'}</p>
        {(localScoring?.local_scores ?? []).filter(score => !runId || score.run_id === runId).slice(0, 10).map(score => (
          <p className="small-text" key={score.id}>科学分 {score.science_score ?? '未知'} ·
            {score.score_source === 'executor_verified' ? '执行器运行，经系统核对' : '系统评分'} ·
            封存包 {score.package_sha256.slice(0, 12)}</p>
        ))}
      </div>
      {runId && <div className="callout" style={{ marginBottom: 12 }}>
        <strong>提交包只读预检</strong>
        <div className="field"><label htmlFor="preflight-package-path">工作区相对包路径（留空用当前 Trial 的 result_package.zip）</label>
          <input id="preflight-package-path" value={packagePath} onChange={(e) => {
            preflightRequest.current += 1
            setPreflight(null)
            setPackagePath(e.target.value)
          }} /></div>
        <button type="button" className="btn" disabled={busy} onClick={() => void checkPackage()}>检查封存包</button>
        {preflight && <div role="status">
          <p>准入：{preflight.admission.verdict} · 门禁：{preflight.error_code || '通过'} · 封存 SHA-256：{preflight.sealed_package_sha256}</p>
          <ul>{Object.entries(preflight.admission.signals).map(([name, signal]) =>
            <li key={name}>{name}：{signal.ok === null ? '未知' : signal.ok ? '通过' : '未满足'} · {signal.detail}</li>)}</ul>
          <p>轨迹确定性诊断：{preflight.trace_diagnostics.status === 'ready'
            ? `可用 · 公开 v6 检查表提示上限 ${preflight.trace_diagnostics.checklist_cap ?? '未知'}（不是官方评分）`
            : `不可用（${preflight.trace_diagnostics.reason || '未知原因'}）；不影响提交准入`}</p>
          {preflight.trace_diagnostics.status === 'ready' && <p className="small-text">
            分级只对历史 v8 回执中可见的代码成立；诊断不证明当前平台会采用同一上限。
          </p>}
          {preflight.trace_diagnostics.advisories.length > 0 && <ul>
            {preflight.trace_diagnostics.advisories.map((item) => <li key={item.code}>
              {item.code} · {item.grade === 'reliable' ? '条件可靠' : '条件提示性'}：{item.reason}
              {item.implied_cap !== null && ` · 该项上限 ${item.implied_cap}`} {item.action}
            </li>)}
          </ul>}
          {preflight.trace_diagnostics.status === 'ready' && <details>
            <summary>查看全部触发项（含历史一致性不足的检查项）</summary>
            <p className="small-text">分级仅按 63 份历史回执中可见代码计算；平台可能未显示所有触发项。</p>
            <ul>{preflight.trace_diagnostics.details.map((item) => <li key={item.code}>
              {item.code} · {item.grade === 'unavailable' ? '未知' : item.grade === 'reliable' ? '条件可靠' : '条件提示性'}：{item.reason}
              {item.implied_cap !== null && ` · 该项上限 ${item.implied_cap}`}
            </li>)}</ul>
          </details>}
        </div>}
      </div>}
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
                {s.score_status === 'scored' && ` · ${s.score_confidence === 'confirmed' ? '已确认' : '暂定'}`}
                {s.score_anomaly && ` · 评分异常：${s.score_anomaly}`}
                {s.scorecard_consistent === 0 && ' · 分项不一致'}
                {s.scorecard_consistent === 1 && ' · 分项一致'}
                {s.replay_of && ` · 原包重复提交，来源 ${s.replay_of}`}
              </div>
              {s.error && <p className="form-error">{s.error}</p>}
              {s.prediction_md && <p className="small-text">提交预测：{s.prediction_md}</p>}
              {localScoring?.calibrations.filter((item) => item.submission_id === s.id).map((item) => (
                <p className="small-text" key={item.submission_id}>
                  {item.source === 'historical' ? '历史校准' : '实时校准'}：本地预测 {item.predicted_display_score ?? '未知'} / 平台 {item.platform_display_score ?? '未知'}
                  {' · '}展示分偏差 {item.display_delta ?? '未知'}
                  {' · '}科学分偏差 {item.science_delta ?? '未知'}
                  {' · '}轨迹分偏差 {item.trace_delta ?? '未知'}
                  {item.valid === 0 && ' · 配对已失效'}
                </p>
              ))}
              {s.prediction_verdict && <p className="small-text">预测判定：{s.prediction_verdict} · {s.prediction_note_md || '无说明'}</p>}
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

export function GuidanceItem({ item }: { item: SupervisionGuidance }) {
  const [expanded, setExpanded] = useState(false)
  const stale = item.status === 'invalidated' || item.status === 'superseded'
  const text = item.text_md ?? ''
  const long = text.length > GUIDANCE_TEXT_LIMIT
  const shown = long && !expanded ? text.slice(0, GUIDANCE_TEXT_LIMIT) + '…' : text
  return (
    <li className="row-item block">
      <div className="actions" style={{ marginBottom: 4 }}>
        {item.source === 'controller' && <Badge tone="neutral">系统修复反馈</Badge>}
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
        <div className="meta-row">
          <span>最近唤醒原因</span>
          <span>{supervision?.last_wake
            ? `${supervision.last_wake.trigger} · ${formatTime(supervision.last_wake.created_at)}`
            : '尚无'}</span>
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
          <summary>研究回答（{supervision?.research_answers?.length ?? 0}）</summary>
          {supervision?.research_answers?.map((answer) => (
            <div key={answer.id} className="row-item block" style={{ marginTop: 8 }}>
              <strong>{answer.id}</strong>
              <div className="small-text">审阅：{answer.status} · 原生表单：{answer.native_form}
                {' · '}正文：{answer.delivery_status ?? '尚未投递'}
                {answer.delivery_channel ? `（${answer.delivery_channel}）` : ''}
                {answer.ack_disposition ? ` · ACK ${answer.ack_disposition}` : ''}</div>
              {answer.answer_md ? <p className="pre-wrap">{answer.answer_md}</p>
                : <p className="small-text">{answer.error ?? '等待大脑判断'}</p>}
              {answer.evidence_refs.length > 0 &&
                <div className="small-text">引用：{answer.evidence_refs.join('、')}</div>}
            </div>
          ))}
        </details>

        <details className="snapshot" style={{ marginTop: 8 }}>
          <summary>大脑实际读取（{supervision?.trace_reads?.length ?? 0}）</summary>
          {supervision?.trace_reads?.map((read) => (
            <div key={read.seq} className="small-text">
              {formatTime(read.recorded_at)} · {read.action}
              {read.ref ? ` · ${read.ref}` : ''}
              {read.source_seq != null ? ` · 来源序号 ${read.source_seq}` : ''}
            </div>
          ))}
        </details>

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
