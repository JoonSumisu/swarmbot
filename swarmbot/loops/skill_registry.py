from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set


VALID_SKILLS: Set[str] = {
    "whiteboard_update",
    "hot_memory_update",
    "web_search",
    "browser_open",
    "browser_read",
    "file_read",
    "file_write",
    "python_exec",
    "shell_exec",
}


@dataclass
class SkillRegistry:
    base_skills: List[str] = field(default_factory=lambda: ["whiteboard_update", "hot_memory_update"])
    role_skills: Dict[str, List[str]] = field(default_factory=lambda: {
        "planner": ["web_search", "python_exec"],
        "analyst": ["web_search", "browser_read", "python_exec"],
        "collector": ["web_search", "browser_open", "browser_read", "file_read", "python_exec"],
        "evaluator": ["file_read", "python_exec"],
        "reviewer": ["file_read", "python_exec"],
        "critic": ["web_search", "python_exec"],
        "summarizer": ["file_read", "python_exec"],
        "master": ["file_read", "web_search"],
        "reasoner": ["python_exec", "file_read"],
        "worker": ["python_exec", "file_read"],
        "coder": ["file_write", "shell_exec", "file_read", "python_exec"],
        "developer": ["file_write", "shell_exec", "file_read", "python_exec"],
        "researcher": ["web_search", "browser_open", "browser_read", "python_exec"],
        "writer": ["web_search", "python_exec"],
        "finance": ["web_search", "python_exec"],
        "market": ["web_search", "python_exec"],
        "data": ["python_exec", "file_read", "file_write"],
    })
    domain_skills: Dict[str, List[str]] = field(default_factory=lambda: {
        "security": ["web_search", "file_read"],
        "performance": ["python_exec", "file_read"],
        "code": ["file_read", "file_write", "python_exec", "shell_exec"],
        "research": ["web_search", "browser_open", "browser_read"],
        "data": ["python_exec", "file_read", "file_write"],
        "document": ["file_read", "file_write"],
        "analysis": ["python_exec", "web_search"],
    })

    def _normalize(self, skills: List[str]) -> List[str]:
        cleaned: List[str] = []
        for s in skills:
            if isinstance(s, str) and s in VALID_SKILLS and s not in cleaned:
                cleaned.append(s)
        return cleaned

    def register_role(self, role: str, skills: List[str]) -> None:
        key = (role or "").strip().lower()
        if not key:
            return
        self.role_skills[key] = self._normalize(skills)

    def get_skills(self, role: str) -> Dict[str, bool]:
        r = (role or "").strip().lower()
        collected: List[str] = list(self.base_skills)
        for k, v in self.role_skills.items():
            if k in r or r in k:
                collected.extend(v)
        for k, v in self.domain_skills.items():
            if k in r:
                collected.extend(v)
        normalized = self._normalize(collected)
        return {name: True for name in normalized}

    def get_skills_for_task(self, role: str, task_desc: str = "", required_skills: List[str] | None = None) -> Dict[str, bool]:
        out = self.get_skills(role)
        desc = (task_desc or "").lower()
        for k, v in self.domain_skills.items():
            if k in desc:
                for s in v:
                    if s in VALID_SKILLS:
                        out[s] = True
        for s in (required_skills or []):
            if isinstance(s, str) and s in VALID_SKILLS:
                out[s] = True
        return out
