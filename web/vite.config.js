import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// m4-runbook K2/K3：dev 期 Vite proxy 把 /api 透传到容器 uvicorn（经 SSH 隧道 8000）；
// http-proxy 透传流式响应（无缓冲），交付期 npm run build 产 dist 入库走 FastAPI 托管。
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
