// 阶段步进条（m4-runbook K6；FR-5.3）：检索 → 重排 → 组装 → 生成。
// 耗时=事件到达差实时估算（done.timing 权威值到达后校正——App.applyEvent 已做）。
const STAGE_LABELS = { retrieve: '检索', rerank: '重排', assemble: '组装', generate: '生成' }
const ORDER = ['retrieve', 'rerank', 'assemble', 'generate']

function fmtMs(ms) {
  if (ms == null) return ''
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`
}

export default function StageBar({ msg }) {
  if (!msg.stageOrder.length) return null
  return (
    <div className="stage-bar">
      {msg.stageOrder.map((s, i) => {
        const st = msg.stages[s]
        const running = !msg.done && i === msg.stageOrder.length - 1
        return (
          <span key={s} className={`stage${running ? ' running' : ''}${st?.elapsed != null ? ' done' : ''}`}>
            <span className="dot" />
            {STAGE_LABELS[s] || s}
            {st?.elapsed != null && <em>{fmtMs(st.elapsed)}</em>}
            {running && <em className="live">…</em>}
          </span>
        )
      })}
    </div>
  )
}
