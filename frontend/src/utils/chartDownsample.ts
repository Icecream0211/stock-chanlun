import type { KLine } from '../api/stock'
import { normDateTime } from './chartDateUtils'

/** 主图渲染超过此根数时做 LTTB 降采样（保留 OHLC 极值） */
export const KLINE_DISPLAY_MAX = 600

/** 用于跳过 K 线未变时的整图重建 */
export function klineSeriesSignature(klines: KLine[]): string {
  if (!klines.length) return '0'
  const last = klines[klines.length - 1]
  return `${klines.length}:${last.date}:${last.open}:${last.high}:${last.low}:${last.close}:${last.volume}`
}

function typicalPrice(k: KLine): number {
  return (k.high + k.low + k.close) / 3
}

/**
 * Largest-Triangle-Three-Buckets — 在保持走势形状的前提下减少点数。
 * 返回包含首尾的下标列表。
 */
export function lttbIndices(yValues: number[], threshold: number): number[] {
  const n = yValues.length
  if (threshold >= n || threshold < 3) {
    return Array.from({ length: n }, (_, i) => i)
  }

  const sampled: number[] = [0]
  const bucketSize = (n - 2) / (threshold - 2)
  let a = 0

  for (let i = 0; i < threshold - 2; i++) {
    const avgRangeStart = Math.floor((i + 1) * bucketSize) + 1
    let avgRangeEnd = Math.floor((i + 2) * bucketSize) + 1
    avgRangeEnd = Math.min(avgRangeEnd, n)

    let avgX = 0
    let avgY = 0
    const avgLen = avgRangeEnd - avgRangeStart
    for (let j = avgRangeStart; j < avgRangeEnd; j++) {
      avgX += j
      avgY += yValues[j]
    }
    if (avgLen > 0) {
      avgX /= avgLen
      avgY /= avgLen
    }

    const rangeOffs = Math.floor(i * bucketSize) + 1
    const rangeTo = Math.floor((i + 1) * bucketSize) + 1
    const pointAx = a
    const pointAy = yValues[a]

    let maxArea = -1
    let maxAreaPoint = rangeOffs

    for (let j = rangeOffs; j < rangeTo; j++) {
      const area = Math.abs(
        (pointAx - avgX) * (yValues[j] - pointAy) -
          (pointAx - j) * (avgY - pointAy),
      ) * 0.5
      if (area > maxArea) {
        maxArea = area
        maxAreaPoint = j
      }
    }

    sampled.push(maxAreaPoint)
    a = maxAreaPoint
  }

  sampled.push(n - 1)
  return sampled
}

/** 在 LTTB 相邻锚点之间补充区间最高/最低价对应 K 线，避免影线被抹平 */
function injectOhlcExtrema(klines: KLine[], indices: number[]): number[] {
  const set = new Set(indices)
  const sorted = [...indices].sort((a, b) => a - b)

  for (let k = 0; k < sorted.length - 1; k++) {
    const start = sorted[k]
    const end = sorted[k + 1]
    if (end - start < 3) continue

    let maxHiIdx = start
    let minLoIdx = start
    let maxHi = klines[start].high
    let minLo = klines[start].low

    for (let j = start + 1; j < end; j++) {
      if (klines[j].high > maxHi) {
        maxHi = klines[j].high
        maxHiIdx = j
      }
      if (klines[j].low < minLo) {
        minLo = klines[j].low
        minLoIdx = j
      }
    }
    set.add(maxHiIdx)
    set.add(minLoIdx)
  }

  return [...set].sort((a, b) => a - b)
}

/**
 * LTTB 降采样 K 线（用于 ECharts 主图）；缠论叠加仍用全量 props。
 */
export function downsampleKlines(
  klines: KLine[],
  maxPoints = KLINE_DISPLAY_MAX,
  anchorDates: string[] = [],
): KLine[] {
  const n = klines.length
  if (n <= maxPoints) return klines

  const y = klines.map(typicalPrice)
  let indices = injectOhlcExtrema(klines, lttbIndices(y, maxPoints))

  if (indices.length > maxPoints) {
    const subY = indices.map(i => typicalPrice(klines[i]))
    const picked = lttbIndices(subY, maxPoints)
    indices = picked.map(p => indices[p])
  }

  // 缠论端点是图形几何的硬锚点。普通 K 线可以降采样，笔、线段和中枢的
  // 起止柱不能被删除，否则叠加层会吸附到邻近柱并产生视觉断点。
  if (anchorDates.length) {
    const anchors = new Set(anchorDates.map(normDateTime))
    const selected = new Set(indices)
    for (let i = 0; i < klines.length; i++) {
      if (anchors.has(normDateTime(klines[i].date))) selected.add(i)
    }
    indices = [...selected].sort((a, b) => a - b)
  }

  return indices.map(i => klines[i])
}
