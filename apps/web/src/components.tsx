import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { pair } from './api'
import { useApp } from './app-context'

export function Badge({
  tone = 'neutral',
  children,
}: {
  tone?: 'neutral' | 'green' | 'blue' | 'amber' | 'danger' | 'demo'
  children: ReactNode
}) {
  return (
    <span className={`badge ${tone}`}>
      <span className="dot" aria-hidden="true" />
      {children}
    </span>
  )
}

export function Modal({
  open,
  onClose,
  title,
  children,
  wide,
}: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  wide?: boolean
}) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      className={wide ? 'modal modal-wide' : 'modal'}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose()
      }}
      aria-label={title}
    >
      <div className="modal-head">
        <h2>{title}</h2>
        <button type="button" className="btn" onClick={onClose}>
          关闭
        </button>
      </div>
      <div className="modal-body">{children}</div>
    </dialog>
  )
}

export function PairDialog() {
  const { pairDialogOpen, setPairDialogOpen, setPaired, toast } = useApp()
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (pairDialogOpen) {
      setCode('')
      setError(null)
    }
  }, [pairDialogOpen])

  async function submit() {
    const value = code.trim()
    if (!value) {
      setError('请输入配对码。')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await pair(value)
      setPaired(true)
      setPairDialogOpen(false)
      toast('配对成功，本会话已获得访问授权。')
    } catch (err) {
      setError(err instanceof Error ? err.message : '配对失败。')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open={pairDialogOpen} onClose={() => setPairDialogOpen(false)} title="配对授权">
      <p className="sub">
        后端要求配对后才能继续。请输入启动后端时显示的配对码；配对状态保存在后端会话中。
      </p>
      <label htmlFor="pair-code">配对码</label>
      <input
        id="pair-code"
        value={code}
        onChange={(e) => setCode(e.target.value)}
        autoComplete="off"
        placeholder="例如 123456"
      />
      {error && <p className="form-error">{error}</p>}
      <div className="modal-actions">
        <button type="button" className="btn primary" disabled={busy} onClick={() => void submit()}>
          {busy ? '配对中…' : '配对'}
        </button>
      </div>
    </Modal>
  )
}
