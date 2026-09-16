import { describe, expect, it } from 'vitest'
import { shouldLoadEarlierWindow, windowStartBefore } from './klineWindow'

describe('K line incremental window policy', () => {
  it.each([
    ['1min', '2026-09-09 15:00:00'],
    ['30min', '2026-09-09 15:00:00'],
    ['daily', '2026-09-09 00:00:00'],
    ['weekly', '2026-09-07 00:00:00'],
    ['monthly', '2026-09-01 00:00:00'],
  ] as const)('plans an earlier same-level window for %s', (level, firstDate) => {
    const next = windowStartBefore(firstDate, level, 160, '2024-09-08')
    expect(next).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(next >= '2024-09-08').toBe(true)
    expect(next < firstDate.slice(0, 10)).toBe(true)
  })

  it('loads only when the visible window is close to the cached left edge', () => {
    expect(shouldLoadEarlierWindow({ viewStart: 8, viewEnd: 167, total: 500 })).toBe(true)
    expect(shouldLoadEarlierWindow({ viewStart: 80, viewEnd: 239, total: 500 })).toBe(false)
  })
})
