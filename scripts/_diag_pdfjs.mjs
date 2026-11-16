// 临时诊断3：用与浏览器同版本的 pdfjs-dist 逐篇加载 PDF，
// 逐页 getOperatorList（触发字体加载），抓取所有警告（用完即删）。
import fs from 'fs';
import path from 'path';
import { pathToFileURL } from 'url';

const PDFJS_DIR = 'D:/Project/RAG/web/node_modules/pdfjs-dist';
const { getDocument, OPS } = await import(pathToFileURL(path.join(PDFJS_DIR, 'legacy/build/pdf.mjs')).href);

const CMAPS = 'D:/Project/RAG/web/dist/pdfjs/cmaps/';
const FONTS = 'D:/Project/RAG/web/dist/pdfjs/standard_fonts/';

class FsCMapFactory {
  async fetch({ name }) {
    const data = await fs.promises.readFile(path.join(CMAPS, name + '.bcmap'));
    return { cMapData: new Uint8Array(data), compressionType: 1 };
  }
}
class FsFontFactory {
  async fetch({ filename }) {
    return new Uint8Array(await fs.promises.readFile(path.join(FONTS, filename)));
  }
}

const out = (...a) => process.stdout.write(a.join(' ') + '\n');
const dir = process.env.TEMP + '/doclens_diag_pdfs';
const files = fs.readdirSync(dir).filter((f) => f.endsWith('.pdf')).sort();

for (const f of files) {
  const warnings = [];
  const cap = (...a) => warnings.push(a.map(String).join(' '));
  const oLog = console.log, oWarn = console.warn, oErr = console.error;
  console.log = cap; console.warn = cap; console.error = cap;
  let status = 'ok', pagesDone = 0, textOps = 0;
  try {
    const data = new Uint8Array(fs.readFileSync(path.join(dir, f)));
    const doc = await getDocument({
      data,
      cMapUrl: CMAPS,
      cMapPacked: true,
      standardFontDataUrl: FONTS,
      CMapReaderFactory: FsCMapFactory,
      StandardFontDataFactory: FsFontFactory,
      useSystemFonts: false,
    }).promise;
    for (let pno = 1; pno <= doc.numPages; pno++) {
      const page = await doc.getPage(pno);
      const ops = await page.getOperatorList();
      for (const op of ops.fnArray) {
        if (op === OPS.showText || op === OPS.showSpacedText) textOps++;
      }
      pagesDone++;
    }
  } catch (e) {
    status = 'ERROR: ' + String(e).slice(0, 200);
  }
  console.log = oLog; console.warn = oWarn; console.error = oErr;
  const uniq = [...new Set(warnings.map((w) => w.slice(0, 120)))];
  const flag = status !== 'ok' || uniq.length ? '  <<<< 异常' : '';
  out(`===== ${f} pages=${pagesDone} textOps=${textOps} status=${status}${flag}`);
  uniq.slice(0, 10).forEach((w) => out('   W:', w));
}
