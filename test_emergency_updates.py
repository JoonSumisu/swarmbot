
import asyncio
import os
import sys

# Add project root to path
sys.path.append("/root/swarmbot")

from swarmbot.config_manager import load_config
from swarmbot.llm_client import OpenAICompatibleClient, LLMConfig

async def test_failover():
    print("Testing Provider Failover...")
    
    # Create a client with a failing provider first, then a working one (mocked)
    failing_config = LLMConfig(base_url="http://fail.com", model="gpt-fail", timeout=1.0, api_key="dummy")
    working_config = LLMConfig(base_url="http://100.110.110.250:8888/v1", model="gpt-oss-20b", timeout=5.0, api_key="dummy")
    
    client = OpenAICompatibleClient(configs=[failing_config, working_config])
    
    try:
        # We expect the first to fail and second to be tried.
        # Since the second is real (internal network), it might work or timeout depending on environment.
        # But we want to see the "Provider 1 failed" log.
        print("Sending request...")
        response = await client.acompletion(
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=5
        )
        print(f"Success! Response: {response}")
    except Exception as e:
        print(f"Final Exception: {e}")

def test_config_loading():
    print("\nTesting Config Loading...")
    cfg = load_config()
    if hasattr(cfg, "providers") and len(cfg.providers) >= 2:
        print(f"Config loaded {len(cfg.providers)} providers.")
        print(f"Provider 1: {cfg.providers[0].base_url}")
        print(f"Provider 2: {cfg.providers[1].base_url}")
    else:
        print("Config loading failed to parse providers list.")

if __name__ == "__main__":
    test_config_loading()
    asyncio.run(test_failover())
