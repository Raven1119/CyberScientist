import { useEffect, useRef } from 'react'
import { usePresentation } from './presentation'

/* RB-29 TargetCursor from frozen reference.html. Capture 200ms / return 300ms.
 * React Bits copyright David Haz; /legal/research-interface-notices.txt.
 * Changes: scoped React cleanup; native pointer retained; no editor/parallax. */
export function TargetCursor() {
  const ref = useRef<HTMLDivElement>(null)
  const { motion, reduced } = usePresentation()
  useEffect(() => {
    const cursor = ref.current
    if (!cursor || !motion || reduced || !window.matchMedia('(hover:hover) and (pointer:fine)').matches) return
    const corners = Array.from(cursor.children) as HTMLElement[]
    let target: HTMLElement | null = null, timer = 0, point = { x: 0, y: 0 }
    const animate = (corner: HTMLElement, x: number, y: number, duration: number, initial?: string) => {
      const from = initial || getComputedStyle(corner).transform
      corner.getAnimations().forEach(a => a.cancel())
      corner.style.transform = `translate(${x}px,${y}px)`
      corner.animate([{ transform: from }, { transform: corner.style.transform }],
        { duration, easing: 'cubic-bezier(.215,.61,.355,1)' })
    }
    const reset = () => { cursor.dataset.active = 'false'; target = null; window.clearTimeout(timer) }
    const hide = () => {
      target = null; window.clearTimeout(timer)
      if (cursor.dataset.active !== 'true') return
      const positions = [[-15, -15], [5, -15], [5, 5], [-15, 5]]
      corners.forEach((corner, i) => animate(corner, point.x + positions[i][0], point.y + positions[i][1], 300))
      timer = window.setTimeout(reset, 300)
    }
    const move = (event: PointerEvent) => { point = { x: event.clientX, y: event.clientY } }
    const over = (event: PointerEvent) => {
      if (document.querySelector('dialog[open]')) { reset(); return }
      const element = event.target instanceof Element
        ? event.target.closest<HTMLElement>('button:not(:disabled),a[href],summary') : null
      if (!element) { if (target) hide(); return }
      if (element === target) return
      window.clearTimeout(timer)
      const r = element.getBoundingClientRect(), size = 10, border = 3
      const positions = [[r.left - border, r.top - border], [r.right + border - size, r.top - border],
        [r.right + border - size, r.bottom + border - size], [r.left - border, r.bottom + border - size]]
      const initial = cursor.dataset.active !== 'true'
      cursor.dataset.active = 'true'; target = element
      corners.forEach((corner, i) => animate(corner, positions[i][0], positions[i][1], 200,
        initial ? `translate(${event.clientX + (i === 1 || i === 2 ? 5 : -15)}px,${event.clientY + (i > 1 ? 5 : -15)}px)` : undefined))
    }
    const out = (event: PointerEvent) => { if (!event.relatedTarget) hide() }
    document.addEventListener('pointermove', move, { passive: true })
    document.addEventListener('pointerover', over, { passive: true })
    document.addEventListener('pointerout', out)
    document.addEventListener('focusin', reset)
    document.addEventListener('visibilitychange', reset)
    window.addEventListener('scroll', reset, true)
    window.addEventListener('resize', reset)
    return () => {
      reset(); corners.forEach(c => c.getAnimations().forEach(a => a.cancel()))
      document.removeEventListener('pointermove', move); document.removeEventListener('pointerover', over)
      document.removeEventListener('pointerout', out); document.removeEventListener('focusin', reset)
      document.removeEventListener('visibilitychange', reset); window.removeEventListener('scroll', reset, true)
      window.removeEventListener('resize', reset)
    }
  }, [motion, reduced])
  return <div ref={ref} className="target-cursor" aria-hidden="true"><i /><i /><i /><i /></div>
}
