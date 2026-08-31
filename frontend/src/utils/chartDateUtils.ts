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
