from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from swarmbot.config_manager import WORKSPACE_PATH, load_config
from swarmbot.loops.inference import InferenceLoop
from scripts.eval_logic_traps import TRAPS, extract_observability, score_case


def run_profile(model_name: str, profile: str) -> dict:
    os.environ["SWARMBOT_LOOP_PROFILE"] = profile
    cfg = load_config()
    cfg.providers[0].model = model_name
    loop = InferenceLoop(cfg, WORKSPACE_PATH)
    rows = []
    for idx, case in enumerate(TRAPS, 1):
        session_id = f"profile-{profile}-{idx}-{int(time.time())}"
        buf = io.StringIO()
        with redirect_stdout(buf):
            answer = loop.run(case["question"], session_id)
        logs = buf.getvalue()
        obs = extract_observability(logs)
        score = score_case(case["id"], answer)
        rows.append({"id": case["id"], "answer": answer, "score": score, "obs": obs})
    avg_score = round(sum(r["score"]["score"] for r in rows) / len(rows), 3)
    avg_tool_calls = round(sum(r["obs"]["tool_calls"] for r in rows) / len(rows), 3)
    avg_skill_calls = round(sum(r["obs"]["skill_calls"] for r in rows) / len(rows), 3)
    avg_eval_steps = round(sum(r["obs"]["eval_steps"] for r in rows) / len(rows), 3)
    avg_replans = round(sum(r["obs"]["replans"] for r in rows) / len(rows), 3)
    avg_agent_starts = round(sum(len(r["obs"]["roles"]) for r in rows) / len(rows), 3)
    return {
        "profile": profile,
        "avg_score": avg_score,
        "avg_tool_calls": avg_tool_calls,
        "avg_skill_calls": avg_skill_calls,
        "avg_eval_steps": avg_eval_steps,
        "avg_replans": avg_replans,
        "avg_agent_starts": avg_agent_starts,
        "rows": rows,
    }


def pick_recommendation(results: list[dict]) -> dict:
    ranked = sorted(results, key=lambda r: (-r["avg_score"], r["avg_tool_calls"], r["avg_agent_starts"]))
    return ranked[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare loop profiles on logic-trap tasks")
    parser.add_argument("--model", default="agentcpm-explore")
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()

    profiles = ["lean", "balanced", "swarm_max"]
    results = [run_profile(args.model, p) for p in profiles]
    best = pick_recommendation(results)
    payload = {
        "tag": args.tag,
        "model": args.model,
        "profiles": results,
        "recommended_profile": best["profile"],
        "ts": int(time.time()),
    }
    out_dir = Path("artifacts")
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"loop_profiles_{args.tag}.json"
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "file": str(out_file),
                "recommended_profile": best["profile"],
                "avg_score": best["avg_score"],
                "avg_tool_calls": best["avg_tool_calls"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
