import { describe, expect, it } from 'vitest'
import { resolveChartGesturePolicy } from './chartNavigation'

describe('chart navigation gesture policy', () => {
  it('uses left-button drag to pan only in the default browsing mode', () => {
    expect(resolveChartGesturePolicy('pan')).toMatchObject({ moveOnMouseDrag: true, manualDrawing: false })
    expect(resolveChartGesturePolicy('select')).toMatchObject({ moveOnMouseDrag: false, manualDrawing: false })
    expect(resolveChartGesturePolicy('trend')).toMatchObject({ moveOnMouseDrag: false, manualDrawing: true })
  })

  it('reserves chart zoom for Shift plus mouse wheel and leaves normal wheel to the page', () => {
    expect(resolveChartGesturePolicy('pan').zoomOnMouseWheel).toBe('shift')
    expect(resolveChartGesturePolicy('pan').moveOnMouseWheel).toBe(false)
  })
})
