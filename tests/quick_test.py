#!/usr/bin/env python3
"""Quick memory test with real LLM"""
import asyncio
import sys
import os
sys.path.insert(0, "/root/swarmbot_dev")

from swarmbot.memory.graphiti_adapter import GraphitiMemoryAdapter
from swarmbot.config_manager import ProviderConfig

async def quick_test():
    print("Quick memory test with real LLM...")
    
    provider = ProviderConfig(
        name="test",
        base_url="http://100.110.110.250:7788/v1",
        api_key="test-key",
        model="qwen3.5-35b-a3b-claude-4.6-opus-reasoning-distilled-i1",
    )
    
    adapter = GraphitiMemoryAdapter(provider_config=provider)
    
    print("1. Initializing Graphiti...")
    await adapter.initialize()
    print("   ✅ Initialized")
    
    print("2. Adding episode...")
    result = await adapter.add_episode("Python is a programming language", {"test": True})
    print(f"   ✅ Added: {result}")
    
    print("3. Getting stats...")
    stats = adapter.get_stats()
    print(f"   ✅ Stats: {stats}")
    
    print("4. Searching...")
    try:
        results = await adapter.search("Python", limit=3)
        print(f"   ✅ Found: {len(results)} results")
    except Exception as e:
        print(f"   ⚠️  Search error: {str(e)[:50]}")
    
    await adapter.close()
    print("\n✅ Test complete!")

if __name__ == "__main__":
    asyncio.run(quick_test())
