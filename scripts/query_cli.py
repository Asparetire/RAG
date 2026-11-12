"""M3/M4 问答 CLI（m3-runbook 3.5/K8；m4-runbook 4.0 起为共享管线薄壳）。

用法：
    python scripts/query_cli.py --profile D --question "问题"
    python scripts/query_cli.py --profile D --smoke          # 20 冒烟题自动验收报告
    python scripts/query_cli.py --profile D --question ... --rerank-pro   # pro 级联对比位

4.0 事件化：编排逻辑抽至 doclens/pipeline.py（CLI 与 SSE 服务共用单一编排源，
K1 防契约双侧漂移）；本文件只保留 CLI 入口/冒烟报告/结果打印，on_event=None
（CLI 不消费事件流），行为与 M3 全等。
Windows 编码（体检发现①）：入口即 reconfigure stdout/stderr 为 UTF-8。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from doclens.config import PROFILES  # noqa: E402
from doclens.pipeline import run_pipeline  # noqa: E402

SMOKE_FILE = Path(__file__).resolve().parent / "smoke_queries.json"
PROJ_ROOT = Path(__file__).resolve().parent.parent


def _print_answer(res: dict) -> None:
    print(f"\n[{res['profile']} 档｜{res['lang']}｜trace={res['query_id']}]")
    print(f"Q: {res['question']}")
    print(f"A: {res['answer']}")
    if res["cited"]:
        print("引用:", ", ".join(f"[{n}]" for n in res["cited"]))
    for r in res["refs"]:
        print(f"  [{r.source_n}] → {r.doc_id} p{r.page}" + (f" bbox={r.bbox}" if r.bbox else ""))
    if res["degraded_citations"]:
        print(f"⚠️ {len(res['degraded_citations'])} 句含无效引用（已标记未删除）")
    if res.get("empty_content"):
        print("⚠️ 空答案守卫触发：生成 content 为空（重试后仍空，按无依据兜底）")
    if res["timings"]:
        print("耗时:", res["timings"])


def _run_smoke(profile_name: str, rerank_pro: bool) -> int:
    """20 冒烟题 × 当前档 → Markdown 报告（人工"通过/失败"列留空待填，R16）。"""
    spec = json.loads(SMOKE_FILE.read_text(encoding="utf-8"))
    queries = spec["queries"]
    report_path = PROJ_ROOT / "reports" / f"smoke_{profile_name}{'_pro' if rerank_pro else ''}.md"
    lines = [
        f"# M3 冒烟验收报告——{profile_name}{'（pro 级联）' if rerank_pro else ''} 档",
        "",
        f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 题集：{SMOKE_FILE.name}（v{spec.get('version', '?')}，{len(queries)} 题）",
        "- 判定规则：可回答题人工对照 gold_hint 判通过/失败；不可回答题以 refused=True 为通过；",
        f"- 验收线：通过率 ≥80%（≥16/20）；不可回答拒绝 ≥3/4；可回答误拒 ≤1（m3-runbook §1）",
        "",
        "| # | q_id | 类型 | 语言 | 问题 | 答案（截 300 字） | 引用 | 弃答 | trace | 通过/失败 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    n_pass_unans = 0
    n_unans = 0
    loop = asyncio.new_event_loop()  # 整个跑批共用一个事件循环（asyncio.run 循环复用会
    asyncio.set_event_loop(loop)     # 触发跨循环资源（Qdrant 连接/信号量）"Event loop is closed"）
    try:
        for i, q in enumerate(queries, 1):
            res = loop.run_until_complete(
                run_pipeline(q["question"], profile_name, rerank_pro=rerank_pro))
            refused = "是" if res["refused"] else "否"
            if q["type"] == "unanswerable":
                n_unans += 1
                n_pass_unans += 1 if res["refused"] else 0
            ans = res["answer"].replace("|", "\\|").replace("\n", " ")[:300]
            cites = ", ".join(f"[{n}]" for n in res["cited"]) or "-"
            lines.append(f"| {i} | {q['q_id']} | {q['type']} | {q['lang']} "
                         f"| {q['question'].replace('|', '\\|')} | {ans} | {cites} | {refused} "
                         f"| {res['query_id']} | |")
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
    lines += [
        "",
        f"**不可回答拒绝率（自动统计）**：{n_pass_unans}/{n_unans}",
        "",
        "## 人工判定",
        "",
        "- gold_hint 对照：见 scripts/smoke_queries.json",
        f"- 逐题证据定位：data/traces/traces-*.jsonl 按 trace 列回放",
        "",
        "| # | q_id | gold_hint | 备注 |",
        "|---|---|---|---|",
    ]
    for i, q in enumerate(queries, 1):
        lines.append(f"| {i} | {q['q_id']} | {q['gold_hint'].replace('|', '\\|')} | |")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n[完成] 报告已写 {report_path}")
    print(f"[自动统计] 不可回答拒绝 {n_pass_unans}/{n_unans}（验收 ≥3/4）；其余人工对照 gold_hint 填报告末列")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="DocLens M3/M4 问答 CLI")
    ap.add_argument("--profile", choices=list(PROFILES), default="D", help="消融档位 A..F")
    ap.add_argument("--question", "-q", help="单次提问")
    ap.add_argument("--smoke", action="store_true", help="跑 20 冒烟题产验收报告")
    ap.add_argument("--rerank-pro", action="store_true", help="pro 档级联重排（对比实验位）")
    ap.add_argument("--no-trace", action="store_true", help="调试期关闭 trace 落盘")
    args = ap.parse_args()

    if args.smoke:
        return _run_smoke(args.profile, args.rerank_pro)
    if not args.question:
        ap.error("需要 --question 或 --smoke")
    res = asyncio.run(run_pipeline(args.question, args.profile,
                                   rerank_pro=args.rerank_pro, trace_on=not args.no_trace))
    _print_answer(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
