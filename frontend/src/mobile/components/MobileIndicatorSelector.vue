<template>
  <div class="ind-selector">
    <!-- 触发按钮 -->
    <button class="ind-btn" @click="toggleOpen" :class="{ active: isOpen }">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="4" y1="6" x2="20" y2="6"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="18" x2="20" y2="18"/>
      </svg>
      指标
    </button>

    <!-- 下拉面板 -->
    <Teleport to="body">
      <Transition name="panel">
        <div v-if="isOpen" class="ind-panel">
          <!-- 拖拽条 -->
          <div class="ind-handle" @click="toggleOpen">
            <div class="handle-bar" />
          </div>

          <div class="ind-content">
            <!-- 主图指标 -->
            <div class="ind-group">
              <div class="ind-group-title">主图指标</div>
              <div class="ind-chips">
                <button
                  v-for="ind in mainInds"
                  :key="ind.key"
                  class="ind-chip"
                  :class="{ active: cfg[ind.key] }"
                  :style="ind.dotStyle"
                  @click="store.toggleIndicator(ind.key)"
                >
                  <span class="chip-dot" :style="{ background: ind.dotColor }" />
                  {{ ind.label }}
                </button>
              </div>
            </div>

            <!-- 缠论元素 -->
            <div class="ind-group">
              <div class="ind-group-title">缠论元素</div>
              <div class="ind-chips">
                <button
                  class="ind-chip auto-chanlun-toggle"
                  :class="{ active: cfg.autoChanlun }"
                  @click="store.toggleIndicator('autoChanlun')"
                >
                  <span class="chip-dot" style="background: #A78BFA" />
                  自动缠论绘制
                </button>
                <button
                  v-for="ind in chanlunInds"
                  :key="ind.key"
                  class="ind-chip"
                  :class="{ active: cfg[ind.key] }"
                  @click="store.toggleIndicator(ind.key)"
                >
                  <span class="chip-dot" :style="ind.dotStyle" />
                  {{ ind.label }}
                </button>
              </div>
              <div class="center-view">
                <span>中枢视角</span>
                <button :class="{ active: cfg.zhongshuView === 'growth' }" @click="store.setZhongshuView('growth')">标准笔级</button>
                <button :class="{ active: cfg.zhongshuView === 'sameLevel' }" @click="store.setZhongshuView('sameLevel')">线段内局部</button>
              </div>
            </div>

            <!-- 副图指标 -->
            <div class="ind-group">
              <div class="ind-group-title">副图指标</div>
              <div class="ind-chips">
                <button
                  v-for="ind in subInds"
                  :key="ind.key"
                  class="ind-chip"
                  :class="{ active: cfg[ind.key] }"
                  @click="store.toggleIndicator(ind.key)"
                >
                  <span class="chip-dot" :style="ind.dotStyle" />
                  {{ ind.label }}
                </button>
              </div>
            </div>

            <!-- 快捷操作 -->
            <div class="ind-quick">
              <button class="quick-btn" @click="showAll">显示全部</button>
              <button class="quick-btn" @click="hideAll">隐藏全部</button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 遮罩 -->
    <div v-if="isOpen" class="ind-backdrop" @click="toggleOpen" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useChanlunStore, type IndicatorConfig } from '@/stores/chanlun'

const store = useChanlunStore()
const isOpen = ref(false)

const cfg = computed(() => store.indicators)

const mainInds = [
  { key: 'ma5' as const, label: 'MA5', dotColor: '#FFD166', dotStyle: { background: '#FFD166' } },
  { key: 'ma20' as const, label: 'MA20', dotColor: '#22D3EE', dotStyle: { background: '#22D3EE' } },
  { key: 'ma60' as const, label: 'MA60', dotColor: '#A78BFA', dotStyle: { background: '#A78BFA' } },
]

const chanlunInds = [
  { key: 'inclusions' as const, label: '包含K', dotStyle: { background: '#8B86A8' } },
  { key: 'divergences' as const, label: '背驰', dotStyle: { background: '#E879F9' } },
  { key: 'bis' as const, label: '笔', dotStyle: { background: '#2F9BFF' } },
  { key: 'biZhongshus' as const, label: '笔中枢', dotStyle: { background: 'rgba(47,155,255,0.45)', border: '1px dashed #2F9BFF' } },
  { key: 'xiangs' as const, label: '线段', dotStyle: { background: '#FF8C42' } },
  { key: 'zhongshus' as const, label: '线段中枢', dotStyle: { background: '#FF4D6D' } },
  { key: 'signals' as const, label: '买卖点', dotStyle: { background: '#3fb950' } },
  { key: 'aiLines' as const, label: '入场/止盈止损', dotStyle: { background: '#d29922' } },
  { key: 'supportResistance' as const, label: '支撑阻力', dotStyle: { background: 'linear-gradient(90deg, #3fb950, #f85149)' } },
]

const subInds = [
  { key: 'volume' as const, label: '成交量', dotStyle: { background: '#7d8590' } },
  { key: 'macd' as const, label: 'MACD', dotStyle: { background: '#58a6ff' } },
  { key: 'rsi' as const, label: 'RSI', dotStyle: { background: '#f0b429' } },
  { key: 'skdj' as const, label: 'SKDJ', dotStyle: { background: '#bc8cff' } },
]

function toggleOpen() {
  isOpen.value = !isOpen.value
}

function showAll() {
  for (const key in store.indicators) {
    if (key !== 'zhongshuView') store.setIndicator(key as Exclude<keyof IndicatorConfig, 'zhongshuView'>, true)
  }
}

function hideAll() {
  for (const key in store.indicators) {
    if (key !== 'zhongshuView') store.setIndicator(key as Exclude<keyof IndicatorConfig, 'zhongshuView'>, false)
  }
}
</script>

<style scoped>
.ind-selector {
  position: relative;
  display: inline-block;
}

.ind-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-secondary);
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
  min-height: 36px;
}

.ind-btn.active,
.ind-btn:active {
  border-color: rgba(56, 189, 248, 0.45);
  color: var(--text-primary);
  background: rgba(56, 189, 248, 0.08);
}

.center-view {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  font-size: 0.76rem;
  color: var(--text-secondary);
}

.center-view button {
  padding: 4px 7px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
}

.center-view button.active {
  border-color: rgba(56, 189, 248, 0.65);
  color: #38bdf8;
  background: rgba(56, 189, 248, 0.1);
}

/* ── 面板 ── */
.ind-backdrop {
  position: fixed;
  inset: 0;
  z-index: 199;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(2px);
}

.ind-panel {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 200;
  background: var(--bg-primary);
  border-top: 1px solid var(--border-strong);
  border-radius: 20px 20px 0 0;
  padding-bottom: env(safe-area-inset-bottom, 0px);
}

.ind-handle {
  display: flex;
  justify-content: center;
  padding: 12px 0 8px;
  cursor: pointer;
}
.handle-bar {
  width: 36px;
  height: 4px;
  background: var(--border-strong);
  border-radius: 2px;
}

.ind-content {
  padding: 0 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-height: 60vh;
  overflow-y: auto;
}

.ind-group {}

.ind-group-title {
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 10px;
}

.ind-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.ind-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: transparent;
  color: var(--text-muted);
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s, background 0.15s, transform 0.1s;
  min-height: 36px;
  -webkit-tap-highlight-color: transparent;
}

.ind-chip:active {
  transform: scale(0.94);
  opacity: 0.8;
}

.ind-chip.active {
  border-color: rgba(56, 189, 248, 0.4);
  color: var(--text-primary);
  background: rgba(56, 189, 248, 0.08);
}

.auto-chanlun-toggle {
  border-color: rgba(167, 139, 250, 0.38);
  background: rgba(167, 139, 250, 0.08);
}

.chip-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.ind-quick {
  display: flex;
  gap: 8px;
  padding-top: 4px;
  border-top: 1px solid var(--border);
}

.quick-btn {
  flex: 1;
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
  min-height: 40px;
}

.quick-btn:active {
  border-color: var(--accent-blue);
  color: var(--text-primary);
  background: var(--bg-hover);
}

/* ── 动画 ── */
.panel-enter-active, .panel-leave-active {
  transition: opacity 0.2s ease;
}
.panel-enter-active .ind-panel,
.panel-leave-active .ind-panel {
  transition: transform 0.25s cubic-bezier(0.32, 0.72, 0, 1);
}
.panel-enter-from, .panel-leave-to {
  opacity: 0;
}
.panel-enter-from .ind-panel {
  transform: translateY(100%);
}
.panel-leave-to .ind-panel {
  transform: translateY(100%);
}
</style>
