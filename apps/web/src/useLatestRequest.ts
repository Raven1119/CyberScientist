import { useCallback, useEffect, useRef } from 'react'

/** Publish completed replies in request order, scoped to the mounted entity.
 * A slower-than-polling backend must still publish before later replies finish.
 */
export function useLatestRequest(scope = '') {
  const ref = useRef({ scope, sequence: 0, published: 0, active: true })
  if (ref.current.scope !== scope) ref.current = { scope, sequence: 0, published: 0, active: true }
  const state = ref.current
  useEffect(() => {
    state.active = true
    return () => { state.active = false; state.published = ++state.sequence }
  }, [state])
  return useCallback(() => {
    const current = ref.current
    const sequence = ++current.sequence
    return () => {
      if (ref.current !== current || !current.active || sequence < current.published) return false
      current.published = sequence
      return true
    }
  }, [])
}
