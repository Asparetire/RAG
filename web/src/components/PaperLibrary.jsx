// 论文库视图（m4-runbook 4.8；调研 §9 范式落地）：
// 左侧=分类树（可折叠，FastGPT 式下钻）+ 右侧=论文表格（RAGFlow 式状态列）+ 上传入口。
// 上传入口=当前选中分类上下文（进入分类后上传即落入，open-webui 惯例，不弹窗选分类）。
// 状态徽标=queued/parsing/indexing/completed/error（dify 粒度）+ 进度条 + 失败重试。
import { useCallback, useEffect, useState } from 'react'
import { authedFetch, AuthError } from '../auth.js'
const STATUS_META = {
  queued: { label: '排队中', cls: 'st-queued' },
  parsing: { label: '解析中', cls: 'st-running' },
  indexing: { label: '索引中', cls: 'st-running' },
  completed: { label: '就绪', cls: 'st-done' },
  error: { label: '失败', cls: 'st-error' },
}

// 组装树：categories 平铺 → 按 parent_id 挂 children（ancestor_ids 已由后端维护）
function buildTree(categories) {
  const byId = new Map(categories.map((c) => [c.id, { ...c, children: [] }]))
  const roots = []
  for (const node of byId.values()) {
    if (node.parent_id != null && byId.has(node.parent_id)) {
      byId.get(node.parent_id).children.push(node)
    } else {
      roots.push(node)
    }
  }
  return { roots, byId }
}

function CategoryTree({ categories, papers, activeCat, onPick, onNewCategory, onRename, onDelete }) {
  const [collapsed, setCollapsed] = useState(new Set())
  const { roots } = buildTree(categories)
  const countByCat = {}
  for (const p of papers) {
    if (p.category_id != null) countByCat[p.category_id] = (countByCat[p.category_id] || 0) + 1
  }

  const renderNode = (node, depth) => {
    const isCollapsed = collapsed.has(node.id)
    const active = activeCat === node.id
    return (
      <div key={node.id}>
        <div className={`cat-row${active ? ' active' : ''}`} style={{ paddingLeft: depth * 16 + 8 }}>
          <button className="cat-caret" title={isCollapsed ? '展开' : '折叠'}
                  onClick={() => setCollapsed((s) => {
                    const n = new Set(s); n.delete(node.id) || n.add(node.id)
                    return n
                  })}>
            {node.children.length ? (isCollapsed ? '▸' : '▾') : '·'}
          </button>
          <button className="cat-name" onClick={() => onPick(node.id)}>{node.name}</button>
          <span className="cat-count">{countByCat[node.id] || 0}</span>
          <span className="cat-ops">
            <button title="重命名" onClick={() => onRename(node)}>✎</button>
            {depth < 2 && <button title="新建子分类" onClick={() => onNewCategory(node.id)}>+</button>}
            <button title="删除" onClick={() => onDelete(node)}>✕</button>
          </span>
        </div>
        {!isCollapsed && node.children.map((ch) => renderNode(ch, depth + 1))}
      </div>
    )
  }

  return (
    <div className="cat-tree">
      <div className={`cat-row${activeCat == null ? ' active' : ''}`} style={{ paddingLeft: 8 }}>
        <button className="cat-name" onClick={() => onPick(null)}>全部论文</button>
        <span className="cat-count">{papers.length}</span>
      </div>
      {roots.map((r) => renderNode(r, 0))}
    </div>
  )
}

function StatusCell({ task }) {
  if (!task) return <span className="badge st-done">就绪（已入库）</span>
  const meta = STATUS_META[task.status] || { label: task.status, cls: 'st-queued' }
  const pct = Math.round((task.progress || 0) * 100)
  return (
    <span className={`badge ${meta.cls}`} title={task.error || task.progress_msg || ''}>
      {meta.label}
      {task.status === 'indexing' || task.status === 'parsing' ? ` ${pct}%` : ''}
      {task.status === 'error' && task.error ? `：${task.error.slice(0, 40)}` : ''}
    </span>
  )
}

export default function PaperLibrary({ onOpenPaper, onAuthError }) {
  const [categories, setCategories] = useState([])
  const [papers, setPapers] = useState([])
  const [activeTasks, setActiveTasks] = useState([])  // 进行中任务（上传后立即可见，RAGFlow 范式）
  const [activeCat, setActiveCat] = useState(null) // null=全部
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState(null)
  const [pendingFile, setPendingFile] = useState(null)
  // 垃圾桶（m6-trash）：软删列表 + 恢复/彻底删除/清空
  const [trash, setTrash] = useState([])
  const [trashBusy, setTrashBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const r = await authedFetch('/api/papers/tree')
      if (r.status === 401) throw new AuthError('请重新登录')
      const data = await r.json()
      setCategories(data.categories)
      setPapers(data.papers)
      setActiveTasks(data.active_tasks || [])
    } catch (e) {
      if (e instanceof AuthError) onAuthError(e)
    }
  }, [onAuthError])

  useEffect(() => { load() }, [load])

  const loadTrash = useCallback(async () => {
    try {
      const r = await authedFetch('/api/papers/trash')
      if (r.status === 401) throw new AuthError('请重新登录')
      const data = await r.json()
      setTrash(data.papers || [])
    } catch (e) {
      if (e instanceof AuthError) onAuthError(e)
    }
  }, [onAuthError])

  // 轮询：只要有进行中任务或刚提交的 batch，就每 2.5s 刷新一次（全部终态即停）
  const hasActive = activeTasks.length > 0
  useEffect(() => {
    if (!hasActive) return undefined
    const timer = setInterval(load, 2500)
    return () => clearInterval(timer)
  }, [hasActive, load])

  const doUpload = async () => {
    if (!pendingFile) return
    setUploading(true)
    setUploadMsg(null)
    try {
      const body = new FormData()
      body.append('file', pendingFile)
      if (activeCat != null) body.append('category_id', activeCat)
      const r = await authedFetch('/api/papers/upload', { method: 'POST', body })
      const data = await r.json()
      if (r.status === 409) {
        setUploadMsg(`重复：${data.detail}`)
      } else if (!r.ok) {
        setUploadMsg(`上传失败：${data.detail || r.status}`)
      } else {
        setUploadMsg(`已提交入库任务（${data.doc_id}），完成后立即可问答`)
        load()   // 立即刷新：新任务出现在"进行中"区
      }
    } catch (e) {
      if (e instanceof AuthError) { onAuthError(e); return }
      setUploadMsg(`上传失败：${e.message}`)
    } finally {
      setUploading(false)
    }
  }

  // ---- 模态框状态（S3 体检/用户反馈：prompt 填 ID 体验差 → 下拉选择式）----
  // kind: 'move' | 'new' | 'rename' | 'renamePaper'
  const [modal, setModal] = useState(null)
  const closeModal = () => setModal(null)

  const submitModal = async () => {
    if (!modal) return
    try {
      let r
      if (modal.kind === 'move') {
        const catId = modal.catId === '' || modal.catId == null ? null : Number(modal.catId)
        r = await authedFetch(`/api/papers/${modal.paper.doc_id}/category`, {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ category_id: catId }),
        })
      } else if (modal.kind === 'new') {
        r = await authedFetch('/api/categories', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: modal.name, parent_id: modal.parentId }),
        })
      } else if (modal.kind === 'rename') {
        r = await authedFetch(`/api/categories/${modal.catId}`, {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: modal.name }),
        })
      } else if (modal.kind === 'renamePaper') {
        r = await authedFetch(`/api/papers/${modal.paper.doc_id}/title`, {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: modal.name }),
        })
      } else if (modal.kind === 'del') {
        // 删除进垃圾桶（m6-trash）：软删，垃圾桶内可恢复
        r = await authedFetch(`/api/papers/${modal.paper.doc_id}`, { method: 'DELETE' })
      }
      const d = await r.json()
      if (!r.ok) { setModal({ ...modal, error: d.detail || '操作失败' }); return }
      closeModal()
      load()
    } catch (e) {
      if (e instanceof AuthError) { onAuthError(e); return }
      setModal({ ...modal, error: e.message })
    }
  }

  const deleteCategory = async (node) => {
    if (!window.confirm(`删除分类「${node.name}」？（不影响论文，仅删除分类本身——若含子分类或论文会被拒绝）`)) return
    const r = await authedFetch(`/api/categories/${node.id}`, { method: 'DELETE' })
    if (!r.ok) { const d = await r.json(); window.alert(d.detail || '删除失败') }
    if (activeCat === node.id) setActiveCat(null)
    load()
  }

  // ---- 垃圾桶操作（m6-trash）：恢复 / 彻底删除 / 清空 ----
  const restorePaper = async (docId) => {
    setTrashBusy(true)
    try {
      const r = await authedFetch(`/api/papers/${docId}/restore`, { method: 'POST' })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) window.alert(d.detail || '恢复失败')
      loadTrash(); load()
    } catch (e) {
      if (e instanceof AuthError) { onAuthError(e); return }
      window.alert(`恢复失败：${e.message}`)
    } finally { setTrashBusy(false) }
  }

  const purgePaper = async (p) => {
    if (!window.confirm(`彻底删除「${p.title}」？此操作不可恢复（PDF 原件将移入 data/trash_files/ 兜底）。`)) return
    setTrashBusy(true)
    try {
      const r = await authedFetch(`/api/papers/${p.doc_id}/purge`, { method: 'DELETE' })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) window.alert(d.detail || '彻底删除失败')
      loadTrash(); load()
    } catch (e) {
      if (e instanceof AuthError) { onAuthError(e); return }
      window.alert(`彻底删除失败：${e.message}`)
    } finally { setTrashBusy(false) }
  }

  const emptyTrash = async () => {
    if (!window.confirm(`清空垃圾桶（${trash.length} 篇）？彻底删除不可恢复。`)) return
    setTrashBusy(true)
    try {
      const r = await authedFetch('/api/papers/trash/empty', { method: 'POST' })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) { window.alert(d.detail || '清空失败'); return }
      if (d.purged < trash.length) window.alert(`部分失败：清空了 ${d.purged}/${trash.length} 篇（其余正在入库或出错，稍后重试）`)
      loadTrash(); load()
    } catch (e) {
      if (e instanceof AuthError) { onAuthError(e); return }
      window.alert(`清空失败：${e.message}`)
    } finally { setTrashBusy(false) }
  }

  // 分类扁平化（带层级缩进）——下拉选项用
  const flatCategories = (() => {
    const { roots, byId } = buildTree(categories)
    const out = []
    const walk = (node, depth) => {
      out.push({ id: node.id, name: node.name, depth })
      node.children.forEach((ch) => walk(ch, depth + 1))
    }
    roots.forEach((r) => walk(r, 0))
    return out
  })()

  const visiblePapers = activeCat == null
    ? papers
    : papers.filter((p) => p.category_id === activeCat)

  return (
    <div className="library">
      <aside className="library-tree">
        <div className="library-tree-head">
          <span>论文库</span>
          <span className="topbar-actions">
            <button className="btn close" onClick={() => { setModal({ kind: 'trash' }); loadTrash() }}>垃圾桶</button>
            <button className="btn close" onClick={() => setModal({ kind: 'new', parentId: null, name: '' })}>新建分类</button>
          </span>
        </div>
        <CategoryTree
          categories={categories}
          papers={papers}
          activeCat={activeCat}
          onPick={setActiveCat}
          onNewCategory={(parentId) => setModal({ kind: 'new', parentId, name: '' })}
          onRename={(node) => setModal({ kind: 'rename', catId: node.id, name: node.name })}
          onDelete={deleteCategory}
        />
        <div className="library-upload">
          <div className="library-upload-hint">
            上传到：<b>{activeCat == null ? '未分类' : (categories.find((c) => c.id === activeCat)?.name || '未分类')}</b>
          </div>
          <input type="file" accept="application/pdf"
                 onChange={(e) => setPendingFile(e.target.files?.[0] || null)} />
          <button className="btn send" disabled={!pendingFile || uploading} onClick={doUpload}>
            {uploading ? '提交中…' : '上传并入库'}
          </button>
          {uploadMsg && <div className="upload-msg">{uploadMsg}</div>}
        </div>
      </aside>
      <div className="library-main">
        {activeTasks.length > 0 && (
          <div className="active-tasks">
            <div className="active-tasks-head">进行中的入库任务（{activeTasks.length}）</div>
            {activeTasks.map((t) => (
              <div key={t.task_id} className="active-task">
                <span className="at-file">{t.filename}</span>
                <span className={`badge ${t.status === 'indexing' ? 'st-running' : 'st-queued'}`}>
                  {t.status === 'queued' ? '排队中' : t.status === 'parsing' ? '解析中' : '索引中'}
                  {' '}{Math.round((t.progress || 0) * 100)}%
                </span>
                <div className="at-progress"><div className="at-bar"
                     style={{ width: `${Math.round((t.progress || 0) * 100)}%` }} /></div>
                <span className="at-msg">{(t.progress_msg || '').slice(0, 60)}</span>
              </div>
            ))}
          </div>
        )}
        <table className="paper-table">
          <thead>
            <tr><th>论文</th><th>分类</th><th>分块数</th><th>状态</th><th>操作</th></tr>
          </thead>
          <tbody>
            {visiblePapers.map((p) => (
              <tr key={p.doc_id}>
                <td>
                  <button className="paper-link" onClick={() => onOpenPaper(p)}>
                    {p.title}
                  </button>
                  <div className="paper-docid">{p.doc_id}</div>
                </td>
                <td>{p.category_name || '未分类'}</td>
                <td>{p.n_chunks ?? '—'}</td>
                <td><span className={`badge ${p.status === 'error' ? 'st-error' : 'st-done'}`}>
                  {p.status === 'error' ? '失败' : '就绪'}</span></td>
                <td>
                  <button className="link-btn" onClick={() => onOpenPaper(p)}>预览</button>
                  {' '}
                  <button className="link-btn"
                          onClick={() => setModal({ kind: 'renamePaper', paper: p, name: p.title })}>
                    改名</button>
                  {' '}
                  <button className="link-btn"
                          onClick={() => setModal({ kind: 'move', paper: p, catId: p.category_id != null ? String(p.category_id) : '' })}>
                    移动</button>
                  {' '}
                  <button className="link-btn" onClick={() => setModal({ kind: 'del', paper: p })}>删除</button>
                </td>
              </tr>
            ))}
            {visiblePapers.length === 0 && (
              <tr><td colSpan={5} className="empty-row">该分类暂无论文——用左下角上传入口添加</td></tr>
            )}
          </tbody>
        </table>

        {modal && (
          <div className="modal-mask" onClick={closeModal}>
            <div className="modal" onClick={(e) => e.stopPropagation()}>
              {modal.kind === 'move' && (
                <>
                  <h4>移动论文</h4>
                  <div className="modal-paper">{modal.paper.title}</div>
                  <label className="modal-label">目标分类</label>
                  <select className="modal-select" value={modal.catId}
                          onChange={(e) => setModal({ ...modal, catId: e.target.value })}>
                    <option value="">未分类</option>
                    {flatCategories.map((c) => (
                      <option key={c.id} value={c.id}>
                        {'　'.repeat(c.depth)}{c.name}
                      </option>
                    ))}
                  </select>
                </>
              )}
              {modal.kind === 'new' && (
                <>
                  <h4>新建分类</h4>
                  <div className="modal-paper">
                    {modal.parentId == null ? '顶层分类'
                      : `子分类（父：${flatCategories.find((c) => c.id === modal.parentId)?.name || modal.parentId}）`}
                  </div>
                  <label className="modal-label">分类名称</label>
                  <input className="modal-select" autoFocus value={modal.name || ''}
                         placeholder="1–64 字符"
                         onChange={(e) => setModal({ ...modal, name: e.target.value })} />
                </>
              )}
              {modal.kind === 'rename' && (
                <>
                  <h4>重命名分类</h4>
                  <label className="modal-label">新名称</label>
                  <input className="modal-select" autoFocus value={modal.name || ''}
                         onChange={(e) => setModal({ ...modal, name: e.target.value })} />
                </>
              )}
              {modal.kind === 'renamePaper' && (
                <>
                  <h4>重命名论文</h4>
                  <div className="modal-paper">{modal.paper.doc_id}</div>
                  <label className="modal-label">论文标题</label>
                  <input className="modal-select" autoFocus value={modal.name || ''}
                         onChange={(e) => setModal({ ...modal, name: e.target.value })} />
                </>
              )}
              {modal.kind === 'del' && (
                <>
                  <h4>删除论文</h4>
                  <div className="modal-paper">{modal.paper.title}</div>
                  <div className="modal-paper">删除后进入<b>垃圾桶</b>：问答与论文列表立即不可见，随时可恢复；彻底删除请到垃圾桶操作。</div>
                </>
              )}
              {modal.kind === 'trash' && (
                <>
                  <h4>垃圾桶（{trash.length}）</h4>
                  {trash.length === 0 && <div className="modal-paper">垃圾桶是空的——删除的论文会出现在这里，保留至被彻底删除。</div>}
                  {trash.length > 0 && (
                    <table className="paper-table">
                      <tbody>
                        {trash.map((p) => (
                          <tr key={p.doc_id}>
                            <td>
                              <div>{p.title}</div>
                              <div className="paper-docid">
                                {p.doc_id} · {p.n_chunks} 块 · 删除于 {String(p.deleted_at || '').slice(0, 16).replace('T', ' ')}
                              </div>
                            </td>
                            <td style={{ whiteSpace: 'nowrap' }}>
                              <button className="link-btn" disabled={trashBusy}
                                      onClick={() => restorePaper(p.doc_id)}>恢复</button>
                              {' '}
                              <button className="link-btn" disabled={trashBusy}
                                      onClick={() => purgePaper(p)}>彻底删除</button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </>
              )}
              {modal.error && <div className="modal-error">{modal.error}</div>}
              <div className="modal-actions">
                <button className="btn close" onClick={closeModal}>
                  {modal.kind === 'trash' ? '关闭' : '取消'}
                </button>
                {modal.kind === 'trash' && trash.length > 0 && (
                  <button className="btn stop" disabled={trashBusy} onClick={emptyTrash}>清空垃圾桶</button>
                )}
                {modal.kind !== 'trash' && (
                  <button className="btn send"
                          disabled={modal.kind !== 'move' && modal.kind !== 'del' && !(modal.name || '').trim()}
                          onClick={submitModal}>
                    {modal.kind === 'del' ? '删除'
                      : modal.kind === 'move' ? '移动' : modal.kind === 'new' ? '创建' : '保存'}
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
