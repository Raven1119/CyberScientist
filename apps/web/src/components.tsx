import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'

export function Badge({
  tone = 'neutral',
  children,
}: {
  tone?: 'neutral' | 'green' | 'blue' | 'amber' | 'danger' | 'demo' | 'purple'
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
