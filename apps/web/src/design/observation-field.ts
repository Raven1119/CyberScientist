/* RB-01 Threads / RB-08 DotGrid: application host port of frozen V9 reference.html.
 * React Bits copyright David Haz; full notices at /legal/research-interface-notices.txt.
 * Changes: typed React-facing lifecycle, theme uniforms, real-state gate. GLSL and
 * DotGrid proximity, impulse, spring/inertia equations retain the reference algorithms. */
import { THREADS, VERTEX100 } from './threads-shader'

export type FieldMode = 'threads' | 'dots'
type Renderer = { draw: (dt: number) => boolean; resize: (w: number, h: number, dpr: number) => void;
  move: (e: PointerEvent) => void; click: (e: MouseEvent) => void; leave: () => void; dispose: () => void }
const rgb = (hex: string) => [0, 2, 4].map(i => parseInt(hex.trim().replace('#', '').slice(i, i + 2), 16) / 255)

export function createField(host: HTMLElement, mode: FieldMode, color: string, base: string) {
  const canvas = document.createElement('canvas')
  canvas.className = 'observation-canvas'; canvas.setAttribute('aria-hidden', 'true')
  host.append(canvas)
  let renderer: Renderer
  try { renderer = mode === 'threads' ? threads(canvas, color) : dots(canvas, color, base) }
  catch (error) { canvas.remove(); throw error }
  let frame = 0, last = 0, visible = false, running = false, disposed = false, frames = 0
  const allowed = () => running && visible && !document.hidden && !disposed
  function draw(dt: number) {
    const moving = renderer.draw(dt)
    canvas.dataset.frames = String(++frames)
    return moving
  }
  function tick(now: number) {
    frame = 0
    if (!allowed()) return
    const moving = draw(last ? Math.min((now - last) / 1000, mode === 'dots' ? .03 : .05) : 0)
    last = now
    if (moving) frame = requestAnimationFrame(tick)
  }
  function reconcile() {
    canvas.dataset.running = String(allowed())
    if (allowed()) { if (!frame) { last = 0; frame = requestAnimationFrame(tick) } }
    else { cancelAnimationFrame(frame); frame = 0; last = 0 }
  }
  function resize() {
    const { width, height } = host.getBoundingClientRect()
    if (width < 2 || height < 2 || disposed) return
    const dpr = Math.min(devicePixelRatio || 1, mode === 'threads' ? Math.min(1.5, 850 / Math.max(width, height)) : 2)
    canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr)
    renderer.resize(width, height, dpr); draw(0)
  }
  const move = (e: PointerEvent) => { if (allowed()) { renderer.move(e); reconcile() } }
  const click = (e: MouseEvent) => { if (allowed()) { renderer.click(e); reconcile() } }
  const leave = () => { if (allowed()) { renderer.leave(); reconcile() } }
  const ro = new ResizeObserver(resize)
  const io = new IntersectionObserver(entries => { visible = entries[0].isIntersecting; reconcile() })
  ro.observe(host); io.observe(host)
  host.addEventListener('pointermove', move); host.addEventListener('click', click); host.addEventListener('pointerleave', leave)
  document.addEventListener('visibilitychange', reconcile)
  resize()
  return {
    setRunning(value: boolean) { running = value; reconcile() },
    dispose() {
      disposed = true; cancelAnimationFrame(frame); ro.disconnect(); io.disconnect()
      host.removeEventListener('pointermove', move); host.removeEventListener('click', click); host.removeEventListener('pointerleave', leave)
      document.removeEventListener('visibilitychange', reconcile); renderer.dispose(); canvas.remove()
    },
  }
}

function threads(canvas: HTMLCanvasElement, color: string): Renderer {
  const gl = canvas.getContext('webgl', { alpha: true, antialias: false, premultipliedAlpha: false })
  if (!gl) throw new Error('浏览器未提供 WebGL，观测图形不可用。研究控制仍可正常使用。')
  const shaders: WebGLShader[] = [], program = gl.createProgram()!, buffer = gl.createBuffer()
  function dispose() {
    gl!.deleteBuffer(buffer); gl!.deleteProgram(program); shaders.forEach(s => gl!.deleteShader(s))
    gl!.getExtension('WEBGL_lose_context')?.loseContext()
  }
  try {
    for (const [kind, source] of [[gl.VERTEX_SHADER, VERTEX100], [gl.FRAGMENT_SHADER, THREADS]] as const) {
      const shader = gl.createShader(kind)!
      shaders.push(shader); gl.shaderSource(shader, source); gl.compileShader(shader)
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error('观测图形编译失败。研究控制仍可正常使用。')
      gl.attachShader(program, shader)
    }
    gl.linkProgram(program)
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error('观测图形初始化失败。')
  } catch (error) { dispose(); throw error }
  gl.useProgram(program); gl.disable(gl.DEPTH_TEST); gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)
  const position = gl.getAttribLocation(program, 'position')
  gl.enableVertexAttribArray(position); gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0)
  const u = Object.fromEntries(['iTime', 'iResolution', 'uColor', 'uAmplitude', 'uDistance', 'uMouse'].map(n => [n, gl.getUniformLocation(program, n)]))
  gl.uniform3fv(u.uColor, rgb(color)); gl.uniform1f(u.uAmplitude, 1.7); gl.uniform1f(u.uDistance, .28)
  let phase = 8
  const mouse = { x: .5, y: .5, tx: .5, ty: .5 }
  return {
    resize() { gl.viewport(0, 0, canvas.width, canvas.height); gl.uniform3f(u.iResolution, canvas.width, canvas.height, canvas.width / canvas.height) },
    draw(dt) {
      phase += dt * .8
      if (dt) { mouse.x += (mouse.tx - mouse.x) * .05; mouse.y += (mouse.ty - mouse.y) * .05 }
      gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT)
      gl.uniform1f(u.iTime, phase); gl.uniform2f(u.uMouse, mouse.x, mouse.y)
      gl.drawArrays(gl.TRIANGLES, 0, 3)
      return true
    },
    move(e) { const r = canvas.getBoundingClientRect(); mouse.tx = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)); mouse.ty = Math.max(0, Math.min(1, 1 - (e.clientY - r.top) / r.height)) },
    leave() { mouse.tx = mouse.ty = .5 }, click() {}, dispose,
  }
}

function dots(canvas: HTMLCanvasElement, color: string, base: string): Renderer {
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('浏览器未提供 Canvas，观测图形不可用。')
  const dotSize = 3, gap = 17, proximity = 115, speedTrigger = 100, shockRadius = 170, shockStrength = 5, maxSpeed = 5000
  const baseRgb = rgb(base).map(v => v * 255), activeRgb = rgb(color).map(v => v * 255)
  let width = 0, height = 0
  const points: { cx: number; cy: number; xOffset: number; yOffset: number; vx: number; vy: number }[] = []
  const pointer = { x: -999, y: -999, lastX: 0, lastY: 0, lastTime: 0 }
  return {
    resize(w, h, dpr) {
      width = w; height = h; ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      const cols = Math.floor((w + gap) / (dotSize + gap)), rows = Math.floor((h + gap) / (dotSize + gap)), cell = dotSize + gap
      const startX = (w - (cell * cols - gap)) / 2 + dotSize / 2, startY = (h - (cell * rows - gap)) / 2 + dotSize / 2
      points.length = 0
      for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) points.push({ cx: startX + x * cell, cy: startY + y * cell, xOffset: 0, yOffset: 0, vx: 0, vy: 0 })
    },
    draw(dt) {
      ctx.clearRect(0, 0, width, height)
      let moving = false
      for (const dot of points) {
        if (dt) {
          dot.vx += (-75 * dot.xOffset - 9 * dot.vx) * dt; dot.vy += (-75 * dot.yOffset - 9 * dot.vy) * dt
          dot.xOffset += dot.vx * dt; dot.yOffset += dot.vy * dt
          if (Math.abs(dot.xOffset) + Math.abs(dot.yOffset) + Math.abs(dot.vx) + Math.abs(dot.vy) < .04) dot.xOffset = dot.yOffset = dot.vx = dot.vy = 0
        }
        if (dot.vx || dot.vy) moving = true
        const dsq = (dot.cx - pointer.x) ** 2 + (dot.cy - pointer.y) ** 2, t = dsq <= proximity * proximity ? 1 - Math.sqrt(dsq) / proximity : 0
        ctx.fillStyle = `rgb(${baseRgb.map((v, i) => Math.round(v + (activeRgb[i] - v) * t)).join(',')})`
        ctx.beginPath(); ctx.arc(dot.cx + dot.xOffset, dot.cy + dot.yOffset, dotSize / 2, 0, Math.PI * 2); ctx.fill()
      }
      return moving
    },
    move(e) {
      const now = performance.now(), dt = pointer.lastTime ? now - pointer.lastTime : 16, r = canvas.getBoundingClientRect()
      let vx = (e.clientX - pointer.lastX) / Math.max(dt, 1) * 1000, vy = (e.clientY - pointer.lastY) / Math.max(dt, 1) * 1000, speed = Math.hypot(vx, vy)
      if (speed > maxSpeed) { vx *= maxSpeed / speed; vy *= maxSpeed / speed; speed = maxSpeed }
      Object.assign(pointer, { x: e.clientX - r.left, y: e.clientY - r.top, lastX: e.clientX, lastY: e.clientY, lastTime: now })
      for (const dot of points) if (speed > speedTrigger && Math.hypot(dot.cx - pointer.x, dot.cy - pointer.y) < proximity) {
        dot.vx += (dot.cx - pointer.x + vx * .005) * 1.5; dot.vy += (dot.cy - pointer.y + vy * .005) * 1.5
      }
    },
    click(e) {
      const r = canvas.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top
      for (const dot of points) {
        const distance = Math.hypot(dot.cx - x, dot.cy - y)
        if (distance < shockRadius) { const falloff = Math.max(0, 1 - distance / shockRadius); dot.vx += (dot.cx - x) * shockStrength * falloff; dot.vy += (dot.cy - y) * shockStrength * falloff }
      }
    },
    leave() { pointer.x = pointer.y = -999 }, dispose() {},
  }
}
