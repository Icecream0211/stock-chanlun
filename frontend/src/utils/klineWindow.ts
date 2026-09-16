import type { LevelOption } from '@/stores/chanlun'

type WindowEdge = { viewStart: number; viewEnd: number; total: number }

const calendarDaysPerBar: Record<LevelOption, number> = {
  '1min': 1 / 120,
  '5min': 1 / 24,
  '15min': 1 / 8,
  '30min': 1 / 4,
  '60min': 1 / 2,
  daily: 1.5,
  weekly: 9,
  monthly: 35,
}

/** 可视区域离左侧缓存边界不到约一成时，再补一屏同周期数据。 */
export function shouldLoadEarlierWindow({ viewStart, viewEnd, total }: WindowEdge): boolean {
  const visible = Math.max(1, viewEnd - viewStart + 1)
  return total > visible && viewStart <= Math.max(8, Math.ceil(visible * 0.1))
}

/** 以当前可见根数回推一屏；交易日非连续，按保守日历时间回推以确保覆盖足量 K 线。 */
export function windowStartBefore(
  firstDate: string,
  level: LevelOption,
  visibleBars: number,
  boundaryStart?: string,
): string {
  const first = new Date(firstDate)
  if (Number.isNaN(first.getTime())) return boundaryStart ?? ''
  const bars = Math.max(20, Math.round(visibleBars))
  const calendarDays = Math.ceil(bars * calendarDaysPerBar[level] * 1.55)
  const next = new Date(first)
  next.setDate(next.getDate() - calendarDays)
  const value = next.toISOString().slice(0, 10)
  return boundaryStart && value < boundaryStart ? boundaryStart : value
}
