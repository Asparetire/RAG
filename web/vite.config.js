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
      // v4 起目录结构原样保留（含 node_modules 前缀）→ 必须 stripBase 平铺，
      // 否则产物落 dist/pdfjs/node_modules/pdfjs-dist/...（且被 .gitignore 的
      // node_modules/ 规则挡住不入库，容器上 404 → PDF 页面渲染空白灰块）。
      targets: [
        { src: 'node_modules/pdfjs-dist/cmaps', dest: 'pdfjs/cmaps', rename: { stripBase: true } },
        { src: 'node_modules/pdfjs-dist/standard_fonts', dest: 'pdfjs/standard_fonts', rename: { stripBase: true } },
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
