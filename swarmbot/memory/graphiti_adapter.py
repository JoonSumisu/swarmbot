from __future__ import annotations

import os
import sqlite3
import json
import hashlib
from typing import Any, Dict, List, Optional
from datetime import datetime

from ..config_manager import WORKSPACE_PATH


class SimpleMemoryAdapter:
    """Simple memory adapter using SQLite (no external dependencies)"""
    
    def __init__(
        self,
        db_path: Optional[str] = None,
    ):
        self.db_path = db_path or os.path.join(WORKSPACE_PATH, "memory.sqlite")
        self._conn = None
    
    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._create_tables()
        return self._conn
    
    def _create_tables(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                source TEXT DEFAULT 'swarmbot',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            );
            
            CREATE TABLE IF NOT EXISTS entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
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
        """)
        conn.commit()
    
    async def initialize(self) -> None:
        self._get_conn()
        print(f"[Memory] Using SQLite: {self.db_path}")
    
    def _extract_entities_simple(self, content: str) -> List[Dict[str, str]]:
        """Simple entity extraction (no LLM needed)"""
        import re
        
        entities = []
        
        # Extract capitalized words as entities
        words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', content)
        for word in words:
            if len(word) > 2:
                entities.append({
                    "name": word,
                    "summary": word,
                    "type": "unknown"
                })
        
        # Extract common patterns
        patterns = [
            (r'(\w+)\s+is\s+a\s+(\w+)', "is_a"),
            (r'(\w+)\s+lives?\s+in\s+(\w+)', "lives_in"),
            (r'(\w+)\s+works?\s+at\s+(\w+)', "works_at"),
            (r'(\w+)\s+created\s+(\w+)', "created"),
            (r'(\w+)\s+likes?\s+(\w+)', "likes"),
        ]
        
        relations = []
        for pattern, rel_type in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                if len(match) == 2:
                    source, target = match
                    relations.append({
                        "source": source,
                        "target": target,
                        "type": rel_type
                    })
        
        return entities, relations
    
    async def add_episode(
        self,
        content: str,
        entities: Optional[List[Dict[str, str]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        try:
            conn = self._get_conn()
            
            # Store episode
            cursor = conn.execute(
                "INSERT INTO episodes (content, source, metadata) VALUES (?, ?, ?)",
                (content, "swarmbot", json.dumps(metadata) if metadata else None)
            )
            episode_id = cursor.lastrowid
            
            # Extract and store entities
            if entities is None:
                extracted_entities, extracted_relations = self._extract_entities_simple(content)
            else:
                extracted_entities = entities
                extracted_relations = []
            
            for entity in extracted_entities:
                conn.execute(
                    "INSERT OR REPLACE INTO entities (name, summary, last_updated) VALUES (?, ?, CURRENT_TIMESTAMP)",
                    (entity["name"], entity.get("summary", ""))
                )
            
            # Store relations
            for rel in extracted_relations:
                conn.execute(
                    "INSERT INTO relations (source_entity, target_entity, relation_type) VALUES (?, ?, ?)",
                    (rel["source"], rel["target"], rel["type"])
                )
            
            conn.commit()
            
            return {
                "ok": True,
                "episode_id": episode_id,
                "entities": len(extracted_entities),
                "relations": len(extracted_relations)
            }
        except Exception as e:
            print(f"[Memory] add_episode error: {e}")
            return {"ok": False, "error": str(e)}
    
    async def search(
        self,
        query: str,
        limit: int = 5,
        time_range: Optional[Dict[str, datetime]] = None,
    ) -> List[Dict[str, Any]]:
        try:
            conn = self._get_conn()
            
            # Search in episodes (simple LIKE search)
            cursor = conn.execute(
                "SELECT * FROM episodes WHERE content LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f"%{query}%", limit)
            )
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                results.append({
                    "uuid": str(row["id"]),
                    "content": row["content"],
                    "name": f"Episode_{row['id']}",
                    "summary": row["content"][:100] + "..." if len(row["content"]) > 100 else row["content"],
                    "score": 1.0,
                })
            
            # Also search entities
            cursor = conn.execute(
                "SELECT * FROM entities WHERE name LIKE ? OR summary LIKE ? LIMIT ?",
                (f"%{query}%", f"%{query}%", limit)
            )
            rows = cursor.fetchall()
            
            for row in rows:
                results.append({
                    "uuid": f"entity_{row['id']}",
                    "content": row["summary"] or row["name"],
                    "name": row["name"],
                    "summary": row["summary"],
                    "score": 0.8,
                })
            
            return results[:limit]
        except Exception as e:
            print(f"[Memory] Search error: {e}")
            return []
    
    async def search_bm25(
        self,
        query: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        return await self.search(query, limit)
    
    async def search_hybrid(
        self,
        query: str,
        limit: int = 5,
        time_range: Optional[Dict[str, datetime]] = None,
    ) -> List[Dict[str, Any]]:
        return await self.search(query, limit, time_range)
    
    async def get_related_entities(
        self,
        entity_name: str,
        depth: int = 2,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        try:
            conn = self._get_conn()
            
            # Find relations where entity is source
            cursor = conn.execute(
                "SELECT target_entity, relation_type FROM relations WHERE source_entity = ? LIMIT ?",
                (entity_name, limit)
            )
            rows = cursor.fetchall()
            
            related = []
            for row in rows:
                related.append({
                    "name": row["target_entity"],
                    "summary": "",
                    "relation": row["relation_type"],
                })
            
            # Find relations where entity is target
            cursor = conn.execute(
                "SELECT source_entity, relation_type FROM relations WHERE target_entity = ? LIMIT ?",
                (entity_name, limit)
            )
            rows = cursor.fetchall()
            
            for row in rows:
                related.append({
                    "name": row["source_entity"],
                    "summary": "",
                    "relation": row["relation_type"],
                })
            
            return related[:limit]
        except Exception as e:
            print(f"[Memory] get_related_entities error: {e}")
            return []
    
    async def get_entity_history(
        self,
        entity_name: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        try:
            conn = self._get_conn()
            cursor = conn.execute(
                "SELECT * FROM entities WHERE name = ? ORDER BY last_updated DESC LIMIT ?",
                (entity_name, limit)
            )
            rows = cursor.fetchall()
            
            return [
                {
                    "name": row["name"],
                    "summary": row["summary"],
                }
                for row in rows
            ]
        except Exception as e:
            return []
    
    async def batch_add(
        self,
        items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        results = []
        for item in items:
            result = await self.add_episode(
                content=item.get("content", ""),
                entities=item.get("entities"),
                metadata=item.get("metadata"),
            )
            results.append(result)
        return {"ok": True, "count": len(items), "results": results}
    
    def get_stats(self) -> Dict[str, Any]:
        try:
            conn = self._get_conn()
            
            entity_count = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
            episode_count = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
            relation_count = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
            
            return {
                "entities": entity_count,
                "episodes": episode_count,
                "relations": relation_count,
            }
        except Exception as e:
            return {"entities": 0, "episodes": 0, "relations": 0}
    
    async def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


# Backward compatible alias
GraphitiMemoryAdapter = SimpleMemoryAdapter
