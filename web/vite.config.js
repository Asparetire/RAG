import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { viteStaticCopy } from 'vite-plugin-static-copy'

// m4-runbook K2/K3：dev 期 Vite proxy 把 /api 透传到容器 uvicorn（经 SSH 隧道 8000）；
// http-proxy 透传流式响应（无缓冲），交付期 npm run build 产 dist 入库走 FastAPI 托管。
// cMaps/standard_fonts：中文 PDF 必需（财报泛化包），英文语料一并配好（B10 细则）。
export default defineConfig({
  base: '/web/', // S3 M-3：SPA 挂 /web 前缀，资源必须相对该前缀（否则交付态全 404）
  plugins: [
    react(),
    viteStaticCopy({
      targets: [
        { src: 'node_modules/pdfjs-dist/cmaps', dest: 'pdfjs' },
        { src: 'node_modules/pdfjs-dist/standard_fonts', dest: 'pdfjs' },
      ],
    }),
  ],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
