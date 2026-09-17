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

const CSRF_KEY = 'csrf-token'

let csrfToken: string | null = sessionStorage.getItem(CSRF_KEY)

export function getCsrfToken(): string | null {
  return csrfToken
}

export function setCsrfToken(token: string | null): void {
  csrfToken = token
  if (token) sessionStorage.setItem(CSRF_KEY, token)
  else sessionStorage.removeItem(CSRF_KEY)
}

export type PairingHandler = () => void

let pairingHandler: PairingHandler | null = null

export function registerPairingHandler(handler: PairingHandler): void {
  pairingHandler = handler
}

export function notifyPairingRequired(): void {
  pairingHandler?.()
}

function captureCsrf(res: Response): void {
  const token = res.headers.get('X-CSRF-Token')
  if (token) setCsrfToken(token)
}

/** 后端错误统一为 {"detail": {code,message,...}}；兼容扁平结构。 */
function unwrapErrorBody(data: unknown): ApiErrorBody | null {
  if (!data || typeof data !== 'object') return null
  const record = data as Record<string, unknown>
  const inner = record.detail
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
  if (csrfToken) headers['X-CSRF-Token'] = csrfToken
  const res = await fetch(path, {
    method,
    headers,
    credentials: 'same-origin',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  captureCsrf(res)
  const data = await readBody(res)
  if (res.status === 401) {
    const errBody = unwrapErrorBody(data)
    if (errBody?.code === 'PAIRING_REQUIRED') {
      notifyPairingRequired()
      throw new ApiError(401, errBody)
    }
  }
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

export async function pair(code: string): Promise<void> {
  const res = await fetch('/api/v1/pair', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify({ code }),
  })
  captureCsrf(res)
  const data = await readBody(res)
  if (!res.ok) throw new ApiError(res.status, unwrapErrorBody(data))
}
