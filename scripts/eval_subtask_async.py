from __future__ import annotations

import argparse
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from swarmbot.config_manager import WORKSPACE_PATH, load_config
from swarmbot.loops.inference import InferenceLoop


def run_loop(loop: InferenceLoop, q: str, sid: str) -> tuple[str, int]:
    t0 = time.time()
    with redirect_stdout(io.StringIO()):
        ans = loop.run(q, sid)
    return ans, int((time.time() - t0) * 1000)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="qwen3-coder-next")
    p.add_argument("--tag", required=True)
    args = p.parse_args()

    cfg = load_config()
    cfg.providers[0].model = args.model
    complex_q = "线上网关偶发超时，涉及重试策略、并发与日志采样，给完整排障改造方案。"
    simple_q = "帮我写一句礼貌的催进度消息。"

    loop_a = InferenceLoop(cfg, WORKSPACE_PATH)
    loop_b = InferenceLoop(cfg, WORKSPACE_PATH)

    route = loop_a.preview_route(complex_q)
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut = ex.submit(run_loop, loop_a, complex_q, f"{args.tag}-complex-{int(time.time())}")
        simple_ans, simple_ms = run_loop(loop_b, simple_q, f"{args.tag}-simple-{int(time.time())}")
        done_before_simple = fut.done()
        complex_ans, complex_ms = fut.result()

    out = {
        "tag": args.tag,
        "model": args.model,
        "route_for_complex": route.get("route"),
        "simple_ms": simple_ms,
        "complex_ms": complex_ms,
        "simple_finished_before_complex_done": not done_before_simple,
        "simple_len": len(simple_ans or ""),
        "complex_len": len(complex_ans or ""),
        "ts": int(time.time()),
    }
    out_dir = Path("artifacts")
    out_dir.mkdir(exist_ok=True)
    fp = out_dir / f"subtask_async_{args.tag}.json"
    fp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"file": str(fp), "simple_ms": simple_ms, "complex_ms": complex_ms, "concurrent_ok": out["simple_finished_before_complex_done"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
