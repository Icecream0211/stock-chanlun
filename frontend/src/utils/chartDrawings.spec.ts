import { describe, expect, it } from 'vitest'
import {
  DrawingRepository,
  buildManualDrawingGraphicChildren,
  createDrawing,
  type DrawingStorage,
} from './chartDrawings'

class MemoryStorage implements DrawingStorage {
  private values = new Map<string, string>()

  getItem(key: string) { return this.values.get(key) ?? null }
  setItem(key: string, value: string) { this.values.set(key, value) }
}

describe('chart drawings', () => {
  it('persists a styled trend line per instrument and timeframe', () => {
    const repository = new DrawingRepository(new MemoryStorage())
    const drawing = createDrawing({
      type: 'trend',
      start: { date: '2026-01-02', price: 10.2 },
      end: { date: '2026-01-08', price: 12.6 },
      color: '#ff7a45',
      width: 3,
    })

    repository.save('000001', 'daily', [drawing])

    expect(repository.load('000001', 'daily')).toEqual([drawing])
    expect(repository.load('000001', '30min')).toEqual([])
    expect(repository.load('600000', 'daily')).toEqual([])
  })

  it('renders a ray to the chart edge while retaining its selected style', () => {
    const children = buildManualDrawingGraphicChildren({
      drawings: [createDrawing({
        id: 'ray-1', type: 'ray', color: '#22c55e', width: 4,
        start: { date: '2026-01-02', price: 10 },
        end: { date: '2026-01-03', price: 12 },
      })],
      dates: ['2026-01-02', '2026-01-03', '2026-01-04'],
      viewStart: 0,
      viewEnd: 2,
      pixelAt: (index, price) => [index * 50, 100 - price],
      selectedId: 'ray-1',
    })

    const line = children.find(child => child.type === 'polyline')
    expect((line?.shape as { points: number[][] }).points).toEqual([[0, 90], [100, 86]])
    expect((line?.style as { stroke?: string; lineWidth?: number }).stroke).toBe('#22c55e')
    expect((line?.style as { lineWidth?: number }).lineWidth).toBe(4)
    expect(children.filter(child => child.type === 'circle')).toHaveLength(2)
  })
})
