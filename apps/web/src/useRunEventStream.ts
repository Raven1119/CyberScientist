import { useEffect } from 'react'
import type { RunEvent } from './types'
import { useStableCallback } from './app-context'

const MAX_RETRY_DELAY_MS = 8000

export type StreamStatus = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed'

export interface RunEventStreamOptions {
  onStatus?: (status: StreamStatus) => void
  /** 终态 Run：服务端回放完历史事件后流自然结束，归档而不再重连。 */
  terminal?: boolean
}

/**
 * 维持到指定 Run 的 SSE 事件流。组件卸载时关闭连接；
 * 断线后用已收到的最大 seq 通过 after= 重连；按 seq 去重。
 * 通过 onStatus 上报连接状态，供界面显示断线/重连提示。
 */
export function useRunEventStream(
  runId: string | null,
  onEvent: (event: RunEvent) => void,
  options?: RunEventStreamOptions,
): void {
  const handleEvent = useStableCallback(onEvent)
  const reportStatus = useStableCallback(options?.onStatus ?? (() => undefined))
  const terminal = options?.terminal ?? false

  useEffect(() => {
    if (!runId) {
      reportStatus('idle')
      return
    }
    let cancelled = false
    let retryTimer = 0
    let retryDelay = 1000
    let maxSeq = 0
    let everConnected = false
    const abort = new AbortController()

    async function connect(): Promise<void> {
      reportStatus(everConnected ? 'reconnecting' : 'connecting')
      let endedCleanly = false
      try {
        const res = await fetch(`/api/v1/runs/${runId}/events?after=${maxSeq}`, {
          signal: abort.signal,
        })
        if (!res.ok || !res.body) {
          throw new Error(`events HTTP ${res.status}`)
        }
        retryDelay = 1000
        everConnected = true
        reportStatus('open')
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        for (;;) {
          const { done, value } = await reader.read()
          if (done) {
            endedCleanly = true
            break
          }
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
      if (cancelled) return
      if (endedCleanly && terminal) {
        // 终态 Run 的历史回放已结束，不再重连，标记为已归档
        reportStatus('closed')
        return
      }
      reportStatus('reconnecting')
      retryTimer = window.setTimeout(() => {
        void connect()
      }, retryDelay)
      retryDelay = Math.min(retryDelay * 2, MAX_RETRY_DELAY_MS)
    }

    void connect()
    return () => {
      cancelled = true
      window.clearTimeout(retryTimer)
      abort.abort()
    }
  }, [runId, handleEvent, reportStatus, terminal])
}
