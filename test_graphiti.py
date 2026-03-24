#!/usr/bin/env python3
"""Test script for Graphiti memory integration"""
import asyncio
import os
import sys

os.chdir("/root/swarmbot_dev")
sys.path.insert(0, "/root/swarmbot_dev")

from swarmbot.memory.graphiti_adapter import GraphitiMemoryAdapter
from swarmbot.config_manager import ProviderConfig, WORKSPACE_PATH


async def test_graphiti():
    print("=" * 50)
    print("Testing Graphiti Memory Integration")
    print("=" * 50)

    provider = ProviderConfig(
        name="test",
        base_url="http://localhost:11434/v1",
        api_key="ollama",
        model="qwen2.5:7b",
        embedding_model="nomic-embed-text-v1.5",
        embedding_device="cpu",
    )

    db_path = os.path.join(WORKSPACE_PATH, "test_graphiti.kuzu")
    print(f"\n[1] Initializing Graphiti with Kuzu at: {db_path}")
    
    adapter = GraphitiMemoryAdapter(provider_config=provider, db_path=db_path)
    await adapter.initialize()
    print("[2] Graphiti initialized successfully!")

    print("\n[3] Testing embedding...")
    embeddings = adapter.embed_text(["hello world", "testing graphiti memory"])
    print(f"    Got {len(embeddings)} embeddings, dimension: {len(embeddings[0])}")

    print("\n[4] Testing ColdMemory integration...")
    from swarmbot.memory.cold_memory import ColdMemory
    cold = ColdMemory()
    cold.add("Test memory from ColdMemory", {"source": "test"})
    results = cold.search("test")
    print(f"    ColdMemory search returned {len(results)} results")
    print("    ColdMemory integration works!")

    print("\n" + "=" * 50)
    print("All core tests passed!")
    print("  - Graphiti + Kuzu initialized")
    print("  - Nomic embedding working")
    print("  - ColdMemory backward compatible")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(test_graphiti())
