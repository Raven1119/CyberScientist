/* Application ports of frozen reference.html: RB-34 PixelTransition / RB-35 AnimatedContent.
 * React Bits copyright David Haz. Full notices: /legal/research-interface-notices.txt.
 * Changes: typed lifecycle, newest-selection cancellation, reduced-motion and visibility cleanup.
 * Not a standalone component library. Timings/grid/stagger/easing retain the V9 algorithms. */
export const canMove = () => document.documentElement.dataset.motion !== 'off'
  && !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

export function enter(element: HTMLElement, distance = 24) {
  if (!canMove() || !element.animate) return () => {}
  const animation = element.animate([
    { opacity: 0, transform: `translateY(${distance}px)` }, { opacity: 1, transform: 'none' },
  ], { duration: 600, easing: 'cubic-bezier(.215,.61,.355,1)', fill: 'backwards' })
  const finish = () => { if (!canMove() || document.hidden) animation.cancel() }
  const observer = new MutationObserver(finish)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-motion'] })
  document.addEventListener('visibilitychange', finish)
  const cleanup = () => { observer.disconnect(); document.removeEventListener('visibilitychange', finish) }
  void animation.finished.then(cleanup, cleanup)
  return () => { animation.cancel(); cleanup() }
}

const pixelJobs = new WeakMap<HTMLElement, (commit?: boolean) => void>()
export function cancelPixels(host: HTMLElement) { pixelJobs.get(host)?.(false) }
export function pixelTransition(host: HTMLElement, swap: () => void) {
  pixelJobs.get(host)?.(false)
  if (!canMove() || document.hidden) { swap(); return }
  const grid = document.createElement('div')
  grid.className = 'source-pixel-grid'
  grid.setAttribute('aria-hidden', 'true')
  const pixels: HTMLElement[] = [], gridSize = 12, duration = 300
  for (let row = 0; row < gridSize; row++) for (let col = 0; col < gridSize; col++) {
    const pixel = document.createElement('i'), size = 100 / gridSize
    Object.assign(pixel.style, { width: `${size}%`, height: `${size}%`, left: `${col * size}%`, top: `${row * size}%` })
    grid.append(pixel); pixels.push(pixel)
  }
  host.append(grid)
  const count = pixels.length, cover = pixels.slice().sort(() => .5 - Math.random()), reveal = pixels.slice().sort(() => .5 - Math.random())
  let frame = 0, start = 0, swapped = false, covered = 0, revealed = 0
  const finish = (commit = true) => {
    if (commit && !swapped) { swapped = true; swap() }
    cancelAnimationFrame(frame); grid.remove(); observer.disconnect()
    document.removeEventListener('visibilitychange', reconcile)
    if (pixelJobs.get(host) === finish) pixelJobs.delete(host)
  }
  const reconcile = () => { if (!canMove() || document.hidden) finish() }
  const observer = new MutationObserver(reconcile)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-motion'] })
  document.addEventListener('visibilitychange', reconcile)
  pixelJobs.set(host, finish)
  function tick(now: number) {
    if (!host.isConnected) { finish(false); return }
    if (!canMove() || document.hidden) { finish(); return }
    if (!start) start = now
    const t = now - start, target = Math.min(count, Math.floor(t / duration * count) + 1)
    while (covered < target) cover[covered++].style.display = 'block'
    if (t >= duration && !swapped) { swapped = true; swap() }
    if (swapped) {
      const targetReveal = Math.min(count, Math.floor((t - duration) / duration * count) + 1)
      while (revealed < targetReveal) reveal[revealed++].style.display = 'none'
    }
    if (t >= duration * 2) { finish(); return }
    frame = requestAnimationFrame(tick)
  }
  frame = requestAnimationFrame(tick)
}
