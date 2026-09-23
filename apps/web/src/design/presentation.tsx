import { createContext, useContext, useEffect, useLayoutEffect, useState } from 'react'
import type { ReactNode } from 'react'

const KEY = 'cyberscientist.presentation.v1'
type Preferences = { theme: 'paper' | 'night'; motion: boolean; ambient: boolean; focus: boolean }
const defaults: Preferences = { theme: 'paper', motion: true, ambient: true, focus: false }
function readPreferences(): Preferences {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || '{}')
    return { theme: saved.theme === 'night' ? 'night' : 'paper', motion: saved.motion !== false,
      ambient: saved.ambient !== false, focus: false }
  } catch { return defaults }
}
const Context = createContext({ ...defaults, reduced: false, writing: false,
  setPreference: (_key: keyof Preferences, _value: Preferences[keyof Preferences]) => {} })

/** Presentation preferences only. No research state or credentials enter this store. */
export function PresentationProvider({ children }: { children: ReactNode }) {
  const [preferences, setPreferences] = useState(readPreferences)
  const [reduced, setReduced] = useState(() => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false)
  const [writing, setWriting] = useState(false)
  useLayoutEffect(() => {
    document.documentElement.dataset.theme = preferences.theme
    document.documentElement.dataset.motion = preferences.motion && !reduced ? 'on' : 'off'
    try { localStorage.setItem(KEY, JSON.stringify(preferences)) } catch { /* Private browsers remain usable. */ }
  }, [preferences, reduced])
  useEffect(() => {
    const media = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    const update = () => setReduced(media?.matches ?? false)
    media?.addEventListener('change', update)
    const focus = () => setWriting(!!document.activeElement?.matches(
      'textarea,input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=button]),[contenteditable=true]'))
    const blur = () => queueMicrotask(focus)
    document.addEventListener('focusin', focus)
    document.addEventListener('focusout', blur)
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !document.querySelector('dialog[open]')) {
        setPreferences(p => ({ ...p, focus: false }))
      }
    }
    document.addEventListener('keydown', escape)
    return () => {
      media?.removeEventListener('change', update)
      document.removeEventListener('focusin', focus)
      document.removeEventListener('focusout', blur)
      document.removeEventListener('keydown', escape)
    }
  }, [])
  return <Context.Provider value={{ ...preferences, reduced, writing,
    setPreference: (key, value) => setPreferences(p => ({ ...p, [key]: value })) }}>{children}</Context.Provider>
}
export const usePresentation = () => useContext(Context)
