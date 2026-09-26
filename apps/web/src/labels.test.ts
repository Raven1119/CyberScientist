import { describe, expect, it } from 'vitest'
import { trialStatusLabel } from './labels'

describe('Trial delivery label', () => {
  it('preserves delivery when an old Trial was later marked interrupted', () => {
    expect(trialStatusLabel('interrupted', true)).toBe('已交付 · 后被终止')
    expect(trialStatusLabel('interrupted', false)).toBe('已中断')
    expect(trialStatusLabel('reported_complete', true)).toBe('已交付')
  })
})
