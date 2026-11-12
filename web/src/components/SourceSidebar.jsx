// 来源侧栏（m4-runbook K5/K6）：Source N 卡片（kind 图标 + 标题行 + snippet + 各路分数小字）。
// 点击卡片 → App.setActiveSource → 4.4 的 PdfPane 打开对应页并 bbox 高亮。
// 空态/拒答态有各自文案；引用点击后高亮当前卡。

const KIND_LABELS = { text: '正文', table: '表格', caption: '图注', image: '图像' }

function routeScores(routes, chunkId) {
  if (!routes) return []
  return Object.entries(routes)
    .map(([route, hits]) => {
      const hit = (hits || []).find((h) => h.chunk_id === chunkId)
      return hit ? { route, score: hit.score, rank: hit.rank } : null
    })
    .filter(Boolean)
}

export default function SourceSidebar({ msg, activeSource, onSourceClick }) {
  const sources = (msg && msg.sources) || []
  const routes = msg && msg.routes
  return (
    <aside className="sidebar">
      <div className="sidebar-head">
        <h3>引用来源</h3>
        {sources.length > 0 && <span className="count">{sources.length} 条</span>}
      </div>
      {msg && msg.finish === 'refused' && (
        <div className="sidebar-note">本题按无依据拒答，无引用来源。</div>
      )}
      {sources.length === 0 && (!msg || !msg.finish) && (
        <div className="sidebar-note">提问后，检索到的证据来源会先于答案出现在这里（R4）。</div>
      )}
      <div className="source-list">
        {sources.map((s) => {
          const active = activeSource && activeSource.n === s.n
          const scores = routeScores(routes, s.chunk_id)
          const isInvalid = (msg.invalid || []).includes(s.n)
          return (
            <button
              key={s.n}
              className={`source-card kind-${s.kind}${active ? ' active' : ''}${isInvalid ? ' invalid' : ''}`}
              onClick={() => onSourceClick(s)}
            >
              <div className="source-head">
                <span className="src-n">[{s.n}]</span>
                <span className={`kind-tag kind-${s.kind}`}>{KIND_LABELS[s.kind] || s.kind}</span>
                <span className="src-loc">{s.doc_id} · p{s.page ?? '?'}</span>
              </div>
              <div className="snippet">{s.snippet}</div>
              {scores.length > 0 && (
                <div className="score-line">
                  {scores.map((sc) => (
                    <span key={sc.route} className="score-chip">
                      {sc.route} {sc.score.toFixed(3)}{sc.rank != null ? ` #${sc.rank}` : ''}
                    </span>
                  ))}
                </div>
              )}
              {isInvalid && <div className="invalid-tag">无效引用（降级标记）</div>}
            </button>
          )
        })}
      </div>
    </aside>
  )
}
