// m4-runbook K1/K4/K5：SSE 事件 → 消息状态机（App 级 useReducer）。
// 事件语义对齐冻结契约（runbook §3.1）：stage/sources/thinking/reasoning/token/citations/done/error。
// 对话本地持久化（4.6）：localStorage 最近 60 条，刷新不丢；"清空对话"一键清除。
// 4.9 登录门：未登录→LoginPage；401/过期自动切回。
// 4.10 模型切换：/api/models 拉清单+默认值；选择随请求下发；答案 meta 显示所用模型。
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { askQuestion, fetchModels } from './api.js'
import { getToken, clearToken, AuthError } from './auth.js'
import ChatPane from './components/ChatPane.jsx'
import SourceSidebar from './components/SourceSidebar.jsx'
import PdfPane from './components/PdfPane.jsx'
import LoginPage from './components/LoginPage.jsx'

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
    stageOrder: [],        // 字符串数组（4.6 修复：不得改写为对象）
    sources: null,
    routes: null,
    thinking: { status: 'none', text: '', elapsed: null },
    cited: null,
    invalid: [],
    finish: null,          // stop | refused | aborted
    usage: null,
    traceId: null,
    model: null,           // K12：本答案所用模型
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
      m.model = data.model || null   // K12：本答案所用模型（答案 meta 区显示）
      m.done = true
      // 权威耗时校正（R6）：done.timing 为准；stageOrder 保持字符串（4.6 修复）
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

export default function App() {
  // 恢复本地持久化的对话（中断的流式消息一律标记完成态）
  const [messages, dispatch] = useReducer(messagesReducer, null, () => {
    const stored = loadStored()
    return stored ? stored.messages.map((m) => ({ ...m, done: true })) : []
  })
  const [profile, setProfile] = useState(() => loadStored()?.profile || 'D')
  const [status, setStatus] = useState('idle') // idle | streaming
  const abortRef = useRef(null)
  const [activeSource, setActiveSource] = useState(null)
  // 4.10 模型状态：清单+当前选择（null=用后端默认）
  const [modelsInfo, setModelsInfo] = useState(null)
  const [selectedModel, setSelectedModel] = useState(null)
  // 4.9 登录态：有 token 即视为已登录（token 失效由 401 兜底切回）
  const [loggedIn, setLoggedIn] = useState(() => Boolean(getToken()))

  // 持久化：消息变更即写（截最近 60 条；失败静默——隐私模式等场景不阻塞主功能）
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY,
        JSON.stringify({ profile, messages: messages.slice(-60) }))
    } catch { /* 存储不可用时跳过 */ }
  }, [messages, profile])

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
      selectedModel,
      ({ event, data }) => dispatch({ type: 'event', targetId: aMsg.id, event, data }),
      (err) => {
        if (err instanceof AuthError) { clearToken(); setLoggedIn(false); return }
        dispatch({ type: 'error', targetId: aMsg.id, message: err.message })
      },
    )
    abortRef.current = abort
  }, [profile, status, selectedModel])

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

  // 4.10：登录后拉模型清单（401 由 authedFetch 转 AuthError）
  useEffect(() => {
    if (!loggedIn) return
    fetchModels()
      .then((info) => {
        setModelsInfo(info)
        setSelectedModel((cur) => cur || info.default)
      })
      .catch((e) => {
        if (e instanceof AuthError) { clearToken(); setLoggedIn(false) }
      })
  }, [loggedIn])

  const handleAuthError = useCallback((err) => {
    if (err instanceof AuthError) { clearToken(); setLoggedIn(false) }
  }, [])

  if (!loggedIn) {
    return <LoginPage onLogin={() => setLoggedIn(true)} />
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">DocLens <span className="brand-sub">多模态论文问答</span></div>
        <div className="topbar-actions">
          <button className="btn close" onClick={() => dispatch({ type: 'clear' })}
                  disabled={status === 'streaming'}>清空对话</button>
          <button className="btn close" onClick={() => { clearToken(); setLoggedIn(false) }}>退出登录</button>
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
          modelsInfo={modelsInfo}
          selectedModel={selectedModel}
          onSelectModel={setSelectedModel}
          onAuthError={handleAuthError}
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
