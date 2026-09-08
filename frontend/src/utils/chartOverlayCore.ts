/**
 * 缠论 ECharts graphic 叠加层 — PC / 移动端共用（索引映射 + 像素渲染）。
 */
import type { KLine, KLineInclusion, Bi, XiangSegment, Zhongshu, Signal, AISignal, DivergenceSignal, SupportResistance } from '../api/stock'
import { buildDateLookup, dateToIdxRobust, resolveBarRange } from './chartDateUtils'
import { simplifySupportResistanceLevels } from './chartOverlayUtils'
import { CHART_PALETTE } from './chartPalette'
import { divergenceChanType, divergenceCompactLabel } from './divergencePresentation'

export type GraphicElement = Record<string, unknown>

export type IndexedRange<T> = T & { _s: number; _e: number }
export type IndexedSignal = Signal & { _idx: number }
export type IndexedDivergence = DivergenceSignal & { _idx: number; _previousIdx?: number }

export type ChanlunOverlayPayload = {
  inclusions: IndexedRange<KLineInclusion>[]
  divergences: IndexedDivergence[]
  bis: IndexedRange<Bi>[]
  biZhongshus: IndexedRange<Zhongshu>[]
  xiangs: IndexedRange<XiangSegment>[]
  zhongshus: IndexedRange<Zhongshu>[]
  signals: IndexedSignal[]
  aiSignal: AISignal | null | undefined
  supportResistance: SupportResistance[]
  dualCrossIndices: number[]
  _n: number
}

export type ChanlunOverlayFlags = {
  inclusions?: boolean
  divergences?: boolean
  bis: boolean
  biZhongshus: boolean
  xiangs: boolean
  zhongshus: boolean
  signals: boolean
  aiLines: boolean
  supportResistance: boolean
}

export type ChanlunOverlayTheme = {
  upColor: string
  downColor: string
  inclusionColor?: string
  divergenceTopColor?: string
  divergenceBottomColor?: string
  divergenceConsolidationTopColor?: string
  divergenceConsolidationBottomColor?: string
  divergenceMomentumTopColor?: string
  divergenceMomentumBottomColor?: string
  overlayLabelBackground?: string
  biColor: string
  biZhongshuStroke: string
  biZhongshuFill: string
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
  inclusionColor: '#8B86A8',
  divergenceTopColor: '#F97373',
  divergenceBottomColor: '#34D399',
  divergenceConsolidationTopColor: '#F59E0B',
  divergenceConsolidationBottomColor: '#14B8A6',
  divergenceMomentumTopColor: '#C084FC',
  divergenceMomentumBottomColor: '#60A5FA',
  overlayLabelBackground: 'rgba(255,255,255,0.88)',
  biColor: CHART_PALETTE.bi,
  biZhongshuStroke: CHART_PALETTE.biZhongshuStroke,
  biZhongshuFill: CHART_PALETTE.biZhongshuFill,
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
  inclusionColor: '#8B86A8',
  divergenceTopColor: '#FB7185',
  divergenceBottomColor: '#34D399',
  divergenceConsolidationTopColor: '#F59E0B',
  divergenceConsolidationBottomColor: '#2DD4BF',
  divergenceMomentumTopColor: '#C084FC',
  divergenceMomentumBottomColor: '#60A5FA',
  overlayLabelBackground: 'rgba(6,8,12,0.86)',
  biColor: CHART_PALETTE.bi,
  biZhongshuStroke: CHART_PALETTE.biZhongshuStroke,
  biZhongshuFill: CHART_PALETTE.biZhongshuFill,
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

type DataZoomSlice = { startValue?: number | string; endValue?: number | string; start?: number; end?: number }

export function resolveDataZoomViewRange(
  datesLength: number,
  dataZoom?: DataZoomSlice[],
): { viewS: number; viewE: number } {
  if (datesLength <= 0) return { viewS: 0, viewE: 0 }
  const dz0 = dataZoom?.[0]
  const maxIndex = datesLength - 1
  const startValue = Number(dz0?.startValue)
  const endValue = Number(dz0?.endValue)
  const percentStart = Number(dz0?.start)
  const percentEnd = Number(dz0?.end)
  const rawStart = Number.isFinite(startValue)
    ? startValue
    : (Number.isFinite(percentStart) ? Math.floor(maxIndex * percentStart / 100) : 0)
  const rawEnd = Number.isFinite(endValue)
    ? endValue
    : (Number.isFinite(percentEnd) ? Math.ceil(maxIndex * percentEnd / 100) : maxIndex)
  const viewS = Math.max(0, Math.min(rawStart, maxIndex))
  const viewE = Math.max(viewS, Math.min(rawEnd, maxIndex))
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
  inclusions?: KLineInclusion[]
  bis: Bi[]
  biZhongshus?: Zhongshu[]
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
    inclusions = [],
    bis,
    biZhongshus = [],
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
  const divergenceSource = aiSignal?.divergences?.length
    ? aiSignal.divergences
    : (aiSignal?.divergence ? [aiSignal.divergence] : [])

  return {
    inclusions: flags.inclusions ? inclusions.flatMap(item => {
      const r = resolveBarRange(item.start, item.end, nBar, dates, dateLookup)
      return r ? [{ ...item, _s: r[0], _e: r[1] }] : []
    }) : [],
    divergences: flags.divergences ? divergenceSource.flatMap(item => {
      const idx = dateToIdxRobust(item.datetime, dates, dateLookup)
      if (idx < 0) return []
      const previousIdx = item.previous_datetime
        ? dateToIdxRobust(item.previous_datetime, dates, dateLookup)
        : -1
      return [{ ...item, _idx: idx, ...(previousIdx >= 0 ? { _previousIdx: previousIdx } : {}) }]
    }) : [],
    bis: flags.bis ? bis.flatMap(b => {
      const r = resolveBarRange(b.start, b.end, nBar, dates, dateLookup)
      return r ? [{ ...b, _s: r[0], _e: r[1] }] : []
    }) : [],
    biZhongshus: flags.biZhongshus ? biZhongshus.flatMap(z => {
      const r = resolveBarRange(z.start, z.end, nBar, dates, dateLookup)
      return r ? [{ ...z, _s: r[0], _e: r[1] }] : []
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
  const inclusionColor = theme.inclusionColor ?? '#8B86A8'

  const { inclusions, divergences, bis, biZhongshus, xiangs, zhongshus, signals, aiSignal, supportResistance, dualCrossIndices } = data

  // 包含关系只画 1px 细括号；两根合并不加文字，避免主图变拥挤。
  for (const item of inclusions) {
    if (item._e < viewS || item._s > viewE || item._e < item._s) continue
    const a = pixelAtIdxCached(item._s, item.high)
    const b = pixelAtIdxCached(item._e, item.high)
    if (!a || !b) continue
    const x1 = Math.min(a[0], b[0])
    const x2 = Math.max(a[0], b[0])
    const y = Math.min(a[1], b[1]) - 4
    const capY = y - 3
    children.push({
      type: 'polyline',
      shape: { points: [[x1, y], [x1, capY], [x2, capY], [x2, y]] },
      style: {
        stroke: inclusionColor,
        fill: null,
        lineWidth: 1,
        opacity: 0.62,
        lineDash: item.direction === 'down' ? [2, 2] : undefined,
      },
      z: 101,
      silent: true,
    })
    if (item.count >= 3 && x2 - x1 >= 16) {
      children.push({
        type: 'text',
        style: {
          x: (x1 + x2) / 2,
          y: capY - 2,
          text: `含${item.count}`,
          fill: inclusionColor,
          font: `8px ${theme.labelFont}`,
          align: 'center',
          verticalAlign: 'bottom',
          opacity: 0.72,
        },
        z: 101,
        silent: true,
      })
    }
  }

  const appendZhongshuRects = (
    items: IndexedRange<Zhongshu>[],
    stroke: string,
    fill: string,
    dashed: boolean,
    z: number,
  ) => {
    for (const zs of items) {
      if (zs._e < viewS || zs._s > viewE || zs._e < zs._s) continue
      const a = pixelAtIdxCached(zs._s, zs.range_high)
      const b = pixelAtIdxCached(zs._e, zs.range_low)
      if (!a || !b) continue
      const xPx1 = Math.min(a[0], b[0])
      const xPx2 = Math.max(a[0], b[0])
      const yPx1 = Math.min(a[1], b[1])
      const yPx2 = Math.max(a[1], b[1])
      const expanded = zs.status === 'expanded'
      const statusLabel = zs.confirmed === false
          ? '候选'
          : zs.status === 'extended'
          ? '延伸'
          : zs.status === 'leaving'
            ? `离开${zs.exit_direction === 'down' ? '↓' : zs.exit_direction === 'up' ? '↑' : ''}待确认`
          : zs.status === 'completed'
            ? '完成'
            : '形成'

      if (expanded) {
        // 高一级扩张中枢常跨越很长区间。完整矩形会遮挡 K 线并与子中枢叠成色块，
        // 因此只画四个角标来保留时间/价格边界，不填充、不重复标注上下沿价格。
        const width = Math.max(xPx2 - xPx1, 4)
        const height = Math.max(yPx2 - yPx1, 1)
        const cornerX = Math.min(18, Math.max(7, width * 0.08))
        const cornerY = Math.min(14, Math.max(6, height * 0.12))
        const corners: [number, number][][] = [
          [[xPx1, yPx1 + cornerY], [xPx1, yPx1], [xPx1 + cornerX, yPx1]],
          [[xPx2 - cornerX, yPx1], [xPx2, yPx1], [xPx2, yPx1 + cornerY]],
          [[xPx1, yPx2 - cornerY], [xPx1, yPx2], [xPx1 + cornerX, yPx2]],
          [[xPx2 - cornerX, yPx2], [xPx2, yPx2], [xPx2, yPx2 - cornerY]],
        ]
        for (const points of corners) {
          children.push({
            type: 'polyline',
            shape: { points },
            style: {
              stroke,
              fill: null,
              lineWidth: 1.35,
              lineDash: [5, 4],
              opacity: 0.72,
              lineJoin: 'round',
            },
            z: z - 2,
            silent: true,
          })
        }
        if (width >= 30) {
          const expansionLabel = zs.expansion_type === 'nine_structure'
            ? `9笔递归候选L${zs.level ?? (dashed ? 2 : 3)}`
            : zs.expansion_type === 'center_overlap'
              ? `同级叠升L${zs.level ?? (dashed ? 2 : 3)}`
              : `扩L${zs.level ?? (dashed ? 2 : 3)}`
          children.push({
            type: 'text',
            style: {
              x: xPx2 - 3,
              y: yPx1 + 3,
              text: expansionLabel,
              fill: stroke,
              fontSize: theme.zsLabelFontSize,
              fontWeight: 650,
              fontFamily: theme.labelFont,
              align: 'right',
              verticalAlign: 'top',
              opacity: 0.82,
              backgroundColor: theme.overlayLabelBackground ?? 'rgba(255,255,255,0.88)',
              borderColor: stroke,
              borderWidth: 0.7,
              borderRadius: 2,
              padding: [1, 3],
            },
            z: z - 1,
            silent: true,
          })
        }
        continue
      }
      children.push({
        type: 'rect',
        shape: { x: xPx1, y: yPx1, width: Math.max(xPx2 - xPx1, 4), height: Math.max(yPx2 - yPx1, 1) },
        style: {
          fill,
          stroke,
          lineWidth: dashed ? 1 : 1.35,
          lineDash: dashed || zs.confirmed === false ? [6, 4] : undefined,
          // 已结束的中枢是历史上下文，不与正在运行的笔、线段争夺视觉层级。
          opacity: zs.confirmed === false ? 0.52 : zs.status === 'completed' ? 0.46 : 0.9,
        },
        z, silent: true,
      })
      children.push({
        type: 'text',
        style: {
          text: `${zs.decomposition === 'same_level' ? '段内局部L' : '笔级L'}${zs.level ?? (dashed ? 1 : 2)}·${statusLabel}${
            zs.status === 'extended' && (zs.structure_count ?? 0) > 3
              ? `·${zs.structure_count}${zs.source_type === 'bi' ? '笔' : '段'}`
              : ''
          } ${zs.range_high.toFixed(2)} / ${zs.range_low.toFixed(2)}`,
          fill: stroke,
          fontSize: theme.zsLabelFontSize,
          fontWeight: 500,
          fontFamily: theme.labelFont,
        },
        x: xPx1 + 4, y: yPx1 + 12,
        z: z + 1, silent: true,
      })
    }
  }

  // 笔中枢：蓝色虚线浅填充；线段中枢：红色实线深填充。
  appendZhongshuRects(biZhongshus, theme.biZhongshuStroke, theme.biZhongshuFill, true, 94)
  appendZhongshuRects(zhongshus, theme.zhongshuStroke, theme.zhongshuFill, false, 96)

  const appendStructurePolylines = <T extends IndexedRange<Bi | XiangSegment>>(
    items: T[],
    color: string,
    lineWidth: number,
    z: number,
  ) => {
    let points: [number, number][] = []
    let previousEnd = -1
    const flush = (dashed = false) => {
      if (points.length >= 2) {
        children.push({
          type: 'polyline',
          shape: { points },
          style: {
            stroke: color,
            fill: null,
            lineWidth,
            opacity: dashed ? 0.78 : 0.96,
            lineDash: dashed ? [7, 5] : undefined,
            lineJoin: 'round',
            lineCap: 'round',
          },
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
      if (item.confirmed === false) {
        flush()
        points = [p1, p2]
        flush(true)
        previousEnd = item._e
        continue
      }
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
  appendStructurePolylines(xiangs, theme.segmentColor, 3.2, 103)

  // 类型用形状/色系区分：趋势=实心圆，盘整=菱形，力度背离=空心圆；上下位置表示顶/底。
  const divergenceStacks = new Map<string, number>()
  for (const div of divergences) {
    if (div._idx < viewS || div._idx > viewE) continue
    const anchor = pixelAtIdxCached(div._idx, div.price)
    if (!anchor) continue
    const isTop = div.type === 'top'
    const chanType = divergenceChanType(div)
    const color = chanType === 'trend'
      ? (isTop ? (theme.divergenceTopColor ?? '#F97373') : (theme.divergenceBottomColor ?? '#34D399'))
      : chanType === 'consolidation'
        ? (isTop ? (theme.divergenceConsolidationTopColor ?? '#F59E0B') : (theme.divergenceConsolidationBottomColor ?? '#14B8A6'))
        : (isTop ? (theme.divergenceMomentumTopColor ?? '#C084FC') : (theme.divergenceMomentumBottomColor ?? '#60A5FA'))
    const stackKey = `${div._idx}:${div.type}`
    const stackIndex = divergenceStacks.get(stackKey) ?? 0
    divergenceStacks.set(stackKey, stackIndex + 1)
    const markerY = anchor[1] + (isTop ? -1 : 1) * (12 + stackIndex * 13)
    children.push({
      type: 'line',
      shape: { x1: anchor[0], y1: anchor[1], x2: anchor[0], y2: markerY },
      style: {
        stroke: color,
        lineWidth: 1,
        opacity: chanType === 'momentum' ? 0.6 : 0.78,
        lineDash: chanType === 'momentum' ? [2, 2] : undefined,
      },
      z: 104,
      silent: true,
    })
    if (chanType === 'consolidation') {
      children.push({
        type: 'polygon',
        shape: { points: [[anchor[0], markerY - 5], [anchor[0] + 5, markerY], [anchor[0], markerY + 5], [anchor[0] - 5, markerY]] },
        style: { fill: color, stroke: theme.strokeBg, lineWidth: 1.1, opacity: 0.95 },
        z: 104,
        silent: true,
      })
    } else {
      children.push({
        type: 'circle',
        shape: { cx: anchor[0], cy: markerY, r: chanType === 'trend' ? 4.5 : 4 },
        style: {
          fill: chanType === 'momentum' ? theme.strokeBg : color,
          stroke: color,
          lineWidth: chanType === 'momentum' ? 1.5 : 1.2,
          opacity: 0.94,
        },
        z: 104,
        silent: true,
      })
    }
    children.push({
      type: 'text',
      style: {
        x: anchor[0] + 6,
        y: markerY,
        text: divergenceCompactLabel(div),
        fill: color,
        font: `9px ${theme.labelFont}`,
        verticalAlign: 'middle',
        backgroundColor: theme.overlayLabelBackground ?? 'rgba(255,255,255,0.88)',
        borderColor: color,
        borderWidth: 0.7,
        borderRadius: 2,
        padding: [1, 3],
      },
      z: 104,
      silent: true,
    })
  }

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
