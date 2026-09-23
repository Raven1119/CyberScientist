import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { enter } from './design/motion'

export function LoadingState({ children = '正在加载…' }: { children?: ReactNode }) {
  return <div className="loading-state" role="status"><span className="loading-mark" aria-hidden="true">···</span>{children}</div>
}

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
  // 只有「按下」和「抬起」都在背板上才关闭：输入框里拖选文本后
  // 在背板松手时 click 的 target 也是 dialog，不能因此误关。
  const downOnBackdrop = useRef(false)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) {
      dialog.showModal()
      return enter(dialog, 16)
    }
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      className={wide ? 'modal modal-wide' : 'modal'}
      onClose={onClose}
      onMouseDown={(e) => {
        downOnBackdrop.current = e.target === ref.current
      }}
      onClick={(e) => {
        const wasDownOnBackdrop = downOnBackdrop.current
        downOnBackdrop.current = false
        if (e.target === ref.current && wasDownOnBackdrop) onClose()
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
