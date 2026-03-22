import argparse
import json
import re
import time
from pathlib import Path

from swarmbot.config_manager import load_config
from swarmbot.llm_client import OpenAICompatibleClient


TASKS = [
    {"id": "l1", "domain": "law", "context": "规则V1：退款期7天。规则V2（后发布）：退款期14天。适用原则：同层级规范后法优于前法。", "question": "当前退款期是多少天？仅输出数字。", "answer": "14"},
    {"id": "l2", "domain": "law", "context": "总则：平台纠纷处理时限10天。特别条款：涉及医疗商品纠纷处理时限3天。原则：特别法优于一般法。案件为医疗商品纠纷。", "question": "处理时限是多少天？仅输出数字。", "answer": "3"},
    {"id": "l3", "domain": "law", "context": "旧规：合同违约金上限为标的额20%。新规：上限15%。原则：后法优先。标的额100万。", "question": "违约金上限是多少万？仅输出数字。", "answer": "15"},
    {"id": "l4", "domain": "law", "context": "主规则：投诉需实名。补充条款：未成年人可由监护人代实名。案例：投诉人13岁，监护人已实名。", "question": "该投诉是否可受理？输出 可受理 或 不可受理。", "answer": "可受理"},
    {"id": "l5", "domain": "law", "context": "A条：广告不得使用“最”字。B条：有国家级检测报告可使用。案件：使用“最佳”，仅有企业内部报告。", "question": "是否合规？输出 合规 或 不合规。", "answer": "不合规"},
    {"id": "l6", "domain": "law", "context": "旧条：数据保留180天。新条：交易数据保留365天。原则：后法优于前法。该数据为交易数据。", "question": "最低保留天数？仅输出数字。", "answer": "365"},
    {"id": "l7", "domain": "law", "context": "一般处罚：逾期备案每日1000元。上位条款：同一违法行为总罚款上限8000元。逾期10天。", "question": "总罚款金额？仅输出数字。", "answer": "8000"},
    {"id": "l8", "domain": "law", "context": "程序条款：先调解后诉讼。例外：金额低于500元可直接诉讼。案件金额300元。", "question": "可否直接诉讼？输出 可以 或 不可以。", "answer": "可以"},
    {"id": "l9", "domain": "law", "context": "总规则：证据需原件。电子证据特别规则：有完整哈希链可视同原件。案件电子证据有完整哈希链。", "question": "该证据是否满足形式要求？输出 满足 或 不满足。", "answer": "满足"},
    {"id": "l10", "domain": "law", "context": "先前口径：个人信息跨境需审批。更新口径：向白名单国家仅备案。国家X在白名单。", "question": "向国家X传输个人信息需要什么？输出 审批 或 备案。", "answer": "备案"},
    {"id": "e1", "domain": "economy", "context": "旧口径：实际增速=名义增速-CPI。修正口径：当增速较高时，实际增速≈(1+名义)/(1+CPI)-1。名义20%，CPI10%。", "question": "按修正口径，实际增速约多少（%）？四舍五入到1位小数，仅输出数字。", "answer": "9.1"},
    {"id": "e2", "domain": "economy", "context": "规则A：毛利=收入-变动成本。规则B：经营利润=毛利-固定成本。收入500，变动成本260，固定成本90。", "question": "经营利润是多少？仅输出数字。", "answer": "150"},
    {"id": "e3", "domain": "economy", "context": "政策冲突：A文件建议加息抑制通胀；B文件（后发布）要求优先稳增长并降息。原则：后政策优先。", "question": "当前利率方向应是加息还是降息？输出 加息 或 降息。", "answer": "降息"},
    {"id": "e4", "domain": "economy", "context": "需求弹性定义：|Ed|>1为富有弹性。某商品价格上升10%，需求量下降25%。", "question": "该商品需求是否富有弹性？输出 是 或 否。", "answer": "是"},
    {"id": "e5", "domain": "economy", "context": "债券A票息3%，市场利率5%。债券B票息8%，市场利率5%。", "question": "哪只债券价格高于票面？输出 A 或 B。", "answer": "B"},
    {"id": "e6", "domain": "economy", "context": "A模型：汇率上升（本币贬值）有利出口。B修正规则：若出口品进口中间品占比极高，短期出口可能下降。该行业进口中间品占比70%。", "question": "短期出口更可能上升还是下降？输出 上升 或 下降。", "answer": "下降"},
    {"id": "e7", "domain": "economy", "context": "企业现金流：经营+120，投资-200，融资+100。", "question": "净现金流是多少？仅输出数字。", "answer": "20"},
    {"id": "e8", "domain": "economy", "context": "一般规则：库存周转天数=365/周转率。某企业周转率5次。", "question": "库存周转天数约多少天？四舍五入到整数，仅输出数字。", "answer": "73"},
    {"id": "e9", "domain": "economy", "context": "旧预算：营销费用率上限12%。新预算：若新品上市期可提高到18%。当前处于新品上市期。收入1000万。", "question": "营销费用上限是多少万？仅输出数字。", "answer": "180"},
    {"id": "e10", "domain": "economy", "context": "税则：基础税率20%。优惠条款：研发投入占比≥10%可降至15%。企业研发占比12%，利润200。", "question": "应纳所得税是多少？仅输出数字。", "answer": "30"},
]


def _ask(llm: OpenAICompatibleClient, prompt: str) -> str:
    r = llm.completion(messages=[{"role": "user", "content": prompt}])
    return (r.choices[0].message.content or "").strip()


def _norm(s: str) -> str:
    t = (s or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^\w\.\-\%]", "", t)
    return t


def _ok(pred: str, ans: str) -> bool:
    return _norm(ans) in _norm(pred)


def _line(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return s
    for k in ["Final Answer:", "答案：", "答案:", "Answer:"]:
        if k in s:
            tail = s.split(k)[-1].strip()
            if tail:
                return tail.splitlines()[0].strip()
    lines = [x.strip() for x in s.splitlines() if x.strip()]
    return lines[-1] if lines else s


def _json(text: str) -> dict:
    m = re.search(r"\{[\s\S]*\}", text or "")
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


def run_pure(llm: OpenAICompatibleClient, context: str, question: str) -> tuple[str, float]:
    st = time.time()
    ans = _ask(llm, f"请基于材料回答，只输出一行最终答案。\n材料：{context}\n问题：{question}")
    return _line(ans), time.time() - st


def run_off(llm: OpenAICompatibleClient, context: str, question: str) -> tuple[str, float, dict]:
    st = time.time()
    plan = _ask(llm, f"你是分析器。给出2-4步推理计划。\n材料：{context}\n问题：{question}")
    ans = _ask(llm, f"你是执行器。按计划回答，只输出最终单行答案。\n计划：{plan}\n材料：{context}\n问题：{question}")
    return _line(ans), time.time() - st, {"plan": plan}


def run_on(llm: OpenAICompatibleClient, context: str, question: str) -> tuple[str, float, dict]:
    st = time.time()
    plan = _ask(llm, f"你是规划器。输出JSON字段 critical_tasks,key_entities,conflict_points,required_evidence。\n材料：{context}\n问题：{question}")
    draft = _ask(llm, f"你是快速执行器。给出简短推理并给Final Answer单行答案。\n计划：{plan}\n材料：{context}\n问题：{question}")
    sup_raw = _ask(
        llm,
        "你是Supervisor。返回严格JSON：final_confidence(0-1),evidence_conflict(bool),revise_needed(bool),revised_answer_line(单行)。"
        "只有在低置信且证据冲突时才建议改写。\n"
        f"材料：{context}\n问题：{question}\n草稿：{draft}",
    )
    sj = _json(sup_raw)
    conf = float(sj.get("final_confidence") or 0.0)
    conflict = bool(sj.get("evidence_conflict", False))
    revise = bool(sj.get("revise_needed", False))
    allow = revise and conflict and conf < 0.72
    revised = _line(str(sj.get("revised_answer_line") or ""))
    draft_line = _line(draft)
    final = revised if (allow and revised) else draft_line
    return final, time.time() - st, {"plan": plan, "supervisor": sj, "rewrite_allowed": allow, "final_answer_line": final}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="unsloth/qwen3-coder-next")
    parser.add_argument("--tag", type=str, default="v1_1_conflict20_gatev2")
    args = parser.parse_args()

    cfg = load_config()
    cfg.providers[0].model = args.model
    llm = OpenAICompatibleClient.from_provider(providers=cfg.providers)

    rows = []
    for i, t in enumerate(TASKS, start=1):
        pure, tp = run_pure(llm, t["context"], t["question"])
        off, to, oobs = run_off(llm, t["context"], t["question"])
        on, tn, nobs = run_on(llm, t["context"], t["question"])
        row = {
            "id": t["id"],
            "domain": t["domain"],
            "context": t["context"],
            "question": t["question"],
            "truth": t["answer"],
            "pure": pure,
            "loop_off": off,
            "loop_on": on,
            "pure_ok": _ok(pure, t["answer"]),
            "loop_off_ok": _ok(off, t["answer"]),
            "loop_on_ok": _ok(on, t["answer"]),
            "pure_t": round(tp, 3),
            "loop_off_t": round(to, 3),
            "loop_on_t": round(tn, 3),
            "loop_off_obs": oobs,
            "loop_on_obs": nobs,
        }
        rows.append(row)
        print(f"[{i}/{len(TASKS)}] {t['id']} pure={row['pure_ok']} off={row['loop_off_ok']} on={row['loop_on_ok']} rewrite={bool((nobs or {}).get('rewrite_allowed'))}")

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
        "on_wrong_off_right_ids": [r["id"] for r in rows if (not r["loop_on_ok"]) and r["loop_off_ok"]],
        "on_better_than_pure_ids": [r["id"] for r in rows if (not r["pure_ok"]) and r["loop_on_ok"]],
        "on_worse_than_pure_ids": [r["id"] for r in rows if r["pure_ok"] and (not r["loop_on_ok"])],
    }
    out = {"tag": args.tag, "model": args.model, "summary": summary, "diagnosis": diagnosis, "rows": rows, "ts": int(time.time())}
    artifacts = Path("artifacts")
    artifacts.mkdir(parents=True, exist_ok=True)
    jf = artifacts / f"conflict_supervisor_{args.tag}.json"
    jl = artifacts / f"conflict_supervisor_{args.tag}.jsonl"
    jf.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    with jl.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({"file": str(jf), "summary": summary, "diagnosis": diagnosis}, ensure_ascii=False))


if __name__ == "__main__":
    main()
