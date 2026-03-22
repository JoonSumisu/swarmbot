from __future__ import annotations

import os
from typing import Dict, List

_ALLOWED: Dict[str, List[str]] = {
    "swarm_manager": ["swarmboot.md", "masteragentboot.md", "SOUL.md"],
    "inference_loop": ["swarmboot.md", "SOUL.md"],
}


def load_boot_markdown(filename: str, module: str, max_chars: int = 12000) -> str:
    allowed = _ALLOWED.get(module, [])
    if filename not in allowed:
        return ""
    user_boot = os.path.expanduser(f"~/.swarmbot/boot/{filename}")
    pkg_boot = os.path.join(os.path.dirname(__file__), filename)
    content = ""
    try:
        if os.path.exists(user_boot):
            with open(user_boot, "r", encoding="utf-8") as f:
                content = f.read()
        elif os.path.exists(pkg_boot):
            with open(pkg_boot, "r", encoding="utf-8") as f:
                content = f.read()
    except:
        content = ""
    if isinstance(content, str) and len(content) > max_chars:
        return content[:max_chars] + "\n...[truncated]\n"
    return content or ""
