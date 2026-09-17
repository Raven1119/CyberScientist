import { useCallback, useEffect, useState } from 'react'
import { api, pair } from '../api'
import { useApp } from '../app-context'
import { Badge } from '../components'
import { formatTime } from '../labels'
import type { ConnectionTestResult, LlmProfile, Settings } from '../types'

type ConnId = 'brain' | 'prime' | 'playground' | 'bohrium'

interface ConnState {
  result?: ConnectionTestResult
  testedAt?: string
  kind?: 'inspect' | 'model_roundtrip'
  busy?: boolean
  error?: string
}

const PROTOCOLS = ['openai_chat_completions', 'openai_responses', 'anthropic_messages']

export default function SettingsPage() {
  const { toast, paired, setPaired } = useApp()
  const [settings, setSettings] = useState<Settings | null>(null)
  const [baseRevision, setBaseRevision] = useState(0)
  const [conns, setConns] = useState<Record<ConnId, ConnState>>({
    brain: {},
    prime: {},
    playground: {},
    bohrium: {},
  })
  const [confirmSpend, setConfirmSpend] = useState<Record<ConnId, boolean>>({
    brain: false,
    prime: false,
    playground: false,
    bohrium: false,
  })
  const [pairCode, setPairCode] = useState('')
  const [pairBusy, setPairBusy] = useState(false)
  const [pairError, setPairError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api
      .get<Settings>('/api/v1/settings')
      .then((s) => {
        setSettings(s)
        setBaseRevision(s.revision)
      })
      .catch((err) => {
        if (err instanceof Error) toast('加载设置失败：' + err.message)
      })
  }, [toast])

  const update = useCallback((fn: (s: Settings) => Settings) => {
    setSettings((prev) => (prev ? fn(structuredClone(prev)) : prev))
  }, [])

  async function saveSettings() {
    if (!settings) return
    setSaving(true)
    try {
      await api.put('/api/v1/settings', { settings, base_revision: baseRevision })
      toast('设置已保存。')
      const fresh = await api.get<Settings>('/api/v1/settings')
      setSettings(fresh)
      setBaseRevision(fresh.revision)
    } catch (err) {
      toast('保存设置失败：' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setSaving(false)
    }
  }

  async function submitPair() {
    const code = pairCode.trim()
    if (!code) {
      setPairError('请输入配对码。')
      return
    }
    setPairBusy(true)
    setPairError(null)
    try {
      await pair(code)
      setPaired(true)
      setPairCode('')
      toast('配对成功。')
    } catch (err) {
      setPairError(err instanceof Error ? err.message : '配对失败。')
    } finally {
      setPairBusy(false)
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

  async function writeSecret(secretId: string, value: string, onSaved: (ref: string) => void) {
    if (!secretId.trim() || !value) {
      toast('请填写 secret_id 和密钥值。')
      return
    }
    try {
      const res = await api.post<{ secret_ref: string; configured: boolean }>('/api/v1/secrets', {
        secret_id: secretId.trim(),
        value,
      })
      onSaved(res.secret_ref)
      toast(`密钥 ${secretId.trim()} 已配置。`)
    } catch (err) {
      toast('保存密钥失败：' + (err instanceof Error ? err.message : String(err)))
    }
  }

  if (!settings) {
    return (
      <section aria-label="连接与设置">
        <div className="empty">
          <strong>正在加载设置…</strong>
          <p>如果长时间没有响应，请确认后端已启动。</p>
        </div>
      </section>
    )
  }

  const brainRuntime = settings.app.mode === 'demo' ? 'demo' : settings.brain.runtime

  return (
    <section aria-label="连接与设置">
      <div className="page-head">
        <div>
          <div className="eyebrow">CONNECTIONS / SEPARATE BY RESPONSIBILITY</div>
          <h1>连接与设置</h1>
          <p className="sub">代理运行时、模型 API、平台 API 独立配置。</p>
        </div>
        <button type="button" className="btn primary" disabled={saving} onClick={() => void saveSettings()}>
          {saving ? '保存中…' : '保存设置'}
        </button>
      </div>

      {!paired && (
        <div className="callout" role="alert">
          <strong>尚未配对。</strong>
          输入配对码后本会话才能执行写操作。
          <span className="pair-inline">
            <label htmlFor="settings-pair-code" className="sr-only">
              配对码
            </label>
            <input
              id="settings-pair-code"
              value={pairCode}
              onChange={(e) => setPairCode(e.target.value)}
              placeholder="配对码"
            />
            <button type="button" className="btn small" disabled={pairBusy} onClick={() => void submitPair()}>
              {pairBusy ? '配对中…' : '配对'}
            </button>
          </span>
          {pairError && <span className="form-error">{pairError}</span>}
        </div>
      )}

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
              <span>{brainRuntime === 'demo' ? '演示模式' : brainRuntime === 'kimi' ? 'Kimi Code' : 'Codex'}</span>
            </div>
            <div className="fields">
              <div className="field">
                <label htmlFor="brain-runtime">原生代理</label>
                <select
                  id="brain-runtime"
                  value={settings.brain.runtime}
                  onChange={(e) => update((s) => ({ ...s, brain: { ...s.brain, runtime: e.target.value } }))}
                >
                  <option value="codex">Codex · App Server</option>
                  <option value="kimi">Kimi Code · Wire</option>
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
              <div className="field">
                <label htmlFor="brain-model">模型 ID</label>
                <input
                  id="brain-model"
                  value={settings.brain.model_id ?? ''}
                  onChange={(e) =>
                    update((s) => ({ ...s, brain: { ...s.brain, model_id: e.target.value || null } }))
                  }
                  placeholder="留空使用原生配置"
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
            />
            <HealthDetail state={conns.brain} />
            {settings.brain.runtime === 'kimi' && (
              <p className="inline-note">Kimi Code 适配尚未完全接入时，检查结果会显示“尚未接入”，这属于已知状态而非错误。</p>
            )}
          </div>
        </article>

        <article className="card">
          <div className="card-head">
            <div className="settings-heading">
              <span className="setting-num">02</span>
              <h2>Prime 执行器</h2>
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
                    <option key={p.label} value={p.label}>
                      {p.label}（{p.model_id}）
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <ConnActions
              id="prime"
              state={conns.prime}
              confirmSpend={confirmSpend.prime}
              onConfirmSpendChange={(v) => setConfirmSpend((c) => ({ ...c, prime: v }))}
              onTest={(kind) => void testConnection('prime', kind)}
            />
            <HealthDetail state={conns.prime} />
          </div>
        </article>

        <article className="card">
          <div className="card-head">
            <div className="settings-heading">
              <span className="setting-num">03</span>
              <h2>模型 Profile 列表</h2>
            </div>
            <Badge tone="neutral">{settings.llm_profiles.length} 个</Badge>
          </div>
          <div className="card-body">
            <p className="sub">Prime 调模型使用的供应商配置。API Key 通过下方密钥输入写入后端，不保存在设置里。</p>
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
                    { label: '', protocol: 'openai_chat_completions', base_url: '', model_id: '', secret_ref: '' },
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
              <span className="setting-num">04</span>
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
                secretId={settings.playground.token_secret_ref || 'playground_token'}
                configured={!!settings.playground.token_secret_ref}
                onSave={(sid, value) =>
                  void writeSecret(sid, value, (ref) =>
                    update((s) => ({ ...s, playground: { ...s.playground, token_secret_ref: ref } })),
                  )
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
                secretId={settings.bohrium.access_key_secret_ref || 'bohrium_access_key'}
                configured={!!settings.bohrium.access_key_secret_ref}
                onSave={(sid, value) =>
                  void writeSecret(sid, value, (ref) =>
                    update((s) => ({ ...s, bohrium: { ...s.bohrium, access_key_secret_ref: ref } })),
                  )
                }
              />
            </div>
            <div className="actions" style={{ marginTop: 10 }}>
              <button type="button" className="btn" disabled={conns.playground.busy} onClick={() => void testConnection('playground', 'inspect')}>
                检查 Playground 连接
              </button>
              <button type="button" className="btn" disabled={conns.bohrium.busy} onClick={() => void testConnection('bohrium', 'inspect')}>
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
      </div>
    </section>
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
      {h.capabilities?.length > 0 && (
        <div className="meta-row">
          <span>能力</span>
          <span>{h.capabilities.join('、')}</span>
        </div>
      )}
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
}: {
  id: ConnId
  state: ConnState
  confirmSpend: boolean
  onConfirmSpendChange: (v: boolean) => void
  onTest: (kind: 'inspect' | 'model_roundtrip') => void
}) {
  return (
    <div className="conn-actions">
      <div className="actions">
        <button type="button" className="btn" disabled={state.busy} onClick={() => onTest('inspect')}>
          检查安装/认证
        </button>
        <button type="button" className="btn" disabled={state.busy} onClick={() => onTest('model_roundtrip')}>
          测试模型工具调用
        </button>
      </div>
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
    </div>
  )
}

function SecretField({
  label,
  secretId,
  configured,
  onSave,
}: {
  label: string
  secretId: string
  configured: boolean
  onSave: (secretId: string, value: string) => void
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
      </div>
      <p className="small-text" role="status">
        {configured ? '已配置' : '未配置'}（保存后输入框清空，不回显密钥）
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
            placeholder="先在下方面板写入密钥"
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
