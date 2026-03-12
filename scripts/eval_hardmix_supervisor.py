import argparse
import json
import re
import time
from pathlib import Path

from swarmbot.config_manager import load_config
from swarmbot.llm_client import OpenAICompatibleClient


QA_TASKS = [
    {
        "id": "qa1",
        "domain": "law",
        "context": "《平台交易法（节选）》第12条：经营者应在7日内回复消费者正式投诉。第25条：逾期未回复，每逾1日处以2000元罚款，上限30000元。某经营者逾期18日。",
        "question": "罚款金额是多少？仅输出数字。",
        "answer": "30000",
        "aliases": [],
    },
    {
        "id": "qa2",
        "domain": "law",
        "context": "《劳动合同细则》规定：试用期工资不得低于转正工资的80%，且不得低于当地最低工资。某员工转正工资12000元，当地最低工资2600元。",
        "question": "试用期最低合法工资是多少？仅输出数字。",
        "answer": "9600",
        "aliases": [],
    },
    {
        "id": "qa3",
        "domain": "law",
        "context": "《数据安全条例》：一般数据泄露需72小时内报告；涉及10万条以上个人记录的重大事件需24小时内报告。某公司泄露12万条记录，30小时后报告。",
        "question": "是否合规？输出 合规 或 不合规。",
        "answer": "不合规",
        "aliases": [],
    },
    {
        "id": "qa4",
        "domain": "law",
        "context": "《采购招标规则》：评分=价格分*40%+技术分*60%。供应商A价格分92，技术分80；供应商B价格分85，技术分88。",
        "question": "谁得分更高？仅输出 A 或 B。",
        "answer": "B",
        "aliases": [],
    },
    {
        "id": "qa5",
        "domain": "law",
        "context": "《广告合规指引》：使用“最高级”“第一”等绝对化用语需有第三方年度报告。某广告文案“行业第一”，仅有内部统计。",
        "question": "该文案是否合规？输出 合规 或 不合规。",
        "answer": "不合规",
        "aliases": [],
    },
    {
        "id": "qa6",
        "domain": "economy",
        "context": "某经济体名义GDP增长8%，CPI为3%。在近似条件下，实际GDP增速≈名义增速-CPI。",
        "question": "实际GDP增速约为多少？仅输出数字，单位%。",
        "answer": "5",
        "aliases": ["5%"],
    },
    {
        "id": "qa7",
        "domain": "economy",
        "context": "某债券票面1000元，年票息6%，每年付息一次。市场利率升至8%时，债券价格与票面关系通常如何变化？",
        "question": "输出 高于票面 或 低于票面。",
        "answer": "低于票面",
        "aliases": ["低于"],
    },
    {
        "id": "qa8",
        "domain": "economy",
        "context": "公司A收入同比+20%，成本同比+10%，基期收入100、成本70。",
        "question": "本期利润是多少？仅输出数字。",
        "answer": "50",
        "aliases": [],
    },
    {
        "id": "qa9",
        "domain": "economy",
        "context": "央行将存款准备金率下调，其他条件不变。",
        "question": "银行可贷资金通常增加还是减少？输出 增加 或 减少。",
        "answer": "增加",
        "aliases": [],
    },
    {
        "id": "qa10",
        "domain": "economy",
        "context": "某企业流动资产300，流动负债200，存货80。",
        "question": "速动比率是多少？仅输出数字。",
        "answer": "1.1",
        "aliases": ["1.10"],
    },
    {
        "id": "qa11",
        "domain": "law",
        "context": "《跨境数据规则》：向“白名单国家”传输一般个人信息仅需备案；向非白名单国家需安全评估。国家X不在白名单。",
        "question": "向国家X传输一般个人信息需要什么？输出 备案 或 安全评估。",
        "answer": "安全评估",
        "aliases": [],
    },
    {
        "id": "qa12",
        "domain": "economy",
        "context": "A国对B国产品加征关税，短期内进口成本上升。",
        "question": "若其他条件不变，A国该类进口量倾向于上升还是下降？输出 上升 或 下降。",
        "answer": "下降",
        "aliases": [],
    },
    {
        "id": "qa13",
        "domain": "law",
        "context": "《证据规则》：电子证据需满足真实性、完整性、关联性。某聊天记录截图无原始文件且可编辑。",
        "question": "真实性是否明显存疑？输出 是 或 否。",
        "answer": "是",
        "aliases": [],
    },
    {
        "id": "qa14",
        "domain": "economy",
        "context": "产品单价50，单位变动成本30，固定成本4000。",
        "question": "盈亏平衡销量是多少？仅输出数字。",
        "answer": "200",
        "aliases": [],
    },
    {
        "id": "qa15",
        "domain": "law",
        "context": "《消费者权益条款》：七天无理由退货不适用于定制商品。某商品为按用户尺寸定制。",
        "question": "七天无理由是否适用？输出 适用 或 不适用。",
        "answer": "不适用",
        "aliases": [],
    },
    {
        "id": "qa16",
        "domain": "economy",
        "context": "某国出口1000，进口1200。",
        "question": "贸易差额是多少（出口-进口）？仅输出数字，可为负。",
        "answer": "-200",
        "aliases": [],
    },
    {
        "id": "qa17",
        "domain": "law",
        "context": "《反洗钱细则》：单笔现金交易≥5万元需报送大额交易报告。某交易为4.9万元。",
        "question": "是否触发该报送门槛？输出 触发 或 不触发。",
        "answer": "不触发",
        "aliases": [],
    },
    {
        "id": "qa18",
        "domain": "economy",
        "context": "某项目初始投资100，未来两年现金流分别为60和60，不考虑贴现。",
        "question": "静态回收期是否小于2年？输出 是 或 否。",
        "answer": "是",
        "aliases": [],
    },
    {
        "id": "qa19",
        "domain": "law",
        "context": "《合同解释规则》：格式条款有两种以上解释时，应作出不利于提供方的解释。争议条款由卖方提供。",
        "question": "解释倾向应不利于哪一方？输出 卖方 或 买方。",
        "answer": "卖方",
        "aliases": [],
    },
    {
        "id": "qa20",
        "domain": "economy",
        "context": "某公司税前利润500，所得税税率25%。",
        "question": "税后利润是多少？仅输出数字。",
        "answer": "375",
        "aliases": [],
    },
]


CODING_TASKS = [
    {"id": "c1", "prompt": "Write Python function longest_unique_substring_len(s).", "fn": "longest_unique_substring_len", "tests": ["longest_unique_substring_len('abcabcbb')==3", "longest_unique_substring_len('bbbbb')==1", "longest_unique_substring_len('pwwkew')==3"]},
    {"id": "c2", "prompt": "Write Python function min_window_len(nums, target) for shortest contiguous subarray sum >= target, return 0 if none.", "fn": "min_window_len", "tests": ["min_window_len([2,3,1,2,4,3],7)==2", "min_window_len([1,1,1,1],5)==0"]},
    {"id": "c3", "prompt": "Write Python function top_k_frequent(nums,k) returning list of k most frequent numbers sorted by frequency desc then value asc.", "fn": "top_k_frequent", "tests": ["top_k_frequent([1,1,1,2,2,3],2)==[1,2]", "top_k_frequent([4,4,1,1,2,2],2)==[1,2]"]},
    {"id": "c4", "prompt": "Write Python function decode_rle(s) where pattern number[chars], nested not required, e.g. '3[a]2[bc]'->'aaabcbc'.", "fn": "decode_rle", "tests": ["decode_rle('3[a]2[bc]')=='aaabcbc'", "decode_rle('1[z]10[a]')=='zaaaaaaaaaa'"]},
    {"id": "c5", "prompt": "Write Python function interval_merge(intervals) merging overlaps and returning sorted intervals.", "fn": "interval_merge", "tests": ["interval_merge([[1,3],[2,6],[8,10],[15,18]])==[[1,6],[8,10],[15,18]]", "interval_merge([[1,4],[4,5]])==[[1,5]]"]},
    {"id": "c6", "prompt": "Write Python function matrix_spiral_order(mat) returning spiral traversal.", "fn": "matrix_spiral_order", "tests": ["matrix_spiral_order([[1,2,3],[4,5,6],[7,8,9]])==[1,2,3,6,9,8,7,4,5]", "matrix_spiral_order([[1],[2],[3]])==[1,2,3]"]},
    {"id": "c7", "prompt": "Write Python function valid_parentheses(s) supporting ()[]{}.", "fn": "valid_parentheses", "tests": ["valid_parentheses('()[]{}') is True", "valid_parentheses('(]') is False", "valid_parentheses('([{}])') is True"]},
    {"id": "c8", "prompt": "Write Python function coin_change_min(coins, amount) returning minimum coins or -1.", "fn": "coin_change_min", "tests": ["coin_change_min([1,2,5],11)==3", "coin_change_min([2],3)==-1"]},
    {"id": "c9", "prompt": "Write Python function group_anagrams(words) returning list of groups, each group sorted; overall groups sorted by first element.", "fn": "group_anagrams", "tests": ["group_anagrams(['eat','tea','tan','ate','nat','bat'])==[['ate','eat','tea'],['bat'],['nat','tan']]", "group_anagrams([])==[]"]},
    {"id": "c10", "prompt": "Write Python function kth_largest(nums,k).", "fn": "kth_largest", "tests": ["kth_largest([3,2,1,5,6,4],2)==5", "kth_largest([3,2,3,1,2,4,5,5,6],4)==4"]},
]


def _norm_text(s: str) -> str:
    t = (s or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^\w\s\-\.\%]", "", t)
    return t


def _qa_ok(pred: str, ans: str, aliases: list[str]) -> bool:
    p = _norm_text(pred)
    a = _norm_text(ans)
    if not p or not a:
        return False
    if a in p:
        return True
    for x in aliases or []:
        xx = _norm_text(str(x))
        if xx and xx in p:
            return True
    return False


def _extract_code(text: str) -> str:
    s = (text or "").strip()
    m = re.search(r"```python\s*([\s\S]*?)```", s)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"```([\s\S]*?)```", s)
    if m2:
        return m2.group(1).strip()
    return s


def _extract_single_line(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return ""
    for tag in ["Final Answer:", "FINAL ANSWER:", "答案:", "答案：", "Answer:"]:
        if tag in s:
            tail = s.split(tag)[-1].strip()
            return tail.splitlines()[0].strip() if tail else ""
    lines = [x.strip() for x in s.splitlines() if x.strip()]
    if not lines:
        return s
    v = lines[-1]
    if len(v) > 220:
        v = v[:220].strip()
    return v


def _ask(llm: OpenAICompatibleClient, prompt: str) -> str:
    r = llm.completion(messages=[{"role": "user", "content": prompt}])
    return (r.choices[0].message.content or "").strip()


def _json_obj(text: str) -> dict:
    m = re.search(r"\{[\s\S]*\}", text or "")
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


def _run_code_tests(code: str, fn: str, tests: list[str]) -> tuple[bool, str]:
    ns = {}
    try:
        exec(code, ns, ns)
        if fn not in ns:
            return False, f"missing_function:{fn}"
        for t in tests:
            if not eval(t, ns, ns):
                return False, f"test_failed:{t}"
        return True, "ok"
    except Exception as e:
        return False, f"exec_error:{e}"


def _qa_pure(llm: OpenAICompatibleClient, context: str, question: str) -> tuple[str, float]:
    st = time.time()
    out = _ask(llm, f"请基于给定材料回答，输出一行最终答案。\n材料：{context}\n问题：{question}")
    return _extract_single_line(out), time.time() - st


def _qa_loop_off(llm: OpenAICompatibleClient, context: str, question: str) -> tuple[str, float, dict]:
    st = time.time()
    plan = _ask(llm, f"你是推理规划器。请给出2-4步计划。\n材料：{context}\n问题：{question}")
    ans = _ask(llm, f"你是执行器。依据计划回答，只输出最终一行答案。\n计划：{plan}\n材料：{context}\n问题：{question}")
    return _extract_single_line(ans), time.time() - st, {"plan": plan}


def _qa_loop_on(llm: OpenAICompatibleClient, context: str, question: str) -> tuple[str, float, dict]:
    st = time.time()
    plan = _ask(llm, f"你是规划器。输出JSON字段：critical_tasks,key_entities,required_evidence。\n材料：{context}\n问题：{question}")
    draft = _ask(llm, f"你是执行器。先简短推理，再给'Final Answer:'单行答案。\n计划：{plan}\n材料：{context}\n问题：{question}")
    sup_raw = _ask(
        llm,
        "你是Supervisor。返回严格JSON字段：final_confidence(0-1),evidence_conflict(bool),revise_needed(bool),revised_answer_line(单行)。"
        "仅在低置信且证据冲突时建议改写。\n"
        f"材料：{context}\n问题：{question}\n草稿：{draft}",
    )
    sj = _json_obj(sup_raw)
    conf = float(sj.get("final_confidence") or 0.0)
    conflict = bool(sj.get("evidence_conflict", False))
    revise = bool(sj.get("revise_needed", False))
    allow = revise and conflict and conf < 0.72
    revised = _extract_single_line(str(sj.get("revised_answer_line") or ""))
    draft_line = _extract_single_line(draft)
    final = revised if (allow and revised) else draft_line
    return final, time.time() - st, {"plan": plan, "supervisor": sj, "rewrite_allowed": allow, "final_answer_line": final}


def _code_pure(llm: OpenAICompatibleClient, prompt: str) -> tuple[str, float]:
    st = time.time()
    out = _ask(llm, f"Write Python code only. Task: {prompt}")
    return _extract_code(out), time.time() - st


def _code_loop_off(llm: OpenAICompatibleClient, prompt: str) -> tuple[str, float, dict]:
    st = time.time()
    plan = _ask(llm, f"Plan coding in 2-4 concise steps. Task:{prompt}")
    out = _ask(llm, f"Write Python code only.\nPlan:{plan}\nTask:{prompt}")
    return _extract_code(out), time.time() - st, {"plan": plan}


def _code_loop_on(llm: OpenAICompatibleClient, prompt: str) -> tuple[str, float, dict]:
    st = time.time()
    plan = _ask(llm, f"Plan coding in JSON fields critical_tasks, risks, tests_needed. Task:{prompt}")
    draft = _ask(llm, f"Write Python code in markdown python block.\nPlan:{plan}\nTask:{prompt}")
    sup_raw = _ask(
        llm,
        "You are supervisor. Return STRICT JSON with final_confidence(0-1), evidence_conflict(bool), revise_needed(bool), revised_code."
        "Only revise when low confidence and concrete conflict.\n"
        f"Task:{prompt}\nDraft:{draft}",
    )
    sj = _json_obj(sup_raw)
    conf = float(sj.get("final_confidence") or 0.0)
    conflict = bool(sj.get("evidence_conflict", False))
    revise = bool(sj.get("revise_needed", False))
    allow = revise and conflict and conf < 0.72
    revised = _extract_code(str(sj.get("revised_code") or ""))
    draft_code = _extract_code(draft)
    code = revised if (allow and revised) else draft_code
    return code, time.time() - st, {"plan": plan, "supervisor": sj, "rewrite_allowed": allow}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="unsloth/qwen3-coder-next")
    parser.add_argument("--tag", type=str, default="v1_1_hardmix30_gatev2")
    args = parser.parse_args()

    cfg = load_config()
    cfg.providers[0].model = args.model
    llm = OpenAICompatibleClient.from_provider(providers=cfg.providers)

    rows = []
    for i, t in enumerate(QA_TASKS, start=1):
        pure, tp = _qa_pure(llm, t["context"], t["question"])
        off, to, oobs = _qa_loop_off(llm, t["context"], t["question"])
        on, tn, nobs = _qa_loop_on(llm, t["context"], t["question"])
        row = {
            "id": t["id"],
            "type": "qa",
            "domain": t["domain"],
            "question": t["question"],
            "context": t["context"],
            "truth": t["answer"],
            "aliases": t["aliases"],
            "pure": pure,
            "loop_off": off,
            "loop_on": on,
            "pure_ok": _qa_ok(pure, t["answer"], t["aliases"]),
            "loop_off_ok": _qa_ok(off, t["answer"], t["aliases"]),
            "loop_on_ok": _qa_ok(on, t["answer"], t["aliases"]),
            "pure_t": round(tp, 3),
            "loop_off_t": round(to, 3),
            "loop_on_t": round(tn, 3),
            "loop_off_obs": oobs,
            "loop_on_obs": nobs,
        }
        rows.append(row)
        print(f"[qa {i}/{len(QA_TASKS)}] {t['id']} pure={row['pure_ok']} off={row['loop_off_ok']} on={row['loop_on_ok']}")

    for i, t in enumerate(CODING_TASKS, start=1):
        pure_code, tp = _code_pure(llm, t["prompt"])
        off_code, to, oobs = _code_loop_off(llm, t["prompt"])
        on_code, tn, nobs = _code_loop_on(llm, t["prompt"])
        pure_ok, pure_reason = _run_code_tests(pure_code, t["fn"], t["tests"])
        off_ok, off_reason = _run_code_tests(off_code, t["fn"], t["tests"])
        on_ok, on_reason = _run_code_tests(on_code, t["fn"], t["tests"])
        row = {
            "id": t["id"],
            "type": "coding",
            "prompt": t["prompt"],
            "fn": t["fn"],
            "tests": t["tests"],
            "pure_ok": pure_ok,
            "loop_off_ok": off_ok,
            "loop_on_ok": on_ok,
            "pure_reason": pure_reason,
            "loop_off_reason": off_reason,
            "loop_on_reason": on_reason,
            "pure_t": round(tp, 3),
            "loop_off_t": round(to, 3),
            "loop_on_t": round(tn, 3),
            "loop_off_obs": oobs,
            "loop_on_obs": nobs,
            "pure_code": pure_code,
            "loop_off_code": off_code,
            "loop_on_code": on_code,
        }
        rows.append(row)
        print(f"[code {i}/{len(CODING_TASKS)}] {t['id']} pure={pure_ok} off={off_ok} on={on_ok}")

    n = len(rows)
    qa_rows = [r for r in rows if r["type"] == "qa"]
    code_rows = [r for r in rows if r["type"] == "coding"]
    summary = {
        "samples": n,
        "qa_samples": len(qa_rows),
        "coding_samples": len(code_rows),
        "pure_acc": round(sum(1 for r in rows if r["pure_ok"]) / n, 4),
        "loop_off_acc": round(sum(1 for r in rows if r["loop_off_ok"]) / n, 4),
        "loop_on_acc": round(sum(1 for r in rows if r["loop_on_ok"]) / n, 4),
        "qa_pure_acc": round(sum(1 for r in qa_rows if r["pure_ok"]) / max(1, len(qa_rows)), 4),
        "qa_loop_off_acc": round(sum(1 for r in qa_rows if r["loop_off_ok"]) / max(1, len(qa_rows)), 4),
        "qa_loop_on_acc": round(sum(1 for r in qa_rows if r["loop_on_ok"]) / max(1, len(qa_rows)), 4),
        "coding_pure_acc": round(sum(1 for r in code_rows if r["pure_ok"]) / max(1, len(code_rows)), 4),
        "coding_loop_off_acc": round(sum(1 for r in code_rows if r["loop_off_ok"]) / max(1, len(code_rows)), 4),
        "coding_loop_on_acc": round(sum(1 for r in code_rows if r["loop_on_ok"]) / max(1, len(code_rows)), 4),
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
    jf = artifacts / f"hardmix_supervisor_{args.tag}.json"
    jl = artifacts / f"hardmix_supervisor_{args.tag}.jsonl"
    jf.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    with jl.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({"file": str(jf), "summary": summary, "diagnosis": diagnosis}, ensure_ascii=False))


if __name__ == "__main__":
    main()
