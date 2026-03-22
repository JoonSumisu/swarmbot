from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from swarmbot.config_manager import WORKSPACE_PATH, load_config
from swarmbot.loops.inference import InferenceLoop

ROUTING_CASES = [
    ("simple_direct_master", "帮我写一句向同事道歉的话。"),
    ("simple_direct_master", "把这句话润色一下：你这方案太烂了。"),
    ("reasoning_swarm", "请从心理学角度分析我为什么总拖延，并给一周改进计划。"),
    ("reasoning_swarm", "请从哲学角度解释控制感，并给出工作中的可执行建议。"),
    ("engineering_complex", "设计 CI 质量门禁，包含单测 lint sast 发布审批与回滚。"),
    ("engineering_complex", "线上网关并发超时，给排障、改造、验证和发布方案。"),
]

LEGAL_CASES = [
    "劳动合同未签，员工是否可主张双倍工资？请给出相关法条并说明。",
    "交通事故轻微伤，责任划分后如何计算赔偿，引用相关条文。",
]

BUSINESS_CASES = [
    "评估一个 AI 笔记产品的商业可行性，给市场、成本、风险和MVP建议。",
    "我们要做跨境电商工具，帮我做竞品与商业模式分析。",
]

THINK_CASES = [
    "我最近总焦虑，先安抚我，再给可执行的今晚计划。",
    "从逻辑上分析‘效率和质量’冲突，给决策框架。",
]


def run_with_logs(loop: InferenceLoop, q: str) -> tuple[str, str, dict]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        ans = loop.run(q, f"bench-{int(time.time()*1000)}")
    logs = buf.getvalue()
    dec = loop.whiteboard.get("route_decision") or {}
    return ans, logs, dec


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3-coder-next")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    cfg.providers[0].model = args.model
    loop = InferenceLoop(cfg, WORKSPACE_PATH)

    routing_cases = ROUTING_CASES if not args.quick else [ROUTING_CASES[0], ROUTING_CASES[2], ROUTING_CASES[4]]
    legal_cases = LEGAL_CASES if not args.quick else LEGAL_CASES[:1]
    business_cases = BUSINESS_CASES if not args.quick else BUSINESS_CASES[:1]
    think_cases = THINK_CASES if not args.quick else THINK_CASES[:1]
    rows = []
    for exp, q in routing_cases:
        d = loop.preview_route(q)
        got = str(d.get("route") or "")
        rows.append({"type": "routing", "expect": exp, "got": got, "ok": got == exp, "reason": d.get("reason", "")})

    legal_kb = Path.home() / ".swarmbot" / "evidence" / "legal" / "incremental.jsonl"
    before_kb_lines = len(legal_kb.read_text(encoding="utf-8").splitlines()) if legal_kb.exists() else 0

    for q in legal_cases:
        ans, logs, dec = run_with_logs(loop, q)
        has_law = bool(re.search(r"《[^》]{2,30}》", ans))
        has_article = bool(re.search(r"第[一二三四五六七八九十百千0-9]{1,8}条", ans))
        used_search = "calls tool: web_search(" in logs
        rows.append(
            {
                "type": "legal",
                "route": dec.get("route"),
                "used_search": used_search,
                "has_law": has_law,
                "has_article": has_article,
                "ok": has_law and has_article,
            }
        )

    for q in business_cases:
        ans, logs, dec = run_with_logs(loop, q)
        used_search = "calls tool: web_search(" in logs
        keywords_ok = all(k in ans for k in ["市场", "风险"]) and ("成本" in ans or "预算" in ans)
        rows.append(
            {
                "type": "business",
                "route": dec.get("route"),
                "used_search": used_search,
                "keywords_ok": keywords_ok,
                "ok": used_search and keywords_ok,
            }
        )

    for q in think_cases:
        ans, logs, dec = run_with_logs(loop, q)
        structured = ("- " in ans) or ("1." in ans) or ("###" in ans)
        rows.append({"type": "think", "route": dec.get("route"), "structured": structured, "ok": structured})

    after_kb_lines = len(legal_kb.read_text(encoding="utf-8").splitlines()) if legal_kb.exists() else 0
    kb_growth = after_kb_lines - before_kb_lines

    routing_rows = [r for r in rows if r["type"] == "routing"]
    eng_rows = [r for r in routing_rows if r["expect"] == "engineering_complex"]
    routing_acc = round(sum(1 for r in routing_rows if r["ok"]) / len(routing_rows), 3)
    engineering_acc = round(sum(1 for r in eng_rows if r["ok"]) / len(eng_rows), 3) if eng_rows else 0.0
    legal_pass = round(sum(1 for r in rows if r["type"] == "legal" and r["ok"]) / max(1, len([r for r in rows if r["type"] == "legal"])), 3)
    business_pass = round(sum(1 for r in rows if r["type"] == "business" and r["ok"]) / max(1, len([r for r in rows if r["type"] == "business"])), 3)
    think_pass = round(sum(1 for r in rows if r["type"] == "think" and r["ok"]) / max(1, len([r for r in rows if r["type"] == "think"])), 3)

    out = {
        "tag": args.tag,
        "model": args.model,
        "routing_acc": routing_acc,
        "engineering_acc": engineering_acc,
        "legal_pass": legal_pass,
        "business_pass": business_pass,
        "think_pass": think_pass,
        "evidence_growth": kb_growth,
        "rows": rows,
        "ts": int(time.time()),
    }
    out_dir = Path("artifacts")
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"inference_benchmark_{args.tag}.json"
    out_file.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"file": str(out_file), "routing_acc": routing_acc, "engineering_acc": engineering_acc, "evidence_growth": kb_growth}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
