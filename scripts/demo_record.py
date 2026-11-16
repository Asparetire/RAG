"""M6 演示录屏（Playwright 脚本化）：分镜脚本自动操作浏览器并录像。

前置：
  pip install playwright && playwright install chromium
  服务已启动（WEB_STATIC=1），隧道/端口可达
  题集就绪（dataset_v1.jsonl）

产出：videos/demo-*.webm（Playwright 原生）；剪辑/转 mp4 用 ffmpeg 或 ScreenToGif。
分镜（m6-polish-survey N 线建议，75-90s）：
  0-15s   论文库 Tab（分类树+上传）
  15-40s  对话 Tab 提问 → SSE 流式回答 + 思考三态面板
  40-60s  点引用 chip → 来源侧栏 → PDF 原页 bbox 高亮（招牌镜头）
  60-70s  多模态题（图表）
  70-90s  评测看板三 Tab + 指标对比表
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8000/web/"
OUT_DIR = Path("videos")

DEMO_QUESTIONS = [
    "Kapur 方法和 Otsu 方法分别是用来做什么的？",
    "根据图 2(b) 所示的互联自动机结构：虚线框内共有几个学习自动机？",
]


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={"width": 1600, "height": 900},
            record_video_dir=str(OUT_DIR),
            record_video_size={"width": 1600, "height": 900},
        )
        page = await ctx.new_page()
        await page.goto(BASE, wait_until="networkidle")

        # 登录（读 .env 的 ADMIN_PASSWORD——由调用方注入环境变量 DEMO_PASSWORD）
        import os
        password = os.environ.get("DEMO_PASSWORD")
        if not password:
            raise SystemExit("请设置 DEMO_PASSWORD 环境变量")
        await page.fill(".login-input", password)
        await page.click(".login-btn")
        await page.wait_for_selector(".topbar", timeout=15000)
        await page.wait_for_timeout(2000)  # 留白供观感

        # 分镜 0-15s：论文库 Tab
        await page.click("text=论文库")
        await page.wait_for_timeout(4000)
        await page.click("text=对话")  # 回对话（截图锚点）

        # 分镜 15-40s：提问 → 流式回答
        await page.fill(".composer textarea", DEMO_QUESTIONS[0])
        await page.click(".btn.send")
        # 等流式完成（思考+生成，最长 3 分钟；看板逐帧收录）
        await page.wait_for_selector(".msg.assistant.done", timeout=200000)
        await page.wait_for_timeout(2000)

        # 分镜 40-60s：点第一个引用 chip → PDF 高亮
        chip = page.locator(".cite-chip").first
        if await chip.count():
            await chip.click()
            await page.wait_for_timeout(5000)  # PDF 渲染+高亮脉冲（招牌镜头）

        # 分镜 60-70s：多模态题
        await page.fill(".composer textarea", DEMO_QUESTIONS[1])
        await page.click(".btn.send")
        await page.wait_for_selector(".msg.assistant.done >> nth=-1", timeout=200000)
        await page.wait_for_timeout(2000)

        # 分镜 70-90s：评测看板
        await page.click("text=评测看板")
        await page.wait_for_timeout(6000)  # 指标表+进度定格

        video = page.video
        await ctx.close()
        if video:
            path = await video.path()
            target = OUT_DIR / "demo-doclens.webm"
            Path(path).replace(target)
            print("[saved]", target)


if __name__ == "__main__":
    asyncio.run(main())
