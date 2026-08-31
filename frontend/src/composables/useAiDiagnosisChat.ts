import { ref, nextTick, onUnmounted, watch, type MaybeRefOrGetter, toValue } from 'vue'
import { stockApi } from '@/api/stock'
import toast from '@/composables/useToast'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  displayText: string
  streaming: boolean
  error?: string
}

const DEFAULT_SUGGESTIONS = [
  '分析当前走势',
  '现在是买点吗？',
  '压力位在哪？',
  '止损位建议',
  '可以买入吗？',
]

export function useAiDiagnosisChat(
  stockCode: MaybeRefOrGetter<string>,
  sessionPrefix = 'session',
  options?: { showErrorToast?: boolean; model?: string },
) {
  const messages = ref<ChatMessage[]>([])
  const inputText = ref('')
  const isLoading = ref(false)
  const msgListRef = ref<HTMLElement>()
  const inputRef = ref<HTMLTextAreaElement>()
  const sessionId = ref('')
  const model = options?.model ?? 'deepseek'

  function resetSession() {
    const code = toValue(stockCode)
    sessionId.value = `${sessionPrefix}_${code}_${Date.now()}`
  }

  resetSession()

  let diagnosisAbort: AbortController | null = null

  function cancelInFlightDiagnosis() {
    diagnosisAbort?.abort()
    diagnosisAbort = null
  }

  let scrollScheduled = false
  function scrollToBottom() {
    if (scrollScheduled) return
    scrollScheduled = true
    requestAnimationFrame(() => {
      scrollScheduled = false
      if (msgListRef.value) {
        msgListRef.value.scrollTop = msgListRef.value.scrollHeight
      }
    })
  }

  function fillQuestion(q: string) {
    inputText.value = q
    inputRef.value?.focus()
  }

  function clearChat() {
    cancelInFlightDiagnosis()
    messages.value = []
    isLoading.value = false
    resetSession()
  }

  watch(
    () => toValue(stockCode),
    () => {
      clearChat()
    },
  )

  const INPUT_MIN_HEIGHT_PX = 52

  function autoResize(e: Event) {
    const el = e.target as HTMLTextAreaElement
    el.style.height = 'auto'
    el.style.height =
      Math.min(Math.max(el.scrollHeight, INPUT_MIN_HEIGHT_PX), 120) + 'px'
  }

  async function sendMessage() {
    const text = inputText.value.trim()
    if (!text || isLoading.value) return

    const code = toValue(stockCode)
    if (!code) return

    cancelInFlightDiagnosis()
    const ctrl = new AbortController()
    diagnosisAbort = ctrl

    messages.value.push({
      role: 'user',
      content: text,
      displayText: text,
      streaming: false,
    })
    inputText.value = ''
    await nextTick()
    if (inputRef.value) {
      inputRef.value.style.height = ''
    }
    scrollToBottom()

    const aiMsgIdx = messages.value.length
    messages.value.push({
      role: 'assistant',
      content: '',
      displayText: '',
      streaming: true,
    })
    isLoading.value = true

    try {
      let fullText = ''
      let tokenCount = 0
      const stream = stockApi.aiDiagnosisStream(
        code,
        text,
        sessionId.value,
        model,
        ctrl.signal,
      )

      for await (const token of stream) {
        if (ctrl.signal.aborted) break
        fullText += token
        tokenCount += 1
        messages.value[aiMsgIdx] = {
          role: 'assistant',
          content: fullText,
          displayText: fullText,
          streaming: true,
        }
        if (tokenCount % 4 === 0) {
          await nextTick()
          scrollToBottom()
        }
      }

      if (ctrl.signal.aborted) return

      messages.value[aiMsgIdx] = {
        role: 'assistant',
        content: fullText,
        displayText: fullText,
        streaming: false,
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') {
        const partial = messages.value[aiMsgIdx]
        if (partial?.streaming) {
          messages.value[aiMsgIdx] = {
            ...partial,
            streaming: false,
            content: partial.content || '（已停止生成）',
            displayText: partial.displayText || '（已停止生成）',
          }
        }
        return
      }
      const message = err instanceof Error ? err.message : '诊断失败，请重试'
      messages.value[aiMsgIdx] = {
        role: 'assistant',
        content: '',
        displayText: '',
        streaming: false,
        error: message,
      }
      if (options?.showErrorToast !== false) {
        toast.error('AI 诊断请求失败，请重试')
      }
    } finally {
      if (diagnosisAbort === ctrl) diagnosisAbort = null
      isLoading.value = false
      await nextTick()
      scrollToBottom()
    }
  }

  function stopGeneration() {
    if (!isLoading.value) return
    cancelInFlightDiagnosis()
    isLoading.value = false
    for (let i = messages.value.length - 1; i >= 0; i--) {
      const m = messages.value[i]
      if (m.role === 'assistant' && m.streaming) {
        messages.value[i] = {
          ...m,
          streaming: false,
          content: m.content || '（已停止生成）',
          displayText: m.displayText || '（已停止生成）',
        }
        break
      }
    }
  }

  onUnmounted(cancelInFlightDiagnosis)

  return {
    messages,
    inputText,
    isLoading,
    msgListRef,
    inputRef,
    sessionId,
    suggestions: DEFAULT_SUGGESTIONS,
    sendMessage,
    stopGeneration,
    fillQuestion,
    clearChat,
    scrollToBottom,
    autoResize,
  }
}
