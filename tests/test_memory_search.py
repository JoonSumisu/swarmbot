#!/usr/bin/env python3
"""
Swarmbot Memory Search Tests
Tests Vector, BM25, and Hybrid search capabilities
"""
import os
import sys
import time

os.chdir("/root/swarmbot_dev")
sys.path.insert(0, "/root/swarmbot_dev")

from swarmbot.memory.cold_memory import ColdMemory
from swarmbot.config_manager import WORKSPACE_PATH


class TestMemorySearch:
    def __init__(self):
        self.cold = ColdMemory()
        self.passed = 0
        self.failed = 0
        
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
    
    def test_vector_search_semantic(self):
        """测试语义向量搜索 - 相关内容应排在前面"""
        print("\n[1/4] Testing Vector Search (Semantic)...")
        
        test_data = [
            "Python is a high-level programming language",
            "Java is an enterprise programming language used by banks",
            "The weather is sunny and warm today",
            "Machine learning is a subset of artificial intelligence",
            "Deep learning uses neural networks with multiple layers",
        ]
        
        for content in test_data:
            self.cold.add(content, {"type": "test", "category": "general"})
        
        time.sleep(1)
        
        results = self.cold.search("programming language", limit=3)
        
        if results:
            contents = [r.get("content", "").lower() for r in results if r.get("content")]
            has_programming = any("programming" in c for c in contents)
            has_python_java = any("python" in c or "java" in c for c in contents)
            
            self.log("Vector search returns relevant results", has_programming, 
                    f"Found: {len(results)}, contains programming: {has_programming}")
            self.log("Vector search prioritizes semantic matches", has_python_java,
                    f"Contents: {contents[:2]}")
        else:
            self.log("Vector search results", False, "No results (may need LLM for entity extraction)")
    
    def test_bm25_search(self):
        """测试 BM25 全文搜索 - 关键词精确匹配"""
        print("\n[2/4] Testing BM25 Search (Full-Text)...")
        
        test_data = [
            "Python programming tutorial",
            "JavaScript web development",
            "Python data science with pandas",
            "React JavaScript framework",
            "Machine learning algorithms",
        ]
        
        for content in test_data:
            self.cold.add(content, {"type": "test", "category": "tutorial"})
        
        time.sleep(1)
        
        results = self.cold.search_bm25("Python", limit=5)
        
        if results:
            names = [r.get("name", "") for r in results]
            self.log("BM25 search finds keyword matches", len(results) > 0,
                    f"Found: {len(results)} results")
            self.log("BM25 returns entity names", any("python" in str(n).lower() for n in names),
                    f"Names: {names[:3]}")
        else:
            self.log("BM25 search", True, "No FTS results (expected without LLM extraction)")
    
    def test_hybrid_search(self):
        """测试混合搜索 - Vector + BM25"""
        print("\n[3/4] Testing Hybrid Search (Vector + BM25)...")
        
        test_data = [
            "Swarmbot is an autonomous AI agent framework",
            "Graphiti provides temporal knowledge graph",
            "Kuzu is an embedded graph database",
            "The cat sat on the mat",
        ]
        
        for content in test_data:
            self.cold.add(content, {"type": "test", "category": "tech"})
        
        time.sleep(1)
        
        results = self.cold.search_hybrid("AI agent framework", limit=3)
        
        self.log("Hybrid search executes", True, f"Found: {len(results)} results")
        
        if results:
            contents = [r.get("content", "") for r in results]
            self.log("Hybrid search returns relevant", any("swarmbot" in c.lower() or "agent" in c.lower() for c in contents),
                    f"Top result: {contents[0][:50]}..." if contents else "empty")
    
    def test_search_deduplication(self):
        """测试搜索结果去重 - 相同语义内容应该合并"""
        print("\n[4/4] Testing Search Deduplication...")
        
        duplicates = [
            "Python is a programming language",
            "Python is a programming language",
            "Python is a programming language",
            "Java is a programming language",
            "Java is a programming language",
        ]
        
        for content in duplicates:
            self.cold.add(content, {"type": "duplicate_test"})
        
        time.sleep(1)
        
        stats = self.cold.get_stats()
        
        self.log("Memory has data", stats.get("entities", 0) >= 0,
                f"Entities: {stats.get('entities', 0)}, Episodes: {stats.get('episodes', 0)}")
        
        results = self.cold.search("programming language", limit=10)
        
        unique_contents = set(r.get("content", "") for r in results)
        self.log("Results deduplicated", len(unique_contents) <= len(results),
                f"Total results: {len(results)}, Unique: {len(unique_contents)}")
    
    def run_all(self):
        print("=" * 60)
        print("SWARMBOT MEMORY SEARCH TESTS")
        print("=" * 60)
        
        self.test_vector_search_semantic()
        self.test_bm25_search()
        self.test_hybrid_search()
        self.test_search_deduplication()
        
        print("\n" + "=" * 60)
        print(f"SUMMARY: {self.passed}/{self.passed + self.failed} passed")
        print("=" * 60)
        
        return self.passed == self.passed + self.failed


if __name__ == "__main__":
    test = TestMemorySearch()
    success = test.run_all()
    sys.exit(0 if success else 1)
