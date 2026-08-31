import { describe, expect, it } from 'vitest'
import {
  buildChanlunGraphicChildren,
  buildChanlunOverlayCache,
  resolveDataZoomViewRange,
} from './chartOverlayCore'

describe('chartOverlayCore', () => {
  it('resolveDataZoomViewRange clamps to series length', () => {
    const { viewS, viewE } = resolveDataZoomViewRange(100, [{ startValue: -5, endValue: 200 }])
    expect(viewS).toBe(0)
    expect(viewE).toBe(99)
  })

  it('buildChanlunOverlayCache maps bis to bar indices', () => {
    const dates = ['2024-01-02', '2024-01-03', '2024-01-04']
    const klines = dates.map((d, i) => ({
      date: d,
      open: 10 + i,
      high: 11 + i,
      low: 9 + i,
      close: 10.5 + i,
      volume: 1000,
    }))
    const cache = buildChanlunOverlayCache({
      dates,
      seriesKlines: klines,
      bis: [{
        id: 'b1',
        start: '2024-01-02',
        end: '2024-01-04',
        direction: 'up',
        high: 12,
        low: 9,
        start_price: 9,
        end_price: 12,
      }],
      zhongshus: [],
      signals: [],
      flags: {
        bis: true,
        xiangs: false,
        zhongshus: false,
        signals: false,
        aiLines: false,
        supportResistance: false,
      },
    })
    expect(cache.bis).toHaveLength(1)
    expect(cache.bis[0]._s).toBe(0)
    expect(cache.bis[0]._e).toBe(2)
  })

  it('renders adjacent bis as one continuous high-contrast polyline', () => {
    const dates = ['2024-01-02', '2024-01-03', '2024-01-04']
    const seriesKlines = dates.map(date => ({ date, open: 10, high: 12, low: 9, close: 10, volume: 1 }))
    const data = buildChanlunOverlayCache({
      dates,
      seriesKlines,
      bis: [
        { id: 'b1', start: dates[0], end: dates[1], direction: 'up', high: 12, low: 9, start_price: 9, end_price: 12 },
        { id: 'b2', start: dates[1], end: dates[2], direction: 'down', high: 12, low: 9, start_price: 12, end_price: 9 },
      ],
      zhongshus: [], signals: [],
      flags: { bis: true, xiangs: false, zhongshus: false, signals: false, aiLines: false, supportResistance: false },
    })
    const children = buildChanlunGraphicChildren({
      data, viewS: 0, viewE: 2, gridLeft: 0, gridRight: 200,
      pixelAtIdx: (i, price) => [i * 100, price],
      theme: {
        upColor: '#f00', downColor: '#0f0', biColor: '#29f', segmentColor: '#f80',
        zhongshuStroke: '#f36', zhongshuFill: 'rgba(255,0,0,.1)', strokeBg: '#000',
        labelFont: 'sans-serif', signalRadius: 8, signalFontSize: 11, zsLabelFontSize: 9,
        srLabelFontSize: 9, aiFontSize: 11, resonanceFontSize: 9, buyColors: {}, sellColors: {},
      },
    })
    const polylines = children.filter(item => item.type === 'polyline')
    expect(polylines).toHaveLength(1)
    expect((polylines[0].shape as { points: unknown[] }).points).toHaveLength(3)
  })

  it('renders a non-zero zhongshu rectangle using ECharts shape coordinates', () => {
    const dates = ['2024-01-02', '2024-01-03', '2024-01-04']
    const seriesKlines = dates.map(date => ({ date, open: 10, high: 12, low: 9, close: 10, volume: 1 }))
    const data = buildChanlunOverlayCache({
      dates, seriesKlines, bis: [], signals: [],
      zhongshus: [{ id: 'zs1', start: dates[0], end: dates[2], range_high: 11, range_low: 9 }],
      flags: { bis: false, xiangs: false, zhongshus: true, signals: false, aiLines: false, supportResistance: false },
    })
    const children = buildChanlunGraphicChildren({
      data, viewS: 0, viewE: 2, gridLeft: 0, gridRight: 200,
      pixelAtIdx: (i, price) => [i * 100, 100 - price],
      theme: {
        upColor: '#f00', downColor: '#0f0', biColor: '#29f', segmentColor: '#f80',
        zhongshuStroke: '#f36', zhongshuFill: 'rgba(255,0,0,.1)', strokeBg: '#000',
        labelFont: 'sans-serif', signalRadius: 8, signalFontSize: 11, zsLabelFontSize: 9,
        srLabelFontSize: 9, aiFontSize: 11, resonanceFontSize: 9, buyColors: {}, sellColors: {},
      },
    })
    const rect = children.find(item => item.type === 'rect')
    expect(rect).toBeDefined()
    expect((rect?.shape as { width: number }).width).toBe(200)
  })
})
