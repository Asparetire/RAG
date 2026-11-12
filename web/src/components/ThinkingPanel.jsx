// 思考面板三态（m4-runbook K4；范式=ai-chatbot reasoning.tsx，§8.2 实抓核实）：
// 等待态（无 reasoning，仅 stage 在跑）= Waiting shimmer；
// 流式态 = 自动展开 + Shimmer"思考中…" + 限高滚动 + 自动滚底；
// 完成态 = "已思考 N 秒"可折叠，默认收起，可回看。
// reasoning 是前端临时态：绝不入对话历史、绝不混入答案正文（R5 双字段分流）。
import { useEffect, useRef, useState } from 'react'

export default function ThinkingPanel({ thinking }) {
  const { status, text, elapsed } = thinking
  const streaming = status === 'streaming'
  const [open, setOpen] = useState(false)
  const bodyRef = useRef(null)

  useEffect(() => {
    if (streaming && text) setOpen(true)          // 流式态自动展开（K4）
    if (status === 'done') {
      const t = setTimeout(() => setOpen(false), 1000)  // 完成 1s 后自动折叠（K4）
      return () => clearTimeout(t)
    }
    return undefined
  }, [status, streaming, text])

  useEffect(() => {
    const el = bodyRef.current
    if (el && streaming) el.scrollTop = el.scrollHeight  // 流式滚底
  }, [text, streaming])

  if (status === 'none') return null
  if (status === 'streaming' && !text) {
    return <div className="thinking waiting"><span className="shimmer">思考中…</span></div>
  }

  return (
    <div className={`thinking${open ? ' open' : ''}`}>
      <button className="thinking-toggle" onClick={() => setOpen(!open)}>
        {streaming
          ? <span className="shimmer">思考中…</span>
          : <span>已思考 {elapsed != null ? `${(elapsed / 1000).toFixed(1)} 秒` : '片刻'}</span>}
        <span className="caret">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className="thinking-body" ref={bodyRef}>{text}</div>
      )}
    </div>
  )
}
