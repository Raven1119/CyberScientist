import { describe, expect, it } from 'vitest'
import { eventLabel, eventText, trialStatusLabel } from './labels'

describe('Trial delivery label', () => {
  it('preserves delivery when an old Trial was later marked interrupted', () => {
    expect(trialStatusLabel('interrupted', true)).toBe('已交付 · 后被终止')
    expect(trialStatusLabel('interrupted', false)).toBe('已中断')
    expect(trialStatusLabel('reported_complete', true)).toBe('已交付')
  })
})

it('shows PI file source and page receipt without exposing file contents', () => {
  expect(eventLabel('brain.file_read')).toBe('PI 读取文件')
  expect(eventText({type: 'brain.file_read', payload: {
    scope: 'trials', path: 'trial-1/results/output.json', bytes: 12000,
    sha256: 'abcdef0123456789', content: 'private raw body',
  }})).toBe('trials/trial-1/results/output.json · 12000 字节 · SHA abcdef012345')
})
