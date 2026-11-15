// 评测看板（m5-runbook 5.8）：跑批列表+进度、六档指标对比表、归因占位。
// 数据源=/api/eval/*（t_eval_result 同源——看板数字与 reports/ablation.md 一致性由数据源保证）。
import { useCallback, useEffect, useState } from 'react'
import { authedFetch, AuthError } from '../auth.js'

export default function EvalDashboard({ onAuthError }) {
  const [runs, setRuns] = useState([])
  const [selectedRun, setSelectedRun] = useState(null)
  const [summary, setSummary] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const loadRuns = useCallback(async () => {
    try {
      const r = await authedFetch('/api/eval/runs')
      if (r.status === 401) throw new AuthError('请重新登录')
      setRuns(await r.json())
    } catch (e) {
      if (e instanceof AuthError) onAuthError(e)
    }
  }, [onAuthError])

  const loadSummary = useCallback(async (runId) => {
    try {
      const r = await authedFetch(`/api/eval/summary?run_id=${encodeURIComponent(runId)}`)
      setSummary(await r.json())
    } catch (e) {
      if (e instanceof AuthError) onAuthError(e)
    }
  }, [onAuthError])

  useEffect(() => { loadRuns() }, [loadRuns])
  useEffect(() => {
    if (!selectedRun) return undefined
    loadSummary(selectedRun)
    const t = setInterval(() => loadSummary(selectedRun), 5000)
    return () => clearInterval(t)
  }, [selectedRun, loadSummary])

  const startRun = async (suite) => {
    setBusy(true)
    try {
      const r = await authedFetch('/api/eval/run', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ suite, profiles: 'D' }),
      })
      const d = await r.json()
      if (r.ok) { loadRuns(); setSelectedRun(d.run_id) }
      else setError(d.detail || '触发失败')
    } catch (e) {
      if (e instanceof AuthError) onAuthError(e)
    } finally {
      setBusy(false)
    }
  }

  // 对比表：profiles → {metric: {profile: mean}}
  const metricTable = (() => {
    if (!summary) return null
    const profiles = Object.keys(summary.profiles).sort()
    const metrics = [...new Set(profiles.flatMap((p) => summary.profiles[p].map((m) => m.metric)))]
    const cells = {}
    for (const p of profiles) {
      for (const m of summary.profiles[p]) cells[`${p}|${m.metric}`] = m
    }
    return { profiles, metrics, cells }
  })()

  return (
    <div className="library eval-dash">
      <div className="eval-main">
        <div className="eval-head">
          <h3>评测看板</h3>
          <div className="eval-run-btns">
            {['main', 'qasper', 'gen_model'].map((s) => (
              <button key={s} className="btn close" disabled={busy}
                      onClick={() => startRun(s)}>跑 {s}</button>
            ))}
          </div>
        </div>
        {error && <div className="eval-error">{error}</div>}

        <div className="runs-table">
          <table className="paper-table">
            <thead><tr><th>跑批</th><th>套件</th><th>状态</th><th>进度</th><th>更新时间</th></tr></thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.run_id}
                    className={selectedRun === r.run_id ? 'active' : ''}
                    onClick={() => setSelectedRun(r.run_id)} style={{ cursor: 'pointer' }}>
                  <td>{r.run_id}</td>
                  <td>{r.suite}</td>
                  <td><span className={`badge ${r.status === 'completed' ? 'st-done'
                        : r.status === 'error' ? 'st-error' : 'st-running'}`}>{r.status}</span></td>
                  <td>{r.completed}/{r.total}</td>
                  <td>{r.updated_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {metricTable && (
          <div className="summary-block">
            <h4>指标对比（run: {selectedRun}）</h4>
            <table className="paper-table">
              <thead>
                <tr><th>metric</th>{metricTable.profiles.map((p) => <th key={p}>{p} 档</th>)}</tr>
              </thead>
              <tbody>
                {metricTable.metrics.map((m) => (
                  <tr key={m}>
                    <td>{m}</td>
                    {metricTable.profiles.map((p) => {
                      const c = metricTable.cells[`${p}|${m}`]
                      return <td key={p}>{c ? c.mean : '—'} <span className="n-tag">n={c?.n}</span></td>
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
