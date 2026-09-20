import type { SkillCatalogResponse } from './types'

export interface ApiErrorBody {
  code: string
  message: string
  recoverable: boolean
  details_ref?: string
  details?: unknown
}

export class ApiError extends Error {
  status: number
  code: string
  recoverable: boolean
  details?: unknown

  constructor(status: number, body: ApiErrorBody | null) {
    super(body?.message ?? `请求失败（HTTP ${status}）`)
    this.status = status
    this.code = body?.code ?? 'UNKNOWN'
    this.recoverable = body?.recoverable ?? false
    this.details = body?.details
  }
}

/** 后端错误统一为 {"detail": {code,message,...}}；兼容扁平结构与 FastAPI 422。 */
function unwrapErrorBody(data: unknown): ApiErrorBody | null {
  if (!data || typeof data !== 'object') return null
  const record = data as Record<string, unknown>
  const inner = record.detail
  if (Array.isArray(inner)) {
    // FastAPI/pydantic 校验错误：[{loc, msg, type}]
    const msgs = inner
      .map((e) => {
        const r = e as Record<string, unknown>
        const loc = Array.isArray(r.loc) ? r.loc.join('.') : ''
        return `${loc}: ${r.msg ?? ''}`.trim()
      })
      .filter(Boolean)
    return {
      code: 'VALIDATION',
      message: msgs.join('；') || '请求参数校验失败',
      recoverable: true,
    }
  }
  if (inner && typeof inner === 'object' && 'code' in (inner as Record<string, unknown>)) {
    return inner as ApiErrorBody
  }
  if ('code' in record) return record as unknown as ApiErrorBody
  return null
}

async function readBody(res: Response): Promise<unknown> {
  const text = await res.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

export async function apiRequest<T = unknown>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const res = await fetch(path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  const data = await readBody(res)
  if (!res.ok) {
    throw new ApiError(res.status, unwrapErrorBody(data))
  }
  return data as T
}

export const api = {
  get: <T = unknown>(path: string) => apiRequest<T>('GET', path),
  post: <T = unknown>(path: string, body?: unknown) => apiRequest<T>('POST', path, body),
  put: <T = unknown>(path: string, body?: unknown) => apiRequest<T>('PUT', path, body),
  delete: <T = unknown>(path: string) => apiRequest<T>('DELETE', path),
}

// ---------------- 技能 ----------------

export function listSkills(challengeId?: string) {
  const qs = challengeId ? `?challenge_id=${encodeURIComponent(challengeId)}` : ''
  return api.get<SkillCatalogResponse>(`/api/v1/skills${qs}`)
}

export function putAlwaysOnSkills(skillIds: string[]) {
  return api.put<{ always_on: string[]; revision: number }>('/api/v1/skills/always_on', {
    skill_ids: skillIds,
  })
}

export function bindChallengeSkill(challengeId: string, skillId: string) {
  return api.post<{ challenge_id: string; bound: string[] }>(
    `/api/v1/challenges/${encodeURIComponent(challengeId)}/skills`,
    { skill_id: skillId },
  )
}

export function unbindChallengeSkill(challengeId: string, skillId: string) {
  return api.delete<{ challenge_id: string; bound: string[] }>(
    `/api/v1/challenges/${encodeURIComponent(challengeId)}/skills/${encodeURIComponent(skillId)}`,
  )
}

// ---------------- 预算 ----------------

export interface BudgetUpdateBody {
  max_brain_reviews?: number
  max_trials?: number
  max_model_turns?: number
  max_run_minutes?: number
  max_submissions?: number
}

export function updateRunBudget(runId: string, body: BudgetUpdateBody) {
  return api.put<{ run_id: string; updated: Record<string, number>; budget: unknown }>(
    `/api/v1/runs/${encodeURIComponent(runId)}/budget`,
    body,
  )
}
