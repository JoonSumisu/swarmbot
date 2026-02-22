from __future__ import annotations

import os
import json
import sqlite3
import time
import math
from typing import List, Dict, Any, Optional

class EmbeddedQMD:
    """
    Lightweight, embedded QMD implementation using SQLite.
    Removes dependency on external npm 'qmd' package.
    
    Features:
    - Text storage
    - Basic BM25-like keyword search (or simple LIKE search for v1)
    - Collection management via tables
    """
    
    def __init__(self, root_path: str):
        self.root = root_path
        os.makedirs(self.root, exist_ok=True)
        self.db_path = os.path.join(self.root, "qmd.sqlite")
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Collections table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS collections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    created_at REAL
                )
            """)
            # Documents table (FTS5 virtual table for search if supported, else standard)
            # Checking FTS5 support
            try:
                cursor.execute("CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(content, collection_id, meta)")
                self.has_fts = True
            except sqlite3.OperationalError:
                self.has_fts = False
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS documents (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        collection_id INTEGER,
                        content TEXT,
                        meta TEXT,
                        created_at REAL,
                        FOREIGN KEY(collection_id) REFERENCES collections(id)
                    )
                """)

    def _get_collection_id(self, name: str) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM collections WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                return row[0]
            cursor.execute("INSERT INTO collections (name, created_at) VALUES (?, ?)", (name, time.time()))
            return cursor.lastrowid

    def add(self, content: str, collection: str = "default", meta: Dict[str, Any] = None) -> None:
        coll_id = self._get_collection_id(collection)
        meta_json = json.dumps(meta or {})
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if self.has_fts:
                cursor.execute("INSERT INTO documents_fts (collection_id, content, meta) VALUES (?, ?, ?)", 
                               (coll_id, content, meta_json))
            else:
                cursor.execute("INSERT INTO documents (collection_id, content, meta, created_at) VALUES (?, ?, ?, ?)",
                               (coll_id, content, meta_json, time.time()))

    def search(self, query: str, collection: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Build query
            sql = ""
            params = []
            
            if self.has_fts:
                sql = "SELECT content, meta FROM documents_fts WHERE content MATCH ?"
                # Simple FTS query sanitization
                safe_query = query.replace('"', '""')
                params.append(f'"{safe_query}"')
                
                if collection:
                    coll_id = self._get_collection_id(collection)
                    sql += " AND collection_id = ?"
                    params.append(coll_id)
                
                sql += f" ORDER BY rank LIMIT {limit}"
            else:
                # Fallback to LIKE
                sql = "SELECT content, meta FROM documents WHERE content LIKE ?"
                params.append(f"%{query}%")
                
                if collection:
                    coll_id = self._get_collection_id(collection)
                    sql += " AND collection_id = ?"
                    params.append(coll_id)
                
                sql += f" ORDER BY created_at DESC LIMIT {limit}"

            cursor.execute(sql, tuple(params))
            results = []
            for row in cursor.fetchall():
                content, meta_raw = row
                results.append({
                    "content": content,
                    "meta": json.loads(meta_raw) if meta_raw else {}
                })
            return results

    def embed(self):
        # No-op for local sqlite (already indexed by FTS or inserted)
        pass
