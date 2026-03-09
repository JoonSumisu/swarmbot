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
from swarmbot.llm_client import OpenAICompatibleClient
from swarmbot.loops.inference import InferenceLoop


CASES = [
    {"id": "url_read_zh", "prompt": "输入 https://my.feishu.cn/docx/BTAWdqMXDod547xbMSec7t2Unyc 请阅读该文档，先进行分析。然后回复我已分析完整"},
    {"id": "url_read_en", "prompt": "Read https://example.com and analyze it now, then reply that analysis is completed."},
]


def is_clarify_response(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in ["clarify", "please confirm", "can you please", "what is your goal", "请确认", "请问", "能否说明", "你的目标是"])


def is_refusal_response(text: str) -> bool:
    t = (text or "").lower()
    return any(x in t for x in ["无法访问", "不能访问", "i cannot access", "i can't access", "no browsing", "无法读取"])


def run_once(model_name: str, tag: str) -> dict:
    cfg = load_config()
    cfg.providers[0].model = model_name
    llm = OpenAICompatibleClient.from_provider(providers=cfg.providers)
    loop = InferenceLoop(cfg, WORKSPACE_PATH)
    rows = []
    for c in CASES:
        q = c["prompt"]
        direct = (llm.completion(messages=[{"role": "user", "content": q}], max_tokens=512).choices[0].message.content or "").strip()
        gate = loop._decide_tool_gate("collection", q, "{}", ["web_search"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            loop_ans = loop.run(q, f"{tag}-{c['id']}-{int(time.time())}")
        loop_logs = buf.getvalue()
        attempted_read = any(x in loop_logs for x in ["calls tool: browser_open(", "calls tool: browser_read(", "calls tool: web_search("])
        rows.append(
            {
                "id": c["id"],
                "prompt": q,
                "direct_answer": direct,
                "direct_clarify": is_clarify_response(direct),
                "direct_refusal": is_refusal_response(direct),
                "loop_answer": loop_ans,
                "loop_clarify": is_clarify_response(loop_ans),
                "loop_refusal": is_refusal_response(loop_ans),
                "tool_gate": gate,
                "tool_call_count": len(re.findall(r"calls tool:", loop_logs)),
                "loop_attempted_read": attempted_read,
            }
        )
    return {
        "tag": tag,
        "model": model_name,
        "direct_clarify_rate": round(sum(1 for r in rows if r["direct_clarify"]) / len(rows), 3),
        "loop_clarify_rate": round(sum(1 for r in rows if r["loop_clarify"]) / len(rows), 3),
        "direct_refusal_rate": round(sum(1 for r in rows if r["direct_refusal"]) / len(rows), 3),
        "loop_attempt_rate": round(sum(1 for r in rows if r["loop_attempted_read"]) / len(rows), 3),
        "forced_gate_rate": round(sum(1 for r in rows if r["tool_gate"].get("mode") == "rule_forced") / len(rows), 3),
        "rows": rows,
        "ts": int(time.time()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare proactive behavior between direct model and InferenceLoop")
    parser.add_argument("--model", default="qwen3-coder-next")
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    result = run_once(args.model, args.tag)
    out_dir = Path("artifacts")
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"proactivity_compare_{args.tag}.json"
    out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"file": str(out_file), "direct_refusal_rate": result["direct_refusal_rate"], "loop_attempt_rate": result["loop_attempt_rate"], "forced_gate_rate": result["forced_gate_rate"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
