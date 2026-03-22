import argparse
import json
import re
import time
from pathlib import Path

from swarmbot.config_manager import load_config
from swarmbot.llm_client import OpenAICompatibleClient


TASKS = [
    {
        "id": "t1",
        "prompt": "Write Python function add(a,b) returning sum.",
        "fn": "add",
        "tests": ["add(2,3)==5", "add(-1,1)==0"],
    },
    {
        "id": "t2",
        "prompt": "Write Python function is_even(n) returning True if n is even.",
        "fn": "is_even",
        "tests": ["is_even(4) is True", "is_even(5) is False"],
    },
    {
        "id": "t3",
        "prompt": "Write Python function factorial(n) for n>=0.",
        "fn": "factorial",
        "tests": ["factorial(0)==1", "factorial(5)==120"],
    },
    {
        "id": "t4",
        "prompt": "Write Python function reverse_string(s).",
        "fn": "reverse_string",
        "tests": ["reverse_string('abc')=='cba'", "reverse_string('')==''"],
    },
    {
        "id": "t5",
        "prompt": "Write Python function fibonacci(n) returning nth Fibonacci with fibonacci(0)=0,fibonacci(1)=1.",
        "fn": "fibonacci",
        "tests": ["fibonacci(0)==0", "fibonacci(7)==13"],
    },
    {
        "id": "t6",
        "prompt": "Write Python function count_vowels(s) counting a,e,i,o,u case-insensitive.",
        "fn": "count_vowels",
        "tests": ["count_vowels('Hello')==2", "count_vowels('xyz')==0"],
    },
    {
        "id": "t7",
        "prompt": "Write Python function is_palindrome(s) ignoring non-alnum and case.",
        "fn": "is_palindrome",
        "tests": ["is_palindrome('A man, a plan, a canal: Panama') is True", "is_palindrome('race a car') is False"],
    },
    {
        "id": "t8",
        "prompt": "Write Python function two_sum(nums,target) returning index pair [i,j] with i<j.",
        "fn": "two_sum",
        "tests": ["two_sum([2,7,11,15],9)==[0,1]", "two_sum([3,2,4],6)==[1,2]"],
    },
    {
        "id": "t9",
        "prompt": "Write Python function merge_sorted(a,b) merging two sorted lists.",
        "fn": "merge_sorted",
        "tests": ["merge_sorted([1,3,5],[2,4])==[1,2,3,4,5]", "merge_sorted([],[])==[]"],
    },
    {
        "id": "t10",
        "prompt": "Write Python function word_count(s) returning dict of lowercase word frequencies split by spaces.",
        "fn": "word_count",
        "tests": ["word_count('A a b')=={'a':2,'b':1}", "word_count('')=={}"],
    },
]


def _ask(llm: OpenAICompatibleClient, text: str) -> str:
    r = llm.completion(messages=[{"role": "user", "content": text}])
    return (r.choices[0].message.content or "").strip()


def _extract_code(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"```python\s*([\s\S]*?)```", text)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"```([\s\S]*?)```", text)
    if m2:
        return m2.group(1).strip()
    return text.strip()


def _extract_single_line(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return ""
    if "Final Code:" in s:
        s = s.split("Final Code:")[-1].strip()
    lines = [x.strip() for x in s.splitlines() if x.strip()]
    return lines[-1] if lines else s


def _run_tests(code: str, fn: str, tests: list[str]) -> tuple[bool, str]:
    ns = {}
    try:
        exec(code, ns, ns)
        if fn not in ns:
            return False, f"missing_function:{fn}"
        for t in tests:
            ok = eval(t, ns, ns)
            if not ok:
                return False, f"test_failed:{t}"
        return True, "ok"
    except Exception as e:
        return False, f"exec_error:{e}"


def _loop_off(llm: OpenAICompatibleClient, prompt: str) -> tuple[str, dict]:
    plan = _ask(llm, f"Plan coding in 2-4 concise steps. Prompt: {prompt}")
    code = _ask(
        llm,
        "Write Python code only. No explanation.\n"
        f"Plan:{plan}\nTask:{prompt}",
    )
    return _extract_code(code), {"plan": plan}


def _loop_on_gated(llm: OpenAICompatibleClient, prompt: str) -> tuple[str, dict]:
    plan = _ask(llm, f"Plan coding in JSON with critical_tasks, risks, tests_needed. Prompt: {prompt}")
    draft = _ask(
        llm,
        "Write Python code in markdown python block.\n"
        f"Plan:{plan}\nTask:{prompt}",
    )
    sup_raw = _ask(
        llm,
        "You are supervisor. Return STRICT JSON with fields: final_confidence(0-1), evidence_conflict(bool), revise_needed(bool), revised_code(single-line or python block). "
        "Only set revise_needed true if confidence is low and there is concrete conflict/bug evidence.\n"
        f"Task:{prompt}\nDraft:\n{draft}",
    )
    sj = {}
    try:
        sj = json.loads(re.search(r"\{[\s\S]*\}", sup_raw).group(0))
    except Exception:
        sj = {}
    final_conf = float(sj.get("final_confidence") or 0.0)
    evidence_conflict = bool(sj.get("evidence_conflict", False))
    revise_needed = bool(sj.get("revise_needed", False))
    allow = revise_needed and evidence_conflict and (final_conf < 0.72)
    revised_code = _extract_code(str(sj.get("revised_code") or ""))
    draft_code = _extract_code(draft)
    code = revised_code if (allow and revised_code) else draft_code
    return code, {"plan": plan, "supervisor": sj, "rewrite_allowed": allow}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="unsloth/qwen3-coder-next")
    parser.add_argument("--tag", type=str, default="v1_1_coding10_gatev2")
    args = parser.parse_args()

    cfg = load_config()
    cfg.providers[0].model = args.model
    llm = OpenAICompatibleClient.from_provider(providers=cfg.providers)

    rows = []
    for i, t in enumerate(TASKS, start=1):
        st = time.time()
        pure_raw = _ask(llm, f"Write Python code only for this task:\n{t['prompt']}")
        pure_code = _extract_code(pure_raw)
        pure_ok, pure_reason = _run_tests(pure_code, t["fn"], t["tests"])
        pure_t = time.time() - st

        st = time.time()
        off_code, off_obs = _loop_off(llm, t["prompt"])
        off_ok, off_reason = _run_tests(off_code, t["fn"], t["tests"])
        off_t = time.time() - st

        st = time.time()
        on_code, on_obs = _loop_on_gated(llm, t["prompt"])
        on_ok, on_reason = _run_tests(on_code, t["fn"], t["tests"])
        on_t = time.time() - st

        row = {
            "id": t["id"],
            "prompt": t["prompt"],
            "fn": t["fn"],
            "tests": t["tests"],
            "pure_ok": pure_ok,
            "loop_off_ok": off_ok,
            "loop_on_ok": on_ok,
            "pure_reason": pure_reason,
            "loop_off_reason": off_reason,
            "loop_on_reason": on_reason,
            "pure_t": round(pure_t, 3),
            "loop_off_t": round(off_t, 3),
            "loop_on_t": round(on_t, 3),
            "loop_off_obs": off_obs,
            "loop_on_obs": on_obs,
            "pure_code": pure_code,
            "loop_off_code": off_code,
            "loop_on_code": on_code,
        }
        rows.append(row)
        print(f"[{i}/10] {t['id']} pure={pure_ok} off={off_ok} on={on_ok} rewrite={bool((on_obs or {}).get('rewrite_allowed'))}")

    n = len(rows)
    summary = {
        "samples": n,
        "pure_acc": round(sum(1 for r in rows if r["pure_ok"]) / n, 4),
        "loop_off_acc": round(sum(1 for r in rows if r["loop_off_ok"]) / n, 4),
        "loop_on_acc": round(sum(1 for r in rows if r["loop_on_ok"]) / n, 4),
        "gain_loop_on_vs_pure": sum(1 for r in rows if (not r["pure_ok"]) and r["loop_on_ok"]),
        "gain_loop_on_vs_off": sum(1 for r in rows if (not r["loop_off_ok"]) and r["loop_on_ok"]),
        "regress_loop_on_vs_pure": sum(1 for r in rows if r["pure_ok"] and (not r["loop_on_ok"])),
        "rewrite_allowed_count": sum(1 for r in rows if bool((r.get("loop_on_obs") or {}).get("rewrite_allowed"))),
        "pure_avg_t": round(sum(r["pure_t"] for r in rows) / n, 3),
        "loop_off_avg_t": round(sum(r["loop_off_t"] for r in rows) / n, 3),
        "loop_on_avg_t": round(sum(r["loop_on_t"] for r in rows) / n, 3),
    }
    diagnosis = {
        "on_wrong_off_right": [r["id"] for r in rows if (not r["loop_on_ok"]) and r["loop_off_ok"]],
        "on_better_than_pure": [r["id"] for r in rows if (not r["pure_ok"]) and r["loop_on_ok"]],
        "on_worse_than_pure": [r["id"] for r in rows if r["pure_ok"] and (not r["loop_on_ok"])],
    }
    out = {
        "tag": args.tag,
        "model": args.model,
        "summary": summary,
        "diagnosis": diagnosis,
        "rows": rows,
        "ts": int(time.time()),
    }
    artifacts = Path("artifacts")
    artifacts.mkdir(parents=True, exist_ok=True)
    jf = artifacts / f"coding10_supervisor_{args.tag}.json"
    jf.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"file": str(jf), "summary": summary, "diagnosis": diagnosis}, ensure_ascii=False))


if __name__ == "__main__":
    main()
