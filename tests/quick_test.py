#!/usr/bin/env python3
"""Quick memory test (no LLM needed)"""
import asyncio
import sys
import os
import tempfile
sys.path.insert(0, "/root/swarmbot_dev")

from swarmbot.memory.graphiti_adapter import SimpleMemoryAdapter

async def quick_test():
    print("Quick memory test...")
    
    # Use temp directory to avoid conflicts
    db_dir = tempfile.mkdtemp(prefix="memory_test_")
    db_path = os.path.join(db_dir, "test.sqlite")
    
    adapter = SimpleMemoryAdapter(db_path=db_path)
    
    try:
        print("1. Initializing...")
        await adapter.initialize()
        print("   ✅ Initialized")
        
        print("2. Adding episode...")
        result = await adapter.add_episode("Python is a programming language", metadata={"test": True})
        print(f"   ✅ Added: {result}")
        
        print("3. Adding another episode...")
        result = await adapter.add_episode("John lives in Tokyo. He works at Google.")
        print(f"   ✅ Added: {result}")
        
        print("4. Getting stats...")
        stats = adapter.get_stats()
        print(f"   ✅ Stats: {stats}")
        
        print("5. Searching...")
        results = await adapter.search("Python", limit=3)
        print(f"   ✅ Found: {len(results)} results")
        for r in results:
            print(f"      - {r['name']}: {r['content'][:50]}...")
        
        print("6. Searching entities...")
        results = await adapter.search("John", limit=3)
        print(f"   ✅ Found: {len(results)} results")
        for r in results:
            print(f"      - {r['name']}: {r['content'][:50]}...")
        
        print("7. Getting related entities...")
        related = await adapter.get_related_entities("John", limit=3)
        print(f"   ✅ Related: {len(related)} entities")
        for r in related:
            print(f"      - {r['name']} ({r['relation']})")
        
        await adapter.close()
        print("\n✅ Test complete!")
    finally:
        import shutil
        shutil.rmtree(db_dir, ignore_errors=True)

if __name__ == "__main__":
    asyncio.run(quick_test())
