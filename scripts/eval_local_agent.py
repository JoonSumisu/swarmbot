from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from swarmbot.config_manager import WORKSPACE_PATH, load_config
from swarmbot.loops.inference import InferenceLoop


CASES = [
    {
        "id": "qa_1",
        "input": "请给我一段 Python 代码，判断一个整数是否为质数，并解释复杂度。",
        "must_have": ["python", "复杂度"],
        "forbid": ["步行", "车辆", "car", "walking"],
    },
    {
        "id": "qa_2",
        "input": "我在 macOS 上 pip 安装报 externally managed，给我稳定安装方案。",
        "must_have": ["venv", "pipx"],
        "forbid": ["步行", "车辆", "car", "walking"],
    },
    {
        "id": "qa_3",
        "input": "请写一段礼貌的英文邮件，主题是申请延后会议到周五。",
        "must_have": ["Subject", "Friday"],
        "forbid": ["步行", "车辆", "car", "walking"],
    },
    {
        "id": "qa_4",
        "input": "帮我概述一下快速排序的核心思想和最坏复杂度。",
        "must_have": ["O(n^2)", "分治"],
        "forbid": ["步行", "车辆", "car", "walking"],
    },
]


def evaluate_response(text: str, must_have: list[str], forbid: list[str]) -> dict:
    low = text.lower()
    hits = [k for k in must_have if k.lower() in low]
    bad = [k for k in forbid if k.lower() in low]
    completion = 1.0 if hits else 0.0
    relevance = 1.0 if not bad else 0.0
    brevity = 1.0 if len(text) <= 1200 else 0.6
    score = round((completion * 0.45 + relevance * 0.45 + brevity * 0.10) * 100, 2)
    return {
        "score": score,
        "must_hit": hits,
        "forbidden_hit": bad,
        "length": len(text),
    }


class SafeInferenceLoop(InferenceLoop):
    def _truncate(self, s: str, n: int) -> str:
        return s[:n] if len(s) <= n else s[:n] + "..."

    def _step_collection(self):
        print("[Step 3] Collection (No Tools in Eval)...")
        analysis = self.whiteboard.get("problem_analysis")
        hot = self.hot_memory.read()
        warm = self.warm_memory.read_today()
        cold = self.cold_memory.search_text(str(analysis), limit=5)
        prompt = json.dumps(
            {
                "analysis": analysis,
                "hot_memory": self._truncate(hot, 1500),
                "warm_memory": self._truncate(warm, 1500),
                "cold_memory": self._truncate(cold, 1500),
            },
            ensure_ascii=False,
        )
        results = self._run_parallel(prompt, 2, "collector", enable_tools=False)
        merged = {"synthesized_context": "\n".join(results), "memory_references": [], "external_info": ""}
        self.whiteboard.update("information_gathering", merged)

    def _step_inference(self):
        print("[Step 5] Inference (No Tools in Eval)...")
        plan = self.whiteboard.get("action_plan")
        context = (self.whiteboard.get("information_gathering") or {}).get("synthesized_context", "")
        results = []
        for task in plan.get("tasks", []):
            worker_role = task.get("worker", "assistant")
            worker = self._create_worker(worker_role, enable_tools=False)
            prompt = f"Task: {task.get('desc')}\nContext: {context[:4000]}"
            res = worker.step(prompt)
            results.append({"task_id": task.get("id"), "result": res})
        self.whiteboard.update("inference_conclusions", results)

    def _step_translation(self) -> str:
        print("[Step 7] Translation (No Tools in Eval)...")
        conclusions = self.whiteboard.get("inference_conclusions")
        conclusions_json = json.dumps(conclusions, ensure_ascii=False)
        prompt = (
            f"User Input: {self.whiteboard.get('input_prompt')}\n"
            f"Conclusions: {self._truncate(conclusions_json, 2000)}\n"
            "Please answer user request directly, briefly, and only with relevant content."
        )
        return self._create_worker("master", enable_tools=False).step(prompt)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate local Swarmbot answer quality")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--limit", type=int, default=4)
    args = parser.parse_args()

    cfg = load_config()
    loop = SafeInferenceLoop(cfg, WORKSPACE_PATH)
    rows = []
    selected = CASES[: max(1, min(args.limit, len(CASES)))]
    for idx, case in enumerate(selected, 1):
        session_id = f"eval-{args.tag}-{idx}-{int(time.time())}"
        output = loop.run(case["input"], session_id)
        m = evaluate_response(output, case["must_have"], case["forbid"])
        rows.append(
            {
                "id": case["id"],
                "input": case["input"],
                "output": output,
                "metrics": m,
            }
        )
    avg = round(sum(r["metrics"]["score"] for r in rows) / max(1, len(rows)), 2)
    result = {
        "tag": args.tag,
        "avg_score": avg,
        "count": len(rows),
        "rows": rows,
        "ts": int(time.time()),
    }
    out_dir = Path("artifacts")
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"eval_{args.tag}.json"
    out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"tag": args.tag, "avg_score": avg, "file": str(out_file)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
