/**
 * 缠论 ECharts graphic 叠加层 — PC / 移动端共用（索引映射 + 像素渲染）。
 */
import type { KLine, Bi, XiangSegment, Zhongshu, Signal, AISignal, SupportResistance } from '../api/stock'
import { buildDateLookup, dateToIdxRobust, resolveBarRange } from './chartDateUtils'
import { simplifySupportResistanceLevels } from './chartOverlayUtils'
import { CHART_PALETTE } from './chartPalette'

export type GraphicElement = Record<string, unknown>

export type IndexedRange<T> = T & { _s: number; _e: number }
export type IndexedSignal = Signal & { _idx: number }

export type ChanlunOverlayPayload = {
  bis: IndexedRange<Bi>[]
  xiangs: IndexedRange<XiangSegment>[]
  zhongshus: IndexedRange<Zhongshu>[]
  signals: IndexedSignal[]
  aiSignal: AISignal | null | undefined
  supportResistance: SupportResistance[]
  dualCrossIndices: number[]
  _n: number
}

export type ChanlunOverlayFlags = {
  bis: boolean
  xiangs: boolean
  zhongshus: boolean
  signals: boolean
  aiLines: boolean
  supportResistance: boolean
}

export type ChanlunOverlayTheme = {
  upColor: string
  downColor: string
  biColor: string
  segmentColor: string
  zhongshuStroke: string
  zhongshuFill: string
  strokeBg: string
  labelFont: string
  signalRadius: number
  signalFontSize: number
  zsLabelFontSize: number
  srLabelFontSize: number
  aiFontSize: number
  resonanceFontSize: number
  buyColors: Record<string, string>
  sellColors: Record<string, string>
}

export const CHANLUN_OVERLAY_THEME_PC: ChanlunOverlayTheme = {
  upColor: CHART_PALETTE.klineUp,
  downColor: CHART_PALETTE.klineDown,
  biColor: CHART_PALETTE.bi,
  segmentColor: CHART_PALETTE.segment,
  zhongshuStroke: CHART_PALETTE.zhongshuStroke,
  zhongshuFill: CHART_PALETTE.zhongshuFill,
  strokeBg: '#0d1117',
  labelFont: 'Noto Sans SC',
  signalRadius: 8,
  signalFontSize: 11,
  zsLabelFontSize: 9,
  srLabelFontSize: 9,
  aiFontSize: 11,
  resonanceFontSize: 9,
  buyColors: { '一买': '#3fb950', '二买': '#58a6ff', '三买': '#d29922' },
  sellColors: { '一卖': '#f85149', '二卖': '#ff7b72', '三卖': '#da3633' },
}

export const CHANLUN_OVERLAY_THEME_MOBILE: ChanlunOverlayTheme = {
  upColor: CHART_PALETTE.klineUp,
  downColor: CHART_PALETTE.klineDown,
  biColor: CHART_PALETTE.bi,
  segmentColor: CHART_PALETTE.segment,
  zhongshuStroke: CHART_PALETTE.zhongshuStroke,
  zhongshuFill: CHART_PALETTE.zhongshuFill,
  strokeBg: '#06080c',
  labelFont: 'monospace',
  signalRadius: 7,
  signalFontSize: 10,
  zsLabelFontSize: 9,
  srLabelFontSize: 8,
  aiFontSize: 10,
  resonanceFontSize: 8,
  buyColors: { '一买': '#22c55e', '二买': '#38bdf8', '三买': '#f59e0b' },
  sellColors: { '一卖': '#ef4444', '二卖': '#ff7b72', '三卖': '#da3633' },
}

type DataZoomSlice = { startValue?: number; endValue?: number; start?: number; end?: number }

export function resolveDataZoomViewRange(
  datesLength: number,
  dataZoom?: DataZoomSlice[],
): { viewS: number; viewE: number } {
  const dz0 = dataZoom?.[0]
  const vStart = dz0?.startValue ?? 0
  const vEnd = dz0?.endValue ?? (datesLength - 1)
  const viewS = Math.max(0, Math.min(Number(vStart) || 0, datesLength - 1))
  const viewE = Math.max(viewS, Math.min(Number(vEnd) || (datesLength - 1), datesLength - 1))
  return { viewS, viewE }
}

export function createCachedPixelFn(
  pixelAtIdx: (i: number, price: number) => [number, number] | null,
): (i: number, price: number) => [number, number] | null {
  const cache = new Map<string, [number, number] | null>()
  return (i: number, price: number) => {
    const key = `${i}:${price}`
    if (cache.has(key)) return cache.get(key) ?? null
    const pt = pixelAtIdx(i, price)
    cache.set(key, pt)
    return pt
  }
}

export function buildChanlunOverlayCache(params: {
  dates: string[]
  seriesKlines: KLine[]
  bis: Bi[]
  xiangs?: XiangSegment[]
  zhongshus: Zhongshu[]
  signals: Signal[]
  aiSignal?: AISignal | null
  supportResistance?: SupportResistance[]
  flags: ChanlunOverlayFlags
  dualCrossIndices?: number[]
}): ChanlunOverlayPayload {
  const {
    dates,
    seriesKlines,
    bis,
    xiangs,
    zhongshus,
    signals,
    aiSignal,
    supportResistance,
    flags,
    dualCrossIndices = [],
  } = params
  const nBar = dates.length
  const refPx = seriesKlines.length > 0 ? seriesKlines[seriesKlines.length - 1].close : 1
  const dateLookup = buildDateLookup(dates)

  return {
    bis: flags.bis ? bis.flatMap(b => {
      const r = resolveBarRange(b.start, b.end, nBar, dates, dateLookup)
      return r ? [{ ...b, _s: r[0], _e: r[1] }] : []
    }) : [],
    xiangs: flags.xiangs && xiangs ? xiangs.flatMap(x => {
      const r = resolveBarRange(x.start, x.end, nBar, dates, dateLookup)
      return r ? [{ ...x, _s: r[0], _e: r[1] }] : []
    }) : [],
    zhongshus: flags.zhongshus ? zhongshus.flatMap(z => {
      const r = resolveBarRange(z.start, z.end, nBar, dates, dateLookup)
      return r ? [{ ...z, _s: r[0], _e: r[1] }] : []
    }) : [],
    signals: flags.signals ? signals.flatMap(s => {
      const ix = dateToIdxRobust(s.datetime, dates, dateLookup)
      return ix >= 0 ? [{ ...s, _idx: ix }] : []
    }) : [],
    aiSignal: flags.aiLines ? (aiSignal ?? null) : null,
    supportResistance: flags.supportResistance
      ? simplifySupportResistanceLevels(supportResistance || [], refPx)
      : [],
    dualCrossIndices,
    _n: nBar,
  }
}

export function buildChanlunGraphicChildren(ctx: {
  data: ChanlunOverlayPayload
  viewS: number
  viewE: number
  gridLeft: number
  gridRight: number
  pixelAtIdx: (i: number, price: number) => [number, number] | null
  theme: ChanlunOverlayTheme
  /** 共振标记取价；缺省用 pixelAtIdx(i, 0) 的 y（由调用方传入 close） */
  priceAtIdx?: (i: number) => number
}): GraphicElement[] {
  const { data, viewS, viewE, gridLeft, gridRight, theme } = ctx
  const pixelAtIdxCached = createCachedPixelFn(ctx.pixelAtIdx)
  const priceAt = ctx.priceAtIdx ?? (() => 0)
  const children: GraphicElement[] = []

  const { bis, xiangs, zhongshus, signals, aiSignal, supportResistance, dualCrossIndices } = data

  for (const zs of zhongshus) {
    if (zs._e < viewS || zs._s > viewE || zs._e < zs._s) continue
    const a = pixelAtIdxCached(zs._s, zs.range_high)
    const b = pixelAtIdxCached(zs._e, zs.range_low)
    if (!a || !b) continue
    const xPx1 = Math.min(a[0], b[0])
    const xPx2 = Math.max(a[0], b[0])
    const yPx1 = Math.min(a[1], b[1])
    const yPx2 = Math.max(a[1], b[1])
    children.push({
      type: 'rect',
      shape: {
        x: xPx1,
        y: yPx1,
        width: Math.max(xPx2 - xPx1, 4),
        height: Math.max(yPx2 - yPx1, 1),
      },
      style: {
        fill: theme.zhongshuFill,
        stroke: theme.zhongshuStroke,
        lineWidth: 1.25,
        lineDash: zs.confirmed === false ? [6, 4] : undefined,
      },
      z: 96,
      silent: true,
    })
    children.push({
      type: 'text',
      style: {
        text: zs.range_high.toFixed(2),
        fill: theme.zhongshuStroke,
        fontSize: theme.zsLabelFontSize,
        fontFamily: theme.labelFont,
      },
      x: xPx1 + 3, y: yPx1 + 12,
      z: 97, silent: true,
    })
    children.push({
      type: 'text',
      style: {
        text: zs.range_low.toFixed(2),
        fill: theme.zhongshuStroke,
        fontSize: theme.zsLabelFontSize,
        fontFamily: theme.labelFont,
      },
      x: xPx1 + 3, y: yPx2 - 2,
      z: 97, silent: true,
    })
  }

  const appendStructurePolylines = <T extends IndexedRange<Bi | XiangSegment>>(
    items: T[],
    color: string,
    lineWidth: number,
    z: number,
  ) => {
    let points: [number, number][] = []
    let previousEnd = -1
    const flush = () => {
      if (points.length >= 2) {
        children.push({
          type: 'polyline',
          shape: { points },
          style: { stroke: color, fill: null, lineWidth, opacity: 0.96, lineJoin: 'round', lineCap: 'round' },
          z, silent: true,
        })
      }
      points = []
    }

    for (const item of items) {
      if (item._e < viewS || item._s > viewE || item._e < item._s) continue
      const startPrice = item.start_price ?? (item.direction === 'up' ? item.low : item.high)
      const endPrice = item.end_price ?? (item.direction === 'up' ? item.high : item.low)
      const p1 = pixelAtIdxCached(item._s, startPrice)
      const p2 = pixelAtIdxCached(item._e, endPrice)
      if (!p1 || !p2) continue
      if (points.length && previousEnd === item._s) points.push(p2)
      else {
        flush()
        points = [p1, p2]
      }
      previousEnd = item._e
    }
    flush()
  }

  // 笔统一使用电光蓝连续折线；线段使用更粗的橙色，避免和涨跌 K 线混淆。
  appendStructurePolylines(bis, theme.biColor, 1.7, 102)
  appendStructurePolylines(xiangs, theme.segmentColor, 2.8, 103)

  for (const sig of signals) {
    if (sig._idx < viewS || sig._idx > viewE) continue
    const pt = pixelAtIdxCached(sig._idx, sig.price)
    if (!pt) continue
    const color = theme.buyColors[sig.type] || theme.sellColors[sig.type] || '#d29922'
    const isBuy = sig.type.includes('买')
    const r = theme.signalRadius
    children.push({
      type: 'circle',
      shape: { cx: pt[0], cy: pt[1], r },
      style: { fill: color, stroke: theme.strokeBg, lineWidth: 2 },
      z: 103, silent: true,
    })
    children.push({
      type: 'text',
      style: {
        text: sig.type,
        fill: color,
        fontSize: theme.signalFontSize,
        fontWeight: 700,
        fontFamily: theme.labelFont,
        textAlign: 'center',
      },
      x: pt[0],
      y: pt[1] + (isBuy ? -(r + 14) : r + 14),
      z: 104, silent: true,
    })
  }

  for (const lvl of supportResistance) {
    const yp = pixelAtIdxCached(viewS, lvl.price)?.[1]
    if (yp == null || !Number.isFinite(yp)) continue
    const isSupport = lvl.type === 'support'
    const color = isSupport ? theme.downColor : theme.upColor
    const dash = isSupport ? [6, 4] : [8, 4]
    const label = isSupport ? `撑 ${lvl.price.toFixed(2)}` : `阻 ${lvl.price.toFixed(2)}`
    const strength = lvl.strength ?? 0.5
    const lw = 0.55 + strength * 0.45
    children.push({
      type: 'line',
      shape: { x1: gridLeft, y1: yp, x2: gridRight, y2: yp },
      style: { stroke: color, lineWidth: lw, opacity: 0.22 + strength * 0.28, lineDash: dash },
      z: 98, silent: true,
    })
    children.push({
      type: 'text',
      style: {
        text: label,
        fill: color,
        fontSize: theme.srLabelFontSize,
        fontFamily: theme.labelFont,
        opacity: 0.45 + strength * 0.35,
      },
      x: gridLeft + 6, y: yp - 4,
      z: 99, silent: true,
    })
  }

  if (aiSignal) {
    const entryColor = aiSignal.direction === '买入' ? theme.downColor : theme.upColor
    const hLine = (price: number, stroke: string, dash: number[], lw: number, label?: string, labelYOffset = -6) => {
      const yp = pixelAtIdxCached(viewS, price)?.[1]
      if (yp == null || !Number.isFinite(yp)) return
      children.push({
        type: 'line',
        shape: { x1: gridLeft, y1: yp, x2: gridRight, y2: yp },
        style: { stroke, lineWidth: lw, opacity: 0.85, lineDash: dash },
        z: 99, silent: true,
      })
      if (label) {
        children.push({
          type: 'text',
          style: { text: label, fill: stroke, fontSize: theme.aiFontSize, fontWeight: 700, fontFamily: theme.labelFont },
          x: gridLeft + 8, y: yp + labelYOffset,
          z: 104, silent: true,
        })
      }
    }
    if (aiSignal.entry_price != null) {
      hLine(aiSignal.entry_price, entryColor, [7, 4], 1.5, `入场 ${aiSignal.entry_price.toFixed(2)}`, -6)
    }
    if (aiSignal.stop_loss != null) {
      hLine(aiSignal.stop_loss, theme.upColor, [3, 3], 1.2, `止损 ${aiSignal.stop_loss.toFixed(2)}`, 14)
    }
    if (aiSignal.take_profit != null) {
      hLine(aiSignal.take_profit, theme.downColor, [3, 3], 1.2, `止盈 ${aiSignal.take_profit.toFixed(2)}`, -6)
    }
  }

  for (const idx of dualCrossIndices) {
    if (idx < viewS || idx > viewE) continue
    const pt = pixelAtIdxCached(idx, priceAt(idx))
    if (!pt) continue
    children.push({
      type: 'circle',
      shape: { cx: pt[0], cy: pt[1], r: 5 },
      style: { fill: 'rgba(255,224,102,0.85)', stroke: theme.strokeBg, lineWidth: 1.5 },
      z: 106, silent: true,
    })
    children.push({
      type: 'text',
      style: {
        text: '共振',
        fill: '#e6c355',
        fontSize: theme.resonanceFontSize,
        fontWeight: 600,
        fontFamily: theme.labelFont,
        textAlign: 'center',
      },
      x: pt[0], y: pt[1] - 10,
      z: 107, silent: true,
    })
  }

  return children
}
