/**
 * 手工图形的领域模型与纯渲染转换。
 *
 * 与具体图表库隔离：锚点使用时间/价格而非像素，缩放、切换数据窗口后仍可复现。
 */
export type DrawingTool = 'pan' | 'select' | 'trend' | 'ray' | 'horizontal'
export type DrawingType = Exclude<DrawingTool, 'pan' | 'select'>

export type DrawingAnchor = {
  date: string
  price: number
}

export type ChartDrawing = {
  id: string
  type: DrawingType
  start: DrawingAnchor
  end: DrawingAnchor
  color: string
  width: number
}

export type DrawingStorage = Pick<Storage, 'getItem' | 'setItem'>
export type DrawingGraphicElement = Record<string, unknown>

const STORAGE_PREFIX = 'chanstock_drawings_v1'
const DEFAULT_COLOR = '#f59e0b'
const DEFAULT_WIDTH = 2

function normalizeWidth(width: number | undefined): number {
  const value = Number(width)
  if (!Number.isFinite(value)) return DEFAULT_WIDTH
  return Math.max(1, Math.min(6, Math.round(value)))
}

function normalizeAnchor(anchor: DrawingAnchor): DrawingAnchor {
  return { date: String(anchor.date), price: Number(anchor.price) }
}

export function createDrawing(input: Omit<ChartDrawing, 'id'> & { id?: string }): ChartDrawing {
  return {
    id: input.id ?? globalThis.crypto?.randomUUID?.() ?? `draw-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    type: input.type,
    start: normalizeAnchor(input.start),
    end: normalizeAnchor(input.end),
    color: input.color || DEFAULT_COLOR,
    width: normalizeWidth(input.width),
  }
}

function storageKey(symbol: string, level: string): string {
  return `${STORAGE_PREFIX}:${symbol}:${level}`
}

function isDrawing(value: unknown): value is ChartDrawing {
  if (!value || typeof value !== 'object') return false
  const item = value as Partial<ChartDrawing>
  return typeof item.id === 'string'
    && (item.type === 'trend' || item.type === 'ray' || item.type === 'horizontal')
    && !!item.start && typeof item.start.date === 'string' && Number.isFinite(item.start.price)
    && !!item.end && typeof item.end.date === 'string' && Number.isFinite(item.end.price)
    && typeof item.color === 'string' && Number.isFinite(item.width)
}

/** 为图表组件提供按标的与周期隔离的本地保存边界。 */
export class DrawingRepository {
  constructor(private readonly storage: DrawingStorage) {}

  load(symbol: string, level: string): ChartDrawing[] {
    try {
      const raw = this.storage.getItem(storageKey(symbol, level))
      if (!raw) return []
      const parsed: unknown = JSON.parse(raw)
      if (!Array.isArray(parsed)) return []
      return parsed.filter(isDrawing).map(item => createDrawing(item))
    } catch {
      return []
    }
  }

  save(symbol: string, level: string, drawings: ChartDrawing[]): void {
    this.storage.setItem(storageKey(symbol, level), JSON.stringify(drawings.map(createDrawing)))
  }
}

export function buildManualDrawingGraphicChildren(params: {
  drawings: ChartDrawing[]
  dates: string[]
  viewStart: number
  viewEnd: number
  pixelAt: (index: number, price: number) => [number, number] | null
  selectedId?: string | null
}): DrawingGraphicElement[] {
  const { drawings, dates, viewStart, viewEnd, pixelAt, selectedId } = params
  const children: DrawingGraphicElement[] = []

  for (const drawing of drawings) {
    const startIndex = dates.indexOf(drawing.start.date)
    const endIndex = dates.indexOf(drawing.end.date)
    if (startIndex < 0 || endIndex < 0) continue

    const start = pixelAt(startIndex, drawing.start.price)
    const end = pixelAt(endIndex, drawing.end.price)
    if (!start || !end) continue

    let points: [number, number][] = [start, end]
    if (drawing.type === 'horizontal') {
      const right = pixelAt(viewEnd, drawing.start.price)
      if (!right) continue
      points = [start, right]
    } else if (drawing.type === 'ray') {
      const barDistance = endIndex - startIndex
      if (barDistance === 0) continue
      const slope = (drawing.end.price - drawing.start.price) / barDistance
      const edgePrice = drawing.end.price + slope * (viewEnd - endIndex)
      const right = pixelAt(viewEnd, edgePrice)
      if (!right) continue
      points = [start, right]
    }

    const visible = points.some(([x]) => {
      const left = pixelAt(viewStart, drawing.start.price)?.[0] ?? -Infinity
      const right = pixelAt(viewEnd, drawing.start.price)?.[0] ?? Infinity
      return x >= Math.min(left, right) - 24 && x <= Math.max(left, right) + 24
    })
    if (!visible) continue

    const selected = drawing.id === selectedId
    children.push({
      id: `manual-line-${drawing.id}`,
      type: 'polyline',
      shape: { points },
      style: {
        stroke: drawing.color,
        lineWidth: drawing.width,
        lineCap: 'round',
        lineJoin: 'round',
        opacity: selected ? 1 : 0.9,
      },
      z: 140,
      silent: true,
    })

    if (selected) {
      for (const point of [start, end]) {
        children.push({
          id: `manual-handle-${drawing.id}-${point === start ? 'start' : 'end'}`,
          type: 'circle',
          shape: { cx: point[0], cy: point[1], r: 5 },
          style: { fill: '#ffffff', stroke: drawing.color, lineWidth: 2 },
          z: 141,
          silent: true,
        })
      }
    }
  }

  return children
}
