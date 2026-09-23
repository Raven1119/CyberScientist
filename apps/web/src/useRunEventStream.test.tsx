import { StrictMode } from 'react'
import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useRunEventStream } from './useRunEventStream'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers() })

function source() {
  let controller!: ReadableStreamDefaultController<Uint8Array>
  const cancelled = vi.fn()
  const stream = new ReadableStream<Uint8Array>({ start: value => { controller = value }, cancel: cancelled })
  return {
    response: new Response(stream), cancelled,
    send: (seq: number, run = 'A') => controller.enqueue(new TextEncoder().encode(
      `data: ${JSON.stringify({ seq, id: `${run}_${seq}`, run_id: run, type: 'execution.progress' })}\n\n`)),
    close: () => controller.close(), fail: () => controller.error(new Error('connection lost')),
  }
}
const flush = () => act(async () => { await Promise.resolve() })

describe('Run event stream lifecycle', () => {
  it('keeps its cursor when the same Run becomes terminal and archives its stream once', async () => {
    const stream = source(), events = vi.fn(), statuses = vi.fn()
    const fetch = vi.fn().mockResolvedValue(stream.response)
    vi.stubGlobal('fetch', fetch)
    const { rerender } = renderHook(({ terminal }) => useRunEventStream('A', events,
      { terminal, onStatus: statuses }), { initialProps: { terminal: false } })
    await flush()
    await act(async () => { stream.send(1) })
    rerender({ terminal: true })
    await act(async () => { stream.send(1); stream.send(2); stream.close() })
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(events.mock.calls.map(([event]) => event.seq)).toEqual([1, 2])
    expect(statuses).toHaveBeenLastCalledWith('closed')
  })

  it('resumes after the delivered sequence on disconnect and deduplicates replay', async () => {
    vi.useFakeTimers()
    const first = source(), second = source(), events = vi.fn()
    const fetch = vi.fn().mockResolvedValueOnce(first.response).mockResolvedValueOnce(second.response)
    vi.stubGlobal('fetch', fetch)
    renderHook(() => useRunEventStream('A', events))
    await flush()
    await act(async () => { first.send(7) })
    await act(async () => { first.fail() })
    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
    expect(fetch.mock.calls[1][0]).toBe('/api/v1/runs/A/events?after=7')
    await act(async () => { second.send(7); second.send(8) })
    expect(events.mock.calls.map(([event]) => event.seq)).toEqual([7, 8])
  })

  it('does not reconnect if the terminal snapshot arrives after a clean EOF', async () => {
    vi.useFakeTimers()
    const stream = source(), events = vi.fn(), statuses = vi.fn()
    const fetch = vi.fn().mockResolvedValue(stream.response)
    vi.stubGlobal('fetch', fetch)
    const { rerender } = renderHook(({ terminal }) => useRunEventStream('A', events,
      { terminal, onStatus: statuses }), { initialProps: { terminal: false } })
    await flush()
    await act(async () => { stream.send(1); stream.close() })
    rerender({ terminal: true })
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(statuses).toHaveBeenLastCalledWith('closed')
  })

  it('isolates Run cursors and rejects an old pending read after switching Run', async () => {
    const first = source(), second = source(), events = vi.fn()
    const fetch = vi.fn().mockResolvedValueOnce(first.response).mockResolvedValueOnce(second.response)
    vi.stubGlobal('fetch', fetch)
    const { rerender } = renderHook(({ run }) => useRunEventStream(run, events),
      { initialProps: { run: 'A' } })
    await flush()
    await act(async () => { first.send(9) })
    rerender({ run: 'B' })
    await flush()
    await act(async () => { first.send(10); second.send(1, 'B') })
    expect(fetch.mock.calls[1][0]).toBe('/api/v1/runs/B/events?after=0')
    expect(events.mock.calls.map(([event]) => event.id)).toEqual(['A_9', 'B_1'])
  })

  it('drops a late cancelled fetch under StrictMode without publishing its events or status', async () => {
    const first = source(), second = source(), events = vi.fn(), statuses = vi.fn()
    let resolveFirst!: (response: Response) => void
    const late = new Promise<Response>(resolve => { resolveFirst = resolve })
    const fetch = vi.fn().mockReturnValueOnce(late).mockResolvedValueOnce(second.response)
    vi.stubGlobal('fetch', fetch)
    renderHook(() => useRunEventStream('A', events, { onStatus: statuses }),
      { wrapper: ({ children }) => <StrictMode>{children}</StrictMode> })
    await flush()
    await act(async () => { second.send(1) })
    await act(async () => { first.send(99); resolveFirst(first.response) })
    expect(fetch).toHaveBeenCalledTimes(2)
    expect((fetch.mock.calls[0][1] as RequestInit).signal?.aborted).toBe(true)
    expect(first.cancelled).toHaveBeenCalledTimes(1)
    expect(events.mock.calls.map(([event]) => event.seq)).toEqual([1])
    expect(statuses.mock.calls.filter(([status]) => status === 'open')).toHaveLength(1)
  })
})
