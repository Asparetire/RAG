// 渲染错误边界（4.6 修复）：任何组件树内的渲染异常都在此兜住，显示错误信息
// 与恢复按钮，而不是整页白屏（4.3 首版曾因 stageOrder 数据损坏导致白屏）。
import React from 'react'

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('UI crash:', error, info)
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 40, maxWidth: 720, margin: '60px auto', fontFamily: 'sans-serif' }}>
          <h2>页面渲染出错了</h2>
          <pre style={{
            whiteSpace: 'pre-wrap', color: '#666', fontSize: 12,
            background: '#f6f7f9', padding: 12, borderRadius: 8,
          }}>
            {String(this.state.error?.message || this.state.error)}
          </pre>
          <button className="btn send" onClick={() => this.setState({ error: null })}>重试恢复</button>
          {' '}
          <button className="btn close" onClick={() => location.reload()}>刷新页面</button>
        </div>
      )
    }
    return this.props.children
  }
}
