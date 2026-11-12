// 单条消息：思考三态面板 + 流式正文（[n] 渲染为可点击 chip）+ 拒答/错误态 + 引用角标。
import { useEffect } from 'react'
import ThinkingPanel from './ThinkingPanel.jsx'
import StageBar from './StageBar.jsx'

// 把正文按 [n] / [n,m] 引用标记切段，n 映射到可点击 chip（命中 sources 的 n 可点）。
function renderContent(content, sources, invalid, onCiteClick) {
  const parts = []
  const re = /\[(\d+(?:[,-]\d+)*)\]/g
  let last = 0
  let match
  const nums = new Set((sources || []).map((s) => s.n))
  while ((match = re.exec(content)) !== null) {
    if (match.index > last) parts.push(<span key={`t${last}`}>{content.slice(last, match.index)}</span>)
    const ids = match[1].split(/[,-]/).map(Number)
    const allInvalid = ids.every((n) => invalid.includes(n))
    parts.push(
      <button
        key={`c${match.index}`}
        className={`cite-chip${nums.has(ids[0]) ? '' : ' dead'}${allInvalid ? ' invalid' : ''}`}
        title={allInvalid ? '无效引用（降级标记）' : '查看原文'}
        onClick={() => {
          const src = (sources || []).find((s) => s.n === ids[0])
          if (src && !allInvalid) onCiteClick(src)
        }}
      >[{match[1]}]</button>,
    )
    last = match.index + match[0].length
  }
  if (last < content.length) parts.push(<span key={`t${last}`}>{content.slice(last)}</span>)
  return parts
}

export default function Message({ msg, onCiteClick, onDone }) {
  if (msg.role === 'user') {
    return <div className="msg user"><div className="bubble">{msg.content}</div></div>
  }
  // 流式完成即上报（App 据此解除输入锁定）——副作用放 effect，不放渲染体
  useEffect(() => {
    if (msg.done) onDone(msg)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [msg.done])
  const sources = msg.sources || []
  return (
    <div className={`msg assistant${msg.done ? '' : ' streaming'}`}>
      <StageBar msg={msg} />
      <ThinkingPanel thinking={msg.thinking} />
      {(msg.content || msg.error) && (
        <div className="bubble answer">
          {msg.error
            ? <span className="err-text">⚠ {msg.error}</span>
            : renderContent(msg.content, sources, msg.invalid, onCiteClick)}
          {msg.finish === 'refused' && <div className="refusal-note">（未找到足够依据，已拒答）</div>}
        </div>
      )}
      {msg.done && msg.traceId && (
        <div className="msg-meta">
          模型 {msg.model || '默认'} · trace {msg.traceId}
          {msg.usage && msg.usage.total_tokens != null ? ` · ${msg.usage.total_tokens} tokens` : ''}
        </div>
      )}
    </div>
  )
}
