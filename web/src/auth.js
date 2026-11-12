// M4 登录门（4.9）：token 存取与登录请求。
// token 存 localStorage（演示单管理员场景；L1 多用户时换 httpOnly cookie 路线）。
const TOKEN_KEY = 'doclens_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

/** 登录（OAuth2 表单格式）；成功返回 true，失败抛错。 */
export async function login(password) {
  const body = new URLSearchParams({ username: 'admin', password })
  const resp = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  })
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`
    try { detail = (await resp.json()).detail || detail } catch { /* keep */ }
    throw new Error(detail)
  }
  const data = await resp.json()
  setToken(data.access_token)
  return true
}

export function logout() {
  clearToken()
}

/** 带 Authorization 的 fetch 封装；401 → 清 token 并要求重新登录。 */
export async function authedFetch(url, options = {}) {
  const headers = { ...(options.headers || {}), Authorization: `Bearer ${getToken()}` }
  const resp = await fetch(url, { ...options, headers })
  if (resp.status === 401) {
    clearToken()
    throw new AuthError('登录已过期，请重新登录')
  }
  return resp
}

export class AuthError extends Error {}
