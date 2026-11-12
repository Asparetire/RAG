// m4-runbook K1/K4/K5：SSE 事件 → 消息状态机（App 级 useReducer）。
// 事件语义对齐冻结契约（runbook §3.1）：stage/sources/thinking/reasoning/token/citations/done/error。
// 对话本地持久化（4.6 修复项）：localStorage 存最近 60 条，刷新不丢；"清空对话"一键清除。
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { askQuestion } from './api.js'
import ChatPane from './components/ChatPane.jsx'
import SourceSidebar from './components/SourceSidebar.jsx'
import PdfPane from './components/PdfPane.jsx'

let _seq = 0
const nextSeq = () => ++_seq

const STORAGE_KEY = 'doclens_chat_v1'

function loadStored() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed?.messages) ? parsed : null
  } catch {
    return null
  }
}

// 新建一条 assistant 消息（流式目标）
function newAssistantMsg(profile) {
  return {
    id: nextSeq(),
    role: 'assistant',
    profile,
    content: '',
    stages: {},            // {stage: {detail, t0, elapsed}}（到达差实时显示）
    stageOrder: [],
    sources: null,         // sources 事件载荷（含 routes）
    routes: null,
    thinking: { status: 'none', text: '', elapsed: null }, // 三态：none/waiting/streaming/done
    cited: null,
    invalid: [],
    finish: null,          // stop | refused
    usage: null,
    traceId: null,
    error: null,
    done: false,
  }
}

// 事件归约：把一个 SSE 事件打到当前 assistant 消息上（返回新对象）
function applyEvent(msg, { event, data }) {
  const m = { ...msg }
  switch (event) {
    case 'stage': {
      const t0 = performance.now()
      if (!m.stages[data.stage]) m.stageOrder = [...m.stageOrder, data.stage]
      m.stages = { ...m.stages, [data.stage]: { detail: data.detail || data.stage, t0, elapsed: null } }
      break
    }
    case 'sources':
      m.sources = data.sources
      m.routes = data.routes
      break
    case 'thinking':
      if (data.status === 'started') {
        m.thinking = { ...m.thinking, status: 'streaming' }
      } else if (data.status === 'done') {
        m.thinking = { ...m.thinking, status: 'done', elapsed: data.elapsed_ms }
      }
      break
    case 'reasoning':
      m.thinking = { ...m.thinking, text: m.thinking.text + (data.text || '') }
      break
    case 'token':
      m.content += data.content || ''
      break
    case 'citations':
      m.cited = data.cited
      m.invalid = data.invalid || []
      break
    case 'done': {
      m.finish = data.finish_reason
      m.usage = data.usage
      m.traceId = data.trace_id
      m.done = true
      // 权威耗时校正（R6）：done.timing 为准；stageOrder 保持字符串（4.6 修复：
      // 之前此处把 stageOrder 改写成对象数组，StageBar 渲染对象为 React 子元素
      // 直接崩溃 → 白屏）
      const timing = data.timing || {}
      const stages = { ...m.stages }
      for (const s of Object.keys(stages)) {
        const v = timing[`${s}_ms`]
        if (v != null) stages[s] = { ...stages[s], elapsed: v }
      }
      m.stages = stages
      break
    }
    case 'error':
      m.error = data.message || '服务错误'
      m.done = true
      break
    default:
      break
  }
  return m
}

export default function App() {
  const [messages, dispatch] = useReducer(messagesReducer, [])
  const [status, setStatus] = useState('idle') // idle | streaming
  const [profile, setProfile] = useState('D')
  const abortRef = useRef(null)

  // 引用点击 → 侧栏切到 PDF 视图（4.4 实现 PdfPane；当前先记录选中源）
  const [activeSource, setActiveSource] = useState(null)

  const ask = useCallback((question) => {
    const q = question.trim()
    if (!q || status === 'streaming') return
    const userMsg = { id: nextSeq(), role: 'user', content: q }
    const aMsg = newAssistantMsg(profile)
    dispatch({ type: 'push', msgs: [userMsg, aMsg] })
    setStatus('streaming')

    const abort = askQuestion(
      q,
      profile,
      ({ event, data }) => dispatch({ type: 'event', targetId: aMsg.id, event, data }),
      (err) => dispatch({ type: 'error', targetId: aMsg.id, message: err.message }),
    )
    abortRef.current = abort
  }, [profile, status])

  const stop = useCallback(() => {
    if (abortRef.current) abortRef.current()
    setStatus('idle')
  }, [])

  const onDone = useCallback((msg) => {
    if (msg.done) setStatus('idle')
  }, [])

  const lastAssistant = useMemo(
    () => [...messages].reverse().find((m) => m.role === 'assistant') || null,
    [messages],
  )

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">DocLens <span className="brand-sub">多模态论文问答</span></div>
        <div className="topbar-actions">
          <button className="btn close" onClick={() => dispatch({ type: 'clear' })}
                  disabled={status === 'streaming'}>清空对话</button>
          <label className="profile-pick">
            检索档位
            <select value={profile} disabled={status === 'streaming'}
                    onChange={(e) => setProfile(e.target.value)}>
              {['A', 'B', 'C', 'D', 'E', 'F'].map((p) => <option key={p} value={p}>{p} 档</option>)}
            </select>
          </label>
        </div>
      </header>
      <div className="main">
        <ChatPane
          messages={messages}
          status={status}
          onAsk={ask}
          onStop={stop}
          onCiteClick={(src) => setActiveSource(src)}
          onMsgDone={onDone}
        />
        <SourceSidebar
          msg={lastAssistant}
          activeSource={activeSource}
          onSourceClick={setActiveSource}
        />
        {activeSource && (
          <PdfPane src={activeSource} onClose={() => setActiveSource(null)} />
        )}
      </div>
    </div>
  )
}

function messagesReducer(state, action) {
  switch (action.type) {
    case 'push':
      return [...state, ...action.msgs]
    case 'event':
      return state.map((m) => (m.id === action.targetId && !m.done
        ? applyEvent(m, { event: action.event, data: action.data }) : m))
    case 'error':
      return state.map((m) => (m.id === action.targetId && !m.done
        ? { ...m, error: action.message, done: true } : m))
    case 'stop':
      return state.map((m) => (m.role === 'assistant' && !m.done
        ? { ...m, done: true, finish: m.finish || 'aborted' } : m))
    case 'clear':
      return []
    default:
      return state
  }
}
