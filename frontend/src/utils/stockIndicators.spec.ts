import { describe, expect, it } from 'vitest'
import { calcMACD, calcMACDHistogram, calcSKDJ } from './stockIndicators'

describe('stockIndicators', () => {
  it('calcMACD returns aligned dif/dea arrays', () => {
    const closes = Array.from({ length: 40 }, (_, i) => 10 + i * 0.2)
    const { dif, dea } = calcMACD(closes)
    expect(dif.length).toBe(closes.length)
    expect(dea.length).toBe(closes.length)
    expect(dif.at(-1)).not.toBeNaN()
    expect(dea.at(-1)).not.toBeNaN()
  })

  it('calcMACDHistogram preserves negative bars below zero', () => {
    const bars = calcMACDHistogram([1, -1, 0.2], [0.5, -0.5, 0.4])
    expect(bars).toEqual([1, -1, -0.4])
    expect(bars[0]).toBeGreaterThan(0)
    expect(bars[1]).toBeLessThan(0)
    expect(bars[2]).toBeLessThan(0)
  })

  it('calcSKDJ produces values after warmup window', () => {
    const n = 30
    const highs = Array.from({ length: n }, (_, i) => 11 + i * 0.1)
    const lows = Array.from({ length: n }, (_, i) => 9 + i * 0.08)
    const closes = Array.from({ length: n }, (_, i) => 10 + i * 0.09)
    const { sk, sd } = calcSKDJ(highs, lows, closes)
    expect(sk.length).toBe(n)
    expect(sd.length).toBe(n)
    expect(sk.at(-1)).not.toBeNull()
    expect(sd.at(-1)).not.toBeNull()
  })
})
