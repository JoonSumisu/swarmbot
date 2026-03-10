from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from swarmbot.config_manager import WORKSPACE_PATH, load_config
from swarmbot.loops.inference import InferenceLoop

CASES = [
    {"id": "s1", "kind": "simple_direct_master", "q": "今天下雨我有点烦，能安慰我一句吗？"},
    {"id": "s2", "kind": "simple_direct_master", "q": "帮我把这句话说得更礼貌：你这个排期不合理。"},
    {"id": "s3", "kind": "simple_direct_master", "q": "晚饭吃啥比较清淡？"},
    {"id": "s4", "kind": "simple_direct_master", "q": "我刚开完会有点乱，先跟我说一句稳住心态的话。"},
    {"id": "s5", "kind": "simple_direct_master", "q": "帮我写一句请假消息给同事。"},
    {"id": "r1", "kind": "reasoning_swarm", "q": "我有点焦虑，先安抚我，再给我今晚三件事的优先级方案。"},
    {"id": "r2", "kind": "reasoning_swarm", "q": "用心理学角度解释我总拖延，并给我一个一周改进计划。"},
    {"id": "r3", "kind": "reasoning_swarm", "q": "帮我修改 boot 提示词语气更自然，给出可直接替换版本。"},
    {"id": "r4", "kind": "reasoning_swarm", "q": "写一个简单脚本，把今天日志里 ERROR 行提取到新文件。"},
    {"id": "r5", "kind": "reasoning_swarm", "q": "哲学上怎么理解‘控制感’，并给出工作中的实践建议。"},
    {"id": "e1", "kind": "engineering_complex", "q": "线上网关偶发超时，涉及重试策略、并发与日志采样，给我完整排障与改造方案。"},
    {"id": "e2", "kind": "engineering_complex", "q": "我要重构三环调度，拆模块并保证兼容，给出分阶段工程实施方案。"},
    {"id": "e3", "kind": "engineering_complex", "q": "这个仓库要加多租户权限隔离、审计日志、回滚策略，给我可执行工程设计。"},
    {"id": "e4", "kind": "engineering_complex", "q": "修复一个跨文件循环依赖并补充测试，要求说明风险和回滚。"},
    {"id": "e5", "kind": "engineering_complex", "q": "设计 CI 质量门禁，包含单测、lint、sast、发布审批全链路。"},
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3-coder-next")
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()

    cfg = load_config()
    cfg.providers[0].model = args.model
    loop = InferenceLoop(cfg, WORKSPACE_PATH)

    rows = []
    for c in CASES:
        t0 = time.time()
        d = loop.preview_route(c["q"])
        ms = int((time.time() - t0) * 1000)
        got = str(d.get("route") or "")
        rows.append(
            {
                "id": c["id"],
                "expect": c["kind"],
                "got": got,
                "ok": got == c["kind"],
                "workers": int(d.get("workers") or 0),
                "confidence": float(d.get("confidence") or 0),
                "reason": str(d.get("reason") or ""),
                "latency_ms": ms,
            }
        )

    acc = round(sum(1 for r in rows if r["ok"]) / len(rows), 3)
    by_kind = {}
    for k in ["simple_direct_master", "reasoning_swarm", "engineering_complex"]:
        ks = [r for r in rows if r["expect"] == k]
        by_kind[k] = round(sum(1 for r in ks if r["ok"]) / len(ks), 3)

    out = {
        "tag": args.tag,
        "model": args.model,
        "acc": acc,
        "acc_by_kind": by_kind,
        "rows": rows,
        "ts": int(time.time()),
    }
    out_dir = Path("artifacts")
    out_dir.mkdir(exist_ok=True)
    f = out_dir / f"analysis_routing_{args.tag}.json"
    f.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"file": str(f), "acc": acc, "acc_by_kind": by_kind}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
