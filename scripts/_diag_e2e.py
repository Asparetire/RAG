"""临时诊断5：端到端复现用户操作——登录、提问、取 sources 的 bbox、正确比例叠加渲染（用完即删）。"""
import json
import urllib.request

BASE = "http://127.0.0.1:8000"
ADMIN_PASSWORD = None  # 从 .env 读取
for line in open("/home/doclens/RAG/.env", encoding="utf-8", errors="ignore"):
    if line.strip().startswith("ADMIN_PASSWORD="):
        ADMIN_PASSWORD = line.split("=", 1)[1].strip().strip('"').strip("'")
assert ADMIN_PASSWORD, "ADMIN_PASSWORD not found"

# 1) 登录（OAuth2 表单）
data = urllib.parse.urlencode({"username": "admin", "password": ADMIN_PASSWORD}).encode()
req = urllib.request.Request(BASE + "/api/auth/login", data=data, method="POST")
with urllib.request.urlopen(req, timeout=15) as r:
    token = json.loads(r.read())["access_token"]
print("login ok")

# 2) 提问（SSE 流，抓 sources 事件）
body = json.dumps({"question": "文中提出的方法整体流程是怎样的？", "profile": "D"}).encode()
req = urllib.request.Request(BASE + "/api/query", data=body, method="POST",
                             headers={"Authorization": f"Bearer {token}",
                                      "Content-Type": "application/json"})
sources = None
with urllib.request.urlopen(req, timeout=180) as r:
    event = None
    for raw in r:
        line = raw.decode("utf-8").strip()
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:") and event == "sources":
            payload = json.loads(line.split(":", 1)[1].strip())
            sources = payload.get("sources") if isinstance(payload, dict) else payload
            break
if not sources:
    raise SystemExit("no sources event captured")
print(f"got {len(sources)} sources")
for s in sources[:6]:
    print("  [%s] %s %s p%s bbox=%s | %r" % (s.get("n"), s.get("kind"), s.get("doc_id"),
                                             s.get("page"), s.get("bbox"),
                                             (s.get("snippet") or "")[:40]))
json.dump(sources, open("/tmp/_e2e_sources.json", "w"), ensure_ascii=False)

# 3) 取第一个带 bbox 的 source
target = next((s for s in sources if s.get("bbox")), None)
if target is None:
    raise SystemExit("no source with bbox")
print("target source:", target["n"], target["doc_id"], "p", target["page"], target["bbox"])

# 4) 下载 PDF
req = urllib.request.Request(BASE + f"/api/docs/{target['doc_id']}/pdf",
                             headers={"Authorization": f"Bearer {token}"})
pdf_bytes = urllib.request.urlopen(req, timeout=30).read()
open("/tmp/_e2e_target.pdf", "wb").write(pdf_bytes)
print("pdf bytes:", len(pdf_bytes))

# 5) 渲染 + 正确比例叠加（这次用渲染像素尺寸）
import pypdfium2 as pdfium

pdf = pdfium.PdfDocument("/tmp/_e2e_target.pdf")
pg = pdf[target["page"] - 1]
bmp = pg.render(scale=1.6)
img = bmp.to_pil().convert("RGB")
W, H = img.size
from PIL import ImageDraw

d = ImageDraw.Draw(img)
for s in sources:
    bb = s.get("bbox")
    if not bb or s.get("doc_id") != target["doc_id"] or s.get("page") != target["page"]:
        continue
    x0, y0, x1, y1 = bb
    if s["n"] == target["n"]:
        d.rectangle([x0 * W, y0 * H, x1 * W, y1 * H], outline=(220, 30, 30), width=5)
    else:
        d.rectangle([x0 * W, y0 * H, x1 * W, y1 * H], outline=(30, 80, 220), width=2)
img.save("/tmp/_e2e_overlay.png")
print("saved /tmp/_e2e_overlay.png", img.size)
pdf.close()
