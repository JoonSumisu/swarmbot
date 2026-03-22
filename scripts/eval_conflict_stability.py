import argparse
import json
import random
import re
import statistics
import time
from pathlib import Path

from swarmbot.config_manager import load_config
from swarmbot.llm_client import OpenAICompatibleClient


TASKS = [
    {"id": "s1", "context": "规则A(2022)：违约金=合同额12%。规则B(2024)：违约金=合同额9%，但高风险项目再上浮2个百分点。原则：后法优先。项目为高风险，合同额260万。", "answer": "28.6"},
    {"id": "s2", "context": "一般条款：处理期10天。特别条款：跨境纠纷处理期6天。紧急条款：若金额>100万，处理期再缩短2天。案件跨境且金额150万。", "answer": "4"},
    {"id": "s3", "context": "税率规则：基础税率20%。若研发占比>=8%降至16%。若绿色认证通过再降1个百分点。企业研发占比9%，绿色认证通过，利润500。", "answer": "75"},
    {"id": "s4", "context": "预算规则V1：营销费率上限14%。V2：新品首季上限18%。补充：若毛利率<20%，在V2基础上再下调3个百分点。当前新品首季，毛利率18%，收入1200万。", "answer": "180"},
    {"id": "s5", "context": "债券定价规则：票息<市场利率则折价；票息>市场利率则溢价。债券X票息4%，市场利率6%；债券Y票息7%，市场利率6%。", "answer": "Y"},
    {"id": "s6", "context": "数据保留：总则180天。交易数据特别规则365天。支付争议数据再增加90天。当前为交易且支付争议数据。", "answer": "455"},
    {"id": "s7", "context": "罚款规则：逾期每日1800元。若连续逾期超过10天，从第11天起按每日2500元。总上限32000元。某企业逾期16天。", "answer": "28800"},
    {"id": "s8", "context": "经济规则：实际增速精确公式=(1+名义)/(1+通胀)-1。名义增速15%，通胀6%。", "answer": "8.5"},
    {"id": "s9", "context": "盈亏平衡：单价80，变动成本52，固定成本5600。若渠道费每件再增加3元，则新的单位贡献=单价-变动成本-渠道费。", "answer": "224"},
    {"id": "s10", "context": "程序规则：先调解后仲裁。例外1：金额<500可直接仲裁。例外2：若涉及人身安全，无论金额均可直接仲裁。案件金额800，涉及人身安全。", "answer": "可以"},
]

QUESTION_TEMPLATES = [
    "基于材料计算最终结果。仅输出单行答案：{context}",
    "请按冲突规则和优先级给出最终值，只输出一行：{context}",
    "阅读后按最新/特别/例外规则求解，单行作答：{context}",
]


def _ask(llm: OpenAICompatibleClient, prompt: str) -> str:
    r = llm.completion(messages=[{"role": "user", "content": prompt}])
    return (r.choices[0].message.content or "").strip()


def _line(s: str) -> str:
    t = (s or "").strip()
    if not t:
        return ""
    for k in ["Final Answer:", "答案：", "答案:", "Answer:"]:
        if k in t:
            tail = t.split(k)[-1].strip()
            if tail:
                return tail.splitlines()[0].strip()
    lines = [x.strip() for x in t.splitlines() if x.strip()]
    return lines[-1] if lines else t


def _norm(x: str) -> str:
    v = (x or "").strip().lower()
    v = re.sub(r"\s+", "", v)
    v = re.sub(r"[^\w\.\-\%]", "", v)
    return v


def _ok(pred: str, ans: str) -> bool:
    p = _norm(pred)
    a = _norm(ans)
    if not p or not a:
        return False
    if a in p:
        return True
    try:
        pv = float(re.sub(r"%", "", p))
        av = float(re.sub(r"%", "", a))
        return abs(pv - av) <= 0.2
    except Exception:
        return False


def _json_obj(text: str) -> dict:
    m = re.search(r"\{[\s\S]*\}", text or "")
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


def run_one(llm: OpenAICompatibleClient, context: str, question: str):
    st = time.time()
    pure = _line(_ask(llm, f"你是求解器。{question}\n只输出单行最终答案。"))
    tp = time.time() - st

    st = time.time()
    plan_off = _ask(llm, f"你是分析器，给2-4步推理计划。\n题目：{question}")
    off = _line(_ask(llm, f"你是执行器，按计划求解，仅输出单行最终答案。\n计划：{plan_off}\n题目：{question}"))
    to = time.time() - st

    st = time.time()
    plan_on = _ask(llm, f"你是规划器，输出JSON字段critical_tasks,key_entities,conflict_points,required_evidence。\n题目：{question}")
    draft = _ask(llm, f"你是快速执行器，给简短推理后输出Final Answer单行。\n计划：{plan_on}\n题目：{question}")
    sup_raw = _ask(
        llm,
        "你是Supervisor。返回严格JSON：final_confidence(0-1),evidence_conflict(bool),revise_needed(bool),revised_answer_line(单行)。"
        "仅在低置信且证据冲突时改写。\n"
        f"题目：{question}\n草稿：{draft}",
    )
    sj = _json_obj(sup_raw)
    conf = float(sj.get("final_confidence") or 0.0)
    conflict = bool(sj.get("evidence_conflict", False))
    revise = bool(sj.get("revise_needed", False))
    allow = revise and conflict and conf < 0.72
    revised = _line(str(sj.get("revised_answer_line") or ""))
    draft_line = _line(draft)
    on = revised if (allow and revised) else draft_line
    tn = time.time() - st

    return {
        "pure": pure,
        "loop_off": off,
        "loop_on": on,
        "pure_t": round(tp, 3),
        "loop_off_t": round(to, 3),
        "loop_on_t": round(tn, 3),
        "loop_off_obs": {"plan": plan_off},
        "loop_on_obs": {"plan": plan_on, "supervisor": sj, "rewrite_allowed": allow, "final_answer_line": on},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="unsloth/qwen3-coder-next")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260314)
    parser.add_argument("--tag", type=str, default="v1_1_conflict_stability_r3")
    args = parser.parse_args()

    cfg = load_config()
    cfg.providers[0].model = args.model
    llm = OpenAICompatibleClient.from_provider(providers=cfg.providers)

    rng = random.Random(args.seed)
    round_summaries = []
    rows = []

    for r in range(1, args.rounds + 1):
        order = TASKS[:]
        rng.shuffle(order)
        pure_hits = 0
        off_hits = 0
        on_hits = 0
        for i, t in enumerate(order, start=1):
            q = rng.choice(QUESTION_TEMPLATES).format(context=t["context"])
            res = run_one(llm, t["context"], q)
            pure_ok = _ok(res["pure"], t["answer"])
            off_ok = _ok(res["loop_off"], t["answer"])
            on_ok = _ok(res["loop_on"], t["answer"])
            pure_hits += 1 if pure_ok else 0
            off_hits += 1 if off_ok else 0
            on_hits += 1 if on_ok else 0
            row = {
                "round": r,
                "id": t["id"],
                "context": t["context"],
                "question": q,
                "truth": t["answer"],
                "pure_ok": pure_ok,
                "loop_off_ok": off_ok,
                "loop_on_ok": on_ok,
            }
            row.update(res)
            rows.append(row)
            print(f"[r{r} {i}/{len(order)}] {t['id']} pure={pure_ok} off={off_ok} on={on_ok}")
        n = len(order)
        round_summary = {
            "round": r,
            "samples": n,
            "pure_acc": round(pure_hits / n, 4),
            "loop_off_acc": round(off_hits / n, 4),
            "loop_on_acc": round(on_hits / n, 4),
        }
        round_summaries.append(round_summary)

    pure_list = [x["pure_acc"] for x in round_summaries]
    off_list = [x["loop_off_acc"] for x in round_summaries]
    on_list = [x["loop_on_acc"] for x in round_summaries]
    summary = {
        "rounds": args.rounds,
        "samples_per_round": len(TASKS),
        "pure_acc_mean": round(statistics.mean(pure_list), 4),
        "loop_off_acc_mean": round(statistics.mean(off_list), 4),
        "loop_on_acc_mean": round(statistics.mean(on_list), 4),
        "pure_acc_std": round(statistics.pstdev(pure_list), 4),
        "loop_off_acc_std": round(statistics.pstdev(off_list), 4),
        "loop_on_acc_std": round(statistics.pstdev(on_list), 4),
        "loop_on_better_than_off_rounds": sum(1 for x in round_summaries if x["loop_on_acc"] > x["loop_off_acc"]),
        "loop_on_better_than_pure_rounds": sum(1 for x in round_summaries if x["loop_on_acc"] > x["pure_acc"]),
        "rewrite_allowed_count": sum(1 for r in rows if bool((r.get("loop_on_obs") or {}).get("rewrite_allowed"))),
    }
    out = {
        "tag": args.tag,
        "model": args.model,
        "seed": args.seed,
        "summary": summary,
        "round_summaries": round_summaries,
        "rows": rows,
        "ts": int(time.time()),
    }
    artifacts = Path("artifacts")
    artifacts.mkdir(parents=True, exist_ok=True)
    jf = artifacts / f"conflict_stability_{args.tag}.json"
    jl = artifacts / f"conflict_stability_{args.tag}.jsonl"
    jf.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    with jl.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({"file": str(jf), "summary": summary, "round_summaries": round_summaries}, ensure_ascii=False))


if __name__ == "__main__":
    main()
