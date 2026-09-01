/** K 线日期与缠论结构在图表轴上的索引映射（PC / 移动端共用） */

/**
 * 生成稳定且可比较的时间键。
 *
 * 日/周/月线保持 YYYY-MM-DD；分钟线必须保留 HH:mm:ss，不能把同一天的
 * 多根 K 线压成同一个 category。
 */
export function normDateTime(s: string): string {
  const raw = String(s ?? '').trim().replace('T', ' ')
  const match = raw.match(/^(\d{4}-\d{2}-\d{2})(?:\s+(\d{2}):(\d{2})(?::(\d{2}))?)?/)
  if (!match) return raw
  const [, day, hour, minute, second] = match
  if (hour == null || minute == null) return day
  return `${day} ${hour}:${minute}:${second ?? '00'}`
}

export function normDay(s: string): string {
  return normDateTime(s).slice(0, 10)
}

export function formatAxisDateLabel(s: string): string {
  const key = normDateTime(s)
  return key.length > 10 ? key.slice(5, 16) : key.slice(5, 10)
}

export type AdaptiveTimeAxisMode = 'year' | 'month' | 'day' | 'time'

export function percentToVisibleIndexRange(
  length: number,
  start = 0,
  end = 100,
): [number, number] {
  if (length <= 0) return [0, 0]
  const maxIndex = length - 1
  const safeStart = Math.max(0, Math.min(100, start))
  const safeEnd = Math.max(safeStart, Math.min(100, end))
  return [
    Math.max(0, Math.min(maxIndex, Math.floor(maxIndex * safeStart / 100))),
    Math.max(0, Math.min(maxIndex, Math.ceil(maxIndex * safeEnd / 100))),
  ]
}

/** 根据当前可视时间跨度选择年、月、日或时分标签。 */
export function resolveAdaptiveTimeAxisMode(
  dates: string[],
  visibleStart = 0,
  visibleEnd = dates.length - 1,
): AdaptiveTimeAxisMode {
  if (!dates.length) return 'day'
  const start = Math.max(0, Math.min(dates.length - 1, visibleStart))
  const end = Math.max(start, Math.min(dates.length - 1, visibleEnd))
  const startTime = parseTime(dates[start])
  const endTime = parseTime(dates[end])
  const spanDays = Number.isFinite(startTime) && Number.isFinite(endTime)
    ? Math.abs(endTime - startTime) / 86_400_000
    : 0

  // 默认行情窗口约为 1 年，按 10 个月以上视作年度总览，避免完整窗口仍挤满月份。
  if (spanDays >= 300) return 'year'
  if (spanDays >= 62) return 'month'
  if (spanDays >= 2) return 'day'
  return dates.slice(start, end + 1).some(date => normDateTime(date).length > 10) ? 'time' : 'day'
}

/**
 * ECharts category 轴 formatter。年/月模式只在周期切换处显示标签，避免缩放后
 * 同一年或同一月被重复标注；分钟模式在跨日的第一根 K 线上补日期。
 */
export function formatAdaptiveTimeAxisLabel(
  value: string,
  index: number,
  dates: string[],
  visibleStart = 0,
  visibleEnd = dates.length - 1,
  maxLabels = 10,
): string {
  const key = normDateTime(value)
  if (!key) return ''
  const mode = resolveAdaptiveTimeAxisMode(dates, visibleStart, visibleEnd)
  // ECharts 在 dataZoom 后传入的 index 可能是“当前可视刻度序号”，而不是完整
  // category 数据索引，因此必须用轴值反查真实位置再判断周期边界。
  const matchedIndex = dates.findIndex(date => normDateTime(date) === key)
  const dataIndex = matchedIndex >= 0 ? matchedIndex : index
  const previous = dataIndex > visibleStart ? normDateTime(dates[dataIndex - 1] ?? '') : ''
  const day = key.slice(0, 10)
  const previousDay = previous.slice(0, 10)
  const visibleCount = Math.max(1, visibleEnd - visibleStart + 1)
  const safeMaxLabels = Math.max(2, maxLabels)

  if (mode === 'year') {
    const year = key.slice(0, 4)
    if (dataIndex > visibleStart && previous.slice(0, 4) === year) return ''
    const startYear = Number(normDateTime(dates[visibleStart] ?? key).slice(0, 4))
    const endYear = Number(normDateTime(dates[visibleEnd] ?? key).slice(0, 4))
    const step = Math.max(1, Math.ceil((endYear - startYear + 1) / safeMaxLabels))
    return dataIndex <= visibleStart || (Number(year) - startYear) % step === 0 ? year : ''
  }
  if (mode === 'month') {
    const month = key.slice(0, 7)
    if (dataIndex > visibleStart && previous.slice(0, 7) === month) return ''
    const startKey = normDateTime(dates[visibleStart] ?? key)
    const endKey = normDateTime(dates[visibleEnd] ?? key)
    const startMonth = Number(startKey.slice(0, 4)) * 12 + Number(startKey.slice(5, 7)) - 1
    const endMonth = Number(endKey.slice(0, 4)) * 12 + Number(endKey.slice(5, 7)) - 1
    const currentMonth = Number(key.slice(0, 4)) * 12 + Number(key.slice(5, 7)) - 1
    const step = Math.max(1, Math.ceil((endMonth - startMonth + 1) / safeMaxLabels))
    if (dataIndex > visibleStart && (currentMonth - startMonth) % step !== 0) return ''
    return dataIndex <= visibleStart || previous.slice(0, 4) !== key.slice(0, 4) ? month : `${key.slice(5, 7)}月`
  }
  if (mode === 'day') {
    const step = Math.max(1, Math.ceil(visibleCount / safeMaxLabels))
    return dataIndex <= visibleStart || (dataIndex - visibleStart) % step === 0 ? day.slice(5, 10) : ''
  }
  const step = Math.max(1, Math.ceil(visibleCount / safeMaxLabels))
  if (dataIndex > visibleStart && (dataIndex - visibleStart) % step !== 0) return ''
  if (key.length <= 10) return key.slice(5, 10)
  const time = key.slice(11, 16)
  return dataIndex <= visibleStart || previousDay !== day ? `${day.slice(5, 10)}\n${time}` : time
}

export function buildDateLookup(dates: string[]): Map<string, number> {
  const lookup = new Map<string, number>()
  const dayCounts = new Map<string, number>()
  for (const date of dates) {
    const day = normDay(date)
    dayCounts.set(day, (dayCounts.get(day) ?? 0) + 1)
  }
  for (let j = 0; j < dates.length; j++) {
    const key = normDateTime(dates[j])
    lookup.set(key, j)
    // 日线结构可能带 00:00:00，而轴值只有日期（反之亦然）。只在该日唯一时
    // 建立日期别名，分钟级同日多根 K 线绝不能使用这个别名。
    const day = normDay(key)
    if (dayCounts.get(day) === 1) lookup.set(day, j)
  }
  return lookup
}

function parseTime(s: string): number {
  const key = normDateTime(s)
  const normalized = key.length === 10 ? `${key} 00:00:00` : key
  return Date.parse(normalized.replace(/-/g, '/'))
}

/** 在完整时间轴中找索引；精确值不存在（如降采样）时找时间最接近的一根。 */
export function dateToIdxRobust(d: string, dates: string[], lookup?: Map<string, number>): number {
  if (!dates.length) return -1
  const key = normDateTime(d)
  const map = lookup ?? buildDateLookup(dates)
  const fromMap = map.get(key) ?? map.get(normDay(key))
  if (fromMap != null) return fromMap
  const t = parseTime(key)
  if (Number.isNaN(t)) return -1
  let best = -1
  let bestDiff = Infinity
  for (let j = 0; j < dates.length; j++) {
    const tj = parseTime(dates[j])
    if (Number.isNaN(tj)) continue
    const diff = Math.abs(tj - t)
    if (diff < bestDiff) {
      bestDiff = diff
      best = j
    }
  }
  return best
}

export function resolveBarRange(
  start: string,
  end: string,
  n: number,
  dates: string[],
  lookup?: Map<string, number>,
): [number, number] | null {
  if (n <= 0) return null
  let s = dateToIdxRobust(start, dates, lookup)
  let e = dateToIdxRobust(end, dates, lookup)
  if (s < 0 || e < 0) return null
  if (s > e) [s, e] = [e, s]
  s = Math.max(0, Math.min(n - 1, s))
  e = Math.max(0, Math.min(n - 1, e))
  if (s > e) return null
  return [s, e]
}
