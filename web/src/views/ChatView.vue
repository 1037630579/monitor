<template>
  <div class="chat-container">
    <div class="chat-header">
      <div class="chat-title">
        <el-icon :size="20"><ChatDotRound /></el-icon>
        <span>多云监控助手</span>
      </div>
      <el-button size="small" :icon="RefreshRight" @click="handleReset" :disabled="loading">
        新对话
      </el-button>
    </div>

    <div class="chat-messages" ref="messagesRef">
      <div v-if="messages.length === 0" class="chat-welcome">
        <el-icon :size="48" color="#409eff"><Monitor /></el-icon>
        <h3>多云统一监控助手</h3>
        <p>输入自然语言查询云平台监控指标，支持 AWS、阿里云等多云平台</p>
        <div class="quick-actions">
          <el-tag
            v-for="q in quickQueries"
            :key="q"
            effect="plain"
            class="quick-tag"
            @click="handleQuickQuery(q)"
          >
            {{ q }}
          </el-tag>
        </div>
      </div>

      <div v-for="(msg, idx) in messages" :key="idx" :class="['chat-msg', msg.role]">
        <div class="msg-avatar">
          <el-avatar v-if="msg.role === 'user'" :size="32" :icon="User" />
          <el-avatar v-else :size="32" :icon="Monitor" style="background: #409eff" />
        </div>
        <div class="msg-content">
          <div v-if="msg.role === 'user'" class="msg-text user-text">{{ msg.text }}</div>
          <div v-else class="msg-text assistant-text">
            <div v-if="msg.toolCalls && msg.toolCalls.length" class="tool-calls">
              <div v-for="(tc, ti) in msg.toolCalls" :key="ti" class="tool-call-item">
                <el-icon :size="14"><Connection /></el-icon>
                <span>{{ formatToolName(tc.name) }}</span>
                <span v-if="tc.paramsText" class="tool-params">{{ tc.paramsText }}</span>
              </div>
            </div>
            <div v-html="msg.html" class="markdown-body"></div>
            <div v-if="msg.cost" class="msg-cost">
              💰 费用: ${{ msg.cost.toFixed(6) }}
            </div>
            <div v-if="msg.webhookOk !== undefined" class="msg-webhook">
              {{ msg.webhookOk ? '✅ 已推送到 Webhook' : '⚠️ Webhook 推送失败' }}
            </div>
          </div>
        </div>
      </div>

      <div v-if="loading" class="chat-msg assistant">
        <div class="msg-avatar">
          <el-avatar :size="32" :icon="Monitor" style="background: #409eff" />
        </div>
        <div class="msg-content">
          <div class="msg-text assistant-text">
            <div v-if="streamToolCalls.length" class="tool-calls">
              <div v-for="(tc, ti) in streamToolCalls" :key="ti" class="tool-call-item">
                <el-icon :size="14" class="spin"><Loading /></el-icon>
                <span>{{ formatToolName(tc.name) }}</span>
                <span v-if="tc.paramsText" class="tool-params">{{ tc.paramsText }}</span>
              </div>
            </div>
            <div v-if="streamText" v-html="streamHtml" class="markdown-body"></div>
            <div v-else-if="!streamToolCalls.length" class="typing-indicator">
              <span></span><span></span><span></span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="chat-input-area">
      <el-input
        v-model="inputText"
        placeholder="输入你的查询，如: 查询 AWS EC2 闲置实例"
        :disabled="loading"
        @keydown.enter.exact.prevent="handleSend"
        size="large"
        clearable
      >
        <template #append>
          <el-button
            :icon="loading ? Loading : Promotion"
            @click="loading ? handleStop() : handleSend()"
            :type="loading ? 'danger' : 'primary'"
          >
            {{ loading ? '停止' : '发送' }}
          </el-button>
        </template>
      </el-input>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
import { marked } from 'marked'
import { sendChatMessage, resetChatSession } from '../api'
import {
  ChatDotRound,
  User,
  Monitor,
  Promotion,
  Loading,
  Connection,
  RefreshRight,
} from '@element-plus/icons-vue'

interface ToolCall {
  name: string
  paramsText: string
}

interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
  html?: string
  toolCalls?: ToolCall[]
  cost?: number
  webhookOk?: boolean
}

const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const loading = ref(false)
const sessionId = ref('')
const messagesRef = ref<HTMLElement>()
const streamText = ref('')
const streamToolCalls = ref<ToolCall[]>([])
let abortController: AbortController | null = null

const quickQueries = [
  '查询 AWS EC2',
  '查看 AWS S3 存储桶',
  '查询 VPN 状态',
  '查看所有 AWS 账户',
]

const streamHtml = computed(() => {
  try {
    return marked.parse(streamText.value) as string
  } catch {
    return streamText.value
  }
})

function formatToolName(name: string): string {
  return name
    .replace(/^mcp__cloud__/, '')
    .replace(/_/g, ' ')
}

function scrollToBottom() {
  nextTick(() => {
    const el = messagesRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

watch([streamText, streamToolCalls], scrollToBottom, { deep: true })

function handleQuickQuery(q: string) {
  inputText.value = q
  handleSend()
}

function handleSend() {
  const text = inputText.value.trim()
  if (!text || loading.value) return

  messages.value.push({ role: 'user', text })
  inputText.value = ''
  loading.value = true
  streamText.value = ''
  streamToolCalls.value = []
  scrollToBottom()

  const currentToolCalls: ToolCall[] = []
  let currentText = ''
  let currentCost: number | undefined
  let currentWebhook: boolean | undefined

  abortController = sendChatMessage(text, sessionId.value, {
    onSession(id) {
      sessionId.value = id
    },
    onText(t) {
      currentText += t + '\n\n'
      streamText.value = currentText
    },
    onToolCall(name, params) {
      const paramsText = Object.entries(params)
        .map(([k, v]) => `${k}=${v}`)
        .join(', ')
      const tc = { name, paramsText }
      currentToolCalls.push(tc)
      streamToolCalls.value = [...currentToolCalls]
    },
    onCost(cost) {
      currentCost = cost
    },
    onWebhook(ok) {
      currentWebhook = ok
    },
    onError(err) {
      loading.value = false
      streamText.value = ''
      streamToolCalls.value = []
      messages.value.push({
        role: 'assistant',
        text: `查询出错: ${err}`,
        html: `<p style="color:#f56c6c">查询出错: ${err}</p>`,
      })
      scrollToBottom()
    },
    onDone() {
      loading.value = false
      if (currentText) {
        let html: string
        try {
          html = marked.parse(currentText) as string
        } catch {
          html = currentText
        }
        messages.value.push({
          role: 'assistant',
          text: currentText,
          html,
          toolCalls: currentToolCalls.length ? [...currentToolCalls] : undefined,
          cost: currentCost,
          webhookOk: currentWebhook,
        })
      }
      streamText.value = ''
      streamToolCalls.value = []
      scrollToBottom()
    },
  })
}

function handleStop() {
  abortController?.abort()
  loading.value = false
  streamText.value = ''
  streamToolCalls.value = []
}

async function handleReset() {
  if (sessionId.value) {
    try {
      await resetChatSession(sessionId.value)
    } catch {
      // ignore
    }
  }
  sessionId.value = ''
  messages.value = []
  streamText.value = ''
  streamToolCalls.value = []
}
</script>

<style scoped>
.chat-container {
  max-width: 960px;
  margin: 0 auto;
  height: calc(100vh - 60px);
  display: flex;
  flex-direction: column;
  padding: 0 16px;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 1px solid #ebeef5;
}

.chat-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px 0;
}

.chat-welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #909399;
  gap: 12px;
}

.chat-welcome h3 {
  color: #303133;
  margin: 0;
}

.chat-welcome p {
  margin: 0;
  font-size: 14px;
}

.quick-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
  justify-content: center;
}

.quick-tag {
  cursor: pointer;
  transition: all 0.2s;
}

.quick-tag:hover {
  color: #409eff;
  border-color: #409eff;
  background: #ecf5ff;
}

.chat-msg {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.chat-msg.user {
  flex-direction: row-reverse;
}

.msg-avatar {
  flex-shrink: 0;
}

.msg-content {
  max-width: 80%;
  min-width: 60px;
}

.msg-text {
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
}

.user-text {
  background: #409eff;
  color: #fff;
  border-top-right-radius: 4px;
}

.assistant-text {
  background: #fff;
  color: #303133;
  border-top-left-radius: 4px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.tool-calls {
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px dashed #ebeef5;
}

.tool-call-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #909399;
  padding: 2px 0;
}

.tool-params {
  color: #b1b3b8;
  font-family: monospace;
  font-size: 11px;
}

.msg-cost {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}

.msg-webhook {
  font-size: 12px;
  color: #909399;
}

.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 4px 0;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  background: #c0c4cc;
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out both;
}

.typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
.typing-indicator span:nth-child(2) { animation-delay: -0.16s; }

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.chat-input-area {
  padding: 12px 0 16px;
  border-top: 1px solid #ebeef5;
}

/* Markdown 样式 */
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  margin: 12px 0 8px;
  font-size: 15px;
  font-weight: 600;
}

.markdown-body :deep(h1) { font-size: 17px; }

.markdown-body :deep(p) {
  margin: 4px 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 20px;
  margin: 4px 0;
}

.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
  font-size: 13px;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid #ebeef5;
  padding: 6px 10px;
  text-align: left;
}

.markdown-body :deep(th) {
  background: #f5f7fa;
  font-weight: 600;
}

.markdown-body :deep(code) {
  background: #f5f7fa;
  padding: 2px 4px;
  border-radius: 3px;
  font-size: 13px;
}

.markdown-body :deep(pre) {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
}

.markdown-body :deep(blockquote) {
  border-left: 3px solid #409eff;
  padding-left: 12px;
  color: #606266;
  margin: 8px 0;
}
</style>
