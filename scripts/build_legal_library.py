from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from swarmbot.config_manager import WORKSPACE_PATH


def main() -> int:
    kb_jsonl = Path(WORKSPACE_PATH) / "legal_kb.jsonl"
    out_json = Path(WORKSPACE_PATH) / "legal_library.json"
    entries = []
    if kb_jsonl.exists():
        for ln in kb_jsonl.read_text(encoding="utf-8").splitlines():
            s = ln.strip()
            if not s:
                continue
            try:
                entries.append(json.loads(s))
            except:
                pass
    law_count = {}
    article_count = {}
    for e in entries:
        for c in e.get("citations") or []:
            if c.startswith("《") and c.endswith("》"):
                law_count[c] = law_count.get(c, 0) + 1
            elif c.startswith("第") and c.endswith("条"):
                article_count[c] = article_count.get(c, 0) + 1
    data = {
        "total_records": len(entries),
        "top_laws": sorted([{"name": k, "count": v} for k, v in law_count.items()], key=lambda x: x["count"], reverse=True)[:200],
        "top_articles": sorted([{"name": k, "count": v} for k, v in article_count.items()], key=lambda x: x["count"], reverse=True)[:500],
    }
    out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"file": str(out_json), "total_records": data["total_records"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
