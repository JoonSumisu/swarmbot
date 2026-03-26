from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional
from pathlib import Path

from ..config_manager import WORKSPACE_PATH


class MemoryManager:
    """
    统一记忆管理器 - 单例模式
    管理 SQLite 中的 conversations, key_facts, episodes, entities, relations, autonomous_actions
    """

    _instance: Optional[MemoryManager] = None
    _lock = threading.Lock()

    def __new__(cls, db_path: Optional[str] = None):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, db_path: Optional[str] = None):
        if self._initialized:
            return
        self.db_path = db_path or os.path.join(WORKSPACE_PATH, "memory.sqlite")
        self._local = threading.local()
        self._llm = None
        self._initialized = True

    @classmethod
    def get_instance(cls, db_path: Optional[str] = None) -> MemoryManager:
        """获取单例实例"""
        return cls(db_path)

    def _get_conn(self) -> sqlite3.Connection:
        """获取线程安全的数据库连接"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._create_tables(self._local.conn)
        return self._local.conn

    def _create_tables(self, conn: sqlite3.Connection):
        """创建所有表"""
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                turn_index INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_used TEXT DEFAULT 'simple',
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id);
            CREATE INDEX IF NOT EXISTS idx_conv_session_turn ON conversations(session_id, turn_index);
            CREATE INDEX IF NOT EXISTS idx_conv_created ON conversations(created_at);

            CREATE TABLE IF NOT EXISTS key_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'fact',
                importance REAL DEFAULT 0.5,
                ref_count INTEGER DEFAULT 1,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_referenced TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_facts_importance ON key_facts(importance DESC);
            CREATE INDEX IF NOT EXISTS idx_facts_session ON key_facts(session_id);
            CREATE INDEX IF NOT EXISTS idx_facts_content ON key_facts(content);

            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                source TEXT DEFAULT 'swarmbot',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            );

            CREATE TABLE IF NOT EXISTS entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);

            CREATE TABLE IF NOT EXISTS relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_entity TEXT NOT NULL,
                target_entity TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                fact TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_entity);
            CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_entity);

            CREATE TABLE IF NOT EXISTS autonomous_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id TEXT,
                bundle_id TEXT,
                action_type TEXT,
                status TEXT,
                input_summary TEXT,
                output_summary TEXT,
                key_facts TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            );
        """)
        conn.commit()

    # ========================================================================
    # 实时写入
    # ========================================================================

    def add_turn(self, session_id: str, role: str, content: str,
                 tool_used: str = "simple", metadata: Optional[Dict] = None) -> int:
        """实时记录对话轮次"""
        conn = self._get_conn()
        turn_index = self._get_turn_count(session_id) + 1
        cursor = conn.execute(
            "INSERT INTO conversations (session_id, turn_index, role, content, tool_used, metadata) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, turn_index, role, content, tool_used, json.dumps(metadata or {}, ensure_ascii=False)),
        )
        conn.commit()
        return cursor.lastrowid

    def add_key_fact(self, session_id: Optional[str], content: str,
                     category: str = "fact", importance: float = 0.5,
                     source: str = "auto") -> int:
        """实时写入关键事实"""
        conn = self._get_conn()
        # 检查是否已存在相似事实
        existing = conn.execute(
            "SELECT id, ref_count FROM key_facts WHERE content = ?",
            (content,)
        ).fetchone()
        if existing:
            new_ref = existing["ref_count"] + 1
            new_imp = min(1.0, importance + 0.1 * new_ref)
            conn.execute(
                "UPDATE key_facts SET ref_count = ?, importance = ?, last_referenced = CURRENT_TIMESTAMP WHERE id = ?",
                (new_ref, new_imp, existing["id"]),
            )
            conn.commit()
            return existing["id"]
        cursor = conn.execute(
            "INSERT INTO key_facts (session_id, content, category, importance, source) VALUES (?, ?, ?, ?, ?)",
            (session_id, content, category, importance, source),
        )
        conn.commit()
        return cursor.lastrowid

    def add_episode(self, content: str, metadata: Optional[Dict] = None) -> int:
        """写入冷记忆 episodes"""
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO episodes (content, source, metadata) VALUES (?, ?, ?)",
            (content, metadata.get("source", "swarmbot") if metadata else "swarmbot",
             json.dumps(metadata or {}, ensure_ascii=False)),
        )
        conn.commit()
        return cursor.lastrowid

    def add(self, content: str, meta: Optional[Dict] = None) -> None:
        """ColdMemory 兼容接口"""
        self.add_episode(content, metadata=meta)

    def add_entity(self, name: str, summary: str = "") -> int:
        """写入实体"""
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "INSERT OR REPLACE INTO entities (name, summary, last_updated) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (name, summary or name),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            row = conn.execute("SELECT id FROM entities WHERE name = ?", (name,)).fetchone()
            return row["id"] if row else 0

    def add_relation(self, source: str, target: str, relation_type: str, fact: str = "") -> int:
        """写入关系"""
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO relations (source_entity, target_entity, relation_type, fact) VALUES (?, ?, ?, ?)",
            (source, target, relation_type, fact),
        )
        conn.commit()
        return cursor.lastrowid

    def add_autonomous_action(self, plan_id: str, bundle_id: str, action_type: str,
                               status: str, input_summary: str = "",
                               output_summary: str = "") -> int:
        """写入自主动作记录"""
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO autonomous_actions (plan_id, bundle_id, action_type, status, input_summary, output_summary, completed_at) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (plan_id, bundle_id, action_type, status, input_summary, output_summary),
        )
        conn.commit()
        return cursor.lastrowid

    # ========================================================================
    # 读取上下文
    # ========================================================================

    def get_recent_context(self, session_id: str, max_turns: int = 10) -> str:
        """获取最近 N 轮对话（只返回 user_input + assistant_response）"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT role, content FROM conversations WHERE session_id = ? ORDER BY turn_index DESC LIMIT ?",
            (session_id, max_turns * 2),
        ).fetchall()
        if not rows:
            return ""
        lines = []
        for row in reversed(rows):
            role = "User" if row["role"] == "user" else "Assistant"
            lines.append(f"{role}: {row['content']}")
        return "\n".join(lines)

    def get_important_facts(self, session_id: Optional[str] = None, limit: int = 10) -> List[str]:
        """获取重要事实（按 importance DESC 排序）"""
        conn = self._get_conn()
        if session_id:
            rows = conn.execute(
                "SELECT content FROM key_facts WHERE session_id = ? ORDER BY importance DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT content FROM key_facts ORDER BY importance DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [row["content"] for row in rows]

    def get_important_facts_text(self, session_id: Optional[str] = None, limit: int = 10) -> str:
        """获取重要事实（文本格式）"""
        facts = self.get_important_facts(session_id, limit)
        if not facts:
            return ""
        return "\n".join([f"- {f}" for f in facts])

    def search_knowledge(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """搜索冷记忆"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM episodes WHERE content LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        results = []
        for row in rows:
            results.append({
                "uuid": str(row["id"]),
                "content": row["content"],
                "name": f"Episode_{row['id']}",
                "summary": row["content"][:100],
                "score": 1.0,
            })
        # 也搜 key_facts
        fact_rows = conn.execute(
            "SELECT * FROM key_facts WHERE content LIKE ? ORDER BY importance DESC LIMIT ?",
            (f"%{query}%", limit),
        ).fetchall()
        for row in fact_rows:
            results.append({
                "uuid": f"fact_{row['id']}",
                "content": row["content"],
                "name": f"Fact_{row['id']}",
                "summary": row["content"],
                "score": 0.9,
            })
        return results[:limit]

    def search_knowledge_text(self, query: str, limit: int = 5) -> str:
        """搜索冷记忆（文本格式）"""
        results = self.search_knowledge(query, limit)
        if not results:
            return ""
        return "\n".join([f"- {r['content'][:200]}" for r in results])

    # ========================================================================
    # 异步事实提取
    # ========================================================================

    def extract_facts_from_turn(self, session_id: str, user_input: str, response: str):
        """LLM 从 (user_input + response) 提取关键事实"""
        try:
            from ..llm_client import OpenAICompatibleClient
            from ..config_manager import load_config

            config = load_config()
            llm = OpenAICompatibleClient.from_provider(providers=config.providers)

            prompt = f"""你是事实提取专家。请从以下对话中提取关键信息。

用户输入: {user_input}
助手回复: {response}

请提取用户个人信息、偏好、技术栈、任务等关键事实。输出 JSON:
{{
    "facts": [
        {{"content": "事实描述", "category": "entity/preference/tech/task", "importance": 0.8}}
    ]
}}

只输出 JSON，不要其他内容。如果对话中没有值得提取的关键信息，输出 {{"facts": []}}。"""

            result = llm.completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=500,
            )

            content = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            match = re.search(r'\{[\s\S]*\}', content)
            if match:
                data = json.loads(match.group())
                for fact in data.get("facts", []):
                    fact_content = fact.get("content", "")
                    if fact_content:
                        self.add_key_fact(
                            session_id=session_id,
                            content=fact_content,
                            category=fact.get("category", "fact"),
                            importance=float(fact.get("importance", 0.5)),
                            source="llm_extracted",
                        )
                        # 写入 entities
                        self.add_entity(fact_content[:50], fact_content)
        except Exception as e:
            print(f"[MemoryManager] Fact extraction error: {e}")

    # ========================================================================
    # Compact
    # ========================================================================

    def compact(self, session_id: str, keep_turns: int = 10):
        """
        滑窗整理：
        1. 保留最近 N 轮对话
        2. 删除更早的轮次
        3. 对被删除的轮次提取关键事实 → 写入 key_facts + episodes
        4. 合并重复的 key_facts
        """
        conn = self._get_conn()

        # 获取总轮次
        total = self._get_turn_count(session_id)
        if total <= keep_turns:
            return {"compact": False, "reason": "not_enough_turns"}

        # 获取要删除的轮次
        delete_before = total - keep_turns
        old_turns = conn.execute(
            "SELECT * FROM conversations WHERE session_id = ? AND turn_index <= ? ORDER BY turn_index",
            (session_id, delete_before),
        ).fetchall()

        if not old_turns:
            return {"compact": False, "reason": "no_turns_to_delete"}

        # 提取关键事实
        user_inputs = []
        assistant_responses = []
        for turn in old_turns:
            if turn["role"] == "user":
                user_inputs.append(turn["content"])
            else:
                assistant_responses.append(turn["content"])

        # 合并为一段文本，提取关键事实
        combined = ""
        for i in range(min(len(user_inputs), len(assistant_responses))):
            combined += f"User: {user_inputs[i]}\nAssistant: {assistant_responses[i]}\n\n"

        # 写入 episodes（归档）
        if combined.strip():
            self.add_episode(
                content=f"[COMPACT from {session_id}] {combined[:2000]}",
                metadata={"source": "compact", "session_id": session_id},
            )

        # 删除旧轮次
        conn.execute(
            "DELETE FROM conversations WHERE session_id = ? AND turn_index <= ?",
            (session_id, delete_before),
        )
        conn.commit()

        # 重新编号剩余轮次
        remaining = conn.execute(
            "SELECT id FROM conversations WHERE session_id = ? ORDER BY turn_index",
            (session_id,),
        ).fetchall()
        for i, row in enumerate(remaining, 1):
            conn.execute("UPDATE conversations SET turn_index = ? WHERE id = ?", (i, row["id"]))
        conn.commit()

        print(f"[MemoryManager] Compact done: deleted {delete_before} turns, kept {keep_turns}")
        return {"compact": True, "deleted": delete_before, "kept": keep_turns}

    # ========================================================================
    # 辅助方法
    # ========================================================================

    def _get_turn_count(self, session_id: str) -> int:
        """获取会话轮次数"""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM conversations WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    # ========================================================================
    # MemoryStore 兼容接口（供 CoreAgent 使用）
    # ========================================================================

    def get_context(self, agent_id: str, limit: int = 8, query: str = None) -> List[Dict[str, Any]]:
        """MemoryStore 兼容接口 - 获取上下文"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT role, content FROM conversations WHERE session_id = ? ORDER BY turn_index DESC LIMIT ?",
            (agent_id, limit * 2),
        ).fetchall()
        result = []
        for row in reversed(rows):
            result.append({"role": row["role"], "content": row["content"]})
        return result

    def add_event(self, agent_id: str, content: str, meta: Optional[Dict[str, Any]] = None) -> None:
        """MemoryStore 兼容接口 - 添加事件"""
        meta = meta or {}
        role = meta.get("role", "user") if "role" in meta else meta.get("kind", "user")
        self.add_turn(agent_id, role, content, tool_used=meta.get("type", "general"), metadata=meta)

    def get_stats(self) -> Dict[str, Any]:
        """返回各表的统计信息"""
        conn = self._get_conn()
        try:
            conversations = conn.execute("SELECT COUNT(*) as cnt FROM conversations").fetchone()["cnt"]
            facts = conn.execute("SELECT COUNT(*) as cnt FROM key_facts").fetchone()["cnt"]
            episodes = conn.execute("SELECT COUNT(*) as cnt FROM episodes").fetchone()["cnt"]
            entities = conn.execute("SELECT COUNT(*) as cnt FROM entities").fetchone()["cnt"]
            relations = conn.execute("SELECT COUNT(*) as cnt FROM relations").fetchone()["cnt"]
            actions = conn.execute("SELECT COUNT(*) as cnt FROM autonomous_actions").fetchone()["cnt"]
            return {
                "conversations": conversations,
                "key_facts": facts,
                "episodes": episodes,
                "entities": entities,
                "relations": relations,
                "autonomous_actions": actions,
            }
        except Exception as e:
            return {"error": str(e)}

    def close(self):
        """关闭数据库连接"""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    # ========================================================================
    # 图遍历能力 - 使用 SQLite 递归 CTE
    # ========================================================================

    def traverse_graph(
        self,
        start_entity: str,
        relation_types: List[str] = None,
        max_depth: int = 5,
        direction: str = "both"  # "outgoing", "incoming", "both"
    ) -> List[Dict[str, Any]]:
        """
        图遍历 - 使用 SQLite 递归 CTE

        参数：
            start_entity: 起始实体名称
            relation_types: 只遍历指定的关系类型
            max_depth: 最大遍历深度
            direction: 遍历方向 (outgoing/incoming/both)

        返回：
            遍历到的所有节点和路径
        """
        conn = self._get_conn()

        # 根据方向构建查询
        if direction == "outgoing":
            where_clause = "r.source_entity = gt.entity"
            select_next = "r.target_entity"
        elif direction == "incoming":
            where_clause = "r.target_entity = gt.entity"
            select_next = "r.source_entity"
        else:  # both
            where_clause = "(r.source_entity = gt.entity OR r.target_entity = gt.entity)"
            select_next = """CASE 
                WHEN r.source_entity = gt.entity THEN r.target_entity
                ELSE r.source_entity
            END"""

        # 关系类型过滤
        type_filter = ""
        if relation_types:
            placeholders = ",".join(["?"] * len(relation_types))
            type_filter = f"AND r.relation_type IN ({placeholders})"

        query = f"""
        WITH RECURSIVE graph_traverse(entity, depth, path) AS (
            -- 初始节点
            SELECT ?, 1, ?
            
            UNION ALL
            
            -- 递归遍历
            SELECT 
                {select_next},
                gt.depth + 1,
                gt.path || ' -> ' || {select_next}
            FROM relations r, graph_traverse gt
            WHERE {where_clause}
            AND gt.depth < ?
            {type_filter}
        )
        SELECT DISTINCT entity, MIN(depth) as depth, path FROM graph_traverse
        WHERE depth <= ?
        GROUP BY entity
        ORDER BY depth
        """

        # 执行查询
        params = [start_entity, start_entity, max_depth]
        if relation_types:
            params.extend(relation_types)
        params.append(max_depth)

        try:
            rows = conn.execute(query, params).fetchall()

            return [
                {
                    "entity": row["entity"],
                    "depth": row["depth"],
                    "path": row["path"]
                }
                for row in rows
            ]
        except Exception as e:
            print(f"[MemoryManager] Graph traversal error: {e}")
            return []

    def find_shortest_path(
        self,
        start_entity: str,
        end_entity: str,
        max_depth: int = 10
    ) -> Optional[List[str]]:
        """
        查找两个实体之间的最短路径

        参数：
            start_entity: 起始实体
            end_entity: 目标实体
            max_depth: 最大搜索深度

        返回：
            最短路径（实体列表），如果不存在返回 None
        """
        conn = self._get_conn()

        query = """
        WITH RECURSIVE path_finder(current_entity, path, depth) AS (
            -- 起始节点
            SELECT ?, ?, 1
            
            UNION ALL
            
            -- 递归扩展
            SELECT 
                CASE 
                    WHEN r.source_entity = pf.current_entity THEN r.target_entity
                    ELSE r.source_entity
                END,
                pf.path || ' -> ' || 
                CASE 
                    WHEN r.source_entity = pf.current_entity THEN r.target_entity
                    ELSE r.source_entity
                END,
                pf.depth + 1
            FROM relations r, path_finder pf
            WHERE (r.source_entity = pf.current_entity OR r.target_entity = pf.current_entity)
            AND pf.depth < ?
            AND pf.path NOT LIKE '%' || 
                CASE 
                    WHEN r.source_entity = pf.current_entity THEN r.target_entity
                    ELSE r.source_entity
                END || '%'
        )
        SELECT path, depth FROM path_finder
        WHERE current_entity = ?
        ORDER BY depth
        LIMIT 1
        """

        try:
            row = conn.execute(query, [start_entity, start_entity, max_depth, end_entity]).fetchone()

            if row:
                return row["path"].split(" -> ")
            return None
        except Exception as e:
            print(f"[MemoryManager] Find shortest path error: {e}")
            return None

    def get_entity_neighbors(
        self,
        entity: str,
        relation_type: str = None,
        direction: str = "both",
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        获取实体的邻居节点

        参数：
            entity: 实体名称
            relation_type: 只返回指定的关系类型
            direction: 遍历方向
            limit: 返回数量限制

        返回：
            邻居节点列表
        """
        conn = self._get_conn()

        if direction == "outgoing":
            where_clause = "r.source_entity = ?"
            neighbor_select = "r.target_entity as neighbor"
        elif direction == "incoming":
            where_clause = "r.target_entity = ?"
            neighbor_select = "r.source_entity as neighbor"
        else:
            where_clause = "(r.source_entity = ? OR r.target_entity = ?)"
            neighbor_select = """CASE 
                WHEN r.source_entity = ? THEN r.target_entity
                ELSE r.source_entity
            END as neighbor"""

        type_filter = ""
        if relation_type:
            type_filter = "AND r.relation_type = ?"

        query = f"""
        SELECT DISTINCT {neighbor_select}, r.relation_type, r.fact
        FROM relations r
        WHERE {where_clause}
        {type_filter}
        AND neighbor != ?
        LIMIT ?
        """

        try:
            params = []
            if direction == "both":
                params.extend([entity, entity, entity])
            else:
                params.append(entity)
            if relation_type:
                params.append(relation_type)
            params.extend([entity, limit])

            rows = conn.execute(query, params).fetchall()

            return [
                {
                    "entity": row["neighbor"],
                    "relation_type": row["relation_type"],
                    "fact": row["fact"]
                }
                for row in rows
            ]
        except Exception as e:
            print(f"[MemoryManager] Get neighbors error: {e}")
            return []

    def add_relation(
        self,
        source_entity: str,
        target_entity: str,
        relation_type: str,
        fact: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        添加实体关系

        参数：
            source_entity: 源实体
            target_entity: 目标实体
            relation_type: 关系类型
            fact: 关系描述
            metadata: 元数据

        返回：
            新关系的 ID
        """
        conn = self._get_conn()
        cur = conn.execute(
            "INSERT INTO relations (source_entity, target_entity, relation_type, fact, metadata) VALUES (?, ?, ?, ?, ?)",
            (source_entity, target_entity, relation_type, fact, json.dumps(metadata) if metadata else None),
        )
        conn.commit()
        return cur.lastrowid

    def search_entities_by_content(
        self,
        query: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        按内容搜索实体

        参数：
            query: 搜索关键词
            limit: 返回数量限制

        返回：
            匹配的实体列表
        """
        conn = self._get_conn()

        try:
            rows = conn.execute(
                "SELECT * FROM entities WHERE name LIKE ? OR summary LIKE ? ORDER BY last_updated DESC LIMIT ?",
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()

            return [
                {
                    "name": row["name"],
                    "summary": row["summary"],
                    "last_updated": row["last_updated"],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {}
                }
                for row in rows
            ]
        except Exception as e:
            print(f"[MemoryManager] Search entities error: {e}")
            return []
