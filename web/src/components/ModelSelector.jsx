// 模型选择器（m4-runbook K12/4.10；ai-chatbot 范式）：
// 位置=输入框底部工具栏；按钮=当前模型名；弹层=白名单清单（含能力图标 vision/thinking）。
// 单选；选中仅影响下一次提问（即时生效）；默认值来自后端 /api/models。
import { useEffect, useRef, useState } from 'react'

const CAP_ICONS = { vision: '👁', thinking: '💭' }

export default function ModelSelector({ modelsInfo, selected, onSelect }) {
  const [open, setOpen] = useState(false)
  const boxRef = useRef(null)

  useEffect(() => {
    const onDoc = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  if (!modelsInfo) return null
  const current = modelsInfo.models.find((m) => m.id === selected)
    || modelsInfo.models.find((m) => m.id === modelsInfo.default)

  return (
    <div className="model-selector" ref={boxRef}>
      <button className="model-btn" onClick={() => setOpen(!open)}
              title="选择生成模型（下一次提问生效）">
        <span className="model-dot" /> {current ? current.label : modelsInfo.default}
        <span className="caret">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className="model-menu">
          {modelsInfo.models.map((m) => (
            <button key={m.id}
                    className={`model-item${m.id === selected ? ' active' : ''}`}
                    onClick={() => { onSelect(m.id); setOpen(false) }}>
              <span className="model-item-label">{m.label}</span>
              <span className="model-item-caps">
                {Object.entries(CAP_ICONS).filter(([k]) => m[k]).map(([k, icon]) => (
                  <span key={k} title={k}>{icon}</span>
                ))}
              </span>
              {m.id === modelsInfo.default && <span className="model-default-tag">默认</span>}
            </button>
          ))}
          <div className="model-menu-foot">
            重排器跟随检索档位（D 档起 flash；--rerank-pro 位为 pro）
          </div>
        </div>
      )}
    </div>
  )
}
