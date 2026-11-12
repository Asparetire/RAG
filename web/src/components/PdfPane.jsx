// PDF 原页面板（m4-runbook K5；R7 换算约定）：
// - bbox 为 0–1 归一化 [x0,y0,x1,y1]、左上原点（M1 实测口径）——overlay 直接百分比定位：
//   left=x0×100% top=y0×100% width=(x1−x0)×100% height=(y1−y0)×100%，天然随视口缩放。
// - 页码 1 起（M1 schema）= react-pdf pageNumber 1 起，直接对齐。
// - 引用点击 → src（{doc_id,page,bbox,...}）→ 打开对应 PDF 并滚动到页 → 高亮框脉冲。
import { useEffect, useRef, useState } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'

// worker：必须在渲染 <Document> 的模块设置（B10；同一模块原则）
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString()

const CMAP_URL = '/pdfjs/cmaps/'
const STD_FONTS_URL = '/pdfjs/standard_fonts/'

export default function PdfPane({ src, onClose }) {
  const [numPages, setNumPages] = useState(0)
  const containerRef = useRef(null)
  const pageRefs = useRef({})

  useEffect(() => {
    if (src && containerRef.current) {
      containerRef.current.scrollTo({ top: 0 })
    }
  }, [src?.doc_id])

  // 引用跳页：滚动到对应页容器
  useEffect(() => {
    if (src?.page && pageRefs.current[src.page]) {
      pageRefs.current[src.page].scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [src?.page, src?.doc_id, numPages])

  if (!src) return null
  const url = `/api/docs/${src.doc_id}/pdf`

  const highlightFor = (pageNo) => {
    if (src.bbox && src.page === pageNo) {
      const [x0, y0, x1, y1] = src.bbox
      return {
        left: `${x0 * 100}%`, top: `${y0 * 100}%`,
        width: `${(x1 - x0) * 100}%`, height: `${(y1 - y0) * 100}%`,
      }
    }
    return null
  }

  return (
    <div className="pdf-pane">
      <div className="pdf-head">
        <span className="pdf-title">{src.doc_id} · 第 {src.page ?? '?'} 页{src.bbox ? ' · 区域高亮' : ''}</span>
        <button className="btn close" onClick={onClose}>关闭</button>
      </div>
      <div className="pdf-scroll" ref={containerRef}>
        <Document
          file={url}
          onLoadSuccess={({ numPages: n }) => setNumPages(n)}
          loading={<div className="pdf-loading">PDF 加载中…</div>}
          error={<div className="pdf-loading">PDF 加载失败</div>}
          options={{
            cMapUrl: CMAP_URL,
            cMapPacked: true,
            standardFontDataUrl: STD_FONTS_URL,
          }}
        >
          {Array.from({ length: numPages }, (_, i) => {
            const pageNo = i + 1
            const hl = highlightFor(pageNo)
            return (
              <div key={pageNo} className="pdf-page-wrap"
                   ref={(el) => { pageRefs.current[pageNo] = el }}>
                <Page pageNumber={pageNo} width={620} renderTextLayer={false} />
                {hl && <div className="bbox-highlight pulse" style={hl} />}
              </div>
            )
          })}
        </Document>
      </div>
    </div>
  )
}
