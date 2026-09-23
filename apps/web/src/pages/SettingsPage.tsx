import { useCallback, useEffect, useState } from 'react'
import { api, listSkills, putAlwaysOnSkills } from '../api'
import { useApp } from '../app-context'
import { Badge, LoadingState } from '../components'
import { formatTime } from '../labels'
import type {
  ConnectionTestResult,
  LlmProfile,
  ReasoningEffort,
  Settings,
  SkillInfo,
} from '../types'

type ConnId = 'brain' | 'executor' | 'prime' | 'playground' | 'bohrium'

interface ConnState {
  result?: ConnectionTestResult
  testedAt?: string
  kind?: 'inspect' | 'model_roundtrip'
  busy?: boolean
  error?: string
}

const PROTOCOLS = ['openai_chat_completions', 'openai_responses', 'anthropic_messages']

const EFFORT_OPTIONS: Record<string, { value: ReasoningEffort; label: string }[]> = {
  kimi: [
    { value: 'low', label: 'low · 快' },
    { value: 'high', label: 'high · 深（默认）' },
    { value: 'max', label: 'max · 最深' },
  ],
  codex: [
    { value: 'low', label: 'low · 快' },
    { value: 'medium', label: 'medium · 均衡' },
    { value: 'high', label: 'high · 深（默认）' },
    { value: 'xhigh', label: 'xhigh · 最深' },
  ],
}
EFFORT_OPTIONS.prime = EFFORT_OPTIONS.codex

const DEFAULT_EFFORT: ReasoningEffort = 'high'

function effortsFor(runtime: string): { value: ReasoningEffort; label: string }[] {
  return EFFORT_OPTIONS[runtime] ?? EFFORT_OPTIONS.codex
}

function normalizeEffort(runtime: string, value: ReasoningEffort): ReasoningEffort {
  return effortsFor(runtime).some((e) => e.value === value) ? value : DEFAULT_EFFORT
}

const BRAIN_MODEL_DEFAULTS: Record<string, string> = {
  kimi: 'kimi-code/k3',
  codex: 'gpt-6-astra',
}

const EXECUTOR_MODEL_DEFAULTS: Record<string, string> = {
  kimi: 'kimi-code/k3-256k',
  codex: 'gpt-5.6-terra',
}

const EXECUTOR_RUNTIME_LABELS: Record<string, string> = {
  kimi: 'Kimi Code',
  prime: 'Prime Agent',
  codex: 'Codex',
}

export default function SettingsPage() {
  const { toast } = useApp()
  const [settings, setSettings] = useState<Settings | null>(null)
  const [baseRevision, setBaseRevision] = useState(0)
  const [conns, setConns] = useState<Record<ConnId, ConnState>>({
    brain: {},
    executor: {},
    prime: {},
    playground: {},
    bohrium: {},
  })
  const [confirmSpend, setConfirmSpend] = useState<Record<ConnId, boolean>>({
    brain: false,
    executor: false,
    prime: false,
    playground: false,
    bohrium: false,
  })
  const [saving, setSaving] = useState(false)

  const reload = useCallback(async () => {
    const fresh = await api.get<Settings>('/api/v1/settings')
    setSettings(fresh)
    setBaseRevision(fresh.revision)
  }, [])

  useEffect(() => {
    reload().catch((err) => {
      if (err instanceof Error) toast('加载设置失败：' + err.message)
    })
  }, [reload, toast])

  const update = useCallback((fn: (s: Settings) => Settings) => {
    setSettings((prev) => (prev ? fn(structuredClone(prev)) : prev))
  }, [])

  async function saveSettings() {
    if (!settings) return
    setSaving(true)
    try {
      await api.put('/api/v1/settings', { settings, base_revision: baseRevision })
      toast('设置已保存。')
      await reload()
    } catch (err) {
      toast('保存设置失败：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setSaving(false)
    }
  }

  async function testConnection(id: ConnId, kind: 'inspect' | 'model_roundtrip') {
    setConns((c) => ({ ...c, [id]: { ...c[id], busy: true, error: undefined } }))
    try {
      const result = await api.post<ConnectionTestResult>(`/api/v1/connections/${id}/test`, {
        kind,
        confirm_spend: kind === 'model_roundtrip' ? confirmSpend[id] : false,
      })
      setConns((c) => ({ ...c, [id]: { result, testedAt: new Date().toISOString(), kind } }))
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      setConns((c) => ({ ...c, [id]: { ...c[id], error: message } }))
    }
  }

  async function writeSecret(secretId: string, value: string, applyRef?: (s: Settings, ref: string) => void) {
    if (!secretId.trim() || !value) {
      toast('请填写 secret_id 和密钥值。')
      return
    }
    try {
      const res = await api.post<{ secret_ref: string; configured: boolean }>('/api/v1/secrets', {
        secret_id: secretId.trim(),
        value,
      })
      toast(`密钥 ${secretId.trim()} 已保存。`)
      if (applyRef && settings) {
        // 密钥引用同步写回设置并立即落盘，连接测试/导入立即可用
        const next = structuredClone(settings)
        applyRef(next, res.secret_ref)
        await api.put('/api/v1/settings', { settings: next, base_revision: baseRevision })
      }
      await reload()
    } catch (err) {
      toast('保存密钥失败：' + (err instanceof Error ? err.message : String(err)))
    }
  }

  async function deleteSecret(secretId: string, applyRef?: (s: Settings, ref: string) => void) {
    if (!secretId.trim()) return
    try {
      await api.delete(`/api/v1/secrets/${encodeURIComponent(secretId.trim())}`)
      toast(`密钥 ${secretId.trim()} 已删除。`)
      if (applyRef && settings) {
        const next = structuredClone(settings)
        applyRef(next, '')
        await api.put('/api/v1/settings', { settings: next, base_revision: baseRevision })
      }
      await reload()
    } catch (err) {
      toast('删除密钥失败：' + (err instanceof Error ? err.message : String(err)))
    }
  }

  if (!settings) {
    return (
      <section aria-label="连接与设置">
        <div className="empty">
          <LoadingState>正在加载设置…</LoadingState>
          <p>如果长时间没有响应，请确认后端已启动。</p>
        </div>
      </section>
    )
  }

  const secretsStatus = settings._status?.secrets ?? {}

  return (
    <section aria-label="连接与设置">
      <div className="page-head">
        <div>
          <div className="eyebrow">CONNECTIONS / SEPARATE BY RESPONSIBILITY</div>
          <h1>连接与设置</h1>
          <p className="sub">大脑、执行器、模型 API、平台 API 独立配置。</p>
        </div>
        <button type="button" className="btn primary" disabled={saving} onClick={() => void saveSettings()}>
          {saving ? '保存中…' : '保存设置'}
        </button>
      </div>

      <div className="settings-stack">
        <article className="card">
          <div className="card-head">
            <div className="settings-heading">
              <span className="setting-num">01</span>
              <h2>大脑运行时</h2>
            </div>
            <HealthBadge state={conns.brain} />
          </div>
          <div className="card-body">
            <div className="meta-row">
              <span>当前运行时</span>
              <span>{settings.brain.runtime === 'kimi' ? 'Kimi Code' : 'Codex'}</span>
            </div>
            <div className="fields">
              <div className="field">
                <label htmlFor="brain-runtime">原生代理</label>
                <select
                  id="brain-runtime"
                  value={settings.brain.runtime}
                  onChange={(e) =>
                    update((s) => ({
                      ...s,
                      brain: {
                        ...s.brain,
                        runtime: e.target.value,
                        model_id: BRAIN_MODEL_DEFAULTS[e.target.value] ?? s.brain.model_id,
                        reasoning_effort: normalizeEffort(e.target.value, s.brain.reasoning_effort),
                      },
                    }))
                  }
                >
                  <option value="kimi">Kimi Code</option>
                  <option value="codex">Codex</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="brain-model">模型 ID</label>
                <input
                  id="brain-model"
                  value={settings.brain.model_id}
                  onChange={(e) => update((s) => ({ ...s, brain: { ...s.brain, model_id: e.target.value } }))}
                  placeholder={BRAIN_MODEL_DEFAULTS[settings.brain.runtime] ?? '留空使用默认'}
                />
              </div>
              <div className="field">
                <label htmlFor="brain-effort">思考强度</label>
                <select
                  id="brain-effort"
                  value={normalizeEffort(settings.brain.runtime, settings.brain.reasoning_effort)}
                  onChange={(e) =>
                    update((s) => ({
                      ...s,
                      brain: { ...s.brain, reasoning_effort: e.target.value as ReasoningEffort },
                    }))
                  }
                >
                  {effortsFor(settings.brain.runtime).map((e) => (
                    <option key={e.value} value={e.value}>
                      {e.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="brain-executable">可执行文件路径</label>
                <input
                  id="brain-executable"
                  value={settings.brain.executable}
                  onChange={(e) => update((s) => ({ ...s, brain: { ...s.brain, executable: e.target.value } }))}
                  placeholder="留空使用 PATH 中的默认命令"
                />
              </div>
            </div>
            <div className="meta-row">
              <span>认证方式</span>
              <span>{settings.brain.auth_mode === 'native' ? '使用原生 CLI 登录' : settings.brain.auth_mode}</span>
            </div>
            <ConnActions
              id="brain"
              state={conns.brain}
              confirmSpend={confirmSpend.brain}
              onConfirmSpendChange={(v) => setConfirmSpend((c) => ({ ...c, brain: v }))}
              onTest={(kind) => void testConnection('brain', kind)}
              allowRoundtrip
            />
            <HealthDetail state={conns.brain} />
          </div>
        </article>

        <article className="card">
          <div className="card-head">
            <div className="settings-heading">
              <span className="setting-num">02</span>
              <h2>执行系统</h2>
            </div>
            <div className="actions">
              {settings._status && (
                <Badge tone={settings._status.prime_models_synced ? 'green' : 'amber'}>
                  {settings._status.prime_models_synced ? 'Prime models 已同步' : 'Prime models 未同步'}
                </Badge>
              )}
              <HealthBadge state={conns.executor} />
            </div>
          </div>
          <div className="card-body">
            <div className="fields">
              <div className="field">
                <label htmlFor="executor-runtime">执行器运行时</label>
                <select
                  id="executor-runtime"
                  value={settings.executor.runtime}
                  onChange={(e) =>
                    update((s) => ({
                      ...s,
                      executor: {
                        ...s.executor,
                        runtime: e.target.value,
                        model_id: EXECUTOR_MODEL_DEFAULTS[e.target.value] ?? s.executor.model_id,
                        reasoning_effort: normalizeEffort(e.target.value, s.executor.reasoning_effort),
                      },
                    }))
                  }
                >
                  <option value="kimi">Kimi Code（默认）</option>
                  <option value="prime">Prime Agent</option>
                  <option value="codex">Codex</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="executor-model">模型 ID</label>
                <input
                  id="executor-model"
                  value={settings.executor.model_id}
                  onChange={(e) =>
                    update((s) => ({ ...s, executor: { ...s.executor, model_id: e.target.value } }))
                  }
                  placeholder={EXECUTOR_MODEL_DEFAULTS[settings.executor.runtime] ?? '留空使用默认'}
                />
              </div>
              <div className="field">
                <label htmlFor="executor-effort">思考强度</label>
                <select
                  id="executor-effort"
                  value={normalizeEffort(settings.executor.runtime, settings.executor.reasoning_effort)}
                  onChange={(e) =>
                    update((s) => ({
                      ...s,
                      executor: { ...s.executor, reasoning_effort: e.target.value as ReasoningEffort },
                    }))
                  }
                >
                  {effortsFor(settings.executor.runtime).map((e) => (
                    <option key={e.value} value={e.value}>
                      {e.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="executor-executable">可执行文件路径</label>
                <input
                  id="executor-executable"
                  value={settings.executor.executable}
                  onChange={(e) =>
                    update((s) => ({ ...s, executor: { ...s.executor, executable: e.target.value } }))
                  }
                  placeholder="留空使用 PATH 中的默认命令"
                />
              </div>
            </div>
            <div className="meta-row">
              <span>当前配置</span>
              <span>
                {EXECUTOR_RUNTIME_LABELS[settings.executor.runtime] ?? settings.executor.runtime}
                {settings.executor.model_id && ` · ${settings.executor.model_id}`}
              </span>
            </div>
            <ConnActions
              id="executor"
              state={conns.executor}
              confirmSpend={confirmSpend.executor}
              onConfirmSpendChange={(v) => setConfirmSpend((c) => ({ ...c, executor: v }))}
              onTest={(kind) => void testConnection('executor', kind)}
            />
            <HealthDetail state={conns.executor} />
            <p className="inline-note">
              连接测试按当前配置路由到所选执行器；如需 Prime 专有排障，请用下方 Prime 排障入口。
            </p>
          </div>
        </article>

        <article className="card">
          <div className="card-head">
            <div className="settings-heading">
              <span className="setting-num">03</span>
              <h2>Prime 排障</h2>
            </div>
            <HealthBadge state={conns.prime} />
          </div>
          <div className="card-body">
            <div className="fields">
              <div className="field">
                <label htmlFor="prime-executable">Prime 可执行文件路径</label>
                <input
                  id="prime-executable"
                  value={settings.prime.executable}
                  onChange={(e) => update((s) => ({ ...s, prime: { ...s.prime, executable: e.target.value } }))}
                  placeholder="留空使用 PATH 中的默认命令"
                />
              </div>
              <div className="field">
                <label htmlFor="prime-profile">默认模型 Profile</label>
                <select
                  id="prime-profile"
                  value={settings.prime.llm_profile_id}
                  onChange={(e) =>
                    update((s) => ({ ...s, prime: { ...s.prime, llm_profile_id: e.target.value } }))
                  }
                >
                  <option value="">未选择</option>
                  {settings.llm_profiles.map((p) => (
                    <option key={p.id || p.label} value={p.id}>
                      {p.label || p.id}（{p.model_id}）
                    </option>
                  ))}
                </select>
                <p className="small-text">按 Profile 的 ID 关联；UI 新建 Profile 时请填写唯一 ID。</p>
              </div>
            </div>
            <div className="actions">
              <button
                type="button"
                className="btn"
                disabled={conns.prime.busy}
                onClick={() => void testConnection('prime', 'inspect')}
              >
                检查 Prime 安装/认证
              </button>
            </div>
            <HealthDetail state={conns.prime} />
          </div>
        </article>

        <article className="card">
          <div className="card-head">
            <div className="settings-heading">
              <span className="setting-num">04</span>
              <h2>模型 Profile 列表</h2>
            </div>
            <Badge tone="neutral">{settings.llm_profiles.length} 个</Badge>
          </div>
          <div className="card-body">
            <p className="sub">执行器调模型使用的供应商配置。API Key 通过下方密钥输入写入后端，不保存在设置里。</p>
            {settings.llm_profiles.length === 0 && (
              <p className="small-text">还没有模型 Profile，点击下方“新增 Profile”。</p>
            )}
            {settings.llm_profiles.map((p, idx) => (
              <ProfileEditor
                key={idx}
                profile={p}
                onChange={(np) =>
                  update((s) => {
                    const list = [...s.llm_profiles]
                    list[idx] = np
                    return { ...s, llm_profiles: list }
                  })
                }
                onRemove={() =>
                  update((s) => ({ ...s, llm_profiles: s.llm_profiles.filter((_, i) => i !== idx) }))
                }
              />
            ))}
            <button
              type="button"
              className="btn"
              style={{ marginTop: 10 }}
              onClick={() =>
                update((s) => ({
                  ...s,
                  llm_profiles: [
                    ...s.llm_profiles,
                    { id: '', label: '', protocol: 'openai_chat_completions', base_url: '', model_id: '', secret_ref: '' },
                  ],
                }))
              }
            >
              新增 Profile
            </button>
          </div>
        </article>

        <article className="card">
          <div className="card-head">
            <div className="settings-heading">
              <span className="setting-num">05</span>
              <h2>玻尔平台</h2>
            </div>
            <HealthBadge state={conns.bohrium} />
          </div>
          <div className="card-body">
            <p className="sub">
              Playground Token 用于竞赛数据与提交；Bohrium AccessKey 用于科学计算；两者相互独立。
            </p>
            <div className="fields">
              <div className="field">
                <label htmlFor="playground-base">Playground Base URL · 题目与提交</label>
                <input
                  id="playground-base"
                  inputMode="url"
                  value={settings.playground.base_url}
                  onChange={(e) =>
                    update((s) => ({ ...s, playground: { ...s.playground, base_url: e.target.value } }))
                  }
                />
              </div>
              <SecretField
                label="Playground Token"
                secretId={(settings.playground.token_secret_ref || 'local:playground_token').replace(/^local:/, '')}
                configured={secretsStatus[(settings.playground.token_secret_ref || 'local:playground_token').replace(/^local:/, '')] ?? false}
                onSave={(sid, value) =>
                  void writeSecret(sid, value, (s, ref) => {
                    s.playground.token_secret_ref = ref
                  })
                }
                onDelete={(sid) =>
                  void deleteSecret(sid, (s) => {
                    s.playground.token_secret_ref = ''
                  })
                }
              />
            </div>
            <div className="divider" />
            <div className="fields">
              <div className="field">
                <label htmlFor="bohr-executable">bohr 可执行文件路径</label>
                <input
                  id="bohr-executable"
                  value={settings.bohrium.executable}
                  onChange={(e) =>
                    update((s) => ({ ...s, bohrium: { ...s.bohrium, executable: e.target.value } }))
                  }
                  placeholder="留空使用 PATH 中的默认命令"
                />
              </div>
              <div className="field">
                <label htmlFor="bohr-project">Bohrium 项目 ID · 科学计算</label>
                <input
                  id="bohr-project"
                  value={settings.bohrium.project_id ?? ''}
                  onChange={(e) =>
                    update((s) => ({ ...s, bohrium: { ...s.bohrium, project_id: e.target.value || null } }))
                  }
                />
              </div>
              <SecretField
                label="Bohrium AccessKey"
                secretId={(settings.bohrium.access_key_secret_ref || 'local:bohrium_access_key').replace(/^local:/, '')}
                configured={secretsStatus[(settings.bohrium.access_key_secret_ref || 'local:bohrium_access_key').replace(/^local:/, '')] ?? false}
                onSave={(sid, value) =>
                  void writeSecret(sid, value, (s, ref) => {
                    s.bohrium.access_key_secret_ref = ref
                  })
                }
                onDelete={(sid) =>
                  void deleteSecret(sid, (s) => {
                    s.bohrium.access_key_secret_ref = ''
                  })
                }
              />
              <SecretField
                label="OpenRouter API Key（执行器模型）"
                secretId="openrouter_api_key"
                configured={secretsStatus['openrouter_api_key'] ?? false}
                onSave={(sid, value) => void writeSecret(sid, value)}
                onDelete={(sid) => void deleteSecret(sid)}
              />
            </div>
            <div className="actions" style={{ marginTop: 10 }}>
              <button
                type="button"
                className="btn"
                disabled={conns.playground.busy}
                onClick={() => void testConnection('playground', 'inspect')}
              >
                检查 Playground 连接
              </button>
              <button
                type="button"
                className="btn"
                disabled={conns.bohrium.busy}
                onClick={() => void testConnection('bohrium', 'inspect')}
              >
                检查 bohr 安装
              </button>
            </div>
            {(conns.playground.result || conns.playground.error) && (
              <HealthDetail state={conns.playground} title="Playground" />
            )}
            {(conns.bohrium.result || conns.bohrium.error) && (
              <HealthDetail state={conns.bohrium} title="bohr" />
            )}
          </div>
        </article>

        <article className="card">
          <div className="card-head">
            <div className="settings-heading">
              <span className="setting-num">06</span>
              <h2>运行模式与监督</h2>
            </div>
            <Badge tone={settings.app.mode === 'demo' ? 'amber' : 'green'}>
              {settings.app.mode === 'demo' ? '演示模式' : '真实连接'}
            </Badge>
          </div>
          <div className="card-body">
            <div className="fields">
              <div className="field">
                <label htmlFor="app-mode">运行模式</label>
                <select
                  id="app-mode"
                  value={settings.app.mode}
                  onChange={(e) => update((s) => ({ ...s, app: { ...s.app, mode: e.target.value } }))}
                >
                  <option value="demo">demo · 合成数据，不作真实证据</option>
                  <option value="connected">connected · 真实大脑/执行器/平台</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="mailbox-platform">邮箱平台（提交目标）</label>
                <select
                  id="mailbox-platform"
                  value={settings.mailbox?.platform ?? 'demo'}
                  onChange={(e) =>
                    update((s) => ({ ...s, mailbox: { ...s.mailbox, platform: e.target.value } }))
                  }
                >
                  <option value="demo">demo · 本地合成邮箱</option>
                  <option value="bohrium_playground">bohrium_playground · 真实竞赛平台</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="shadow-max-reviews">静默监督审阅上限（次/Run）</label>
                <input
                  id="shadow-max-reviews"
                  type="number"
                  min={0}
                  value={settings.shadow?.max_reviews ?? 8}
                  onChange={(e) =>
                    update((s) => ({
                      ...s,
                      shadow: { ...s.shadow, max_reviews: Number(e.target.value) || 0 },
                    }))
                  }
                />
              </div>
              <div className="field">
                <label htmlFor="shadow-min-interval">静默监督最小间隔（秒）</label>
                <input
                  id="shadow-min-interval"
                  type="number"
                  min={1}
                  value={settings.shadow?.min_interval_seconds ?? 60}
                  onChange={(e) =>
                    update((s) => ({
                      ...s,
                      shadow: { ...s.shadow, min_interval_seconds: Number(e.target.value) || 60 },
                    }))
                  }
                />
              </div>
            </div>
            <p className="inline-note">
              保存后对新启动的 Run 生效；运行中的 Run 用创建时的快照。演示模式始终标识、使用独立数据，不作为真实联调证据。
            </p>
          </div>
        </article>

        <SkillsCard />

        <div className="save-bar">
          <button type="button" className="btn primary" disabled={saving} onClick={() => void saveSettings()}>
            {saving ? '保存中…' : '保存设置'}
          </button>
        </div>
      </div>
    </section>
  )
}

function SkillsCard() {
  const { toast } = useApp()
  const [skills, setSkills] = useState<SkillInfo[] | null>(null)
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [query, setQuery] = useState('')

  const reload = useCallback(async () => {
    const data = await listSkills()
    setSkills(data.skills)
    setChecked(new Set(data.always_on))
    setDirty(false)
  }, [])

  useEffect(() => {
    reload().catch((err) => {
      toast('加载技能目录失败：' + (err instanceof Error ? err.message : String(err)))
    })
  }, [reload, toast])

  function toggle(id: string) {
    setChecked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
    setDirty(true)
  }

  async function save() {
    setSaving(true)
    try {
      await putAlwaysOnSkills([...checked])
      toast('常驻技能已保存。')
      await reload()
    } catch (err) {
      toast('保存常驻技能失败：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setSaving(false)
    }
  }

  const q = query.trim().toLowerCase()
  const filtered =
    skills === null || !q
      ? skills
      : skills.filter(
          (s) =>
            s.name.toLowerCase().includes(q) ||
            s.description.toLowerCase().includes(q) ||
            s.id.toLowerCase().includes(q),
        )

  return (
    <article className="card">
      <div className="card-head">
        <div className="settings-heading">
          <span className="setting-num">07</span>
          <h2>技能管理</h2>
        </div>
        <div className="actions">
          {skills && (
            <Badge tone="neutral">
              {q ? `${filtered?.length ?? 0} / ${skills.length}` : `${skills.length}`} 个技能
            </Badge>
          )}
          <button
            type="button"
            className="btn small"
            disabled={!dirty || saving}
            onClick={() => void save()}
          >
            {saving ? '保存中…' : '保存常驻技能'}
          </button>
        </div>
      </div>
      <div className="card-body">
        <p className="sub">
          常驻技能对所有 Trial 生效；随题目启用的技能在研究工作台按题绑定。
          启用后，大脑和执行器会收到技能说明与 SKILL.md 路径，并在使用前阅读。
        </p>
        {skills !== null && skills.length > 0 && (
          <div className="field" style={{ marginBottom: 10 }}>
            <label htmlFor="skill-search">搜索技能（按名称 / 描述过滤）</label>
            <input
              id="skill-search"
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="输入关键词过滤技能…"
            />
          </div>
        )}
        {skills === null ? (
          <LoadingState>正在加载技能目录…</LoadingState>
        ) : skills.length === 0 ? (
          <p className="small-text">
            未在 ~/.kimi-code/skills、~/.agents/skills、~/.codex/skills 发现技能（含 SKILL.md 的子目录）。
          </p>
        ) : filtered && filtered.length === 0 ? (
          <p className="small-text">没有匹配「{query}」的技能。</p>
        ) : (
          <ul className="plain-list">
            {(filtered ?? []).map((s) => (
              <li key={s.id} className="row-item">
                <div>
                  <strong>{s.name}</strong>
                  {s.description && <div className="small-text">{s.description}</div>}
                  <div className="small-text">{s.source}</div>
                </div>
                <div className="field checkbox">
                  <input
                    id={`skill-always-${s.id}`}
                    type="checkbox"
                    checked={checked.has(s.id)}
                    onChange={() => toggle(s.id)}
                  />
                  <label htmlFor={`skill-always-${s.id}`}>常驻</label>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </article>
  )
}

function HealthBadge({ state }: { state: ConnState }) {
  if (state.error) return <Badge tone="danger">失败</Badge>
  if (state.busy) return <Badge tone="blue">检查中…</Badge>
  if (!state.result) return <Badge tone="neutral">未测试</Badge>
  const ok = state.result.status === 'ok' || state.result.status === 'healthy'
  return <Badge tone={ok ? 'green' : 'amber'}>{ok ? '正常' : state.result.status}</Badge>
}

function HealthDetail({ state, title }: { state: ConnState; title?: string }) {
  if (state.error) {
    return (
      <p className="form-error" role="alert">
        {title && <strong>{title}：</strong>}
        {state.error}
      </p>
    )
  }
  if (!state.result) return null
  const h = state.result.health
  return (
    <div className="health-detail">
      {title && <div className="small-title">{title}</div>}
      <div className="meta-row">
        <span>已安装</span>
        <span>{h.installed === null || h.installed === undefined ? '未知' : h.installed ? '是' : '否'}</span>
      </div>
      <div className="meta-row">
        <span>已认证</span>
        <span>{h.authenticated === null || h.authenticated === undefined ? '未知' : h.authenticated ? '是' : '否'}</span>
      </div>
      <div className="meta-row">
        <span>版本</span>
        <span>{h.version ?? '未知'}</span>
      </div>
      {h.detail && (
        <div className="meta-row">
          <span>详情</span>
          <span>{h.detail}</span>
        </div>
      )}
      {(() => {
        const caps = h.capabilities
        const entries = Array.isArray(caps)
          ? caps.map((c) => [c, true] as const)
          : Object.entries(caps ?? {})
        const enabled = entries.filter(([, v]) => v).map(([k]) => k)
        if (enabled.length === 0) return null
        return (
          <div className="meta-row">
            <span>能力</span>
            <span>{enabled.join('、')}</span>
          </div>
        )
      })()}
      {state.testedAt && (
        <p className="small-text">
          测试类型 {state.kind === 'model_roundtrip' ? '模型工具调用（消耗额度）' : '安装/认证检查'} · 时间{' '}
          {formatTime(state.testedAt)}
        </p>
      )}
    </div>
  )
}

function ConnActions({
  id,
  state,
  confirmSpend,
  onConfirmSpendChange,
  onTest,
  allowRoundtrip = false,
}: {
  id: ConnId
  state: ConnState
  confirmSpend: boolean
  onConfirmSpendChange: (v: boolean) => void
  onTest: (kind: 'inspect' | 'model_roundtrip') => void
  allowRoundtrip?: boolean
}) {
  return (
    <div className="conn-actions">
      <div className="actions">
        <button type="button" className="btn" disabled={state.busy} onClick={() => onTest('inspect')}>
          检查安装/认证
        </button>
        {allowRoundtrip && (
          <button type="button" className="btn" disabled={state.busy} onClick={() => onTest('model_roundtrip')}>
            测试模型工具调用
          </button>
        )}
      </div>
      {allowRoundtrip && (
        <>
          <div className="field checkbox">
            <input
              id={`${id}-confirm-spend`}
              type="checkbox"
              checked={confirmSpend}
              onChange={(e) => onConfirmSpendChange(e.target.checked)}
            />
            <label htmlFor={`${id}-confirm-spend`}>我确认消耗额度</label>
          </div>
          <p className="inline-note">“检查安装/认证”不调用付费模型；模型工具调用测试会消耗额度，需勾选确认。</p>
        </>
      )}
      {!allowRoundtrip && (
        <p className="inline-note">模型工具调用往返仅大脑支持；此处只提供零费用的安装/认证检查。</p>
      )}
    </div>
  )
}

function SecretField({
  label,
  secretId,
  configured,
  onSave,
  onDelete,
}: {
  label: string
  secretId: string
  configured: boolean
  onSave: (secretId: string, value: string) => void
  onDelete?: (secretId: string) => void
}) {
  const [id, setId] = useState(secretId)
  const [value, setValue] = useState('')

  useEffect(() => setId(secretId), [secretId])

  return (
    <div className="field secret-field">
      <label>{label}</label>
      <div className="secret-row">
        <input
          aria-label={`${label} 的 secret_id`}
          value={id}
          onChange={(e) => setId(e.target.value)}
          placeholder="secret_id"
          autoComplete="off"
        />
        <input
          aria-label={`${label} 的值`}
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="密钥值"
          autoComplete="off"
        />
        <button
          type="button"
          className="btn small"
          onClick={() => {
            onSave(id, value)
            setValue('')
          }}
        >
          保存密钥
        </button>
        {onDelete && configured && (
          <button
            type="button"
            className="btn small danger"
            onClick={() => onDelete(id)}
          >
            删除
          </button>
        )}
      </div>
      <p className="small-text" role="status">
        {configured ? '已配置' : '未配置'}（后端回读 secrets.json 状态，不回显值）
      </p>
    </div>
  )
}

function ProfileEditor({
  profile,
  onChange,
  onRemove,
}: {
  profile: LlmProfile
  onChange: (p: LlmProfile) => void
  onRemove: () => void
}) {
  return (
    <div className="profile-editor">
      <div className="fields triple">
        <div className="field">
          <label>ID（关联键，唯一）</label>
          <input
            value={profile.id}
            onChange={(e) => onChange({ ...profile, id: e.target.value.trim() })}
            placeholder="如 dsv41-flash"
          />
        </div>
        <div className="field">
          <label>标签</label>
          <input value={profile.label} onChange={(e) => onChange({ ...profile, label: e.target.value })} />
        </div>
        <div className="field">
          <label>协议</label>
          <select
            value={profile.protocol}
            onChange={(e) => onChange({ ...profile, protocol: e.target.value })}
          >
            {PROTOCOLS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>模型 ID</label>
          <input value={profile.model_id} onChange={(e) => onChange({ ...profile, model_id: e.target.value })} />
        </div>
        <div className="field">
          <label>Base URL</label>
          <input
            inputMode="url"
            value={profile.base_url}
            onChange={(e) => onChange({ ...profile, base_url: e.target.value })}
          />
        </div>
        <div className="field">
          <label>secret_ref</label>
          <input
            value={profile.secret_ref}
            onChange={(e) => onChange({ ...profile, secret_ref: e.target.value })}
            placeholder="先在下方密钥区写入密钥"
          />
        </div>
        <div className="field">
          <label>输入价（每百万 token，可空）</label>
          <input
            type="number"
            min={0}
            step={0.01}
            value={profile.pricing?.input_per_million ?? ''}
            onChange={(e) =>
              onChange({
                ...profile,
                pricing: {
                  ...profile.pricing,
                  input_per_million: e.target.value === '' ? undefined : Number(e.target.value),
                  output_per_million: profile.pricing?.output_per_million,
                },
              })
            }
          />
        </div>
        <div className="field">
          <label>输出价（每百万 token，可空）</label>
          <input
            type="number"
            min={0}
            step={0.01}
            value={profile.pricing?.output_per_million ?? ''}
            onChange={(e) =>
              onChange({
                ...profile,
                pricing: {
                  input_per_million: profile.pricing?.input_per_million,
                  output_per_million: e.target.value === '' ? undefined : Number(e.target.value),
                },
              })
            }
          />
        </div>
      </div>
      <button type="button" className="btn small" onClick={onRemove}>
        删除此 Profile
      </button>
    </div>
  )
}
