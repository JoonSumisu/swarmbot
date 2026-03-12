from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass
class EvidenceRecord:
    ts: int
    domain: str
    route: str
    question: str
    citations: List[str]
    answer_preview: str


class EvidenceStore:
    def __init__(self, root: str | None = None):
        self.root = Path(root or os.path.expanduser("~/.swarmbot/evidence"))
        self.root.mkdir(parents=True, exist_ok=True)

    def classify_domain(self, question: str) -> str:
        t = (question or "").lower()
        if any(k in t for k in ["法律", "法条", "劳动法", "刑法", "民法", "合同法", "判例", "条文"]):
            return "legal"
        if any(k in t for k in ["经济", "宏观", "通胀", "利率", "货币", "gdp", "财政", "就业"]):
            return "economy"
        if any(k in t for k in ["商业", "市场", "竞品", "商业模式", "产品设计", "可行性", "项目评估"]):
            return "business"
        if any(k in t for k in ["政策", "监管", "合规", "条例", "规范"]):
            return "policy"
        return "general"

    def extract_citations(self, answer: str) -> List[str]:
        text = answer or ""
        urls = re.findall(r"https?://[^\s`\"'<>]+", text)
        laws = re.findall(r"《[^》]{2,40}》", text)
        articles = re.findall(r"第[一二三四五六七八九十百千0-9]{1,10}条", text)
        out: List[str] = []
        for x in urls + laws + articles:
            if x not in out:
                out.append(x)
        return out

    def append_incremental(self, question: str, answer: str, route: str) -> Dict[str, str]:
        domain = self.classify_domain(question)
        rec = EvidenceRecord(
            ts=int(time.time()),
            domain=domain,
            route=route,
            question=(question or "")[:1200],
            citations=self.extract_citations(answer)[:40],
            answer_preview=(answer or "")[:3000],
        )
        domain_dir = self.root / domain
        domain_dir.mkdir(parents=True, exist_ok=True)
        file_path = domain_dir / "incremental.jsonl"
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec.__dict__, ensure_ascii=False) + "\n")
        return {"domain": domain, "file": str(file_path)}

    def build_summary(self) -> Dict[str, object]:
        summary: Dict[str, object] = {"generated_at": int(time.time()), "domains": {}}
        for domain_dir in sorted([p for p in self.root.iterdir() if p.is_dir()]):
            f = domain_dir / "incremental.jsonl"
            if not f.exists():
                continue
            lines = [ln for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
            cites: Dict[str, int] = {}
            for ln in lines:
                try:
                    row = json.loads(ln)
                    for c in row.get("citations") or []:
                        cites[c] = cites.get(c, 0) + 1
                except:
                    pass
            summary["domains"][domain_dir.name] = {
                "records": len(lines),
                "top_citations": sorted([{"name": k, "count": v} for k, v in cites.items()], key=lambda x: x["count"], reverse=True)[:100],
            }
        out_file = self.root / "library_summary.json"
        out_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"file": str(out_file), "summary": summary}
