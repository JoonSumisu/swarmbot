#!/usr/bin/env python3
"""Simple memory test - no LLM blocking"""
import sys
import os
sys.path.insert(0, "/root/swarmbot_dev")

from swarmbot.memory.cold_memory import ColdMemory

def test_basic():
    print("Testing basic ColdMemory (no LLM)...")
    
    cold = ColdMemory()
    print("✅ ColdMemory created")
    
    cold.add("Test memory", {"test": True})
    print("✅ Add memory")
    
    results = cold.search("test", limit=5)
    print(f"✅ Search: {len(results)} results")
    
    stats = cold.get_stats()
    print(f"✅ Stats: {stats}")
    
    print("\n✅ Basic test complete!")

if __name__ == "__main__":
    test_basic()
