<template>
  <div class="ai-chat">
    <!-- 欢迎语 -->
    <div v-if="messages.length === 0" class="welcome">
      <p class="welcome-title">AI 诊股 · 缠师</p>
      <div class="suggestions">
        <button
          v-for="s in suggestions"
          :key="s"
          class="suggestion-chip"
          @click="fillQuestion(s)"
        >{{ s }}</button>
      </div>
    </div>

    <!-- 消息列表 -->
    <div v-else ref="msgListRef" class="message-list">
      <div
        v-for="(msg, idx) in messages"
        :key="idx"
        class="message"
        :class="msg.role"
      >
        <div class="msg-bubble">
          <span v-if="msg.role === 'user'">{{ msg.content }}</span>
          <template v-else>{{ msg.displayText }}{{ msg.streaming ? '▌' : '' }}</template>
        </div>
        <div v-if="msg.error" class="msg-error">{{ msg.error }}</div>
      </div>
      <div v-if="isLoading && !hasStreamingReply" class="message assistant">
        <div class="msg-bubble typing">
          <span></span><span></span><span></span>
        </div>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="input-area">
      <textarea
        ref="inputRef"
        v-model="inputText"
        class="input-field"
        :placeholder="`询问 ${stockCode} 的走势...`"
        rows="2"
        @keydown.enter.exact.prevent="sendMessage"
        @input="autoResize"
      />
      <button
        v-if="isLoading"
        type="button"
        class="send-btn stop-btn"
        title="停止生成"
        @click="stopGeneration"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="6" y="6" width="12" height="12" rx="1"/>
        </svg>
      </button>
      <button
        v-else
        type="button"
        class="send-btn"
        :disabled="!inputText.trim()"
        @click="sendMessage"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useChanlunStore } from '@/stores/chanlun'
import { useAiDiagnosisChat } from '@/composables/useAiDiagnosisChat'

const props = defineProps<{ stockCode: string }>()

const chanlunStore = useChanlunStore()

const {
  messages,
  inputText,
  isLoading,
  msgListRef,
  inputRef,
  suggestions,
  sendMessage,
  stopGeneration,
  fillQuestion,
  autoResize,
} = useAiDiagnosisChat(props.stockCode, 'm_session', {
  showErrorToast: false,
  model: chanlunStore.aiModel,
})

const hasStreamingReply = computed(() =>
  messages.value.some(m => m.role === 'assistant' && m.streaming && m.displayText.length > 0),
)
</script>

<style scoped>
.ai-chat {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 300px;
}

.welcome {
  text-align: center;
  padding: 20px 0 12px;
}
.welcome-title {
  font-size: 0.85rem;
  font-weight: 700;
  color: var(--text-secondary);
  margin-bottom: 12px;
}
.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: center;
}
.suggestion-chip {
  padding: 5px 12px;
  border-radius: 16px;
  border: 1px solid var(--accent-blue);
  background: rgba(14, 165, 233, 0.08);
  color: var(--accent-blue);
  font-size: 0.72rem;
  cursor: pointer;
  transition: background 0.15s;
}
.suggestion-chip:active {
  background: rgba(14, 165, 233, 0.2);
}

.message-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-bottom: 8px;
  max-height: 320px;
}

.message {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.message.user { align-items: flex-end; }
.message.assistant { align-items: flex-start; }

.msg-bubble {
  max-width: 80%;
  padding: 8px 12px;
  border-radius: 14px;
  font-size: 0.82rem;
  line-height: 1.5;
  word-break: break-all;
}
.user .msg-bubble {
  background: linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%);
  color: #fff;
  border-bottom-right-radius: 4px;
}
.assistant .msg-bubble {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
}
.msg-error {
  font-size: 0.72rem;
  color: var(--accent-red);
  padding: 0 4px;
}

/* 打字机动画 */
.typing {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 10px 14px;
}
.typing span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
  animation: bounce 1.2s infinite;
}
.typing span:nth-child(2) { animation-delay: 0.2s; }
.typing span:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.5; }
  30% { transform: translateY(-4px); opacity: 1; }
}

.input-area {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  padding-top: 8px;
  border-top: 1px solid var(--border);
  margin-top: 4px;
}
.input-field {
  flex: 1;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 9px 14px;
  font-size: 0.85rem;
  line-height: 1.55;
  color: var(--text-primary);
  resize: none;
  outline: none;
  min-height: 52px;
  max-height: 120px;
  font-family: inherit;
  box-sizing: border-box;
  transition: border-color 0.15s;
}
.input-field:focus {
  border-color: var(--accent-blue);
}
.input-field::placeholder {
  color: var(--text-muted);
}
.send-btn {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  border: none;
  background: linear-gradient(135deg, #0ea5e9, #0284c7);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: filter 0.15s, opacity 0.15s;
}
.send-btn:disabled {
  opacity: 0.4;
  cursor: default;
}
.send-btn:not(:disabled):active {
  filter: brightness(1.1);
}
.send-btn.stop-btn {
  background: linear-gradient(135deg, #ef4444, #dc2626);
}
</style>
