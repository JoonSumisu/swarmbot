from __future__ import annotations

import os
import json
import time
import fcntl
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta


class SessionMemory:
    """
    L1.5 Session Memory: 按 chat_id 索引的会话级记忆

    位于 L1 Whiteboard 和 L2 HotMemory 之间：
    - 持久化：~/.swarmbot/workspace/sessions/{chat_id}.md
    - 生命周期：用户主动清除或 7 天无活动
    - 内容：对话历史、任务状态、待办事项、关键结论

    与现有记忆层的区别：
    - L1 Whiteboard: 单次 Loop 内的临时工作区，Loop 完成后清除
    - L1.5 SessionMemory: 同一 chat_id 的多轮对话共享，7 天 TTL
    - L2 HotMemory: 全局共享的待办/计划，跨会话持久化
    - L3 WarmMemory: 按日归档的完整日志
    - L4 ColdMemory: 永久知识库
    """

    def __init__(self, workspace_path: str):
        self.workspace_path = workspace_path
        self.sessions_dir = os.path.join(workspace_path, "sessions")
        os.makedirs(self.sessions_dir, exist_ok=True)
        self.ttl_days = 7
        self._cache: Dict[str, Dict[str, Any]] = {}

    def _session_path(self, chat_id: str) -> str:
        """Get session file path for given chat_id"""
        return os.path.join(self.sessions_dir, f"{chat_id}.md")

    def _load_session(self, chat_id: str) -> Dict[str, Any]:
        """Load session data from disk or cache"""
        if chat_id in self._cache:
            cached = self._cache[chat_id]
            last_access = cached.get("metadata", {}).get("last_access", 0)
            if time.time() - last_access < self.ttl_days * 86400:
                return cached

        path = self._session_path(chat_id)
        session_data = {
            "metadata": {
                "chat_id": chat_id,
                "created_at": time.time(),
                "last_access": time.time(),
                "turn_count": 0,
            },
            "dialogue_history": [],
            "task_states": {},
            "key_facts": [],
            "pending_items": [],
        }

        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    fcntl.flock(f, fcntl.LOCK_SH)
                    content = f.read()
                    fcntl.flock(f, fcntl.LOCK_UN)

                current_section = None
                current_content = []

                for line in content.split("\n"):
                    if line.startswith("## "):
                        if current_section:
                            self._parse_section(session_data, current_section, current_content)
                        current_section = line[3:].strip()
                        current_content = []
                    elif current_section and line.strip():
                        current_content.append(line)

                if current_section:
                    self._parse_section(session_data, current_section, current_content)

            except Exception as e:
                print(f"[SessionMemory] Load error for {chat_id}: {e}")

        self._cache[chat_id] = session_data
        return session_data

    def _parse_section(self, session_data: Dict, section: str, content: List[str]):
        """Parse a section from markdown format"""
        text = "\n".join(content)

        if section == "METADATA":
            try:
                meta = json.loads(text)
                session_data["metadata"].update(meta)
            except Exception:
                pass
        elif section == "DIALOGUE_HISTORY":
            for line in content:
                if line.startswith("- "):
                    try:
                        item = json.loads(line[2:])
                        session_data["dialogue_history"].append(item)
                    except Exception:
                        pass
        elif section == "KEY_FACTS":
            for line in content:
                if line.startswith("- "):
                    session_data["key_facts"].append(line[2:].strip())
        elif section == "PENDING_ITEMS":
            for line in content:
                if line.startswith("- "):
                    session_data["pending_items"].append(line[2:].strip())
        elif section == "TASK_STATES":
            try:
                states = json.loads(text)
                session_data["task_states"].update(states)
            except Exception:
                pass

    def _save_session(self, chat_id: str, session_data: Dict[str, Any]) -> None:
        """Save session data to disk"""
        path = self._session_path(chat_id)

        lines = []

        lines.append("## METADATA")
        lines.append(json.dumps(session_data["metadata"], ensure_ascii=False, indent=2))
        lines.append("")

        lines.append("## DIALOGUE_HISTORY")
        for item in session_data["dialogue_history"][-50:]:
            lines.append("- " + json.dumps(item, ensure_ascii=False))
        lines.append("")

        lines.append("## KEY_FACTS")
        for fact in session_data["key_facts"]:
            lines.append("- " + fact)
        lines.append("")

        lines.append("## PENDING_ITEMS")
        for item in session_data["pending_items"]:
            lines.append("- " + item)
        lines.append("")

        lines.append("## TASK_STATES")
        lines.append(json.dumps(session_data["task_states"], ensure_ascii=False, indent=2))

        try:
            with open(path, "w", encoding="utf-8") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                f.write("\n".join(lines))
                fcntl.flock(f, fcntl.LOCK_UN)
        except Exception as e:
            print(f"[SessionMemory] Save error for {chat_id}: {e}")

        self._cache[chat_id] = session_data

    def add_turn(self, chat_id: str, user_input: str, assistant_response: str, metadata: Optional[Dict] = None) -> None:
        """Add a dialogue turn to the session"""
        session = self._load_session(chat_id)

        turn = {
            "timestamp": time.time(),
            "user_input": user_input,
            "assistant_response": assistant_response,
            "metadata": metadata or {},
        }

        session["dialogue_history"].append(turn)
        session["metadata"]["turn_count"] += 1
        session["metadata"]["last_access"] = time.time()

        self._save_session(chat_id, session)

    def add_key_fact(self, chat_id: str, fact: str) -> None:
        """Add a key fact to the session"""
        session = self._load_session(chat_id)

        if fact not in session["key_facts"]:
            session["key_facts"].append(fact)
            session["metadata"]["last_access"] = time.time()
            self._save_session(chat_id, session)

    def add_pending_item(self, chat_id: str, item: str) -> None:
        """Add a pending item to the session"""
        session = self._load_session(chat_id)

        if item not in session["pending_items"]:
            session["pending_items"].append(item)
            session["metadata"]["last_access"] = time.time()
            self._save_session(chat_id, session)

    def update_task_state(self, chat_id: str, task_id: str, state: Dict[str, Any]) -> None:
        """Update task state in the session"""
        session = self._load_session(chat_id)
        session["task_states"][task_id] = {
            **session["task_states"].get(task_id, {}),
            **state,
            "updated_at": time.time(),
        }
        session["metadata"]["last_access"] = time.time()
        self._save_session(chat_id, session)

    def get_context(self, chat_id: str, max_turns: int = 10) -> Dict[str, Any]:
        """Get session context for injection into prompts"""
        session = self._load_session(chat_id)
        session["metadata"]["last_access"] = time.time()

        recent_turns = session["dialogue_history"][-max_turns:]

        return {
            "chat_id": chat_id,
            "turn_count": session["metadata"]["turn_count"],
            "created_at": session["metadata"]["created_at"],
            "last_access": session["metadata"]["last_access"],
            "recent_dialogue": recent_turns,
            "key_facts": session["key_facts"],
            "pending_items": session["pending_items"],
            "task_states": session["task_states"],
        }

    def get_recent_turns(self, chat_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent dialogue turns"""
        session = self._load_session(chat_id)
        return session["dialogue_history"][-limit:]

    def get_key_facts(self, chat_id: str) -> List[str]:
        """Get all key facts for the session"""
        session = self._load_session(chat_id)
        return session["key_facts"]

    def get_pending_items(self, chat_id: str) -> List[str]:
        """Get all pending items for the session"""
        session = self._load_session(chat_id)
        return session["pending_items"]

    def cleanup_expired(self) -> List[str]:
        """Remove expired sessions (older than TTL)"""
        removed = []
        current_time = time.time()
        ttl_seconds = self.ttl_days * 86400

        for filename in os.listdir(self.sessions_dir):
            if not filename.endswith(".md"):
                continue

            chat_id = filename[:-3]
            path = os.path.join(self.sessions_dir, filename)

            try:
                mtime = os.path.getmtime(path)
                if current_time - mtime > ttl_seconds:
                    os.remove(path)
                    if chat_id in self._cache:
                        del self._cache[chat_id]
                    removed.append(chat_id)
            except Exception as e:
                print(f"[SessionMemory] Cleanup error for {chat_id}: {e}")

        return removed

    def clear_session(self, chat_id: str) -> None:
        """Manually clear a session"""
        path = self._session_path(chat_id)
        if os.path.exists(path):
            os.remove(path)
        if chat_id in self._cache:
            del self._cache[chat_id]

    def compact_session(self, chat_id: str, keep_turns: int = 3) -> None:
        """Compact session memory - keep only recent turns"""
        session = self._load_session(chat_id)

        old_turns = session["dialogue_history"]
        if len(old_turns) > keep_turns:
            old_turns_to_archive = old_turns[:-keep_turns]
            session["dialogue_history"] = old_turns[-keep_turns:]

            if old_turns_to_archive:
                last_archived = old_turns_to_archive[-1]
                summary = f"之前完成了：{last_archived.get('user_input', '')[:50]}"
                if summary not in session["key_facts"]:
                    session["key_facts"].append(summary)

            session["metadata"]["last_access"] = time.time()
            session["metadata"]["turn_count"] = len(session["dialogue_history"])
            self._save_session(chat_id, session)

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all active sessions with metadata"""
        sessions = []
        for filename in os.listdir(self.sessions_dir):
            if not filename.endswith(".md"):
                continue

            chat_id = filename[:-3]
            session = self._load_session(chat_id)
            sessions.append({
                "chat_id": chat_id,
                "turn_count": session["metadata"]["turn_count"],
                "created_at": session["metadata"]["created_at"],
                "last_access": session["metadata"]["last_access"],
            })

        sessions.sort(key=lambda x: x["last_access"], reverse=True)
        return sessions
