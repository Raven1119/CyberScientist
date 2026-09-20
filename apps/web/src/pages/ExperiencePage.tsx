import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import { useApp } from '../app-context'
import { Badge, Modal } from '../components'
import {
  EVIDENCE_LABELS,
  formatTime,
  KIND_LABELS,
  shortHash,
  STATUS_LABELS,
} from '../labels'
import type {
  ExperienceDetail,
  ExperienceFrontmatter,
  ExperienceItem,
  ExperienceRevision,
  RevisionConflictDetails,
} from '../types'

type ScopeFilter = 'all' | 'global' | 'challenge'

const EMPTY_FRONTMATTER: ExperienceFrontmatter = {
  id: '',
  title: '',
  scope: 'global',
  challenge_id: null,
  status: 'candidate',
  evidence_status: 'hypothesis',
  kind: 'heuristic',
  tags: [],
  applicability: '',
  evidence_refs: [],
  expires_at: null,
}

interface ConflictState {
  details: RevisionConflictDetails
  yourFrontmatter: ExperienceFrontmatter
  yourBody: string
  reason: string
}

interface CurationStatus {
  state?: 'running' | 'done' | 'failed'
  summary?: string
  proposals_applied?: number
  error?: string
  finished_at?: string
}

export default function ExperiencePage() {
  const { toast, currentChallengeId } = useApp()
  const [items, setItems] = useState<ExperienceItem[]>([])
  const [pendingItems, setPendingItems] = useState<ExperienceItem[]>([])
  const [loadErrors, setLoadErrors] = useState<{ file: string; error: string }[]>([])
  const [filter, setFilter] = useState<ScopeFilter>('all')
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<ExperienceDetail | null>(null)
  const [frontmatter, setFrontmatter] = useState<ExperienceFrontmatter>(EMPTY_FRONTMATTER)
  const [body, setBody] = useState('')
  const [reason, setReason] = useState('')
  const [creating, setCreating] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [conflict, setConflict] = useState<ConflictState | null>(null)
  const [busy, setBusy] = useState(false)
  const [rejectTarget, setRejectTarget] = useState<ExperienceItem | null>(null)
  const [rejectNote, setRejectNote] = useState('')
  const [curateOpen, setCurateOpen] = useState(false)
  const [challengeOptions, setChallengeOptions] = useState<{ id: string; title: string }[]>([])
  const [curateSelection, setCurateSelection] = useState<string[]>([])
  const [curating, setCurating] = useState(false)
  const [curationResult, setCurationResult] = useState<CurationStatus | null>(null)
  const pollTimer = useRef<number | null>(null)

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams()
      if (filter === 'challenge' && currentChallengeId) {
        params.set('scope', 'challenge')
        params.set('challenge_id', currentChallengeId)
      } else if (filter === 'global') {
        params.set('scope', 'global')
      }
      const mainReq = api.get<{ items: ExperienceItem[]; errors?: { file: string; error: string }[] }>(
        `/api/v1/experiences?${params.toString()}`,
      )
      // 待审批队列固定看全局 candidate，不随列表筛选变化；筛选为全局时复用同一请求
      const pendingReq =
        filter === 'global'
          ? mainReq
          : api.get<{ items: ExperienceItem[]; errors?: { file: string; error: string }[] }>(
              '/api/v1/experiences?scope=global',
            )
      const [data, pendingData] = await Promise.all([mainReq, pendingReq])
      setItems(data.items)
      setLoadErrors(data.errors ?? [])
      setPendingItems(pendingData.items.filter((e) => e.status === 'candidate'))
    } catch (err) {
      toast('加载经验失败：' + (err instanceof Error ? err.message : String(err)))
    }
  }, [filter, currentChallengeId, toast])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!selectedId && items.length) setSelectedId(items[0].id)
  }, [items, selectedId])

  const loadDetail = useCallback(async (id: string) => {
    try {
      const d = await api.get<ExperienceDetail>(`/api/v1/experiences/${id}`)
      setDetail(d)
      setFrontmatter({ ...EMPTY_FRONTMATTER, ...d.frontmatter })
      setBody(d.body_md)
      setReason('')
      setCreating(false)
    } catch (err) {
      toast('加载经验详情失败：' + (err instanceof Error ? err.message : String(err)))
    }
  }, [toast])

  useEffect(() => {
    if (selectedId) void loadDetail(selectedId)
    else {
      setDetail(null)
      setFrontmatter(EMPTY_FRONTMATTER)
      setBody('')
    }
  }, [selectedId, loadDetail])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return items.filter((e) => {
      if (!q) return true
      return (
        e.title.toLowerCase().includes(q) ||
        e.id.toLowerCase().includes(q) ||
        e.tags.some((t) => t.toLowerCase().includes(q))
      )
    })
  }, [items, search])

  async function approve(exp: ExperienceItem) {
    try {
      await api.post(`/api/v1/experiences/${exp.id}/approve`)
      toast(`已批准「${exp.title}」，经验已启用。`)
      void load()
    } catch (err) {
      toast('批准失败：' + (err instanceof Error ? err.message : String(err)))
    }
  }

  async function confirmReject() {
    if (!rejectTarget) return
    const note = rejectNote.trim()
    if (!note) {
      toast('请填写驳回批注。')
      return
    }
    try {
      await api.post(`/api/v1/experiences/${rejectTarget.id}/reject`, { note })
      toast('已驳回，批注已记录。')
      setRejectTarget(null)
      setRejectNote('')
      void load()
    } catch (err) {
      toast('驳回失败：' + (err instanceof Error ? err.message : String(err)))
    }
  }

  function stopCurationPolling() {
    if (pollTimer.current !== null) {
      window.clearTimeout(pollTimer.current)
      pollTimer.current = null
    }
  }

  useEffect(() => stopCurationPolling, [])

  async function pollCuration() {
    try {
      const st = await api.get<CurationStatus>('/api/v1/experiences/curate_global')
      if (st.state === 'done' || st.state === 'failed') {
        setCurating(false)
        setCurationResult(st)
        void load()
        return
      }
    } catch {
      // 状态查询失败时继续轮询
    }
    pollTimer.current = window.setTimeout(() => void pollCuration(), 3000)
  }

  function beginCurationPolling() {
    stopCurationPolling()
    setCurating(true)
    setCurationResult(null)
    pollTimer.current = window.setTimeout(() => void pollCuration(), 3000)
  }

  async function openCurate() {
    setCurateOpen(true)
    try {
      const data = await api.get<{ items: { id: string; title: string }[] }>('/api/v1/challenges')
      setChallengeOptions(data.items)
    } catch {
      const ids = Array.from(
        new Set(
          items
            .filter((e) => e.scope === 'challenge' && e.challenge_id)
            .map((e) => e.challenge_id as string),
        ),
      )
      setChallengeOptions(ids.map((id) => ({ id, title: id })))
    }
  }

  async function startCuration() {
    try {
      await api.post('/api/v1/experiences/curate_global', { challenge_ids: curateSelection })
      setCurateOpen(false)
      beginCurationPolling()
    } catch (err) {
      if (err instanceof ApiError && err.code === 'CURATION_RUNNING') {
        setCurateOpen(false)
        beginCurationPolling()
        toast('已有整理任务进行中，等待其完成。')
        return
      }
      toast('启动整理失败：' + (err instanceof Error ? err.message : String(err)))
    }
  }

  async function save(baseHash?: string, fmOverride?: ExperienceFrontmatter) {
    const fmToSave = fmOverride ?? frontmatter
    if (creating) {
      await create(fmToSave)
      return
    }
    if (!detail) return
    setBusy(true)
    try {
      await api.put(`/api/v1/experiences/${detail.id}`, {
        frontmatter: fmToSave,
        body_md: body,
        base_hash: baseHash ?? detail.current_hash,
        reason: reason.trim() || undefined,
      })
      toast('已保存，下一轮实验生效。')
      await loadDetail(detail.id)
      void load()
    } catch (err) {
      handleSaveError(err)
    } finally {
      setBusy(false)
    }
  }

  async function create(fmToSave: ExperienceFrontmatter) {
    setBusy(true)
    try {
      const fm = { ...fmToSave }
      if (!fm.id.trim()) {
        toast('新经验需要填写 ID。')
        return
      }
      await api.post('/api/v1/experiences', {
        id: fm.id.trim(),
        frontmatter: fm,
        body_md: body,
        reason: reason.trim() || undefined,
      })
      toast('已创建，下一轮实验生效。')
      setCreating(false)
      setSelectedId(fm.id.trim())
      void load()
    } catch (err) {
      handleSaveError(err)
    } finally {
      setBusy(false)
    }
  }

  function handleSaveError(err: unknown) {
    if (err instanceof ApiError && err.code === 'REVISION_CONFLICT') {
      const details = err.details as RevisionConflictDetails | undefined
      if (details) {
        setConflict({ details, yourFrontmatter: frontmatter, yourBody: body, reason: reason.trim() })
        return
      }
    }
    toast('保存失败：' + (err instanceof Error ? err.message : String(err)))
  }

  async function restore(revision: ExperienceRevision) {
    if (!detail) return
    setBusy(true)
    try {
      await api.post(`/api/v1/experiences/${detail.id}/restore`, {
        revision_hash: revision.revision_hash,
        reason: `回滚到 ${shortHash(revision.revision_hash)}`,
      })
      toast('已回滚为新修订，原修订仍保留。')
      setHistoryOpen(false)
      await loadDetail(detail.id)
      void load()
    } catch (err) {
      toast('回滚失败：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setBusy(false)
    }
  }

  function startCreate() {
    setCreating(true)
    setSelectedId(null)
    setDetail(null)
    setFrontmatter({
      ...EMPTY_FRONTMATTER,
      id: `EXP_${Date.now().toString(36).toUpperCase()}`,
      challenge_id: filter === 'challenge' ? currentChallengeId : null,
      scope: filter === 'challenge' && currentChallengeId ? 'challenge' : 'global',
    })
    setBody('## 建议\n\n\n\n## 证据\n\n\n\n## 适用边界\n\n')
    setReason('')
  }

  const fm = frontmatter

  return (
    <section aria-label="经验库">
      <div className="page-head">
        <div>
          <div className="eyebrow">MEMORY / EDITABLE & VERSIONED</div>
          <h1>经验库</h1>
          <p className="sub">可以编辑判断，但不覆盖过去的证据。</p>
        </div>
        <div className="actions">
          <button
            type="button"
            className="btn"
            disabled={curating}
            onClick={() => void openCurate()}
          >
            {curating ? '整理中…' : '整理全局经验'}
          </button>
          <button type="button" className="btn" onClick={() => void load()}>
            刷新
          </button>
          <button type="button" className="btn primary" onClick={startCreate}>
            新建经验
          </button>
        </div>
      </div>

      {curationResult && (
        <div
          className={`callout${curationResult.state === 'failed' ? ' danger' : ''}`}
          style={{ marginBottom: 14 }}
        >
          {curationResult.state === 'done' ? (
            <span>
              整理完成：{curationResult.summary || '（无摘要）'} · 应用提议{' '}
              {curationResult.proposals_applied ?? 0} 条
            </span>
          ) : (
            <span>整理失败：{curationResult.error || '未知错误'}</span>
          )}
          <button type="button" className="btn small" onClick={() => setCurationResult(null)}>
            知道了
          </button>
        </div>
      )}

      {pendingItems.length > 0 && (
        <article className="card" style={{ marginBottom: 16 }}>
          <div className="card-head">
            <h2>待审批的全局经验（{pendingItems.length}）</h2>
          </div>
          <div className="card-body">
            <ul className="plain-list">
              {pendingItems.map((e) => (
                <li key={e.id} className="row-item block">
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      gap: 12,
                      flexWrap: 'wrap',
                    }}
                  >
                    <div>
                      <strong>{e.title}</strong>
                      <span className="small-text" style={{ marginLeft: 8 }}>
                        {KIND_LABELS[e.kind] ?? e.kind} ·{' '}
                        {EVIDENCE_LABELS[e.evidence_status] ?? e.evidence_status} · 更新{' '}
                        {formatTime(e.updated_at)}
                      </span>
                    </div>
                    <div className="actions">
                      <button
                        type="button"
                        className="btn small primary"
                        onClick={() => void approve(e)}
                      >
                        批准
                      </button>
                      <button type="button" className="btn small" onClick={() => setRejectTarget(e)}>
                        驳回
                      </button>
                    </div>
                  </div>
                  {e.review_note && (
                    <p className="small-text" style={{ margin: '6px 0 0' }}>
                      上次驳回批注：{e.review_note}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </div>
        </article>
      )}

      <div className="exp-grid">
        <article className="card">
          <div className="card-body">
            <label htmlFor="exp-search">检索标题、ID 或标签</label>
            <input
              className="search"
              id="exp-search"
              placeholder="搜索经验…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <div className="filter" aria-label="经验作用域">
              <button type="button" className={filter === 'all' ? 'active' : ''} onClick={() => setFilter('all')}>
                全部
              </button>
              <button type="button" className={filter === 'global' ? 'active' : ''} onClick={() => setFilter('global')}>
                全局
              </button>
              <button
                type="button"
                className={filter === 'challenge' ? 'active' : ''}
                onClick={() => setFilter('challenge')}
                disabled={!currentChallengeId}
                title={currentChallengeId ? undefined : '研究工作台尚未选择题目'}
              >
                当前题目
              </button>
            </div>
          </div>
          <div className="exp-list">
            {filtered.length === 0 && <p className="small-text pad">没有匹配的经验。</p>}
            {filtered.map((e) => (
              <button
                key={e.id}
                type="button"
                className={`exp-item ${selectedId === e.id && !creating ? 'selected' : ''}`}
                onClick={() => {
                  setCreating(false)
                  setSelectedId(e.id)
                }}
              >
                <span className="exp-item-badges">
                  <Badge tone={e.scope === 'global' ? 'blue' : 'green'}>
                    {e.scope === 'global' ? '全局' : '题目内'}
                  </Badge>
                  <Badge tone={e.status === 'active' ? 'green' : e.status === 'retired' ? 'neutral' : 'amber'}>
                    {STATUS_LABELS[e.status] ?? e.status}
                  </Badge>
                  <Badge
                    tone={
                      e.evidence_status === 'validated'
                        ? 'green'
                        : e.evidence_status === 'contradicted'
                          ? 'danger'
                          : 'blue'
                    }
                  >
                    {EVIDENCE_LABELS[e.evidence_status] ?? e.evidence_status}
                  </Badge>
                  {e.status === 'candidate' && e.review_note && (
                    <Badge tone="danger">有驳回批注</Badge>
                  )}
                </span>
                <strong>{e.title}</strong>
                <small>
                  {e.id} · {KIND_LABELS[e.kind] ?? e.kind} · 更新 {formatTime(e.updated_at)}
                </small>
              </button>
            ))}
          </div>
          {loadErrors.length > 0 && (
            <div className="callout danger">
              {loadErrors.map((e, i) => (
                <div key={i} className="small-text">
                  {e.file}：{e.error}
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="card">
          <div className="card-head">
            <h2>{creating ? '新建经验' : '编辑经验'}</h2>
            <div className="actions">
              {detail && (
                <Badge tone="neutral">当前 hash {shortHash(detail.current_hash)}</Badge>
              )}
              {detail && (
                <button type="button" className="btn" onClick={() => setHistoryOpen(true)}>
                  修订历史
                </button>
              )}
            </div>
          </div>
          <div className="card-body">
            <div className="fields triple">
              <div className="field">
                <label htmlFor="exp-id">ID</label>
                <input
                  id="exp-id"
                  value={fm.id}
                  disabled={!creating}
                  onChange={(e) => setFrontmatter({ ...fm, id: e.target.value })}
                />
              </div>
              <div className="field">
                <label htmlFor="exp-title">标题</label>
                <input
                  id="exp-title"
                  value={fm.title}
                  onChange={(e) => setFrontmatter({ ...fm, title: e.target.value })}
                />
              </div>
              <div className="field">
                <label htmlFor="exp-scope">作用域</label>
                <select
                  id="exp-scope"
                  value={fm.scope}
                  onChange={(e) => setFrontmatter({ ...fm, scope: e.target.value as 'global' | 'challenge' })}
                >
                  <option value="global">全局</option>
                  <option value="challenge">当前题目</option>
                </select>
              </div>
              {fm.scope === 'challenge' && (
                <div className="field">
                  <label htmlFor="exp-challenge">challenge_id</label>
                  <input
                    id="exp-challenge"
                    value={fm.challenge_id ?? ''}
                    placeholder={currentChallengeId ?? '题目 ID'}
                    onChange={(e) => setFrontmatter({ ...fm, challenge_id: e.target.value || null })}
                  />
                </div>
              )}
              <div className="field">
                <label htmlFor="exp-status">使用状态</label>
                <select
                  id="exp-status"
                  value={fm.status}
                  onChange={(e) =>
                    setFrontmatter({ ...fm, status: e.target.value as ExperienceFrontmatter['status'] })
                  }
                >
                  <option value="candidate">候选</option>
                  <option value="active">启用</option>
                  <option value="retired">停用</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="exp-evidence">证据状态</label>
                <select
                  id="exp-evidence"
                  value={fm.evidence_status}
                  onChange={(e) =>
                    setFrontmatter({
                      ...fm,
                      evidence_status: e.target.value as ExperienceFrontmatter['evidence_status'],
                    })
                  }
                >
                  <option value="hypothesis">假设</option>
                  <option value="observed">已观察</option>
                  <option value="validated">已验证</option>
                  <option value="contradicted">已被否定</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="exp-kind">类型</label>
                <select
                  id="exp-kind"
                  value={fm.kind}
                  onChange={(e) => setFrontmatter({ ...fm, kind: e.target.value as ExperienceFrontmatter['kind'] })}
                >
                  <option value="heuristic">启发式</option>
                  <option value="procedure">流程</option>
                  <option value="failure">失败模式</option>
                  <option value="platform">平台</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="exp-tags">标签（逗号分隔）</label>
                <input
                  id="exp-tags"
                  value={fm.tags.join(', ')}
                  onChange={(e) =>
                    setFrontmatter({
                      ...fm,
                      tags: e.target.value
                        .split(/[,，]/)
                        .map((s) => s.trim())
                        .filter(Boolean),
                    })
                  }
                />
              </div>
              <div className="field">
                <label htmlFor="exp-applicability">适用条件</label>
                <input
                  id="exp-applicability"
                  value={fm.applicability}
                  onChange={(e) => setFrontmatter({ ...fm, applicability: e.target.value })}
                />
              </div>
              <div className="field">
                <label htmlFor="exp-expires">过期时间（ISO，可空）</label>
                <input
                  id="exp-expires"
                  value={fm.expires_at ?? ''}
                  placeholder="例如 2027-01-01T00:00:00Z"
                  onChange={(e) => setFrontmatter({ ...fm, expires_at: e.target.value || null })}
                />
              </div>
            </div>
            <div className="field">
              <label htmlFor="exp-evidence-refs">证据引用（每行一个）</label>
              <textarea
                id="exp-evidence-refs"
                className="editor"
                rows={2}
                value={fm.evidence_refs.join('\n')}
                onChange={(e) =>
                  setFrontmatter({
                    ...fm,
                    evidence_refs: e.target.value
                      .split('\n')
                      .map((s) => s.trim())
                      .filter(Boolean),
                  })
                }
                spellCheck={false}
              />
            </div>
            <label htmlFor="exp-body">Markdown 正文</label>
            <textarea
              id="exp-body"
              className="editor editor-tall"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              spellCheck={false}
            />
            <div className="field" style={{ marginTop: 10 }}>
              <label htmlFor="exp-reason">修改原因（可选）</label>
              <input
                id="exp-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </div>
            <div className="editor-foot">
              <span className="inline-note">保存为新修订，下一轮生效；本轮 Run 的经验快照保持不变。</span>
              <div className="actions">
                {!creating && detail && fm.status !== 'retired' && (
                  <button
                    type="button"
                    className="btn"
                    disabled={busy}
                    onClick={() => {
                      setFrontmatter({ ...fm, status: 'retired' })
                      setReason(reason || '停用')
                      void save(undefined, { ...fm, status: 'retired' })
                    }}
                  >
                    停用
                  </button>
                )}
                <button
                  type="button"
                  className="btn primary"
                  disabled={busy || !fm.title.trim() || !body.trim() || (!creating && !detail)}
                  onClick={() => void save()}
                >
                  {busy ? '保存中…' : creating ? '创建' : '保存新修订'}
                </button>
              </div>
            </div>
          </div>
        </article>
      </div>

      <Modal open={historyOpen} onClose={() => setHistoryOpen(false)} title="修订历史" wide>
        {!detail || detail.revisions.length === 0 ? (
          <p className="sub">暂无修订记录。</p>
        ) : (
          <ul className="plain-list">
            {detail.revisions.map((r) => (
              <li key={r.revision_hash} className="row-item">
                <div>
                  <code>{shortHash(r.revision_hash)}</code>
                  <span className="small-text" style={{ marginLeft: 8 }}>
                    {r.operator} · {formatTime(r.created_at)}
                    {r.reason && ` · ${r.reason}`}
                  </span>
                </div>
                <button type="button" className="btn small" disabled={busy} onClick={() => void restore(r)}>
                  回滚为新修订
                </button>
              </li>
            ))}
          </ul>
        )}
        <p className="inline-note">回滚会创建新修订，原有修订仍保留。</p>
      </Modal>

      <Modal
        open={rejectTarget !== null}
        onClose={() => setRejectTarget(null)}
        title={`驳回：${rejectTarget?.title ?? ''}`}
      >
        <div className="field">
          <label htmlFor="reject-note">驳回批注（必填，大脑下轮整理时会参考）</label>
          <textarea
            id="reject-note"
            className="editor"
            rows={4}
            value={rejectNote}
            onChange={(e) => setRejectNote(e.target.value)}
            placeholder="说明为什么不采纳这条经验…"
          />
        </div>
        <div className="modal-actions">
          <button type="button" className="btn" onClick={() => setRejectTarget(null)}>
            取消
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={!rejectNote.trim()}
            onClick={() => void confirmReject()}
          >
            确认驳回
          </button>
        </div>
      </Modal>

      <Modal open={curateOpen} onClose={() => setCurateOpen(false)} title="整理全局经验">
        <p className="sub">
          选择要纳入整理素材的题目（可全不选，只整理全局经验）。大脑将阅读全局条目（含待审批与驳回批注）
          与入选题目的题内经验，产出仍落候选，需你审批后启用。
        </p>
        {challengeOptions.length === 0 ? (
          <p className="small-text">暂无已导入的题目，将只整理全局经验。</p>
        ) : (
          <ul className="plain-list">
            {challengeOptions.map((c) => (
              <li key={c.id} className="row-item">
                <div className="field checkbox" style={{ margin: 0 }}>
                  <input
                    id={`curate-ch-${c.id}`}
                    type="checkbox"
                    checked={curateSelection.includes(c.id)}
                    onChange={(e) =>
                      setCurateSelection(
                        e.target.checked
                          ? [...curateSelection, c.id]
                          : curateSelection.filter((id) => id !== c.id),
                      )
                    }
                  />
                  <label htmlFor={`curate-ch-${c.id}`}>
                    {c.title}（{c.id}）
                  </label>
                </div>
              </li>
            ))}
          </ul>
        )}
        <div className="modal-actions">
          <button type="button" className="btn" onClick={() => setCurateOpen(false)}>
            取消
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={curating}
            onClick={() => void startCuration()}
          >
            开始整理
          </button>
        </div>
      </Modal>

      <Modal
        open={conflict !== null}
        onClose={() => setConflict(null)}
        title="保存冲突：文件已被其他修改更新"
        wide
      >
        {conflict && (
          <>
            <p>
              你编辑的版本基于旧内容保存失败。请对照下方两栏内容：左边是服务器当前版本，
              右边是你的修改。两者都不会被丢弃。
            </p>
            <div className="diff-grid">
              <div>
                <label>当前版本（服务器）</label>
                <pre>{conflict.details.current_content}</pre>
              </div>
              <div>
                <label>你的修改</label>
                <pre>{conflict.details.your_content}</pre>
              </div>
            </div>
            <div className="modal-actions">
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setConflict(null)
                  if (detail) {
                    setBody(conflict.details.current_content)
                    void loadDetail(detail.id)
                  }
                }}
              >
                放弃我的修改
              </button>
              <button
                type="button"
                className="btn primary"
                disabled={busy}
                onClick={() => {
                  const c = conflict
                  setConflict(null)
                  setFrontmatter(c.yourFrontmatter)
                  setBody(c.yourBody)
                  setReason(c.reason)
                  void save(c.details.current_hash)
                }}
              >
                用当前内容重试
              </button>
            </div>
          </>
        )}
      </Modal>
    </section>
  )
}
