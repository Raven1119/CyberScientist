import { useEffect } from 'react'
import { notifyPairingRequired } from './api'
import type { RunEvent } from './types'
import { useStableCallback } from './app-context'

const MAX_RETRY_DELAY_MS = 8000

/**
 * 维持到指定 Run 的 SSE 事件流。组件卸载时关闭连接；
 * 断线后用已收到的最大 seq 通过 after= 重连；按 seq 去重。
 */
export function useRunEventStream(runId: string | null, onEvent: (event: RunEvent) => void): void {
  const handleEvent = useStableCallback(onEvent)

  useEffect(() => {
    if (!runId) return
    let cancelled = false
    let retryTimer = 0
    let retryDelay = 1000
    let maxSeq = 0
    const abort = new AbortController()

    async function connect(): Promise<void> {
      try {
        const res = await fetch(`/api/v1/runs/${runId}/events?after=${maxSeq}`, {
          signal: abort.signal,
          credentials: 'same-origin',
        })
        if (res.status === 401) {
          const data = await res.json().catch(() => null)
          if (data?.code === 'PAIRING_REQUIRED') {
            notifyPairingRequired()
            return
          }
        }
        if (!res.ok || !res.body) {
          throw new Error(`events HTTP ${res.status}`)
        }
        retryDelay = 1000
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        for (;;) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const chunks = buffer.split('\n\n')
          buffer = chunks.pop() ?? ''
          for (const chunk of chunks) {
            for (const line of chunk.split('\n')) {
              if (!line.startsWith('data:')) continue
              try {
                const event = JSON.parse(line.slice(5).trim()) as RunEvent
                if (typeof event.seq === 'number' && event.seq > maxSeq) {
                  maxSeq = event.seq
                  handleEvent(event)
                }
              } catch {
                // 忽略无法解析的行
              }
            }
          }
        }
      } catch {
        // 网络中断或读取失败，进入重连
      }
      if (!cancelled) {
        retryTimer = window.setTimeout(() => {
          void connect()
        }, retryDelay)
        retryDelay = Math.min(retryDelay * 2, MAX_RETRY_DELAY_MS)
      }
    }

    void connect()
    return () => {
      cancelled = true
      window.clearTimeout(retryTimer)
      abort.abort()
    }
  }, [runId, handleEvent])
}
