import type { DrawingTool } from './chartDrawings'

/**
 * K 线浏览与手工绘图的手势边界。
 * 浏览优先：普通滚轮属于页面，Shift + 滚轮才交给图表缩放。
 */
export function resolveChartGesturePolicy(tool: DrawingTool) {
  return {
    zoomOnMouseWheel: 'shift' as const,
    moveOnMouseWheel: false,
    moveOnMouseDrag: tool === 'pan',
    manualDrawing: tool !== 'pan' && tool !== 'select',
  }
}
