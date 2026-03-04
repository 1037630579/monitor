import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

// ── 实时对话 ──

export interface ChatCallbacks {
  onSession?: (sessionId: string) => void
  onText?: (text: string) => void
  onToolCall?: (name: string, params: Record<string, any>) => void
  onCost?: (costUsd: number) => void
  onWebhook?: (success: boolean) => void
  onError?: (error: string) => void
  onDone?: () => void
}

export function sendChatMessage(
  message: string,
  sessionId: string,
  callbacks: ChatCallbacks,
): AbortController {
  const controller = new AbortController()

  fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId }),
    signal: controller.signal,
  })
    .then((response) => {
      const reader = response.body?.getReader()
      if (!reader) return

      const decoder = new TextDecoder()
      let buffer = ''

      function processLines(text: string) {
        buffer += text
        const lines = buffer.split(/\r\n|\r|\n/)
        buffer = lines.pop() || ''

        let currentEvent = ''
        for (const rawLine of lines) {
          const line = rawLine.trim()
          if (!line) {
            currentEvent = ''
            continue
          }
          if (line.startsWith(':')) continue
          if (line.startsWith('event:')) {
            currentEvent = line.slice(6).trim()
            continue
          }
          if (!line.startsWith('data:') || !currentEvent) continue

          const data = line.slice(5).trim()
          try {
            const parsed = JSON.parse(data)
            switch (currentEvent) {
              case 'session':
                callbacks.onSession?.(parsed.session_id)
                break
              case 'text':
                callbacks.onText?.(parsed.text)
                break
              case 'tool_call':
                callbacks.onToolCall?.(parsed.name, parsed.params)
                break
              case 'cost':
                callbacks.onCost?.(parsed.cost_usd)
                break
              case 'webhook':
                callbacks.onWebhook?.(parsed.success)
                break
              case 'error':
                callbacks.onError?.(parsed.error)
                break
              case 'done':
                callbacks.onDone?.()
                break
            }
          } catch {
            // ignore malformed JSON
          }
          currentEvent = ''
        }
      }

      function pump(): Promise<void> {
        return reader!.read().then(({ done, value }) => {
          if (done) {
            if (buffer) processLines('\n')
            callbacks.onDone?.()
            return
          }
          processLines(decoder.decode(value, { stream: true }))
          return pump()
        })
      }

      return pump()
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        callbacks.onError?.(err.message)
      }
    })

  return controller
}

export async function resetChatSession(sessionId: string): Promise<void> {
  await api.post('/chat/reset', { session_id: sessionId })
}

// ── AWS 巡检 ──

export interface AwsResource {
  resource_type: string
  instance_id: string
  instance_name: string
  instance_type: string
  account: string
  status: string
  region: string
  availability_zone: string
  private_ip: string
  public_ip: string | null
  avg_cpu: number | null
  max_cpu: number | null
  avg_mem: number | null
  max_mem: number | null
  tags: Record<string, string>
  extra: Record<string, string>
  scan_time: string
}

export interface AwsPageResult {
  total: number
  items: AwsResource[]
  page: number
  page_size: number
}

export interface AwsSummary {
  total: number
  by_resource_type: Record<string, number>
  by_status: Record<string, number>
  by_region: Record<string, number>
  scan_time: string | null
}

export interface AwsFilterOptions {
  resource_types: string[]
  statuses: string[]
  regions: string[]
  accounts: string[]
}

export async function fetchAwsResources(params: Record<string, any>): Promise<AwsPageResult> {
  const { data } = await api.get('/aws-checks', { params })
  return data
}

export async function fetchAwsSummary(): Promise<AwsSummary> {
  const { data } = await api.get('/aws-checks/summary')
  return data
}

export async function fetchAwsFilterOptions(): Promise<AwsFilterOptions> {
  const { data } = await api.get('/aws-checks/filter-options')
  return data
}

// ── 华为云巡检 ──

export interface CheckItem {
  check_type: string
  risk_level: string
  resource_type: string
  resource_id: string
  resource_name: string
  region: string
  detail: string
  status: string
  extra?: Record<string, any>
  scan_time: string
}

export interface CheckPageResult {
  total: number
  items: CheckItem[]
  page: number
  page_size: number
}

export interface CheckSummary {
  total: number
  by_check_type: Record<string, number>
  by_risk_level: Record<string, number>
  by_resource_type: Record<string, number>
  check_type_names: Record<string, string>
  scan_time: string | null
}

export interface CheckFilterOptions {
  check_types: string[]
  risk_levels: string[]
  resource_types: string[]
  regions: string[]
  check_type_names: Record<string, string>
}

export async function fetchCheckResults(params: Record<string, any>): Promise<CheckPageResult> {
  const { data } = await api.get('/huawei-checks', { params })
  return data
}

export async function fetchCheckSummary(): Promise<CheckSummary> {
  const { data } = await api.get('/huawei-checks/summary')
  return data
}

export async function fetchCheckFilterOptions(): Promise<CheckFilterOptions> {
  const { data } = await api.get('/huawei-checks/filter-options')
  return data
}
