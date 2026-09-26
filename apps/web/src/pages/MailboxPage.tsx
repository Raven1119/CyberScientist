import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { useApp } from '../app-context'
import { Badge, Modal } from '../components'
import { SCORE_STATUS_LABELS, SUBMISSION_STATUS_LABELS } from '../labels'
import type { Mailbox, MailboxList, MailboxUsage, Submission } from '../types'

interface RunSummary {
  id: string
  challenge_id: string
  phase: string
}

interface PollResult {
  polled: number
  updated: number
  still_unknown: number
  errors: number
}

interface PollingTask {
  challenge_id: string
  title: string
  pending: number
  enabled: boolean
  last_poll_at: string | null
  last_result: PollResult | null
}

const ROLE_LABEL: Record<string, string> = { harvest: '收割', experiment: '实验' }
const STATUS_LABEL: Record<string, string> = {
  active: '可用',
  disabled: '已停用',
}

function scoreText(s: Submission): string {
  if (s.score_status === 'scored' && s.score !== null) return String(s.score)
  return SCORE_STATUS_LABELS[s.score_status] ?? '未知'
}

export default function MailboxPage() {
  const { toast, demoMode } = useApp()
  const [mailboxes, setMailboxes] = useState<MailboxList | null>(null)
  const [usage, setUsage] = useState<MailboxUsage[]>([])
  const [submissions, setSubmissions] = useState<Submission[]>([])
  const [candidates, setCandidates] = useState<Submission[]>([])
  const [currentRun, setCurrentRun] = useState<RunSummary | null>(null)
  const [currentTrialId, setCurrentTrialId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [harvestEmail, setHarvestEmail] = useState('')
  const [harvestSecret, setHarvestSecret] = useState('')
  const [regCount, setRegCount] = useState(1)
  const [confirming, setConfirming] = useState<Submission | null>(null)
  const [pkgPath, setPkgPath] = useState('')
  const [allowProxyEvidence, setAllowProxyEvidence] = useState(false)
  const [allowIndeterminateAdmission, setAllowIndeterminateAdmission] = useState(false)
  const [pollingTasks, setPollingTasks] = useState<PollingTask[]>([])

  const refreshPolling = useCallback(async () => {
    try {
      const res = await api.get<{ tasks: PollingTask[] }>('/api/v1/polling')
      setPollingTasks(res.tasks)
    } catch {
      // 轻刷新失败不打扰用户：后台轮询循环本身不受影响
    }
  }, [])

  const refresh = useCallback(async () => {
    try {
      const mb = await api.get<MailboxList>('/api/v1/mailboxes')
      setMailboxes(mb)
      const quota = await api.get<{ items: MailboxUsage[] }>('/api/v1/mailboxes/usage')
      setUsage(quota.items)
      const runs = await api.get<{ items: RunSummary[] }>('/api/v1/runs')
      const run = runs.items[0] ?? null
      setCurrentRun(run)
      if (run) {
        const detail = await api.get<{ current_trial_id: string | null }>(
          `/api/v1/runs/${run.id}`)
        setCurrentTrialId(detail.current_trial_id)
        const subs = await api.get<{ items: Submission[] }>(
          `/api/v1/runs/${run.id}/submissions`)
        setSubmissions(subs.items)
        const cand = await api.get<{ items: Submission[] }>(
          `/api/v1/harvest/candidates?challenge_id=${encodeURIComponent(run.challenge_id)}`)
        setCandidates(cand.items)
      } else {
        setCurrentTrialId(null)
        setSubmissions([])
        setCandidates([])
      }
    } catch (err) {
      toast('加载邮箱数据失败：' + (err instanceof Error ? err.message : String(err)))
    }
  }, [toast])

  useEffect(() => {
    void refresh()
    void refreshPolling()
    // 后台轮询 45 秒一轮；卡片每 30 秒轻刷新一次（不触发后端轮询）
    const timer = setInterval(() => void refreshPolling(), 30_000)
    return () => clearInterval(timer)
  }, [refresh, refreshPolling])

  const togglePolling = async (task: PollingTask) => {
    setBusy(true)
    try {
      await api.post(
        `/api/v1/polling/${encodeURIComponent(task.challenge_id)}`,
        { enabled: !task.enabled })
      toast(task.enabled ? `已中断「${task.title}」的评分轮询。`
                         : `已启用「${task.title}」的评分轮询。`)
      await refreshPolling()
    } catch (err) {
      toast('轮询开关失败：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setBusy(false)
    }
  }

  const runPollingNow = async (task: PollingTask) => {
    setBusy(true)
    try {
      const res = await api.post<PollResult>(
        `/api/v1/polling/${encodeURIComponent(task.challenge_id)}/run`)
      toast(`「${task.title}」轮询完成：检查 ${res.polled}，拉回 ${res.updated}，仍未知 ${res.still_unknown}，错误 ${res.errors}。`)
      await refreshPolling()
    } catch (err) {
      toast('轮询失败：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setBusy(false)
    }
  }

  const addHarvest = async () => {
    setBusy(true)
    try {
      await api.post('/api/v1/mailboxes/harvest', {
        email: harvestEmail,
        secret: harvestSecret,
      })
      setHarvestEmail('')
      setHarvestSecret('')
      toast('收割邮箱已保存（凭据不回显）。')
      await refresh()
    } catch (err) {
      toast('保存收割邮箱失败：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setBusy(false)
    }
  }

  const registerExperiment = async () => {
    setBusy(true)
    try {
      const res = await api.post<{ items: Mailbox[]; is_demo: boolean }>(
        '/api/v1/mailboxes/experiment/register', { count: regCount })
      toast(`已注册 ${res.items.length} 个实验邮箱${res.is_demo ? '（演示平台合成账号）' : ''}。`)
      await refresh()
    } catch (err) {
      toast('注册实验邮箱失败：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setBusy(false)
    }
  }

  const disableMailbox = async (id: string) => {
    setBusy(true)
    try {
      await api.delete(`/api/v1/mailboxes/${id}`)
      toast('邮箱已停用。')
      await refresh()
    } catch (err) {
      toast('停用失败：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setBusy(false)
    }
  }

  const pollScores = async () => {
    setBusy(true)
    try {
      const res = await api.post<{ polled: number; updated: number; still_unknown: number; errors: number }>(
        '/api/v1/submissions/poll', {})
      toast(`评分轮询：检查 ${res.polled}，拉回 ${res.updated}，仍未知 ${res.still_unknown}，错误 ${res.errors}。`)
      await refresh()
    } catch (err) {
      toast('轮询失败：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setBusy(false)
    }
  }

  const harvestSubmit = async () => {
    if (!confirming) return
    setBusy(true)
    try {
      await api.post('/api/v1/harvest/submit', {
        submission_id: confirming.id,
        operation_id: `harvest-${crypto.randomUUID()}`,
        confirm: true,
      })
      toast('收割提交已受理。')
      setConfirming(null)
      await refresh()
    } catch (err) {
      toast('收割提交失败：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setBusy(false)
    }
  }

  const submitExperiment = async () => {
    if (!currentRun) return
    setBusy(true)
    try {
      // 留空包路径时带当前 Trial：后端在该 Trial 目录找 result_package.json
      await api.post(`/api/v1/runs/${currentRun.id}/submissions`, {
        package_path: pkgPath.trim() || undefined,
        trial_id: pkgPath.trim() ? undefined : (currentTrialId ?? undefined),
        operation_id: `sub-${crypto.randomUUID()}`,
        allow_proxy_evidence: allowProxyEvidence,
        allow_indeterminate_admission: allowIndeterminateAdmission,
      })
      toast('实验提交已受理。')
      await refresh()
    } catch (err) {
      toast('实验提交失败：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setBusy(false)
    }
  }

  const harvest = mailboxes?.items.find((m) => m.role === 'harvest' && m.status !== 'disabled')
  const experiments = mailboxes?.items.filter((m) => m.role === 'experiment') ?? []
  const best = candidates[0] ?? null

  return (
    <section aria-label="邮箱与提交">
      <div className="page-head">
        <div>
          <div className="eyebrow">MAILBOX / SUBMISSION</div>
          <h1>邮箱与提交</h1>
          <p className="sub">
            实验与收割邮箱均按题目分别计数（每邮箱每题限 {mailboxes?.items[0]?.submission_limit ?? 10} 次）。
            {mailboxes?.platform_is_demo && ' 当前为演示平台，账号与提交均为本地合成。'}
          </p>
        </div>
      </div>

      <div className="mailbox-grid">
        <article className="card">
          <div className="card-head">
            <h2>评分轮询任务</h2>
            <Badge tone="blue">{pollingTasks.filter((t) => t.enabled).length} 启用</Badge>
          </div>
          <div className="card-body">
            {pollingTasks.length === 0 ? (
              <p className="small-text">尚无评分轮询任务：有提交记录的题目会出现在这里。</p>
            ) : (
              <ul className="plain-list">
                {pollingTasks.map((t) => (
                  <li key={t.challenge_id}>
                    <div className="meta-row">
                      <span>
                        {t.title}
                        <span className="small-text">（待评分 {t.pending}）</span>
                      </span>
                      <span>
                        <Badge tone={t.enabled ? 'green' : 'neutral'}>
                          {t.enabled ? '轮询中' : '已中断'}
                        </Badge>
                        <button type="button" className="btn" style={{ marginLeft: 8 }}
                          disabled={busy} onClick={() => void togglePolling(t)}>
                          {t.enabled ? '中断' : '启用'}
                        </button>
                        <button type="button" className="btn" style={{ marginLeft: 8 }}
                          disabled={busy} onClick={() => void runPollingNow(t)}>
                          立即轮询
                        </button>
                      </span>
                    </div>
                    <div className="small-text">
                      {t.last_poll_at
                        ? `上次轮询 ${new Date(t.last_poll_at).toLocaleString()}`
                          + (t.last_result
                            ? ` · 更新 ${t.last_result.updated} 条 · 错误 ${t.last_result.errors} 条`
                            : '')
                        : '尚未轮询'}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </article>

        <article className="card">
          <div className="card-head">
            <h2>收割邮箱</h2>
            {harvest
              ? <Badge tone="green">已配置</Badge>
              : <Badge tone="amber">未配置</Badge>}
          </div>
          <div className="card-body">
            {harvest ? (
              <>
                <div className="meta-row"><span>邮箱</span><span>{harvest.email}</span></div>
                <div className="meta-row"><span>凭据</span><span>{harvest.secret_configured ? '已配置' : '缺失'}</span></div>
                <div className="actions" style={{ marginTop: 10 }}>
                  <button type="button" className="btn" disabled={busy}
                    onClick={() => void disableMailbox(harvest.id)}>
                    停用（更换邮箱）
                  </button>
                </div>
              </>
            ) : (
              <>
                <p className="sub">由你提供，只有一个。只在你手动确认时提交最高分现成包。</p>
                <label htmlFor="harvest-email">邮箱地址</label>
                <input id="harvest-email" value={harvestEmail}
                  onChange={(e) => setHarvestEmail(e.target.value)}
                  placeholder="you@example.com" />
                <label htmlFor="harvest-secret">凭据（保存后不回显）</label>
                <input id="harvest-secret" type="password" value={harvestSecret}
                  onChange={(e) => setHarvestSecret(e.target.value)} />
                <div className="actions" style={{ marginTop: 10 }}>
                  <button type="button" className="btn primary" disabled={busy || !harvestEmail || !harvestSecret}
                    onClick={() => void addHarvest()}>
                    保存收割邮箱
                  </button>
                </div>
              </>
            )}
          </div>
        </article>

        <article className="card">
          <div className="card-head">
            <h2>实验邮箱</h2>
            <Badge tone="blue">{experiments.filter((m) => m.status === 'active').length} 可用</Badge>
          </div>
          <div className="card-body">
            <div className="actions" style={{ marginBottom: 10 }}>
              <input type="number" min={1} max={20} value={regCount}
                style={{ width: 64 }}
                onChange={(e) => setRegCount(Number(e.target.value) || 1)} />
              <button type="button" className="btn" disabled={busy}
                onClick={() => void registerExperiment()}>
                批量注册
              </button>
            </div>
            {experiments.length === 0 ? (
              <p className="small-text">尚无实验邮箱。</p>
            ) : (
              <ul className="plain-list">
                {experiments.map((m) => (
                  <li key={m.id} className="meta-row">
                    <span>
                      {m.email}
                      {m.is_demo ? '（演示）' : ''}
                    </span>
                    <span>
                      {STATUS_LABEL[m.status] ?? m.status}
                      {m.status !== 'disabled' && (
                        <button type="button" className="btn" style={{ marginLeft: 8 }}
                          disabled={busy} onClick={() => void disableMailbox(m.id)}>
                          停用
                        </button>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </article>

        <article className="card">
          <div className="card-head"><h2>题目 × 邮箱用量</h2></div>
          <div className="card-body">
            {usage.length === 0 ? <p className="small-text">尚无额度预留。</p> : (
              <table aria-label="题目邮箱用量"><thead><tr>
                <th>题目</th><th>邮箱</th><th>角色</th><th>已用 / 上限</th>
              </tr></thead><tbody>{usage.map((item) => (
                <tr key={`${item.platform_challenge_id}:${item.mailbox_id}`}>
                  <td>{item.challenge_title} ({item.platform_challenge_id})</td>
                  <td>{item.email}</td><td>{ROLE_LABEL[item.role]}</td>
                  <td>{item.used} / {item.limit}</td>
                </tr>
              ))}</tbody></table>
            )}
          </div>
        </article>

        <article className="card">
          <div className="card-head">
            <h2>收割候选</h2>
            <Badge tone={best ? 'purple' : 'neutral'}>{best ? `最高 ${best.score}` : '无已知得分'}</Badge>
          </div>
          <div className="card-body">
            {best ? (
              <>
                <p className="sub">最高分现成包（实验邮箱已提交验证）：</p>
                <div className="meta-row"><span>得分</span><span>{best.score}</span></div>
                <div className="meta-row"><span>提交邮箱</span><span>{best.mailbox_email}</span></div>
                <div className="meta-row"><span>包哈希</span><span>{best.package_sha256.slice(0, 16)}…</span></div>
                <div className="actions" style={{ marginTop: 10 }}>
                  <button type="button" className="btn primary"
                    disabled={busy || !harvest}
                    title={harvest ? '' : '先配置收割邮箱'}
                    onClick={() => setConfirming(best)}>
                    用收割邮箱提交此包
                  </button>
                </div>
              </>
            ) : (
              <p className="small-text">
                尚无可收割候选：需要实验邮箱已提交且平台已给出得分的包。
                {submissions.some((s) => s.score_status !== 'scored') && ' 有提交尚未出分，可轮询评分。'}
              </p>
            )}
            <div className="actions" style={{ marginTop: 10 }}>
              <button type="button" className="btn" disabled={busy} onClick={() => void pollScores()}>
                轮询评分
              </button>
            </div>
          </div>
        </article>

        <article className="card">
          <div className="card-head">
            <h2>提交记录</h2>
            {demoMode && <Badge tone="demo">演示模式</Badge>}
          </div>
          <div className="card-body">
            {currentRun && (
              <div className="field" style={{ marginBottom: 10 }}>
                <label htmlFor="pkg-path">提交现成包（实验邮箱，消耗提交授权）</label>
                <div className="actions">
                  <input
                    id="pkg-path"
                    type="text"
                    style={{ flex: 1 }}
                    placeholder="工作区相对路径，留空优先取 Trial 目录下 result_package.zip"
                    value={pkgPath}
                    onChange={(e) => setPkgPath(e.target.value)}
                  />
                  <button type="button" className="btn primary"
                    disabled={busy}
                    onClick={() => void submitExperiment()}>
                    提交
                  </button>
                </div>
                <div className="field checkbox">
                  <input id="allow-proxy-evidence" type="checkbox" checked={allowProxyEvidence}
                    onChange={(e) => setAllowProxyEvidence(e.target.checked)} />
                  <label htmlFor="allow-proxy-evidence">明确允许代理证据提交（未用到题目官方公开数据）</label>
                </div>
                <div className="field checkbox">
                  <input id="allow-indeterminate-admission" type="checkbox" checked={allowIndeterminateAdmission}
                    onChange={(e) => setAllowIndeterminateAdmission(e.target.checked)} />
                  <label htmlFor="allow-indeterminate-admission">明确允许本地轨迹准入未知时继续</label>
                </div>
                {!pkgPath.trim() && (
                  <p className="small-text">
                    {currentTrialId
                      ? `留空优先提交当前 Trial（${currentTrialId}）目录下的 result_package.zip，兼容 JSON/CSV`
                      : '当前 Run 无活跃 Trial；请填写提交包的工作区相对路径'}
                  </p>
                )}
              </div>
            )}
            {!currentRun ? (
              <p className="small-text">尚无 Run。</p>
            ) : submissions.length === 0 ? (
              <p className="small-text">当前 Run（{currentRun.id}）尚无提交记录。</p>
            ) : (
              <ul className="plain-list">
                {submissions.map((s) => (
                  <li key={s.id} className="meta-row">
                    <span>
                      {s.is_harvest ? '收割' : '实验'} · {s.mailbox_email ?? s.mailbox_id}
                    </span>
                    <span>
                      {SUBMISSION_STATUS_LABELS[s.status] ?? s.status} · 分数 {scoreText(s)}
                      {s.score_status === 'scored' && ` · ${s.score_confidence === 'confirmed' ? '已确认' : '暂定'}`}
                      {s.score_anomaly && ` · 异常 ${s.score_anomaly}`}
                      {s.scorecard_consistent === 0 && ' · 分项不一致'}
                      {s.scorecard_consistent === 1 && ' · 分项一致'}
                      {s.error ? ` · ${s.error.slice(0, 60)}` : ''}
                      {s.platform_ref && <div className="small-text">Attempt {s.platform_ref}</div>}
                      {s.platform_feedback && Object.keys(s.platform_feedback).length > 0 && (
                        <details>
                          <summary>平台回执与评分详情</summary>
                          <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxWidth: '70ch' }}>
                            {JSON.stringify(s.platform_feedback, null, 2)}
                          </pre>
                        </details>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </article>
      </div>

      <Modal open={confirming !== null} onClose={() => setConfirming(null)}
        title="确认收割提交">
        {confirming && (
          <>
            <p>
              将用收割邮箱 <b>{harvest?.email}</b> 提交以下现成包。
              该包此前已由实验邮箱 {confirming.mailbox_email} 提交并获得官方得分
              <b> {confirming.score}</b>。
            </p>
            <div className="meta-row"><span>包路径</span><span>{confirming.package_path}</span></div>
            <div className="meta-row"><span>包哈希</span><span>{confirming.package_sha256.slice(0, 24)}…</span></div>
            <div className="actions" style={{ marginTop: 12 }}>
              <button type="button" className="btn primary" disabled={busy}
                onClick={() => void harvestSubmit()}>
                确认提交
              </button>
              <button type="button" className="btn" onClick={() => setConfirming(null)}>
                取消
              </button>
            </div>
          </>
        )}
      </Modal>
    </section>
  )
}
