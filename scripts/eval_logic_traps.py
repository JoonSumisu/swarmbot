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
import swarmbot.loops.inference as inference_mod


TRAPS = [
    {
        "id": "trap_carwash",
        "question": "我想洗车，洗车店距离我家 50 米，你建议我开车去还是走路去？",
        "expected_any": ["开车", "把车开过去", "先把车带去"],
        "forbid_any": ["走路去洗车", "直接走路去洗车"],
    },
    {
        "id": "trap_parcel",
        "question": "快递点离我 100 米，但我要寄的包裹还在家里。是先去快递点还是先回家拿包裹？",
        "expected_any": ["先回家拿包裹", "先回家取包裹", "先拿包裹", "先取包裹"],
        "forbid_any": ["先去快递点"],
    },
    {
        "id": "trap_usb",
        "question": "打印店在楼下，但我要打印的文件在U盘里，U盘在办公室。现在我应该直接去打印店吗？",
        "expected_any": ["先去办公室拿U盘", "先去办公室取U盘", "先拿U盘", "先取U盘"],
        "forbid_any": ["直接去打印店"],
    },
]


def score_case(case_id: str, text: str) -> dict:
    t = (text or "").lower()
    if case_id == "trap_carwash":
        ok = bool(re.search(r"(建议|推荐|结论).{0,10}(开车|驾车|把车开)", text) or "开车去" in text)
        bad = bool(re.search(r"(建议|推荐|结论).{0,10}(走路|步行)", text) or "走路去" in text or "步行更优" in text)
        score = 1 if ok and not bad else 0
        return {"score": score, "expected_hit": ok, "forbid_hit": bad}
    if case_id == "trap_parcel":
        ok = bool(
            re.search(r"先.{0,6}(回家|去家里).{0,6}(拿|取).{0,4}包裹", text)
            or re.search(r"先.{0,6}(拿|取).{0,4}包裹", text)
        )
        bad = bool(re.search(r"(建议|推荐).{0,8}先.{0,4}去.{0,4}快递点", text))
        score = 1 if ok and not bad else 0
        return {"score": score, "expected_hit": ok, "forbid_hit": bad}
    if case_id == "trap_usb":
        ok = bool(
            re.search(r"先.{0,8}去.{0,6}办公室.{0,6}(拿|取).{0,4}(u盘|文件)", t)
            or re.search(r"先.{0,8}(拿|取).{0,4}(u盘|文件)", t)
        )
        bad = bool(re.search(r"(建议|推荐).{0,8}(直接|先).{0,4}去.{0,4}打印店", text))
        score = 1 if ok and not bad else 0
        return {"score": score, "expected_hit": ok, "forbid_hit": bad}
    return {"score": 0, "expected_hit": False, "forbid_hit": False}


def extract_observability(log_text: str) -> dict:
    roles = sorted(set(re.findall(r"\[CoT\] Agent ([^ ]+) starting thought process", log_text)))
    eval_steps = len(re.findall(r"\[Step 6\] Evaluation", log_text))
    replans = len(re.findall(r"\[Step 4b\] Re-Planning", log_text))
    tool_calls = len(re.findall(r"calls tool:", log_text))
    skill_calls = len(
        re.findall(r"calls tool: (skill_summary|skill_load|skill_fetch)\(", log_text)
    )
    return {
        "roles": roles,
        "eval_steps": eval_steps,
        "replans": replans,
        "tool_calls": tool_calls,
        "skill_calls": skill_calls,
    }


def direct_answer(llm: OpenAICompatibleClient, question: str) -> str:
    r = llm.completion(messages=[{"role": "user", "content": question}], max_tokens=512)
    return (r.choices[0].message.content or "").strip()


def run_once(model_name: str, tag: str) -> dict:
    cfg = load_config()
    cfg.providers[0].model = model_name
    llm = OpenAICompatibleClient.from_provider(providers=cfg.providers)
    loop = InferenceLoop(cfg, WORKSPACE_PATH)

    rows = []
    for i, c in enumerate(TRAPS, 1):
        direct = direct_answer(llm, c["question"])
        direct_score = score_case(c["id"], direct)

        session_id = f"{tag}-{c['id']}-{i}-{int(time.time())}"
        buf = io.StringIO()
        with redirect_stdout(buf):
            loop_answer = loop.run(c["question"], session_id)
        loop_logs = buf.getvalue()
        loop_score = score_case(c["id"], loop_answer)
        obs = extract_observability(loop_logs)

        rows.append(
            {
                "id": c["id"],
                "question": c["question"],
                "direct_answer": direct,
                "direct_score": direct_score,
                "loop_answer": loop_answer,
                "loop_score": loop_score,
                "observability": obs,
            }
        )

    direct_avg = round(sum(r["direct_score"]["score"] for r in rows) / len(rows), 3)
    loop_avg = round(sum(r["loop_score"]["score"] for r in rows) / len(rows), 3)
    return {
        "tag": tag,
        "model": model_name,
        "inference_module": inference_mod.__file__,
        "direct_avg": direct_avg,
        "loop_avg": loop_avg,
        "rows": rows,
        "ts": int(time.time()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate logic-trap calibration for local model")
    parser.add_argument("--model", default="agentcpm-explore")
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()

    result = run_once(args.model, args.tag)
    out_dir = Path("artifacts")
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"logic_traps_{args.tag}.json"
    out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"file": str(out_file), "direct_avg": result["direct_avg"], "loop_avg": result["loop_avg"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
