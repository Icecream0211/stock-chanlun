import { describe, expect, it } from 'vitest'
import {
  buildChanlunGraphicChildren,
  buildChanlunOverlayCache,
  CHANLUN_OVERLAY_THEME_PC,
  resolveDataZoomViewRange,
} from './chartOverlayCore'

describe('chartOverlayCore', () => {
  it('resolveDataZoomViewRange clamps to series length', () => {
    const { viewS, viewE } = resolveDataZoomViewRange(100, [{ startValue: -5, endValue: 200 }])
    expect(viewS).toBe(0)
    expect(viewE).toBe(99)
  })

  it('falls back to zoom percentages when category startValue is a date string', () => {
    const { viewS, viewE } = resolveDataZoomViewRange(101, [{
      startValue: '2025-01-01',
      endValue: '2026-01-01',
      start: 70,
      end: 90,
    }])
    expect(viewS).toBe(70)
    expect(viewE).toBe(90)
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
        biZhongshus: false,
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

  it('renders inclusion as a compact bracket with a tiny count label', () => {
    const dates = ['2024-01-02', '2024-01-03', '2024-01-04']
    const seriesKlines = dates.map(date => ({ date, open: 10, high: 12, low: 9, close: 10, volume: 1 }))
    const data = buildChanlunOverlayCache({
      dates,
      seriesKlines,
      inclusions: [{
        start: dates[0], end: dates[2], merged_date: dates[1], direction: 'up', count: 3,
        high: 12, low: 9, high_date: dates[1], low_date: dates[2],
      }],
      bis: [], zhongshus: [], signals: [],
      flags: {
        inclusions: true, bis: false, biZhongshus: false, xiangs: false,
        zhongshus: false, signals: false, aiLines: false, supportResistance: false,
      },
    })

    const children = buildChanlunGraphicChildren({
      data, viewS: 0, viewE: 2, gridLeft: 0, gridRight: 40,
      pixelAtIdx: (i, price) => [i * 20, 100 - price],
      theme: CHANLUN_OVERLAY_THEME_PC,
    })

    const bracket = children.find(item => item.type === 'polyline')
    const label = children.find(item => item.type === 'text')
    expect((bracket?.shape as { points: unknown[] }).points).toHaveLength(4)
    expect((bracket?.style as { lineWidth?: number }).lineWidth).toBe(1)
    expect((label?.style as { text?: string; font?: string }).text).toBe('含3')
    expect((label?.style as { font?: string }).font).toContain('8px')
  })

  it('renders a located multi-factor divergence marker on the second pen endpoint', () => {
    const dates = ['2024-01-02', '2024-01-03', '2024-01-04']
    const seriesKlines = dates.map(date => ({ date, open: 10, high: 12, low: 9, close: 10, volume: 1 }))
    const data = buildChanlunOverlayCache({
      dates,
      seriesKlines,
      bis: [], zhongshus: [], signals: [],
      aiSignal: {
        stock_code: '000001', level: 'daily', direction: '观望', confidence: 0.7,
        risk_level: '中', holding_period: '1-4周', description: '', trend: '上涨',
        divergences: [{
          type: 'top', probability: 0.86, description: '价格新高但力度减弱',
          datetime: dates[2], price: 12, previous_datetime: dates[0], previous_price: 11,
          confirmations: ['MACD', 'RSI', 'KDJ'], confirm_count: 3,
        }],
      },
      flags: {
        divergences: true, bis: false, biZhongshus: false, xiangs: false,
        zhongshus: false, signals: false, aiLines: false, supportResistance: false,
      },
    })

    expect(data.divergences[0]._idx).toBe(2)
    expect(data.divergences[0]._previousIdx).toBe(0)

    const children = buildChanlunGraphicChildren({
      data, viewS: 0, viewE: 2, gridLeft: 0, gridRight: 40,
      pixelAtIdx: (i, price) => [i * 20, 100 - price],
      theme: CHANLUN_OVERLAY_THEME_PC,
    })
    const label = children.find(item => item.type === 'text')
    expect((label?.style as { text?: string }).text).toBe('力顶·L1·A')
    expect(children.some(item => item.type === 'circle')).toBe(true)
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
      flags: { bis: true, biZhongshus: false, xiangs: false, zhongshus: false, signals: false, aiLines: false, supportResistance: false },
    })
    const children = buildChanlunGraphicChildren({
      data, viewS: 0, viewE: 2, gridLeft: 0, gridRight: 200,
      pixelAtIdx: (i, price) => [i * 100, price],
      theme: {
        upColor: '#f00', downColor: '#0f0', biColor: '#29f', biZhongshuStroke: '#29f', biZhongshuFill: 'rgba(0,0,255,.1)', segmentColor: '#f80',
        zhongshuStroke: '#f36', zhongshuFill: 'rgba(255,0,0,.1)', strokeBg: '#000',
        labelFont: 'sans-serif', signalRadius: 8, signalFontSize: 11, zsLabelFontSize: 9,
        srLabelFontSize: 9, aiFontSize: 11, resonanceFontSize: 9, buyColors: {}, sellColors: {},
      },
    })
    const polylines = children.filter(item => item.type === 'polyline')
    expect(polylines).toHaveLength(1)
    expect((polylines[0].shape as { points: unknown[] }).points).toHaveLength(3)
  })

  it('renders the virtual tail connected to the confirmed pen with a dashed style', () => {
    const dates = ['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05']
    const seriesKlines = dates.map(date => ({ date, open: 10, high: 12, low: 9, close: 10, volume: 1 }))
    const data = buildChanlunOverlayCache({
      dates,
      seriesKlines,
      bis: [
        { id: 'b1', start: dates[0], end: dates[1], direction: 'up', high: 12, low: 9, start_price: 9, end_price: 12 },
        { id: 'b2', start: dates[1], end: dates[2], direction: 'down', high: 12, low: 10, start_price: 12, end_price: 10 },
        { id: 'b3', start: dates[2], end: dates[3], direction: 'up', high: 11.5, low: 10, start_price: 10, end_price: 11.5, confirmed: false },
      ],
      zhongshus: [], signals: [],
      flags: { bis: true, biZhongshus: false, xiangs: false, zhongshus: false, signals: false, aiLines: false, supportResistance: false },
    })
    const children = buildChanlunGraphicChildren({
      data, viewS: 0, viewE: 3, gridLeft: 0, gridRight: 300,
      pixelAtIdx: (i, price) => [i * 100, price],
      theme: {
        upColor: '#f00', downColor: '#0f0', biColor: '#29f', biZhongshuStroke: '#29f', biZhongshuFill: 'rgba(0,0,255,.1)', segmentColor: '#f80',
        zhongshuStroke: '#f36', zhongshuFill: 'rgba(255,0,0,.1)', strokeBg: '#000',
        labelFont: 'sans-serif', signalRadius: 8, signalFontSize: 11, zsLabelFontSize: 9,
        srLabelFontSize: 9, aiFontSize: 11, resonanceFontSize: 9, buyColors: {}, sellColors: {},
      },
    })

    const polylines = children.filter(item => item.type === 'polyline')
    expect(polylines).toHaveLength(2)
    const confirmedPoints = (polylines[0].shape as { points: number[][] }).points
    const virtualPoints = (polylines[1].shape as { points: number[][] }).points
    expect(confirmedPoints.at(-1)).toEqual(virtualPoints[0])
    expect((polylines[1].style as { lineDash?: number[] }).lineDash).toEqual([7, 5])
  })

  it('renders a non-zero zhongshu rectangle using ECharts shape coordinates', () => {
    const dates = ['2024-01-02', '2024-01-03', '2024-01-04']
    const seriesKlines = dates.map(date => ({ date, open: 10, high: 12, low: 9, close: 10, volume: 1 }))
    const data = buildChanlunOverlayCache({
      dates, seriesKlines, bis: [], signals: [],
      zhongshus: [{ id: 'zs1', start: dates[0], end: dates[2], range_high: 11, range_low: 9 }],
      flags: { bis: false, biZhongshus: false, xiangs: false, zhongshus: true, signals: false, aiLines: false, supportResistance: false },
    })
    const children = buildChanlunGraphicChildren({
      data, viewS: 0, viewE: 2, gridLeft: 0, gridRight: 200,
      pixelAtIdx: (i, price) => [i * 100, 100 - price],
      theme: {
        upColor: '#f00', downColor: '#0f0', biColor: '#29f', biZhongshuStroke: '#29f', biZhongshuFill: 'rgba(0,0,255,.1)', segmentColor: '#f80',
        zhongshuStroke: '#f36', zhongshuFill: 'rgba(255,0,0,.1)', strokeBg: '#000',
        labelFont: 'sans-serif', signalRadius: 8, signalFontSize: 11, zsLabelFontSize: 9,
        srLabelFontSize: 9, aiFontSize: 11, resonanceFontSize: 9, buyColors: {}, sellColors: {},
      },
    })
    const rect = children.find(item => item.type === 'rect')
    expect(rect).toBeDefined()
    expect((rect?.shape as { width: number }).width).toBe(200)
  })

  it('renders pen and segment centers with distinct colors and line styles', () => {
    const dates = ['2024-01-02', '2024-01-03', '2024-01-04']
    const seriesKlines = dates.map(date => ({ date, open: 10, high: 12, low: 9, close: 10, volume: 1 }))
    const data = buildChanlunOverlayCache({
      dates,
      seriesKlines,
      bis: [],
      biZhongshus: [{ id: 'bi-zs', start: dates[0], end: dates[1], range_high: 10.5, range_low: 9.5 }],
      zhongshus: [{ id: 'seg-zs', start: dates[1], end: dates[2], range_high: 11, range_low: 10 }],
      signals: [],
      flags: { bis: false, biZhongshus: true, xiangs: false, zhongshus: true, signals: false, aiLines: false, supportResistance: false },
    })
    const children = buildChanlunGraphicChildren({
      data, viewS: 0, viewE: 2, gridLeft: 0, gridRight: 200,
      pixelAtIdx: (i, price) => [i * 100, 100 - price],
      theme: {
        upColor: '#f00', downColor: '#0f0', biColor: '#29f', biZhongshuStroke: '#29f', biZhongshuFill: 'rgba(0,0,255,.1)', segmentColor: '#f80',
        zhongshuStroke: '#f36', zhongshuFill: 'rgba(255,0,0,.1)', strokeBg: '#000',
        labelFont: 'sans-serif', signalRadius: 8, signalFontSize: 11, zsLabelFontSize: 9,
        srLabelFontSize: 9, aiFontSize: 11, resonanceFontSize: 9, buyColors: {}, sellColors: {},
      },
    })
    const rects = children.filter(item => item.type === 'rect')
    const penStyle = rects[0].style as { stroke?: string; lineDash?: number[] }
    const segmentStyle = rects[1].style as { stroke?: string; lineDash?: number[] }
    expect(rects).toHaveLength(2)
    expect(penStyle.stroke).toBe('#29f')
    expect(penStyle.lineDash).toEqual([6, 4])
    expect(segmentStyle.stroke).toBe('#f36')
    expect(segmentStyle.lineDash).toBeUndefined()
  })

  it('renders an expanded center as unobtrusive corner brackets', () => {
    const dates = ['2024-01-02', '2024-01-03', '2024-01-04']
    const seriesKlines = dates.map(date => ({ date, open: 10, high: 12, low: 9, close: 10, volume: 1 }))
    const data = buildChanlunOverlayCache({
      dates,
      seriesKlines,
      bis: [],
      zhongshus: [{
        id: 'expanded-zs', start: dates[0], end: dates[2], range_high: 11, range_low: 9,
        level: 3, status: 'expanded', expansion_type: 'nine_structure',
      }],
      signals: [],
      flags: { bis: false, biZhongshus: false, xiangs: false, zhongshus: true, signals: false, aiLines: false, supportResistance: false },
    })
    const children = buildChanlunGraphicChildren({
      data, viewS: 0, viewE: 2, gridLeft: 0, gridRight: 200,
      pixelAtIdx: (i, price) => [i * 100, 100 - price],
      theme: {
        upColor: '#f00', downColor: '#0f0', biColor: '#29f', biZhongshuStroke: '#29f', biZhongshuFill: 'rgba(0,0,255,.1)', segmentColor: '#f80',
        zhongshuStroke: '#f36', zhongshuFill: 'rgba(255,0,0,.1)', strokeBg: '#000',
        labelFont: 'sans-serif', signalRadius: 8, signalFontSize: 11, zsLabelFontSize: 9,
        srLabelFontSize: 9, aiFontSize: 11, resonanceFontSize: 9, buyColors: {}, sellColors: {},
      },
    })

    const corners = children.filter(item => item.type === 'polyline')
    const label = children.find(item => item.type === 'text')
    expect(children.some(item => item.type === 'rect')).toBe(false)
    expect(corners).toHaveLength(4)
    expect((corners[0].style as { lineDash?: number[] }).lineDash).toEqual([5, 4])
    expect((label?.style as { text?: string }).text).toBe('9结构升L3')
  })
})
