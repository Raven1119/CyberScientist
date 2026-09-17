import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from './api'
import type { HealthInfo } from './types'

export type Page = 'research' | 'experience' | 'settings'

interface AppState {
  page: Page
  setPage: (page: Page) => void
  demoMode: boolean
  healthTime: string | null
  currentChallengeId: string | null
  setCurrentChallengeId: (id: string | null) => void
  toast: (message: string) => void
}

const AppContext = createContext<AppState | null>(null)

export function useApp(): AppState {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used within AppProvider')
  return ctx
}

let toastId = 0

export function AppProvider({ children }: { children: ReactNode }) {
  const [page, setPage] = useState<Page>('research')
  const [demoMode, setDemoMode] = useState(false)
  const [healthTime, setHealthTime] = useState<string | null>(null)
  const [currentChallengeId, setCurrentChallengeId] = useState<string | null>(null)
  const [toasts, setToasts] = useState<{ id: number; text: string }[]>([])

  const toast = useCallback((message: string) => {
    const id = ++toastId
    setToasts((list) => [...list, { id, text: message }])
    window.setTimeout(() => {
      setToasts((list) => list.filter((t) => t.id !== id))
    }, 6000)
  }, [])

  useEffect(() => {
    api
      .get<HealthInfo>('/api/v1/health')
      .then((h) => {
        setDemoMode(h.mode === 'demo')
        setHealthTime(h.time)
      })
      .catch(() => {
        toast('无法连接后端，请确认服务已在 127.0.0.1:8765 运行。')
      })
  }, [toast])

  const state: AppState = {
    page,
    setPage,
    demoMode,
    healthTime,
    currentChallengeId,
    setCurrentChallengeId,
    toast,
  }

  return (
    <AppContext.Provider value={state}>
      {children}
      <div className="toast-region" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div className="toast" key={t.id}>
            {t.text}
          </div>
        ))}
      </div>
    </AppContext.Provider>
  )
}

export function useStableCallback<A extends unknown[]>(
  fn: (...args: A) => void,
): (...args: A) => void {
  const ref = useRef(fn)
  useEffect(() => {
    ref.current = fn
  })
  return useCallback((...args: A) => ref.current(...args), [])
}
