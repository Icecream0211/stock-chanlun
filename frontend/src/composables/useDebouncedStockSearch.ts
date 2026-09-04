/**
 * 股票搜索：缓存即时展示 + 防抖请求（PC 首页下拉 / 移动搜索栏共用）
 */
import { ref } from 'vue'
import { stockApi } from '@/api/stock'
import { peekApiCache } from '@/utils/apiCache'

export type StockSearchHit = { code: string; name: string; instrument_id?: string | null }

type SearchPayload = { data: { stocks?: StockSearchHit[] } }

function cacheKey(q: string) {
  return `GET:/stocks/search?q=${encodeURIComponent(q.trim())}`
}

export function useDebouncedStockSearch(debounceMs = 280) {
  const results = ref<StockSearchHit[]>([])
  const loading = ref(false)
  /** '' | 'no-results' | 'error' */
  const errorCode = ref<'no-results' | 'error' | ''>('')

  let timer: ReturnType<typeof setTimeout> | null = null
  let reqSeq = 0

  function applyHits(stocks: StockSearchHit[]) {
    results.value = stocks
    errorCode.value = stocks.length === 0 ? 'no-results' : ''
  }

  function clear() {
    if (timer) clearTimeout(timer)
    timer = null
    reqSeq += 1
    results.value = []
    errorCode.value = ''
    loading.value = false
  }

  function runQuery(q: string) {
    const q2 = q.trim()
    if (!q2 || q2.length < 2) {
      clear()
      return
    }
    if (timer) clearTimeout(timer)

    const peek = peekApiCache<SearchPayload>(cacheKey(q2))
    if (peek) {
      applyHits(peek.data.data.stocks ?? [])
      if (!peek.isStale) {
        loading.value = false
        return
      }
    } else {
      loading.value = true
    }

    const delay = peek ? 0 : debounceMs
    const seq = ++reqSeq

    timer = setTimeout(() => {
      void (async () => {
        try {
          const res = await stockApi.search(q2, peek?.isStale ? { force: true } : undefined)
          if (seq !== reqSeq) return
          applyHits(res.data.stocks ?? [])
        } catch {
          if (seq !== reqSeq) return
          results.value = []
          errorCode.value = 'error'
        } finally {
          if (seq === reqSeq) loading.value = false
        }
      })()
    }, delay)
  }

  async function searchImmediate(q: string): Promise<StockSearchHit[]> {
    const q2 = q.trim()
    if (!q2) {
      clear()
      return []
    }
    if (timer) clearTimeout(timer)
    const seq = ++reqSeq

    const peek = peekApiCache<SearchPayload>(cacheKey(q2))
    if (peek && !peek.isStale) {
      applyHits(peek.data.data.stocks ?? [])
      loading.value = false
      return results.value
    }
    if (peek) applyHits(peek.data.data.stocks ?? [])

    loading.value = !peek
    try {
      const res = await stockApi.search(q2, { force: !!peek })
      if (seq !== reqSeq) return results.value
      applyHits(res.data.stocks ?? [])
      return results.value
    } catch {
      if (seq !== reqSeq) return results.value
      results.value = []
      errorCode.value = 'error'
      return []
    } finally {
      if (seq === reqSeq) loading.value = false
    }
  }

  return { results, loading, errorCode, runQuery, searchImmediate, clear }
}
