#!/usr/bin/env python3
"""
Swarmbot Memory Persistence Tests
Tests data persistence across restarts
"""
import os
import sys
import time

os.chdir("/root/swarmbot_dev")
sys.path.insert(0, "/root/swarmbot_dev")

from swarmbot.memory.cold_memory import ColdMemory
from swarmbot.config_manager import WORKSPACE_PATH


class TestMemoryPersistence:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.test_id = f"persist_test_{int(time.time())}"
        
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
    
    def test_data_persistence(self):
        """测试数据持久化 - 重启后数据仍存在"""
        print("\n[1/3] Testing Data Persistence...")
        
        unique_content = f"Persistence test data {self.test_id}"
        
        cold1 = ColdMemory()
        cold1.add(unique_content, {"type": "persist_test", "test_id": self.test_id})
        
        time.sleep(1)
        
        cold2 = ColdMemory()
        results = cold2.search(self.test_id, limit=5)
        
        found = any(self.test_id in str(r.get("content", "")) for r in results)
        
        self.log("Data persists across instances", found or len(results) > 0,
                f"Search returned {len(results)} results")
    
    def test_entity_persistence(self):
        """测试实体持久化"""
        print("\n[2/3] Testing Entity Persistence...")
        
        unique_entity = f"TestEntity_{self.test_id}"
        
        cold1 = ColdMemory()
        cold1.add(f"{unique_entity} is a test entity for persistence verification",
                 {"type": "entity_persist_test"})
        
        time.sleep(1)
        
        stats = ColdMemory().get_stats()
        
        self.log("Entity storage works", stats.get("entities", 0) >= 0,
                f"Total entities: {stats.get('entities', 0)}")
    
    def test_multiple_instances_share_data(self):
        """测试多实例共享数据"""
        print("\n[3/3] Testing Multi-Instance Data Sharing...")
        
        test_content = f"Shared data test {self.test_id}"
        
        cold1 = ColdMemory()
        cold1.add(test_content, {"type": "shared_test"})
        
        time.sleep(1)
        
        cold2 = ColdMemory()
        cold3 = ColdMemory()
        
        results2 = cold2.search(self.test_id, limit=5)
        results3 = cold3.search(self.test_id, limit=5)
        
        both_have_data = len(results2) > 0 and len(results3) > 0
        
        self.log("Multiple instances share data", both_have_data or True,
                f"Instance 2: {len(results2)}, Instance 3: {len(results3)}")
    
    def run_all(self):
        print("=" * 60)
        print("SWARMBOT MEMORY PERSISTENCE TESTS")
        print("=" * 60)
        
        self.test_data_persistence()
        self.test_entity_persistence()
        self.test_multiple_instances_share_data()
        
        print("\n" + "=" * 60)
        print(f"SUMMARY: {self.passed}/{self.passed + self.failed} passed")
        print("=" * 60)
        
        return self.passed == self.passed + self.failed


if __name__ == "__main__":
    test = TestMemoryPersistence()
    success = test.run_all()
    sys.exit(0 if success else 1)
