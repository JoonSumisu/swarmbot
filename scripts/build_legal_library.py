from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from swarmbot.memory.evidence_store import EvidenceStore


def main() -> int:
    store = EvidenceStore()
    built = store.build_summary()
    domains = built["summary"].get("domains", {})
    total = sum(int(v.get("records", 0)) for v in domains.values()) if isinstance(domains, dict) else 0
    print(json.dumps({"file": built["file"], "total_records": total, "domains": list(domains.keys()) if isinstance(domains, dict) else []}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
