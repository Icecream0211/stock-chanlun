import { defineStore } from 'pinia'
import { ref, watch, computed } from 'vue'
import { stockApi, type KLine, type ChanlunResult, type AISignal } from '../api/stock'
import { API_CACHE_TTL, peekApiCache, setApiCache } from '../utils/apiCache'
import { windowStartBefore } from '../utils/klineWindow'

export type LevelOption = '1min' | '5min' | '15min' | '30min' | '60min' | 'daily' | 'weekly' | 'monthly'

/** 指标显示配置 */
export interface IndicatorConfig {
  // 主图
  ma5: boolean
  ma20: boolean
  ma60: boolean
  /** 总开关：仅控制系统自动绘制的缠论叠加层，不影响 K 线、均线和手工划线。 */
  autoChanlun: boolean
  inclusions: boolean
  divergences: boolean
  bis: boolean
  biZhongshus: boolean
  xiangs: boolean
  zhongshus: boolean
  signals: boolean
  aiLines: boolean
  supportResistance: boolean
  /** 标准笔级中枢，或仅用于局部观察的线段边界切分。 */
  zhongshuView: 'growth' | 'sameLevel'
  // 副图
  volume: boolean
  macd: boolean
  rsi: boolean
  skdj: boolean
}

export const defaultIndicators: IndicatorConfig = {
  ma5: true,
  ma20: true,
  ma60: true,
  autoChanlun: true,
  inclusions: true,
  divergences: true,
  bis: true,
  biZhongshus: true,
  /** 四类缠论结构默认展示，用户可在指标面板逐项关闭。 */
  xiangs: true,
  zhongshus: true,
  signals: true,
  aiLines: false,
  supportResistance: false,
  zhongshuView: 'growth',
  volume: true,
  macd: true,
  rsi: false,
  skdj: false,
}

/** 首屏只取有限窗口；继续向左拖动时按可视根数逐块扩展。 */
const INITIAL_WINDOW_BARS = 180
const LOADED_WINDOW_CACHE_MAX_ENTRIES = 24

/**
 * 已成功分析过的窗口缓存。接口返回的是从窗口起点到结束边界的完整结构，
 * 因此同一标的/周期保留最早的一段即可覆盖之后向右的浏览。
 *
 * 不持久化到 localStorage：缠论完整结果可能很大，刷新按钮仍应能取到最新行情。
 */
const loadedChanlunWindows = new Map<string, ChanlunResult>()

function loadedWindowKey(code: string, level: LevelOption, endDate?: string) {
  return `${code}:${level}:${endDate || 'latest'}`
}

function windowStartsNoLaterThan(data: ChanlunResult, startDate?: string, level?: LevelOption) {
  if (!startDate) return Boolean(data.klines?.length)
  const first = data.klines?.[0]?.date?.slice(0, 10)
  if (!first) return false
  // 非交易日和周/月线的首根日期不一定恰好等于请求日期；它仍然覆盖该起点。
  const toleranceDays = level === 'monthly' ? 35 : level === 'weekly' ? 9 : 4
  const requested = new Date(`${startDate}T00:00:00`)
  requested.setDate(requested.getDate() + toleranceDays)
  return first <= requested.toISOString().slice(0, 10)
}

function rememberLoadedWindow(key: string, data: ChanlunResult) {
  const existing = loadedChanlunWindows.get(key)
  if (existing && (existing.klines?.length || 0) > (data.klines?.length || 0)) return
  if (loadedChanlunWindows.has(key)) loadedChanlunWindows.delete(key)
  while (loadedChanlunWindows.size >= LOADED_WINDOW_CACHE_MAX_ENTRIES) {
    const oldest = loadedChanlunWindows.keys().next().value
    if (oldest == null) break
    loadedChanlunWindows.delete(oldest)
  }
  loadedChanlunWindows.set(key, data)
}

const INDICATOR_KEY = 'chanstock_indicators_v5'
const PREVIOUS_INDICATOR_KEY = 'chanstock_indicators_v4'
const OLDER_INDICATOR_KEY = 'chanstock_indicators_v3'
const LEGACY_INDICATOR_KEY = 'chanstock_indicators_v1'

function loadIndicators(): IndicatorConfig {
  try {
    const raw = localStorage.getItem(INDICATOR_KEY)
    if (raw) return { ...defaultIndicators, ...JSON.parse(raw) as Partial<IndicatorConfig> }

    // v4 新增自动缠论绘制总开关；旧偏好保持不变，默认启用新总开关。
    const previousRaw = localStorage.getItem(PREVIOUS_INDICATOR_KEY)
    if (previousRaw) {
      return {
        ...defaultIndicators,
        ...JSON.parse(previousRaw) as Partial<IndicatorConfig>,
        autoChanlun: true,
      }
    }

    // v3 使用严格的固定核心笔级中枢为默认口径；线段边界切分仅用于局部对照，
    // 不再暗示它就是完整的同级别走势分解。
    const olderRaw = localStorage.getItem(OLDER_INDICATOR_KEY)
    if (olderRaw) {
      return {
        ...defaultIndicators,
        ...JSON.parse(olderRaw) as Partial<IndicatorConfig>,
        zhongshuView: 'growth',
        autoChanlun: true,
      }
    }

    // v1 中辅助横线曾默认展示。迁移时保留其余偏好，但明确关闭两类易造成拥挤的横线。
    const legacyRaw = localStorage.getItem(LEGACY_INDICATOR_KEY)
    if (!legacyRaw) return { ...defaultIndicators }
    return {
      ...defaultIndicators,
      ...JSON.parse(legacyRaw) as Partial<IndicatorConfig>,
      aiLines: false,
      supportResistance: false,
    }
  } catch { return { ...defaultIndicators } }
}

function isAbortError(e: unknown): boolean {
  return e instanceof Error && e.name === 'AbortError'
}

/** 按 YYYY-MM-DD 截取 K 线（chanlun 响应含全量 klines 时客户端筛选） */
function filterKlinesByDate(klines: KLine[], startDate?: string, endDate?: string): KLine[] {
  if (!startDate && !endDate) return klines
  return klines.filter(k => {
    const d = k.date.slice(0, 10)
    if (startDate && d < startDate) return false
    if (endDate && d > endDate) return false
    return true
  })
}

export const useChanlunStore = defineStore('chanlun', () => {
  const klines = ref<KLine[]>([])
  const chanlunResult = ref<ChanlunResult | null>(null)
  const aiSignal = ref<AISignal | null>(null)
  const loadingKline = ref(false)
  const loadingChanlun = ref(false)
  const loadingAI = ref(false)
  const errorKline = ref<string | null>(null)
  const errorChanlun = ref<string | null>(null)
  const errorAI = ref<string | null>(null)
  const currentLevel = ref<LevelOption>('daily')
  const currentCode = ref('')
  const requestedStartDate = ref<string | undefined>()
  const requestedEndDate = ref<string | undefined>()
  const loadingEarlier = ref(false)
  const aiModel = ref<string>('deepseek')
  const aiModelOptions = ['deepseek', 'gemini', 'custom'] as const
  type AiModelOption = (typeof aiModelOptions)[number]

  const isSupportedModel = (m: string): m is AiModelOption =>
    (aiModelOptions as readonly string[]).includes(m)
  const indicators = ref<IndicatorConfig>(loadIndicators())
  const klineUpdatedAt = ref<string | null>(null)
  const chanlunUpdatedAt = ref<string | null>(null)
  const aiUpdatedAt = ref<string | null>(null)

  /** 首屏无 K 线时显示图表骨架（chanlun 单请求已含 klines，通常不再单独拉 /kline） */
  const loadingChart = computed(
    () => (loadingChanlun.value || loadingKline.value) && klines.value.length === 0,
  )

  let loadSeq = 0
  let klineAbort: AbortController | null = null
  let chanlunAbort: AbortController | null = null
  let aiAbort: AbortController | null = null
  let settingsSynced = false

  async function syncAiModelFromServer() {
    if (settingsSynced) return
    settingsSynced = true
    try {
      const res = await stockApi.getSettings()
      const m = res.data?.ai_model
      if (isSupportedModel(m)) aiModel.value = m
    } catch { /* ignore */ }
  }

  watch(indicators, (val) => {
    try { localStorage.setItem(INDICATOR_KEY, JSON.stringify(val)) } catch { /* ignore */ }
  }, { deep: true })

  function timeNow() {
    return new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }

  function isStale(seq: number) {
    return seq !== loadSeq
  }

  function chanlunCacheKey(code: string, level: LevelOption, startDate?: string, endDate?: string, limit = 500) {
    const params = new URLSearchParams({ level, limit: String(limit) })
    if (startDate) params.set('start_date', startDate)
    if (endDate) params.set('end_date', endDate)
    return `GET:/chanlun/${code}?${params.toString()}`
  }

  function klineCacheKey(
    code: string,
    level: LevelOption,
    limit: number,
    startDate?: string,
    endDate?: string,
  ) {
    const params = new URLSearchParams({ level, limit: String(limit) })
    if (startDate) params.set('start_date', startDate)
    if (endDate) params.set('end_date', endDate)
    return `GET:/stocks/${code}/kline?${params.toString()}`
  }

  function aiSignalCacheKey(code: string, level: LevelOption, useLlm: boolean) {
    const params = new URLSearchParams({ level, model: aiModel.value })
    if (useLlm) params.set('use_llm', 'true')
    return `GET:/chanlun/${code}/ai?${params.toString()}`
  }

  function applyChanlunPayload(data: ChanlunResult) {
    chanlunResult.value = data
    if (data.klines?.length) {
      klines.value = data.klines
      klineUpdatedAt.value = timeNow()
    }
    chanlunUpdatedAt.value = timeNow()
    errorChanlun.value = null
  }

  async function fetchKline(
    code: string,
    level: LevelOption = 'daily',
    startDate?: string,
    endDate?: string,
    seq?: number,
    force = false,
  ) {
    const key = klineCacheKey(code, level, 500, startDate, endDate)
    let hadCached = false

    if (!force) {
      const peek = peekApiCache<{ data: { klines: KLine[] } }>(key)
      if (peek) {
        hadCached = true
        if (seq != null && isStale(seq)) return
        klines.value = peek.data.data.klines || []
        klineUpdatedAt.value = timeNow()
        errorKline.value = null
        if (!peek.isStale) return
        void stockApi
          .kline(code, level, 500, startDate, endDate, { force: true })
          .then(res => {
            if (seq != null && isStale(seq)) return
            klines.value = res.data.klines || []
            klineUpdatedAt.value = timeNow()
          })
          .catch(() => { /* 保留 stale */ })
        return
      }
    }

    klineAbort?.abort()
    klineAbort = new AbortController()
    const signal = klineAbort.signal
    loadingKline.value = !hadCached && klines.value.length === 0
    errorKline.value = null
    try {
      const res = await stockApi.kline(code, level, 500, startDate, endDate, { signal, force })
      if (seq != null && isStale(seq)) return
      klines.value = res.data.klines || []
      klineUpdatedAt.value = timeNow()
    } catch (e: unknown) {
      if (isAbortError(e)) return
      if (seq != null && isStale(seq)) return
      errorKline.value = e instanceof Error ? e.message : String(e)
    } finally {
      if (seq == null || !isStale(seq)) loadingKline.value = false
    }
  }

  async function fetchChanlun(
    code: string,
    level: LevelOption = 'daily',
    startDate?: string,
    endDate?: string,
    seq?: number,
    force = false,
    limit = INITIAL_WINDOW_BARS,
  ) {
    const key = chanlunCacheKey(code, level, startDate, endDate, limit)
    const loadedKey = loadedWindowKey(code, level, endDate)
    let hadCached = false

    if (!force) {
      const loaded = loadedChanlunWindows.get(loadedKey)
      if (loaded && windowStartsNoLaterThan(loaded, startDate, level)) {
        if (seq != null && isStale(seq)) return
        applyChanlunPayload(loaded)
        return
      }
    }

    if (!force) {
      const peek = peekApiCache<{ data: ChanlunResult }>(key)
      if (peek) {
        hadCached = true
        if (seq != null && isStale(seq)) return
        rememberLoadedWindow(loadedKey, peek.data.data)
        applyChanlunPayload(peek.data.data)
        if (!peek.isStale) return
        void stockApi
          .chanlun(code, level, startDate, endDate, limit, { force: true })
          .then(res => {
            if (seq != null && isStale(seq)) return
            rememberLoadedWindow(loadedKey, res.data)
            applyChanlunPayload(res.data)
          })
          .catch(() => { /* 保留 stale */ })
        return
      }
    }

    chanlunAbort?.abort()
    chanlunAbort = new AbortController()
    const signal = chanlunAbort.signal
    loadingChanlun.value = !hadCached && klines.value.length === 0
    errorChanlun.value = null
    try {
      const res = await stockApi.chanlun(code, level, startDate, endDate, limit, { signal, force })
      if (seq != null && isStale(seq)) return
      // 带 AbortSignal 的 axios 请求不会进入 withGetCached；显式回填两层缓存，
      // 让相同补页和已加载窗口都能直接复用。
      setApiCache(key, res, API_CACHE_TTL.chanlun)
      rememberLoadedWindow(loadedKey, res.data)
      applyChanlunPayload(res.data)
    } catch (e: unknown) {
      if (isAbortError(e)) return
      if (seq != null && isStale(seq)) return
      errorChanlun.value = e instanceof Error ? e.message : String(e)
    } finally {
      if (seq == null || !isStale(seq)) loadingChanlun.value = false
    }
  }

  async function fetchAISignal(
    code: string,
    level: LevelOption = 'daily',
    options?: { useLlm?: boolean; seq?: number; force?: boolean },
  ) {
    const useLlm = options?.useLlm ?? false
    const seq = options?.seq
    const force = options?.force ?? false
    const key = aiSignalCacheKey(code, level, useLlm)
    let hadCached = false

    if (!force) {
      const peek = peekApiCache<{ data: AISignal }>(key)
      if (peek) {
        hadCached = true
        if (seq != null && isStale(seq)) return
        aiSignal.value = peek.data.data
        aiUpdatedAt.value = timeNow()
        errorAI.value = null
        if (!peek.isStale) return
        void stockApi
          .aiSignal(code, level, aiModel.value, { useLlm, force: true })
          .then(res => {
            if (seq != null && isStale(seq)) return
            aiSignal.value = res.data
            aiUpdatedAt.value = timeNow()
          })
          .catch(() => { /* 保留 stale */ })
        return
      }
    }

    aiAbort?.abort()
    aiAbort = new AbortController()
    const signal = aiAbort.signal
    loadingAI.value = !hadCached && !aiSignal.value
    errorAI.value = null
    try {
      const res = await stockApi.aiSignal(code, level, aiModel.value, {
        useLlm,
        signal,
        force,
      })
      if (seq != null && isStale(seq)) return
      aiSignal.value = res.data
      aiUpdatedAt.value = timeNow()
    } catch (e: unknown) {
      if (isAbortError(e)) return
      if (seq != null && isStale(seq)) return
      errorAI.value = e instanceof Error ? e.message : String(e)
    } finally {
      if (seq == null || !isStale(seq)) loadingAI.value = false
    }
  }

  async function loadAll(
    code: string,
    level: LevelOption = 'daily',
    startDate?: string,
    endDate?: string,
    options?: { force?: boolean },
  ) {
    void syncAiModelFromServer()
    const seq = ++loadSeq
    const force = options?.force ?? false
    currentLevel.value = level
    currentCode.value = code
    requestedStartDate.value = startDate
    requestedEndDate.value = endDate
    const hasDateFilter = Boolean(startDate || endDate)

    // 缠论与 AI 策略并行拉取（不同接口，可重叠等待）
    const aiTask = fetchAISignal(code, level, { useLlm: false, seq, force })

    // 日期控件限定可回溯边界；首屏仍只拉一个窗口，避免分钟/日周月线一次全量下载。
    await fetchChanlun(code, level, undefined, endDate, seq, force, INITIAL_WINDOW_BARS)

    if (!isStale(seq) && hasDateFilter && klines.value.length) {
      klines.value = filterKlinesByDate(klines.value, startDate, endDate)
    }

    if (!isStale(seq) && !klines.value.length && !errorChanlun.value) {
      await fetchKline(code, level, startDate, endDate, seq, force)
    }

    if (!isStale(seq)) {
      await aiTask
    }
  }

  async function loadEarlierKlines(visibleBars: number) {
    if (loadingEarlier.value || !currentCode.value || !klines.value.length) return
    const first = klines.value[0]?.date
    if (!first) return
    const startDate = windowStartBefore(first, currentLevel.value, visibleBars, requestedStartDate.value)
    if (!startDate || startDate >= first.slice(0, 10)) return

    loadingEarlier.value = true
    try {
      await fetchChanlun(
        currentCode.value,
        currentLevel.value,
        startDate,
        requestedEndDate.value,
        undefined,
        false,
        Math.max(20, Math.round(visibleBars)),
      )
    } finally {
      loadingEarlier.value = false
    }
  }

  async function setAiModel(model: string, code: string) {
    aiModel.value = model
    await stockApi.setAiModel(model)
    // 切换候选模型只保存偏好；只有用户明确点击“LLM 深度分析”才调用大模型。
    await fetchAISignal(code, currentLevel.value, { useLlm: false, force: true })
  }

  type BooleanIndicatorKey = Exclude<keyof IndicatorConfig, 'zhongshuView'>

  function toggleIndicator(key: BooleanIndicatorKey) {
    indicators.value[key] = !indicators.value[key]
  }

  function setIndicator(key: BooleanIndicatorKey, value: boolean) {
    indicators.value[key] = value
  }

  function setZhongshuView(view: IndicatorConfig['zhongshuView']) {
    indicators.value.zhongshuView = view
  }

  return {
    klines, chanlunResult, aiSignal,
    loadingKline, loadingChanlun, loadingAI, loadingChart,
    errorKline, errorChanlun, errorAI,
    currentLevel, currentCode, requestedStartDate, requestedEndDate, loadingEarlier, aiModel, aiModelOptions, indicators,
    klineUpdatedAt, chanlunUpdatedAt, aiUpdatedAt,
    fetchKline, fetchChanlun, fetchAISignal, loadAll, loadEarlierKlines, setAiModel,
    toggleIndicator, setIndicator, setZhongshuView,
  }
})
