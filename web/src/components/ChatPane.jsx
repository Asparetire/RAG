// 对话区：消息列表 + 输入框（Enter 发送 / Shift+Enter 换行）+ 流式停止按钮
// + 模型选择器（K12/4.10，输入框工具栏位；ai-chatbot 惯例）。
import { useEffect, useRef, useState } from 'react'
import Message from './Message.jsx'
import ModelSelector from './ModelSelector.jsx'

export default function ChatPane({ messages, status, onAsk, onStop, onCiteClick, onMsgDone,
                                   modelsInfo, selectedModel, onSelectModel }) {
  const [draft, setDraft] = useState('')
  const listRef = useRef(null)

  useEffect(() => {
    const el = listRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages])

  const submit = () => {
    if (status === 'streaming' || !draft.trim()) return
    onAsk(draft)
    setDraft('')
  }

  return (
    <section className="chat">
      <div className="msg-list" ref={listRef}>
        {messages.length === 0 && (
          <div className="empty-hint">
            <h2>向 11 篇论文提问</h2>
            <p>支持中英文 · 图表题 · 表格题 · 引用可溯源到 PDF 原页</p>
            <div className="suggestions">
              {['Kapur 方法和 Otsu 方法分别是用来做什么的？',
                '哈里斯鹰优化算法（HHO）的各个阶段是什么样的？',
                '在预选择策略的对比研究中，哪种预选择策略表现最好？',
                '2025 年的图灵奖得主是谁？'].map((s) => (
                  <button key={s} className="suggestion" onClick={() => onAsk(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m) => (
          <Message key={m.id} msg={m} onCiteClick={onCiteClick} onDone={onMsgDone} />
        ))}
      </div>
      <div className="composer">
        <textarea
          value={draft}
          placeholder="输入问题…（Enter 发送，Shift+Enter 换行）"
          rows={2}
          disabled={status === 'streaming'}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            // S3 m-6：中文输入法选词回车不发送（isComposing）
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault()
              submit()
            }
          }}
        />
        <div className="composer-side">
          <ModelSelector modelsInfo={modelsInfo} selected={selectedModel} onSelect={onSelectModel} />
          <div className="composer-buttons">
            {status === 'streaming'
              ? <button className="btn stop" onClick={onStop}>停止</button>
              : <button className="btn send" onClick={submit} disabled={!draft.trim()}>发送</button>}
          </div>
        </div>
      </div>
    </section>
  )
}
