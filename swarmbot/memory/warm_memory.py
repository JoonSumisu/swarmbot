from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import time
import os
import json


class WarmMemory:
    """
    L3 Warm Memory: Sequential daily log.
    File: memory/YYYY-MM-DD.md
    Content: Time-stamped conclusions and facts from each loop.
    """
    def __init__(self, workspace_path: str):
        self.root = Path(workspace_path) / "memory"
        self.root.mkdir(parents=True, exist_ok=True)

    def _get_today_file(self) -> Path:
        date_str = time.strftime("%Y-%m-%d")
        return self.root / f"{date_str}.md"

    def append_log(self, loop_id: str, input_prompt: str, summary: str, facts: list):
        file_path = self._get_today_file()
        timestamp = time.strftime("%H:%M:%S")
        
        entry = f"\n\n## Entry [{timestamp}] Loop: {loop_id}\n"
        entry += f"### Input\n{input_prompt}\n"
        entry += f"### Conclusion\n{summary}\n"
        if facts:
            entry += "### Facts\n" + "\n".join([f"- {f}" for f in facts]) + "\n"
        
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(entry)

    def add_event(self, session_id: str, content: str, meta: Optional[Dict[str, Any]] = None) -> None:
        """Add an event to the daily log (for inference tool integration)"""
        file_path = self._get_today_file()
        timestamp = time.strftime("%H:%M:%S")
        
        role = meta.get("role", "assistant") if meta else "assistant"
        event_type = meta.get("type", "general") if meta else "general"
        
        entry = f"\n\n## [{timestamp}] Session: {session_id} | Type: {event_type}\n"
        entry += f"**Role**: {role}\n\n"
        entry += f"{content}\n"
        
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(entry)

    def get_context(self, agent_id: str, limit: int = 20, query: str | None = None) -> List[Dict[str, Any]]:
        """Get context from recent events (for MemoryStore interface)"""
        return []

    def read_today(self) -> str:
        file_path = self._get_today_file()
        if file_path.exists():
            return file_path.read_text(encoding="utf-8")
        return ""

    def list_files(self) -> list[Path]:
        return sorted(list(self.root.glob("*.md")))
        
    def delete_file(self, filename: str):
        path = self.root / filename
        if path.exists():
            os.remove(path)
            
    def get_file_path(self, filename: str) -> Path:
        return self.root / filename
