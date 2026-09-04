import type { DivergenceSignal } from '../api/stock'

const PERIOD_SHORT: Record<string, string> = {
  '1min': '1分',
  '5min': '5分',
  '15min': '15分',
  '30min': '30分',
  '60min': '60分',
  daily: '日',
  weekly: '周',
  monthly: '月',
}

export function divergenceChanType(div: DivergenceSignal): 'trend' | 'consolidation' | 'momentum' {
  return div.chan_type ?? (div.strict_chan ? 'trend' : 'momentum')
}

export function divergenceTypeLabel(div: DivergenceSignal): string {
  const orientation = div.type === 'top' ? '顶' : '底'
  switch (divergenceChanType(div)) {
    case 'trend': return `趋势${orientation}背驰`
    case 'consolidation': return `盘整${orientation}背驰`
    default: return `${orientation}部力度背离`
  }
}

export function divergenceLevelLabel(div: DivergenceSignal): string {
  if (div.level_label) return div.level_label
  const period = PERIOD_SHORT[div.analysis_level ?? ''] ?? div.analysis_level ?? '当前周期'
  const structure = div.structure_type === 'segment' ? '线段级' : '笔级'
  return `${period}·${structure}`
}

function evidenceGrade(div: DivergenceSignal): 'A' | 'B' | 'C' {
  if (div.evidence_grade) return div.evidence_grade
  const count = div.confirm_count ?? div.confirmations?.length ?? 1
  if (count >= 3) return 'A'
  if (count === 2) return 'B'
  return 'C'
}

export function divergenceCompactLabel(div: DivergenceSignal): string {
  const type = divergenceChanType(div)
  const prefix = type === 'trend' ? '趋' : type === 'consolidation' ? '盘' : '力'
  const orientation = div.type === 'top' ? '顶' : '底'
  const period = PERIOD_SHORT[div.analysis_level ?? ''] ?? ''
  const structure = `L${div.structure_level ?? (div.structure_type === 'segment' ? 2 : 1)}`
  const level = period ? `${period}/${structure}` : structure
  const grade = evidenceGrade(div)
  return `${prefix}${orientation}·${level}·${grade}`
}

export function divergenceEvidenceLabel(div: DivergenceSignal): string {
  const count = div.confirm_count ?? div.confirmations?.length ?? 1
  const grade = evidenceGrade(div)
  return `${grade}级证据 · ${count}因子`
}
