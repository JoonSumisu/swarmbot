from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any, Dict, List

from .base import MemoryStore
from ..config_manager import WORKSPACE_PATH


class MemoryMap:
    """
    记忆地图（Whiteboard）：
    用于多 Agent 协作时的共享白板，存储当前任务的全局状态、关键决策和依赖关系。
    """
    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}
        
    def update(self, key: str, value: Any) -> None:
        self._data[key] = value
        
    def get(self, key: str) -> Any:
        return self._data.get(key)
        
    def get_snapshot(self) -> str:
        """返回当前白板的快照字符串，用于注入 Context"""
        return json.dumps(self._data, ensure_ascii=False, indent=2)


class LocalMDStore:
    """
    本地 MD（Short-term Cache）：
    以 Markdown 文件形式存储在本地，作为短期缓存或草稿箱。
    """
    def __init__(self, root_path: str) -> None:
        self.root = root_path
        os.makedirs(self.root, exist_ok=True)
        
    def write(self, filename: str, content: str) -> None:
        path = os.path.join(self.root, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
            
    def read(self, filename: str) -> str:
        path = os.path.join(self.root, filename)
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()


class QMDMemoryStore(MemoryStore):
    """
    三层记忆系统：
    1. MemoryMap (Whiteboard): 内存中的共享状态，用于协作同步。
    2. LocalMD (Short-term): 本地 Markdown 文件，作为短期缓存。
    3. QMD (Long-term): 真正的知识库索引，用于长短期记忆的持久化与检索。
    """
    def __init__(self) -> None:
        # 1. MemoryMap
        self.whiteboard = MemoryMap()
        
        # 2. LocalMD
        self._cache_root = os.path.join(WORKSPACE_PATH, "cache")
        self.local_cache = LocalMDStore(self._cache_root)
        
        # 3. QMD Setup
        self._qmd_root = os.path.join(WORKSPACE_PATH, "qmd")
        os.makedirs(self._qmd_root, exist_ok=True)
        
        # In-memory buffer for fast context retrieval (part of QMD/Short-term mix)
        self._events: Dict[str, List[Dict[str, Any]]] = {}

    def add_event(self, agent_id: str, content: str, meta: Dict[str, Any] | None = None) -> None:
        # 1. Update In-memory buffer
        if agent_id not in self._events:
            self._events[agent_id] = []
        
        event = {
            "content": content,
            "meta": meta or {},
            "timestamp": time.time()
        }
        self._events[agent_id].append(event)
        
        # 2. Persist to LocalMD (Daily/Session Log)
        date_str = time.strftime("%Y-%m-%d")
        log_file = f"chat_log_{date_str}.md"
        log_entry = f"\n## [{time.strftime('%H:%M:%S')}] {agent_id}\n{content}\n"
        
        # Append to daily log
        current_log = self.local_cache.read(log_file)
        self.local_cache.write(log_file, current_log + log_entry)
        
        # 3. Update Whiteboard (if meta contains 'update_map')
        if meta and "update_map" in meta:
            for k, v in meta["update_map"].items():
                self.whiteboard.update(k, v)

    def get_context(self, agent_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get combined context:
        - Recent events (Short-term)
        - Whiteboard snapshot (Shared state)
        """
        items = self._events.get(agent_id, [])
        recent = items[-limit:] if items else []
        
        # Inject whiteboard state as a system message if not empty
        snapshot = self.whiteboard.get_snapshot()
        if snapshot != "{}":
            return [{"content": f"Current WorkMap (Whiteboard):\n{snapshot}", "role": "system"}] + recent
            
        return recent

    def search(self, query: str, collection: str | None = None, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search QMD (Long-term / Knowledge Base).
        """
        try:
            cmd = ["qmd", "search", query, "--json", "-n", str(limit)]
            if collection:
                cmd.extend(["-c", collection])
            result = subprocess.run(
                cmd,
                cwd=self._qmd_root,
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            return []
        if not result.stdout:
            return []
        try:
            data = json.loads(result.stdout)
        except Exception:
            return []
        docs = data if isinstance(data, list) else data.get("results", [])
        return docs
