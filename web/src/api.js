// m4-runbook K3：SSE 消费层——@microsoft/fetch-event-source（POST+JSON body，事件回调）。
// openWhenHidden=true：切走标签页不断流（演示场景保险）。
// 备选方案（未采用）：eventsource-parser + 手写 fetch 分帧（RAGFlow/OpenWebUI 同款）。
import { fetchEventSource } from '@microsoft/fetch-event-source'

/**
 * 发起一次流式问答。
 * @param {string} question
 * @param {string} profile "A".."F"
 * @param {(payload: {event: string, data: object}) => void} onEvent 每个契约事件回调一次
 * @param {(err: Error) => void} onError 致命错误（网络/非 2xx）
 * @returns {() => void} abort 函数（中断本次流）
 */
export function askQuestion(question, profile, onEvent, onError) {
  const ctrl = new AbortController()
  fetchEventSource('/api/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, profile }),
    signal: ctrl.signal,
    openWhenHidden: true,
    async onopen(resp) {
      if (!resp.ok) {
        let detail = `HTTP ${resp.status}`
        try {
          const j = await resp.json()
          if (j && j.detail) detail = String(j.detail)
        } catch { /* 非 JSON 错误体，用状态码 */ }
        throw new Error(detail)
      }
    },
    onmessage(msg) {
      if (!msg.event || msg.event === 'ping') return
      let data = {}
      try { data = JSON.parse(msg.data) } catch { data = {} }
      onEvent({ event: msg.event, data })
    },
    onerror(err) {
      onError(err instanceof Error ? err : new Error(String(err)))
      throw err // 不重试：单次问答流语义，失败由用户重新提问（runbook K1）
    },
  }).catch((err) => {
    if (ctrl.signal.aborted) return
    onError(err instanceof Error ? err : new Error(String(err)))
  })
  return () => ctrl.abort()
}
