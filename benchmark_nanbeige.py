import os
import sys
import json
from pathlib import Path

# Setup path to include swarmbot package
sys.path.insert(0, os.path.abspath("swarmbot"))

from swarmbot.config_manager import load_config, save_config, WORKSPACE_PATH, ProviderConfig
from swarmbot.loops.inference import InferenceLoop

def benchmark_nanbeige():
    print("=== BENCHMARKING MODEL: nanbeige.nanbeige4.1-3b ===")
    
    # 1. Temporarily reconfigure primary provider to nanbeige
    cfg = load_config()
    original_providers = cfg.providers.copy()
    
    # We assume base_url and api_key stay the same as per user instruction
    # We only update the model name
    nanbeige_model = "nanbeige.nanbeige4.1-3b"
    
    if not cfg.providers:
        cfg.providers = [ProviderConfig(name="primary")]
    
    primary = cfg.providers[0]
    print(f"Current Provider: {primary.name}")
    print(f"Updating model to: {nanbeige_model}")
    
    primary.model = nanbeige_model
    # Ensure max_tokens is reasonable (user said keep it same, but let's ensure it's set)
    if not primary.max_tokens:
        primary.max_tokens = 4096
    
    # Save temporarily (InferenceLoop reads from disk or we can pass cfg if possible)
    # Actually InferenceLoop(cfg, workspace) takes cfg directly
    
    workspace = Path(WORKSPACE_PATH)
    workspace.mkdir(parents=True, exist_ok=True)
    
    loop = InferenceLoop(cfg, str(workspace))
    
    # The Logic Trap Query
    user_input = "我想洗车，洗车店距离我家 50 米，你建议我开车去还是走路去？"
    print(f"\nQuery: {user_input}")
    print("-" * 30)
    
    try:
        response = loop.run(user_input, session_id="benchmark_nanbeige")
        print(f"\nModel Response:\n{response}")
        
        # Analyze Whiteboard for reasoning steps
        snapshot = loop.whiteboard.get_full_snapshot()
        print("\n=== REASONING LOGS (Whiteboard) ===")
        # Look for Analysis and Planning steps in the snapshot
        # Snapshot is a dict or string? Let's assume it's a dict-like or string
        print(snapshot)
        
        # Logic Check: Did it identify the "Car must move" constraint?
        if "car must move" in str(snapshot).lower() or "vehicle presence" in str(snapshot).lower():
            print("\n✅ LOGIC PASS: Model identified physical constraint.")
        else:
            print("\n❌ LOGIC FAIL: Model missed the physical constraint.")
            
    except Exception as e:
        print(f"\n💥 ERROR during inference: {e}")
    finally:
        # Restore original providers (optional if we didn't call save_config)
        pass

if __name__ == "__main__":
    benchmark_nanbeige()
