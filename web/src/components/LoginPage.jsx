// 登录页（m4-runbook 4.9 L0）：单管理员密码门。token 失效/登出后回到此页。
import { useState } from 'react'
import { login } from '../auth.js'

export default function LoginPage({ onLogin }) {
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    if (!password || busy) return
    setBusy(true)
    setError(null)
    try {
      await login(password)
      onLogin()
    } catch (err) {
      setError(err.message || '登录失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <h1 className="login-brand">DocLens</h1>
        <p className="login-sub">多模态论文问答 · 管理员登录</p>
        <input
          type="password"
          className="login-input"
          placeholder="管理员密码"
          value={password}
          autoFocus
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && <div className="login-error">{error}</div>}
        <button className="btn send login-btn" disabled={busy || !password}>
          {busy ? '登录中…' : '登录'}
        </button>
      </form>
    </div>
  )
}
