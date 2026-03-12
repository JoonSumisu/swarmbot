import argparse
import json
import random
import re
import time
from pathlib import Path

from datasets import load_dataset

from swarmbot.config_manager import load_config
from swarmbot.llm_client import OpenAICompatibleClient


def _norm_text(s: str) -> str:
    t = (s or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^\w\s]", "", t)
    return t


def _is_correct(prediction: str, ground_truth: str, aliases: list[str]) -> bool:
    pred = _norm_text(prediction)
    gt = _norm_text(ground_truth)
    if not pred or not gt:
        return False
    if gt in pred:
        return True
    for a in aliases or []:
        aa = _norm_text(str(a))
        if aa and aa in pred:
            return True
    return False


def _format_prompt(sample: dict) -> tuple[str, str]:
    question = sample["question"]
    parts = []
    for i, p in enumerate(sample["paragraphs"]):
        parts.append(f"Document {i+1} (Title: {p.get('title','')}):\n{p.get('paragraph_text','')}")
    context = "\n\n".join(parts)
    return question, context


def _ask(llm: OpenAICompatibleClient, text: str) -> str:
    r = llm.completion(messages=[{"role": "user", "content": text}])
    return (r.choices[0].message.content or "").strip()


def _extract_json_obj(text: str) -> dict:
    m = re.search(r"\{[\s\S]*\}", text or "")
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


def _extract_single_line_answer(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return s
    for tag in ["Final Answer:", "FINAL ANSWER:", "Answer:", "答案：", "答案:"]:
        if tag in s:
            tail = s.split(tag)[-1].strip()
            if "\n" in tail:
                tail = tail.split("\n")[0].strip()
            if tail:
                return tail
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if not lines:
        return s
    candidate = lines[-1]
    candidate = re.sub(r"^\*\*|\*\*$", "", candidate).strip()
    if len(candidate) > 180:
        candidate = candidate[:180].strip()
    return candidate


def run_pure(llm: OpenAICompatibleClient, question: str, context: str) -> tuple[str, float]:
    st = time.time()
    try:
        ans = _ask(
            llm,
            "You answer multi-hop QA with concise final answer only.\n"
            f"Background Information:\n{context}\n\nQuestion: {question}\n\n"
            "Return only one short final answer.",
        )
    except Exception as e:
        ans = f"PURE_ERROR: {e}"
    return _extract_single_line_answer(ans), time.time() - st


def run_loop_off(llm: OpenAICompatibleClient, question: str, context: str) -> tuple[str, float, dict]:
    st = time.time()
    try:
        plan = _ask(
            llm,
            "You are planner. Output a JSON array with 2-4 reasoning steps.\n"
            f"Question: {question}\nBackground:\n{context[:12000]}",
        )
        draft = _ask(
            llm,
            "You are executor. Use the reasoning plan and context to answer.\n"
            f"Plan: {plan}\nQuestion: {question}\nBackground:\n{context}\n"
            "Return only one short final answer.",
        )
        final_line = _extract_single_line_answer(draft)
    except Exception as e:
        plan = ""
        final_line = f"LOOP_OFF_ERROR: {e}"
    return final_line, time.time() - st, {"plan": plan}


def run_loop_on_gated(llm: OpenAICompatibleClient, question: str, context: str) -> tuple[str, float, dict]:
    st = time.time()
    supervisor_raw = ""
    try:
        plan = _ask(
            llm,
            "You are planner. Output JSON with fields: critical_tasks, key_entities, required_evidence.\n"
            f"Question: {question}\nBackground:\n{context[:12000]}",
        )
        draft = _ask(
            llm,
            "You are executor. Provide answer with brief rationale, then a line prefixed with 'Final Answer:'.\n"
            f"Plan: {plan}\nQuestion: {question}\nBackground:\n{context}",
        )
        supervisor_raw = _ask(
            llm,
            "You are supervisor. Evaluate the draft answer and return STRICT JSON with fields:\n"
            "key_task_completion_rate (0-1), evidence_coverage (0-1), consistency_score (0-1), final_confidence (0-1), "
            "evidence_conflict (bool), revise_needed (bool), revised_answer_line (single-line string).\n"
            "Important: revised_answer_line must be exactly one line and no explanation.\n"
            f"Question: {question}\nBackground:\n{context}\nDraftAnswer:\n{draft}",
        )
        sj = _extract_json_obj(supervisor_raw)
        final_conf = float(sj.get("final_confidence") or 0.0)
        evidence_conflict = bool(sj.get("evidence_conflict", False))
        revise_needed = bool(sj.get("revise_needed", False))
        revised_line = _extract_single_line_answer(str(sj.get("revised_answer_line") or ""))
        draft_line = _extract_single_line_answer(draft)
        allow_rewrite = revise_needed and evidence_conflict and (final_conf < 0.72)
        if allow_rewrite and revised_line:
            final_line = revised_line
        else:
            final_line = draft_line
        obs = {
            "plan": plan,
            "supervisor": sj,
            "rewrite_allowed": allow_rewrite,
            "final_answer_line": final_line,
        }
    except Exception as e:
        final_line = f"LOOP_ON_ERROR: {e}"
        obs = {"supervisor_raw": supervisor_raw, "rewrite_allowed": False}
    return final_line, time.time() - st, obs


def pick_indices(ds_len: int, num_samples: int, seed: int, exclude_ids: set[int]) -> list[int]:
    rng = random.Random(seed)
    pool = [i for i in range(ds_len) if i not in exclude_ids]
    if len(pool) < num_samples:
        pool = list(range(ds_len))
    return rng.sample(pool, num_samples)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--num-samples", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20260312)
    parser.add_argument("--model", type=str, default="unsloth/qwen3-coder-next")
    parser.add_argument("--tag", type=str, default="v1_1_musique30_gatev2")
    parser.add_argument(
        "--exclude-from",
        type=str,
        default="artifacts/musique_loop_vs_pure_v1_1_musique30_looplite.json",
    )
    args = parser.parse_args()

    cfg = load_config()
    cfg.providers[0].model = args.model
    llm = OpenAICompatibleClient.from_provider(providers=cfg.providers)
    ds = load_dataset("bdsaglam/musique", split="validation")

    exclude_ids: set[int] = set()
    ef = Path(args.exclude_from)
    if ef.exists():
        try:
            prev = json.loads(ef.read_text(encoding="utf-8"))
            for r in prev.get("rows") or []:
                exclude_ids.add(int(r.get("id")))
        except Exception:
            pass

    indices = pick_indices(len(ds), args.num_samples, args.seed, exclude_ids)
    rows = []
    for i, idx in enumerate(indices, start=1):
        sample = ds[idx]
        q, ctx = _format_prompt(sample)
        truth = sample.get("answer", "")
        aliases = sample.get("answer_aliases", []) or []
        pure_ans, pure_t = run_pure(llm, q, ctx)
        off_ans, off_t, off_obs = run_loop_off(llm, q, ctx)
        on_ans, on_t, on_obs = run_loop_on_gated(llm, q, ctx)
        row = {
            "id": int(idx),
            "question": q,
            "truth": truth,
            "aliases": aliases,
            "pure": pure_ans,
            "loop_off": off_ans,
            "loop_on": on_ans,
            "pure_ok": _is_correct(pure_ans, truth, aliases),
            "loop_off_ok": _is_correct(off_ans, truth, aliases),
            "loop_on_ok": _is_correct(on_ans, truth, aliases),
            "pure_t": round(pure_t, 3),
            "loop_off_t": round(off_t, 3),
            "loop_on_t": round(on_t, 3),
            "loop_off_obs": off_obs,
            "loop_on_obs": on_obs,
        }
        rows.append(row)
        print(
            f"[{i}/{args.num_samples}] id={idx} pure={row['pure_ok']} "
            f"off={row['loop_off_ok']} on={row['loop_on_ok']} "
            f"rewrite={bool((row.get('loop_on_obs') or {}).get('rewrite_allowed'))}"
        )

    n = len(rows)
    summary = {
        "samples": n,
        "pure_acc": round(sum(1 for r in rows if r["pure_ok"]) / max(1, n), 4),
        "loop_off_acc": round(sum(1 for r in rows if r["loop_off_ok"]) / max(1, n), 4),
        "loop_on_acc": round(sum(1 for r in rows if r["loop_on_ok"]) / max(1, n), 4),
        "gain_loop_on_vs_pure": sum(1 for r in rows if (not r["pure_ok"]) and r["loop_on_ok"]),
        "gain_loop_on_vs_off": sum(1 for r in rows if (not r["loop_off_ok"]) and r["loop_on_ok"]),
        "regress_loop_on_vs_pure": sum(1 for r in rows if r["pure_ok"] and (not r["loop_on_ok"])),
        "rewrite_allowed_count": sum(1 for r in rows if bool((r.get("loop_on_obs") or {}).get("rewrite_allowed"))),
        "pure_avg_t": round(sum(r["pure_t"] for r in rows) / max(1, n), 3),
        "loop_off_avg_t": round(sum(r["loop_off_t"] for r in rows) / max(1, n), 3),
        "loop_on_avg_t": round(sum(r["loop_on_t"] for r in rows) / max(1, n), 3),
    }
    diagnosis = {
        "hard_case_count": sum(1 for r in rows if (not r["pure_ok"]) and (not r["loop_on_ok"])),
        "on_wrong_off_right_count": sum(1 for r in rows if (not r["loop_on_ok"]) and r["loop_off_ok"]),
        "on_better_than_pure_ids": [r["id"] for r in rows if (not r["pure_ok"]) and r["loop_on_ok"]][:12],
        "on_worse_than_pure_ids": [r["id"] for r in rows if r["pure_ok"] and (not r["loop_on_ok"])][:12],
    }
    out = {
        "tag": args.tag,
        "model": args.model,
        "seed": args.seed,
        "exclude_from": args.exclude_from,
        "summary": summary,
        "diagnosis": diagnosis,
        "rows": rows,
        "ts": int(time.time()),
    }
    artifacts = Path("artifacts")
    artifacts.mkdir(parents=True, exist_ok=True)
    jf = artifacts / f"musique_loop_vs_pure_{args.tag}.json"
    jl = artifacts / f"musique_loop_vs_pure_{args.tag}.jsonl"
    jf.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    with jl.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({"file": str(jf), "summary": summary, "diagnosis": diagnosis}, ensure_ascii=False))


if __name__ == "__main__":
    main()
