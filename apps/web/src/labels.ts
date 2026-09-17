import type { RunPhase } from './types'

export const PHASE_LABELS: Record<RunPhase, string> = {
  created: '已创建',
  running: '研究进行中',
  pausing: '正在暂停',
  paused: '已暂停',
  blocked: '已阻塞',
  finished: '已完成',
  failed: '已失败',
  cancelled: '已终止',
}

export const PHASE_TONES: Record<RunPhase, 'green' | 'blue' | 'amber' | 'danger' | 'neutral'> = {
  created: 'neutral',
  running: 'green',
  pausing: 'amber',
  paused: 'amber',
  blocked: 'danger',
  finished: 'blue',
  failed: 'danger',
  cancelled: 'neutral',
}

export const ACTIVE_PHASES: RunPhase[] = ['created', 'running', 'pausing', 'paused', 'blocked']

export const SOURCE_LABELS: Record<string, string> = {
  brain: '大脑',
  prime: '执行器',
  controller: '控制器',
  user: '用户',
  demo: '演示',
}

const EVENT_LABELS: Record<string, string> = {
  'run.started': '研究开始',
  'run.pausing': '正在暂停',
  'run.paused': '已暂停',
  'run.finished': '研究完成',
  'run.blocked': '研究被阻塞',
  'brain.decision': '大脑决策',
  'brain.wait': '大脑等待',
  'brain.error': '大脑出错',
  'prime.task_accepted': '任务已接受',
  'prime.trial.started': 'Trial 开始',
  'prime.execution.progress': '执行进度',
  'prime.checkpoint.created': '检查点已创建',
  'prime.trial.completed': 'Trial 完成',
  'prime.steer': '指导已接收',
  'prime.steer.consumed': '指导已生效',
  'trial.created': 'Trial 创建',
  'trial.done': 'Trial 结束',
  'user.steer.queued': '指导已排队',
  'experience.proposed': '经验候选',
  'checkpoint.created': '检查点已创建',
}

export function eventLabel(type: string): string {
  return EVENT_LABELS[type] ?? type
}

export function eventText(event: {
  type: string
  payload: Record<string, unknown>
}): string {
  const p = event.payload ?? {}
  const summary = typeof p.summary === 'string' ? p.summary : null
  const detail = typeof p.detail === 'string' ? p.detail : null
  const status = typeof p.status === 'string' ? p.status : null
  const reason = typeof p.reason === 'string' ? p.reason : null
  const message = typeof p.message === 'string' ? p.message : null
  const goal = typeof p.goal === 'string' ? p.goal : null
  const text = typeof p.text === 'string' ? p.text : null

  switch (event.type) {
    case 'brain.decision':
      return summary ?? detail ?? '大脑给出决策。'
    case 'brain.wait':
      return reason ?? detail ?? '大脑等待中。'
    case 'brain.error':
      return message ?? detail ?? '大脑报告错误。'
    case 'prime.execution.progress':
      return detail ?? summary ?? '执行器推进中。'
    case 'prime.steer':
    case 'prime.steer.consumed':
      return text ?? detail ?? ''
    case 'trial.created':
    case 'prime.trial.started':
      return goal ?? detail ?? ''
    case 'run.blocked':
      return reason ?? detail ?? '研究被阻塞。'
    default:
      return summary ?? detail ?? status ?? text ?? ''
  }
}

export const CONTRACT_LABELS: Record<string, string> = {
  verified: '契约已验证',
  partial: '契约部分验证',
  unverified: '契约未验证',
  unknown: '契约未验证',
  missing: '缺少评分契约',
  invalid: '契约无效',
}

export const TRIAL_STATUS_LABELS: Record<string, string> = {
  active: '进行中',
  done: '已完成',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

export const EVIDENCE_LABELS: Record<string, string> = {
  hypothesis: '假设',
  observed: '已观察',
  validated: '已验证',
  contradicted: '已被否定',
}

export const STATUS_LABELS: Record<string, string> = {
  candidate: '候选',
  active: '启用',
  retired: '停用',
}

export const KIND_LABELS: Record<string, string> = {
  heuristic: '启发式',
  procedure: '流程',
  failure: '失败模式',
  platform: '平台',
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN', { hour12: false })
}

export function shortHash(hash: string | null | undefined): string {
  if (!hash) return '—'
  return hash.slice(0, 12)
}
