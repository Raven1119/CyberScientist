import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import TraceGate from './TraceGate'

describe('TraceGate', () => {
  it('preserves unknown evidence and labels replica limitations', () => {
    render(<TraceGate report={{ version: 'v8-advisory-1', conclusion: 'unknown', possible_cap: null,
      checks: [{ code: 'N18', status: 'unknown', reliability: 'unavailable', evidence: { count: null } }],
      visibility: { event_count: 2, over_900: 1 }, missing_evidence: [{ id: 'C01', question: '核对原始输出' }],
      judge_replica_hint: { enabled: true, label: '仅供参考（留出集准确率 54–62%）', status: 'standalone_only' } }} />)
    expect(screen.getByText(/不预测评分/)).toBeTruthy()
    expect(screen.getByText(/N18：无法判定/)).toBeTruthy()
    expect(screen.getByText(/54–62%/)).toBeTruthy()
  })
})
