/** 主图统一配色：K 线、均线与缠论结构互不复用主色，便于快速辨识。 */
export const CHART_PALETTE = {
  klineUp: '#F6465D',
  klineDown: '#0ECB81',
  ma5: '#FFD166',
  ma20: '#22D3EE',
  ma60: '#A78BFA',
  bi: '#2F9BFF',
  biZhongshuStroke: '#2F9BFF',
  biZhongshuFill: 'rgba(47, 155, 255, 0.08)',
  segment: '#FF8C42',
  zhongshuStroke: '#FF4D6D',
  zhongshuFill: 'rgba(255, 77, 109, 0.13)',
} as const
