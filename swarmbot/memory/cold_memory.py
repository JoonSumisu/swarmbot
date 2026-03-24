from __future__ import annotations

import os
import asyncio
from typing import Any, Dict, List, Optional
from .base import MemoryStore
from ..config_manager import WORKSPACE_PATH, load_config


class ColdMemory(MemoryStore):
    """
    L4 Cold Memory: Semantic Search DB (QMD).
    Stores facts, experiences, theories derived from Warm Memory.
    
    Now uses Graphiti + Kuzu + Nomic Embedding for intelligent entity extraction.
    """
    _graphiti_instance: Optional[Any] = None

    def __init__(self, default_collection: str = "default") -> None:
        self.default_collection = default_collection
        self._events: Dict[str, List[Dict[str, Any]]] = {}
        self._ensure_graphiti()

    def _ensure_graphiti(self):
        if ColdMemory._graphiti_instance is not None:
            return
        try:
            from .graphiti_adapter import GraphitiMemoryAdapter
            config = load_config()
            provider = config.providers[0] if config.providers else None
            ColdMemory._graphiti_instance = GraphitiMemoryAdapter(provider_config=provider)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import nest_asyncio
                    nest_asyncio.apply()
                    loop.run_until_complete(ColdMemory._graphiti_instance.initialize())
                else:
                    loop.run_until_complete(ColdMemory._graphiti_instance.initialize())
            except Exception as e:
                print(f"[ColdMemory] Graphiti init (sync): {e}")
        except Exception as e:
            print(f"[ColdMemory] Failed to create Graphiti adapter: {e}")
            ColdMemory._graphiti_instance = None

    def add(self, content: str, meta: Dict[str, Any] | None = None) -> None:
        if ColdMemory._graphiti_instance and content:
            try:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(
                    ColdMemory._graphiti_instance.add_episode(
                        content=content,
                        metadata=meta or {},
                    )
                )
            except Exception as e:
                pass

    def search(self, query: str, limit: int = 5) -> List[Any]:
        results = []
        if ColdMemory._graphiti_instance:
            try:
                loop = asyncio.get_event_loop()
                graphiti_results = loop.run_until_complete(
                    ColdMemory._graphiti_instance.search(query, limit=limit)
                )
                for r in graphiti_results:
                    results.append(r)
            except Exception as e:
                pass
        return results

    def search_text(self, query: str, limit: int = 5) -> str:
        results = self.search(query, limit=limit)
        if not results:
            return ""
        return "\n".join([str(r) for r in results])

    def add_event(self, agent_id: str, content: str, meta: Dict[str, Any] | None = None) -> None:
        self.add(content, meta)

    def get_context(self, agent_id: str, limit: int = 20, query: str | None = None) -> List[Dict[str, Any]]:
        if query:
            return self.search(query, limit)
        return []

    def search_bm25(self, query: str, limit: int = 5) -> List[Any]:
        """BM25 全文搜索"""
        results = []
        if ColdMemory._graphiti_instance:
            try:
                loop = asyncio.get_event_loop()
                graphiti_results = loop.run_until_complete(
                    ColdMemory._graphiti_instance.search_bm25(query, limit=limit)
                )
                results = graphiti_results
            except Exception as e:
                pass
        return results

    def search_hybrid(self, query: str, limit: int = 5) -> List[Any]:
        """混合搜索"""
        return self.search(query, limit)

    def get_related_entities(self, entity_name: str, depth: int = 2, limit: int = 10) -> List[Dict[str, Any]]:
        """获取关联实体"""
        if ColdMemory._graphiti_instance:
            try:
                loop = asyncio.get_event_loop()
                return loop.run_until_complete(
                    ColdMemory._graphiti_instance.get_related_entities(entity_name, depth, limit)
                )
            except Exception as e:
                pass
        return []

    def get_stats(self) -> Dict[str, Any]:
        """获取记忆统计"""
        if ColdMemory._graphiti_instance:
            try:
                return ColdMemory._graphiti_instance.get_stats()
            except Exception as e:
                pass
        return {"entities": 0, "episodes": 0, "relations": 0}
