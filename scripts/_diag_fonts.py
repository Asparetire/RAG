"""临时诊断2：财报 PDF 字体内嵌情况（pypdf）+ pdfium 渲染截图（用完即删）。"""
from pypdf import PdfReader
from pypdf import PdfWriter

PDF = "/home/doclens/RAG/data/pdfs/526144f26443.pdf"
r = PdfReader(PDF)
print("pages:", len(r.pages))


def font_rows(page):
    res = page.get("/Resources")
    if not res:
        return
    fonts = res.get("/Font")
    if not fonts:
        return
    for name, ref in fonts.get_object().items():
        f = ref.get_object()
        base = f.get("/BaseFont")
        st = f.get("/Subtype")
        embedded = False
        descriptors = []
        desc = f.get("/FontDescriptor")
        if desc is not None:
            descriptors.append(desc.get_object())
        if st == "/Type0":
            for df in f.get("/DescendantFonts") or []:
                dfo = df.get_object()
                dd = dfo.get("/FontDescriptor")
                if dd is not None:
                    descriptors.append(dd.get_object())
        for d in descriptors:
            if any(k in d for k in ("/FontFile", "/FontFile2", "/FontFile3")):
                embedded = True
        yield name, base, st, embedded


# 全文档扫描：未内嵌字体汇总
agg = {}
for i, page in enumerate(r.pages):
    for name, base, st, emb in font_rows(page) or []:
        if not emb:
            agg.setdefault(str(base), set()).add(i + 1)

print("== 未内嵌字体 ==")
if not agg:
    print("  (无——全部内嵌)")
for base, pages in agg.items():
    print(f"  {base} -> {len(pages)} 页, 如 p{sorted(pages)[:5]}")

# 前 3 页逐字体明细 + 旋转角
for i in range(3):
    page = r.pages[i]
    rot = page.get("/Rotate", 0)
    mb = page.mediabox
    print(f"== page {i+1}: rotate={rot} mediabox={mb}")
    for name, base, st, emb in font_rows(page) or []:
        print(f"   {name} {base} {st} {'EMBEDDED' if emb else 'NOT-EMBEDDED'}")

# pdfium 渲染第 1/5 页（PDFium 自带字体回退，可对照 pdf.js 行为）
import pypdfium2 as pdfium

pdf = pdfium.PdfDocument(PDF)
for idx in (0, 4):
    p = pdf[idx]
    bmp = p.render(scale=1.3)
    pil = bmp.to_pil()
    out = f"/tmp/_diag_page{idx+1}.png"
    pil.save(out)
    print("saved:", out, pil.size)
    tp = p.get_textpage()
    print("   text head:", tp.get_text_range()[:60].replace("\n", " "))
