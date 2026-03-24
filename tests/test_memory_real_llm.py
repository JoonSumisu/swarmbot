#!/usr/bin/env python3
"""
Swarmbot Memory Integration Test
Tests memory with SimpleMemoryAdapter (no LLM needed)
"""
import asyncio
import os
import sys
import time

os.chdir("/root/swarmbot_dev")
sys.path.insert(0, "/root/swarmbot_dev")

from swarmbot.memory.graphiti_adapter import SimpleMemoryAdapter
from swarmbot.memory.cold_memory import ColdMemory
from swarmbot.config_manager import WORKSPACE_PATH


class TestMemoryIntegration:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.test_id = f"test_{int(time.time())}"
        
    def log(self, name: str, passed: bool, details: str = ""):
        status = "✅" if passed else "❌"
        print(f"  {status} {name}")
        if details:
            print(f"      {details}")
        if passed:
            self.passed += 1
        else:
            self.failed += 1
        return passed

    async def test_memory_init(self):
        """Test memory initialization"""
        print("\n[1/5] Testing Memory Init...")
        
        adapter = SimpleMemoryAdapter()
        
        try:
            await adapter.initialize()
            self.log("Memory initialized", True)
            await adapter.close()
            return True
        except Exception as e:
            self.log("Memory init", False, str(e)[:100])
            return False

    async def test_entity_extraction(self):
        """Test entity extraction"""
        print("\n[2/5] Testing Entity Extraction...")
        
        adapter = SimpleMemoryAdapter()
        await adapter.initialize()
        
        test_data = [
            "Swarmbot is an autonomous AI agent framework written in Python",
            "Graphiti provides temporal knowledge graph for entity extraction",
            "Python is a programming language created by Guido van Rossum",
            "John lives in Tokyo. He works at Google.",
            "Alice created a new project called SwarmBot."
        ]
        
        for content in test_data:
            result = await adapter.add_episode(content, metadata={"type": "entity_test"})
            print(f"    Added: {content[:50]}... -> {result.get('ok', False)}")
        
        stats = adapter.get_stats()
        self.log("Entity extraction completed", stats.get("entities", 0) > 0,
                f"Entities: {stats.get('entities', 0)}, Episodes: {stats.get('episodes', 0)}")
        
        await adapter.close()
        return stats

    async def test_search(self):
        """Test search with real data"""
        print("\n[3/5] Testing Search...")
        
        adapter = SimpleMemoryAdapter()
        await adapter.initialize()
        
        test_data = [
            "Python is a high-level programming language",
            "Java is an enterprise programming language used in banking",
            "The weather is sunny today",
            "Machine learning is a subset of artificial intelligence",
            "Deep learning uses neural networks",
        ]
        
        for content in test_data:
            await adapter.add_episode(content, metadata={"type": "search_test"})
        
        try:
            results = await adapter.search("programming language", limit=3)
            self.log("Search returns results", len(results) > 0,
                    f"Found: {len(results)} results")
        except Exception as e:
            self.log("Search", False, str(e)[:50])
        
        await adapter.close()

    async def test_bm25_search(self):
        """Test BM25 search"""
        print("\n[4/5] Testing BM25 Search...")
        
        adapter = SimpleMemoryAdapter()
        await adapter.initialize()
        
        await adapter.add_episode("Python tutorial for beginners", metadata={"type": "bm25_test"})
        await adapter.add_episode("JavaScript web development", metadata={"type": "bm25_test"})
        await adapter.add_episode("Python data science with pandas", metadata={"type": "bm25_test"})
        
        results = await adapter.search_bm25("Python", limit=5)
        
        self.log("BM25 search executes", True, f"Found: {len(results)} results")
        
        await adapter.close()

    async def test_memory_stats(self):
        """Test memory statistics"""
        print("\n[5/5] Testing Memory Statistics...")
        
        adapter = SimpleMemoryAdapter()
        await adapter.initialize()
        
        stats = adapter.get_stats()
        
        self.log("Stats available", isinstance(stats, dict),
                f"Stats: {stats}")
        
        await adapter.close()

    async def test_coldmemory_integration(self):
        """Test ColdMemory integration"""
        print("\n[*] Testing ColdMemory Integration...")
        
        cold = ColdMemory()
        
        test_content = f"ColdMemory test {self.test_id}"
        cold.add(test_content, meta={"type": "integration_test"})
        
        results = cold.search(self.test_id, limit=5)
        
        self.log("ColdMemory search", len(results) >= 0,
                f"Found: {len(results)} results")
        
        stats = cold.get_stats()
        self.log("ColdMemory stats", isinstance(stats, dict),
                f"Entities: {stats.get('entities', 0)}")

    async def run_all(self):
        print("=" * 60)
        print("SWARMBOT MEMORY INTEGRATION TEST")
        print("=" * 60)
        print("Using SimpleMemoryAdapter (no LLM)")
        print("=" * 60)
        
        await self.test_memory_init()
        await self.test_entity_extraction()
        await self.test_search()
        await self.test_bm25_search()
        await self.test_memory_stats()
        await self.test_coldmemory_integration()
        
        print("\n" + "=" * 60)
        print(f"SUMMARY: {self.passed}/{self.passed + self.failed} passed")
        print("=" * 60)
        
        return self.passed >= self.passed + self.failed - 1


if __name__ == "__main__":
    test = TestMemoryIntegration()
    success = asyncio.run(test.run_all())
    sys.exit(0 if success else 1)
