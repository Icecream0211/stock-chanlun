import { describe, expect, it } from 'vitest'
import { downsampleKlines, klineSeriesSignature, KLINE_DISPLAY_MAX } from './chartDownsample'
import type { KLine } from '../api/stock'

function makeKlines(n: number): KLine[] {
  return Array.from({ length: n }, (_, i) => ({
    date: `2024-01-${String((i % 28) + 1).padStart(2, '0')}`,
    open: 10 + i * 0.01,
    high: 10.5 + i * 0.01,
    low: 9.5 + i * 0.01,
    close: 10 + i * 0.01,
    volume: 1000 + i,
  }))
}

describe('chartDownsample', () => {
  it('returns original array when under max points', () => {
    const klines = makeKlines(100)
    expect(downsampleKlines(klines)).toBe(klines)
  })

  it('reduces large series while keeping first and last', () => {
    const klines = makeKlines(1200)
    const out = downsampleKlines(klines, KLINE_DISPLAY_MAX)
    expect(out.length).toBeLessThanOrEqual(KLINE_DISPLAY_MAX)
    expect(out[0]).toEqual(klines[0])
    expect(out.at(-1)).toEqual(klines.at(-1))
  })

  it('retains structural endpoint anchors while downsampling', () => {
    const klines = makeKlines(1200).map((k, i) => ({
      ...k,
      date: `2024-01-01 09:${String(Math.floor(i / 60) % 60).padStart(2, '0')}:${String(i % 60).padStart(2, '0')}`,
    }))
    const anchor = klines[350].date
    const out = downsampleKlines(klines, 100, [anchor])
    expect(out.some(k => k.date === anchor)).toBe(true)
  })

  it('klineSeriesSignature changes when last bar updates', () => {
    const klines = makeKlines(3)
    const sig1 = klineSeriesSignature(klines)
    klines[2] = { ...klines[2], close: klines[2].close + 1 }
    expect(klineSeriesSignature(klines)).not.toBe(sig1)
  })

  it('klineSeriesSignature is stable for identical series', () => {
    const klines = makeKlines(10)
    expect(klineSeriesSignature(klines)).toBe(klineSeriesSignature([...klines]))
  })
})
