from __future__ import annotations

import json
import os
import subprocess
import time
import fcntl
from typing import Any, Dict, List, Optional

from .base import MemoryStore
from ..config_manager import WORKSPACE_PATH


class MemoryMap:
    """
    记忆地图（Whiteboard）：
    用于多 Agent 协作时的共享白板，存储当前任务的全局状态、关键决策和依赖关系。
    """
    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}
        self.ensure_task_frame()
        
    def update(self, key: str, value: Any) -> None:
        self._data[key] = value
        
    def get(self, key: str) -> Any:
        return self._data.get(key)
        
    def get_snapshot(self) -> str:
        """返回当前白板的快照字符串，用于注入 Context"""
        return json.dumps(self._data, ensure_ascii=False, indent=2)

    def ensure_task_frame(self) -> None:
        """
        初始化或补全三层记忆中的 Whiteboard 核心结构。
        """
        core_defaults = {
            "task_specification": {},
            "execution_plan": {},
            "current_state": "INIT",
            "loop_counter": 0,
            "completed_subtasks": [],
            "pending_subtasks": [],
            "intermediate_results": {},
            "content_registry": [],
            "checkpoint_data": {},
            "qmd_candidates": [],
        }
        for k, v in core_defaults.items():
            if k not in self._data:
                # 对于列表 / 字典类型要复制一份，避免共享引用
                if isinstance(v, (list, dict)):
                    self._data[k] = v.copy()
                else:
                    self._data[k] = v

    def clear(self, preserve_core: bool = True) -> None:
        """
        清理白板。
        默认保留核心结构（任务规格、计划、循环计数等），只清空临时键。
        """
        if not preserve_core:
            self._data.clear()
            self.ensure_task_frame()
            return

        core_keys = {
            "task_specification",
            "execution_plan",
            "current_state",
            "loop_counter",
            "completed_subtasks",
            "pending_subtasks",
            "intermediate_results",
            "content_registry",
            "checkpoint_data",
        }
        preserved = {}
        for k, v in self._data.items():
            if k in core_keys:
                if isinstance(v, (list, dict)):
                    preserved[k] = v.copy()
                else:
                    preserved[k] = v
        self._data = preserved
        self.ensure_task_frame()


class LocalMDStore:
    """
    本地 MD（Short-term Cache）：
    以 Markdown 文件形式存储在本地，作为短期缓存或草稿箱。
    支持文件锁以防止多进程/线程写入冲突。
    """
    def __init__(self, root_path: str) -> None:
        self.root = root_path
        os.makedirs(self.root, exist_ok=True)
        
    def write(self, filename: str, content: str) -> None:
        path = os.path.join(self.root, filename)
        with open(path, "w", encoding="utf-8", errors='replace') as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX)
                f.write(content)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
            
    def read(self, filename: str) -> str:
        path = os.path.join(self.root, filename)
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8", errors='replace') as f:
            try:
                fcntl.flock(f, fcntl.LOCK_SH)
                return f.read()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def append(self, filename: str, content: str) -> None:
        """Atomic append"""
        path = os.path.join(self.root, filename)
        with open(path, "a", encoding="utf-8", errors='replace') as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX)
                f.write(content)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)


from .qmd_wrapper import EmbeddedQMD

class QMDMemoryStore(MemoryStore):
    """
    三层记忆系统：
    1. MemoryMap (Whiteboard): 内存中的共享状态，用于协作同步。
    2. LocalMD (Short-term): 本地 Markdown 文件，作为短期缓存，支持文件锁。
    3. QMD (Long-term): 真正的知识库索引，用于长短期记忆的持久化与检索，支持 Collection 隔离。
    """
    def __init__(self, default_collection: str = "default") -> None:
        # 1. MemoryMap
        self.whiteboard = MemoryMap()
        
        # 2. LocalMD
        self._cache_root = os.path.join(WORKSPACE_PATH, "cache")
        self.local_cache = LocalMDStore(self._cache_root)
        
        # 3. QMD Setup (Embedded)
        self._qmd_root = os.path.join(WORKSPACE_PATH, "qmd")
        self.default_collection = default_collection
        self.embedded_qmd = EmbeddedQMD(self._qmd_root)
        
        # In-memory buffer for fast context retrieval (part of QMD/Short-term mix)
        self._events: Dict[str, List[Dict[str, Any]]] = {}

    def _ensure_collection(self, name: str) -> None:
        """Create QMD collection if not exists"""
        # Managed internally by EmbeddedQMD
        pass

    def add_event(self, agent_id: str, content: str, meta: Dict[str, Any] | None = None) -> None:
        # Validation: Do not store empty content
        if not content or not content.strip():
            return
            
        # 1. Update In-memory buffer
        if agent_id not in self._events:
            self._events[agent_id] = []
        
        event = {
            "content": content,
            "meta": meta or {},
            "timestamp": time.time()
        }
        self._events[agent_id].append(event)
        
        # 2. Persist to LocalMD (Daily/Session Log) using Atomic Append
        date_str = time.strftime("%Y-%m-%d")
        log_file = f"chat_log_{date_str}.md"
        log_entry = f"\n## [{time.strftime('%H:%M:%S')}] {agent_id}\n{content}\n"
        self.local_cache.append(log_file, log_entry)
        
        # 3. Update Whiteboard (if meta contains 'update_map')
        if meta and "update_map" in meta:
            for k, v in meta["update_map"].items():
                self.whiteboard.update(k, v)

    def add(self, content: str, meta: Dict[str, Any] | None = None) -> None:
        """
        API Compatibility for Overthinking Loop.
        Writes consolidated memory to QMD (Long-term).
        """
        self.persist_to_qmd(content, collection=meta.get("collection") if meta else None)

    def persist_to_qmd(self, content: str, collection: Optional[str] = None) -> None:
        """
        Explicitly write refined memory to QMD Long-term storage.
        This is usually called by Overthinking Loop or explicit 'save' action.
        """
        target_coll = collection or self.default_collection
        
        # Use EmbeddedQMD
        self.embedded_qmd.add(content, collection=target_coll)
        
        # Optional: Still save markdown file for portability/backup
        filename = f"memory_{int(time.time())}.md"
        coll_path = os.path.join(self._qmd_root, target_coll, filename)
        os.makedirs(os.path.dirname(coll_path), exist_ok=True)
        with open(coll_path, "w", encoding="utf-8", errors='replace') as f:
            f.write(content)

    def _extract_keywords(self, text: str) -> List[str]:
        tokens: List[str] = []
        if not text:
            return tokens
        for w in text.split():
            if len(w) >= 3:
                tokens.append(w)
        buf = []
        for ch in text:
            if "\u4e00" <= ch <= "\u9fff":
                buf.append(ch)
            else:
                if len(buf) >= 2:
                    tokens.append("".join(buf))
                buf = []
        if len(buf) >= 2:
            tokens.append("".join(buf))
        return list(dict.fromkeys(tokens))

    def _build_whiteboard_summary(self, query: Optional[str]) -> str:
        data = getattr(self.whiteboard, "_data", {})
        if not isinstance(data, dict) or not data:
            return self.whiteboard.get_snapshot()
        parts: List[str] = []
        state = data.get("current_state")
        loop_counter = data.get("loop_counter")
        if state is not None or loop_counter is not None:
            parts.append(f"State: {state}, Loop: {loop_counter}")
        spec = data.get("task_specification")
        if spec:
            parts.append("Task Specification:")
            if isinstance(spec, dict):
                for k, v in list(spec.items())[:8]:
                    val = str(v)
                    if len(val) > 120:
                        val = val[:120] + "..."
                    parts.append(f"- {k}: {val}")
            else:
                val = str(spec)
                if len(val) > 400:
                    val = val[:400] + "..."
                parts.append(val)
        plan = data.get("execution_plan")
        if plan:
            parts.append("Execution Plan:")
            if isinstance(plan, dict):
                for k, v in list(plan.items())[:8]:
                    val = str(v)
                    if len(val) > 120:
                        val = val[:120] + "..."
                    parts.append(f"- {k}: {val}")
            elif isinstance(plan, list):
                for idx, v in enumerate(plan[:8]):
                    val = str(v)
                    if len(val) > 120:
                        val = val[:120] + "..."
                    parts.append(f"- [{idx+1}] {val}")
            else:
                val = str(plan)
                if len(val) > 400:
                    val = val[:400] + "..."
                parts.append(val)
        pending = data.get("pending_subtasks") or []
        completed = data.get("completed_subtasks") or []
        terms: List[str] = self._extract_keywords(query or "")
        def score_item(text: str) -> int:
            if not terms or not text:
                return 0
            s = 0
            for t in terms:
                if t and t in text:
                    s += 1
            return s
        if pending:
            scored = []
            for item in pending:
                txt = str(item)
                scored.append((score_item(txt), txt))
            scored.sort(key=lambda x: x[0], reverse=True)
            picked = []
            for s, txt in scored:
                picked.append(txt)
                if len(picked) >= 5:
                    break
            if picked:
                parts.append("Pending Subtasks:")
                for txt in picked:
                    t = txt
                    if len(t) > 160:
                        t = t[:160] + "..."
                    parts.append(f"- {t}")
        if completed:
            tail = completed[-8:]
            picked = []
            for item in reversed(tail):
                txt = str(item)
                picked.append(txt)
                if len(picked) >= 5:
                    break
            picked.reverse()
            if picked:
                parts.append("Recent Completed Subtasks:")
                for txt in picked:
                    t = txt
                    if len(t) > 160:
                        t = t[:160] + "..."
                    parts.append(f"- {t}")
        inter = data.get("intermediate_results")
        if inter and isinstance(inter, dict):
            keys = list(inter.keys())[:6]
            if keys:
                parts.append("Intermediate Results Keys:")
                for k in keys:
                    parts.append(f"- {k}")
        if not parts:
            return self.whiteboard.get_snapshot()
        return "\n".join(parts)

    def get_context(self, agent_id: str, limit: int = 20, query: str = None) -> List[Dict[str, Any]]:
        policy = {}
        try:
            data = getattr(self.whiteboard, "_data", {})
            if isinstance(data, dict):
                p = data.get("context_policy")
                if isinstance(p, dict):
                    policy = p
        except Exception:
            policy = {}
        wb_chars = int(policy.get("max_whiteboard_chars", 4000))
        hist_items = int(policy.get("max_history_items", limit))
        hist_chars = int(policy.get("max_history_chars_per_item", 1000))
        qmd_docs = int(policy.get("max_qmd_docs", 3))
        qmd_chars = int(policy.get("max_qmd_chars", 3000))
        summary = self._build_whiteboard_summary(query)
        if summary and len(summary) > wb_chars:
            summary = summary[:wb_chars] + "\n...[whiteboard summary truncated]\n"
        context = []
        if summary and summary != "{}":
            context.append({"content": f"Current WorkMap (Whiteboard):\n{summary}", "role": "system"})
        items = self._events.get(agent_id, [])
        if not items:
            pass
        recent = items[-hist_items:] if items else []
        for r in recent:
            text = r.get("content", "")
            if not text:
                continue
            if len(text) > hist_chars:
                text = text[:hist_chars] + "..."
            context.append({"content": text, "role": "user"})
        if query:
            qmd_results = self.search(query, limit=qmd_docs)
            if qmd_results:
                terms = self._extract_keywords(query)
                ranked: List[Dict[str, Any]] = []
                for doc in qmd_results:
                    c = doc.get("content", "")
                    if not c:
                        continue
                    score = 0
                    if terms:
                        for t in terms:
                            if t and t in c:
                                score += 1
                    ranked.append({"content": c, "score": score})
                ranked.sort(key=lambda x: x["score"], reverse=True)
                filtered: List[str] = []
                for item in ranked:
                    if item["score"] <= 0 and terms:
                        continue
                    filtered.append(item["content"])
                    if len(filtered) >= 3:
                        break
                knowledge = "\n".join(filtered)
                if len(knowledge) > qmd_chars:
                    knowledge = knowledge[:qmd_chars] + "\n...[qmd results truncated]\n"
                if knowledge:
                    context.insert(0, {"content": f"Relevant Long-term Memory (QMD):\n{knowledge}", "role": "system"})
        return context

    def search(self, query: str, collection: str | None = None, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search QMD (Long-term / Knowledge Base).
        """
        return self.embedded_qmd.search(query, collection=collection, limit=limit)
