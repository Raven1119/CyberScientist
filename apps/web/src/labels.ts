import type { RunPhase } from './types'

export const PHASE_LABELS: Record<RunPhase, string> = {
  created: '已创建',
  running: '研究进行中',
  pausing: '正在暂停',
  paused: '已暂停',
  blocked: '已阻塞',
  recovering: '恢复中',
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
  recovering: 'amber',
  finished: 'blue',
  failed: 'danger',
  cancelled: 'neutral',
}

export const ACTIVE_PHASES: RunPhase[] = ['created', 'running', 'pausing', 'paused', 'blocked', 'recovering']

export const TERMINAL_PHASES: RunPhase[] = ['finished', 'failed', 'cancelled']

export const SOURCE_LABELS: Record<string, string> = {
  brain: '大脑',
  prime: '执行器',
  executor: '执行器',
  controller: '控制器',
  user: '用户',
  demo: '演示',
}

const EVENT_LABELS: Record<string, string> = {
  'run.started': '研究开始',
  'run.pausing': '正在暂停',
  'run.paused': '已暂停',
  'run.pause_unknown': '暂停结果未知',
  'run.pause.unknown': '暂停结果未知',
  'run.finished': '研究完成',
  'run.terminated': '研究已终止',
  'run.blocked': '研究被阻塞',
  'run.stop_requested': '已请求停止执行器',
  'run.stop_confirmed': '执行器停止已确认',
  'run.finish_deferred': '收尾延迟（先整理本题经验）',
  'run.budget_updated': '预算已更新',
  'brain.decision': '大脑决策',
  'brain.review_started': '大脑开始判断',
  'brain.review_done': '大脑审阅完成',
  'brain.raw_output': '大脑原始输出',
  'brain.wait': '大脑等待',
  'brain.error': '大脑出错',
  'prime.task_accepted': '任务已被执行器接受',
  'prime.task_resumed': '执行器任务已恢复',
  'prime.approval.granted': '工具自动批准',
  'prime.trial.started': 'Trial 开始',
  'prime.execution.progress': '执行进度',
  'prime.checkpoint.created': '检查点已创建',
  'prime.trial.completed': 'Trial 完成',
  'prime.trial.stalled': '执行器挂起已处置',
  'controller.trial.stalled': '执行器挂起已处置',
  'trial.stalled': '执行器挂起已处置',
  'prime.aborted': '执行器会话中止',
  'prime.error': '执行器出错',
  'prime.late_event_ignored': '暂停期间的迟到事件已忽略',
  'prime.steer': '指导已接收',
  'prime.steer.consumed': '指导已生效',
  'trial.created': 'Trial 创建',
  'trial.done': 'Trial 结束',
  'trial.reported_complete': 'Trial 报告完成',
  'trial.skills_enabled': 'Trial 已挂载技能',
  'user.steer.queued': '指导已排队',
  'guidance.queued': '指导已排队',
  'guidance.sent': '指导已投递执行器',
  'guidance.send_deferred': '指导投递暂缓',
  'guidance.acknowledged': '指导已被执行器确认',
  'guidance.superseded': '指导已被取代',
  'guidance.invalidated': '指导已失效',
  'submission.created': '提交已创建',
  'submission.submitted': '已提交到平台',
  'submission.failed': '提交失败',
  'review.requested': '已请求大脑审阅',
  'shadow.toggled': '静默监督开关切换',
  'shadow.degraded': '静默监督降级',
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
  const trigger = typeof p.trigger === 'string' ? p.trigger : null

  switch (event.type) {
    case 'brain.decision':
      return summary ?? detail ?? '大脑给出决策。'
    case 'brain.review_started':
      return trigger ? `触发：${trigger}` : '大脑开始判断。'
    case 'brain.raw_output':
      return text ?? ''
    case 'brain.wait':
      return reason ?? detail ?? '大脑等待中。'
    case 'brain.error':
      return message ?? detail ?? '大脑报告错误。'
    case 'prime.approval.granted':
      return detail ?? '执行器工具已自动批准。'
    case 'prime.execution.progress':
      return detail ?? summary ?? '执行器推进中。'
    case 'prime.trial.stalled':
    case 'controller.trial.stalled':
    case 'trial.stalled':
      return reason ?? message ?? detail ?? '执行器挂起已处置。'
    case 'prime.steer':
    case 'prime.steer.consumed':
      return text ?? detail ?? ''
    case 'guidance.queued':
    case 'guidance.sent':
    case 'guidance.acknowledged':
    case 'guidance.send_deferred':
      return detail ?? (typeof p.text_excerpt === 'string' ? p.text_excerpt : '') ?? ''
    case 'submission.created':
    case 'submission.submitted':
    case 'submission.failed':
      return detail ?? message ?? ''
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
  reported_complete: '已交付',
  failed: '失败',
  cancelled: '已取消',
  interrupted: '已中断',
}

export function trialStatusLabel(status: string, delivered?: boolean): string {
  return status === 'interrupted' && delivered
    ? '已交付 · 后被终止'
    : TRIAL_STATUS_LABELS[status] ?? status
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

export const SUBMISSION_STATUS_LABELS: Record<string, string> = {
  unknown: '待提交',
  created: '已创建',
  submitted: '已提交',
  failed: '提交失败',
}

export const SCORE_STATUS_LABELS: Record<string, string> = {
  unknown: '未知',
  pending: '待评分',
  scored: '已评分',
  failed: '评分失败',
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
