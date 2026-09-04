<template>
  <div class="card strategy-card">
    <div class="card-header">
      <div class="title-with-source">
        <span class="card-title">策略建议</span>
        <span v-if="signal" class="source-badge" :class="isRuleOnly ? 'source-rule' : 'source-llm'">
          {{ isRuleOnly ? '规则引擎' : 'LLM 深度分析' }}
        </span>
      </div>
      <div class="header-right">
        <span v-if="updatedAt" class="card-time">{{ updatedAt }}</span>
        <button
          v-if="showDeepButton"
          type="button"
          class="btn-deep"
          :disabled="loading"
          @click="$emit('deepAnalyze')"
        >
          {{ loading ? '分析中…' : 'LLM 深度分析' }}
        </button>
        <span v-if="signal" class="risk-badge" :class="riskClass">{{ signal.risk_level }}风险</span>
      </div>
    </div>

    <div v-if="!signal && loading" class="empty-strategy">
      <div class="skeleton" style="height: 100px; border-radius: 8px;" />
      <p class="hint-loading">正在生成策略…</p>
    </div>

    <div v-else-if="!signal" class="empty-strategy">
      <div class="skeleton" style="height: 100px; border-radius: 8px;" />
    </div>

    <div v-else class="strategy-content">
      <p v-if="isRuleOnly" class="rule-hint">根据笔、线段、中枢、背驰与多级别共振自动计算；未调用大模型。</p>

      <!-- Direction -->
      <div class="direction-block" :class="dirClass">
        <div class="direction-main">
          <span class="dir-arrow">{{ dirSymbol }}</span>
          <span class="dir-text">{{ signal.direction }}</span>
        </div>
        <div class="dir-confidence">
          <div class="confidence-bar">
            <div
              class="confidence-fill"
              :style="{
                width: (signal.confidence * 100) + '%',
                background: confColor(signal.confidence)
              }"
            />
          </div>
          <span class="conf-pct mono">{{ (signal.confidence * 100).toFixed(0) }}%</span>
        </div>
      </div>

      <div v-if="signal.decision_guard?.applied" class="counter-trend-guard">
        <strong>{{ counterTrendGuardTitle }}</strong>
        <span>{{ signal.decision_guard.reason }}</span>
      </div>

      <!-- Price levels -->
      <div class="price-levels">
        <div class="level-row">
          <span class="level-label">入场价</span>
          <span class="level-value mono">{{ signal.entry_price?.toFixed(2) || '—' }}</span>
        </div>
        <div class="level-row">
          <span class="level-label">止盈价</span>
          <span class="level-value mono price-up">{{ signal.take_profit?.toFixed(2) || '—' }}</span>
        </div>
        <div class="level-row">
          <span class="level-label">止损价</span>
          <span class="level-value mono price-down">{{ signal.stop_loss?.toFixed(2) || '—' }}</span>
        </div>
      </div>

      <!-- Holding period -->
      <div class="period-row">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
        </svg>
        <span>操作窗口: {{ signal.holding_period }}</span>
      </div>

      <!-- Divergence -->
      <div v-if="divergenceRows.length" class="divergence-block">
        <div class="divergence-header">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
          </svg>
          <span>背驰与力度检测</span>
          <span class="divergence-count">最近 {{ divergenceRows.length }} 处</span>
        </div>
        <p class="divergence-help">
          趋势背驰＝至少两个同级中枢；盘整背驰＝单中枢内第一/第三同向段比较；力度背离＝仅价格与指标满足。
          “日/30分 + L1/L2”是图表周期与笔/线段层级，A/B/C 只是指标证据等级，不是背驰级别；百分比是规则匹配度，不是未来涨跌成功率。
        </p>
        <div v-for="(div, index) in divergenceRows" :key="`${div.datetime}-${div.type}-${index}`" class="divergence-row">
          <div class="divergence-row-head">
            <span class="divergence-kind" :class="divergenceKindClass(div)">
              {{ divergenceTypeLabel(div) }}
            </span>
            <span class="divergence-prob mono">匹配 {{ (divergenceMatchScore(div) * 100).toFixed(0) }}%</span>
          </div>
          <div class="divergence-meta">
            <span>{{ divergenceLevelLabel(div) }}</span>
            <span>{{ divergenceEvidenceLabel(div) }}</span>
            <span>{{ divergenceFactors(div) }}</span>
          </div>
          <div class="divergence-location mono">{{ formatDivergenceLocation(div) }}</div>
          <div class="divergence-desc">{{ div.description }}</div>
          <div v-if="div.turn_scope" class="divergence-scope">{{ div.turn_scope }}</div>
          <div v-if="div.previous_price != null && div.macd_ratio != null" class="divergence-compare mono">
            前值 {{ div.previous_price.toFixed(2) }} → 当前 {{ div.price.toFixed(2) }}；MACD 力度 {{ (div.macd_ratio * 100).toFixed(0) }}%
          </div>
        </div>
        <p class="divergence-large-turn">小级别背驰不自动等于大级别转折；还需末个次级别中枢出现三卖/三买，且该条件仅为必要条件。</p>
      </div>

      <!-- Resonance -->
      <MultiLevelTrendChips v-if="levelTrends?.length" :trends="levelTrends" />

      <div v-if="signal.resonance?.共振" class="resonance-block">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
        </svg>
        <span>多级别共振: {{ signal.resonance.levels?.join(' + ') }}</span>
      </div>

      <!-- Description -->
      <div class="strategy-desc">{{ signal.description }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AISignal, DivergenceSignal } from '../../api/stock'
import type { LevelTrendChip } from '../../composables/useMultiLevelTrends'
import MultiLevelTrendChips from './MultiLevelTrendChips.vue'
import {
  divergenceChanType,
  divergenceEvidenceLabel,
  divergenceLevelLabel,
  divergenceTypeLabel,
} from '../../utils/divergencePresentation'

const props = defineProps<{
  signal: AISignal | null
  updatedAt?: string | null
  loading?: boolean
  levelTrends?: LevelTrendChip[]
}>()

defineEmits<{
  deepAnalyze: []
}>()

const isRuleOnly = computed(
  () => props.signal?.llm?.skipped === true || (props.signal != null && props.signal.llm?.used === false),
)

const showDeepButton = computed(
  () => isRuleOnly.value && !props.loading,
)

const divergenceRows = computed<DivergenceSignal[]>(() => {
  const rows = props.signal?.divergences?.length
    ? props.signal.divergences
    : (props.signal?.divergence ? [props.signal.divergence] : [])
  return rows.slice(-3).reverse()
})

function divergenceFactors(div: DivergenceSignal): string {
  const factors = div.confirmations?.length
    ? div.confirmations
    : ['MACD', ...(div.rsi_confirm ? ['RSI'] : []), ...(div.kdj_confirm ? ['KDJ'] : [])]
  return factors.join(' + ')
}

function divergenceKindClass(div: DivergenceSignal): string {
  return `div-${divergenceChanType(div)}-${div.type}`
}

function divergenceMatchScore(div: DivergenceSignal): number {
  return div.match_score ?? div.probability ?? 0
}

function formatDivergenceLocation(div: DivergenceSignal): string {
  const date = String(div.datetime || div.end || '').replace('T', ' ').slice(0, 16)
  return `${date || '位置未知'} @ ${Number(div.price).toFixed(2)}`
}

const dirClass = computed(() => {
  if (!props.signal) return ''
  if (props.signal.direction === '买入') return 'dir-buy'
  if (props.signal.direction === '卖出') return 'dir-sell'
  return 'dir-wait'
})

const dirSymbol = computed(() => {
  if (!props.signal) return '—'
  if (props.signal.direction === '买入') return '▲'
  if (props.signal.direction === '卖出') return '▼'
  return '◆'
})

const counterTrendGuardTitle = computed(() =>
  props.signal?.decision_guard?.mode === 'counter_trend_pullback'
    ? '逆势回调观察'
    : '逆势反弹观察',
)

const riskClass = computed(() => {
  if (!props.signal) return ''
  if (props.signal.risk_level === '低') return 'risk-low'
  if (props.signal.risk_level === '中') return 'risk-mid'
  return 'risk-high'
})

function confColor(c: number) {
  if (c >= 0.75) return 'var(--accent-green)'
  if (c >= 0.5) return 'var(--accent-amber)'
  return 'var(--accent-red)'
}
</script>

<style scoped>
.strategy-card { padding: 14px; }
.card-header { display: flex; align-items: center; justify-content: space-between; gap: 6px; flex-wrap: wrap; }
.title-with-source { display: flex; align-items: center; gap: 7px; }
.source-badge { font-size: 0.62rem; padding: 2px 7px; border-radius: 999px; font-weight: 600; }
.source-rule { color: var(--text-secondary); background: rgba(139,134,168,0.14); border: 1px solid rgba(139,134,168,0.28); }
.source-llm { color: var(--accent-blue); background: rgba(88,166,255,0.1); border: 1px solid rgba(88,166,255,0.25); }
.header-right { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.card-time { font-size: 0.65rem; color: var(--text-muted); font-family: var(--font-mono); }

.btn-deep {
  font-size: 0.68rem;
  padding: 4px 10px;
  border-radius: 8px;
  border: 1px solid var(--accent-blue);
  background: rgba(88, 166, 255, 0.1);
  color: var(--accent-blue);
  cursor: pointer;
}
.btn-deep:disabled { opacity: 0.6; cursor: not-allowed; }

.risk-badge {
  font-size: 0.7rem;
  padding: 3px 8px;
  border-radius: 10px;
  font-weight: 600;
}
.risk-low { background: rgba(63,185,80,0.15); color: var(--accent-green); }
.risk-mid { background: rgba(210,153,34,0.15); color: var(--accent-amber); }
.risk-high { background: rgba(248,81,73,0.15); color: var(--accent-red); }

.empty-strategy { padding: 8px 0; }
.hint-loading { font-size: 0.75rem; color: var(--text-muted); margin-top: 8px; text-align: center; }
.rule-hint {
  font-size: 0.72rem;
  color: var(--text-secondary);
  margin: 0 0 8px;
  line-height: 1.5;
}

.strategy-content { display: flex; flex-direction: column; gap: 12px; }

.direction-block {
  padding: 14px;
  border-radius: 10px;
  text-align: center;
}
.dir-buy { background: rgba(63,185,80,0.1); border: 1px solid rgba(63,185,80,0.2); }
.dir-sell { background: rgba(248,81,73,0.1); border: 1px solid rgba(248,81,73,0.2); }
.dir-wait { background: rgba(210,153,34,0.1); border: 1px solid rgba(210,153,34,0.2); }

.direction-main { display: flex; align-items: center; justify-content: center; gap: 8px; margin-bottom: 8px; }
.dir-arrow { font-size: 1.4rem; }
.dir-text { font-size: 1.3rem; font-weight: 700; }
.dir-buy .dir-text { color: var(--accent-green); }
.dir-sell .dir-text { color: var(--accent-red); }
.dir-wait .dir-text { color: var(--accent-amber); }

.dir-confidence { display: flex; align-items: center; gap: 8px; justify-content: center; }
.conf-pct { font-size: 0.8rem; color: var(--text-secondary); }

.counter-trend-guard {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 9px 10px;
  color: var(--accent-amber);
  background: rgba(210,153,34,0.08);
  border: 1px solid rgba(210,153,34,0.24);
  border-radius: 8px;
  font-size: 0.72rem;
  line-height: 1.45;
}
.counter-trend-guard span { color: var(--text-secondary); }

.price-levels { display: flex; flex-direction: column; gap: 6px; }
.level-row { display: flex; justify-content: space-between; align-items: center; }
.level-label { font-size: 0.8rem; color: var(--text-secondary); }
.level-value { font-size: 0.9rem; font-weight: 600; }

.period-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8rem;
  color: var(--text-secondary);
  padding: 8px 0;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
}

.divergence-block {
  padding: 8px 10px;
  background: rgba(88,166,255,0.08);
  border: 1px solid rgba(88,166,255,0.15);
  border-radius: 8px;
}
.divergence-header { display: flex; align-items: center; gap: 6px; font-size: 0.8rem; font-weight: 600; margin-bottom: 4px; color: var(--accent-blue); }
.divergence-count { margin-left: auto; color: var(--text-muted); font-size: 0.68rem; font-weight: 500; }
.divergence-help { margin: 5px 0 8px; color: var(--text-muted); font-size: 0.68rem; line-height: 1.45; }
.divergence-row { padding: 7px 0; border-top: 1px dashed rgba(88,166,255,0.16); }
.divergence-row-head { display: flex; align-items: center; gap: 6px; }
.divergence-kind { font-size: 0.7rem; font-weight: 700; }
.div-trend-top { color: #f43f5e; }
.div-trend-bottom { color: #10b981; }
.div-consolidation-top { color: #f59e0b; }
.div-consolidation-bottom { color: #14b8a6; }
.div-momentum-top { color: #c084fc; }
.div-momentum-bottom { color: #60a5fa; }
.divergence-prob { color: var(--accent-blue); }
.divergence-meta { display: flex; flex-wrap: wrap; gap: 4px 8px; margin-top: 4px; color: var(--text-muted); font-size: 0.63rem; }
.divergence-location { margin-top: 4px; color: var(--text-secondary); font-size: 0.68rem; }
.divergence-desc { font-size: 0.75rem; color: var(--text-secondary); }
.divergence-scope { margin-top: 3px; color: var(--text-muted); font-size: 0.66rem; line-height: 1.4; }
.divergence-compare { margin-top: 3px; color: var(--text-muted); font-size: 0.65rem; }
.divergence-large-turn { margin: 7px 0 0; padding-top: 7px; border-top: 1px solid rgba(88,166,255,0.12); color: var(--text-muted); font-size: 0.65rem; line-height: 1.45; }

.resonance-block {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8rem;
  color: var(--accent-purple);
  padding: 6px 10px;
  background: rgba(188,140,255,0.08);
  border: 1px solid rgba(188,140,255,0.15);
  border-radius: 8px;
}

.strategy-desc {
  font-size: 0.78rem;
  color: var(--text-secondary);
  line-height: 1.6;
  padding: 10px;
  background: var(--bg-secondary);
  border-radius: 8px;
}
</style>
