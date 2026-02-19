
import os
import sys
import pytest
from swarmbot.config_manager import load_config, save_config
from swarmbot.swarm.manager import SwarmManager
from swarmbot.middleware.long_horizon import HierarchicalTaskGraph, WorkMapMemory

# Setup environment variables for test
os.environ["SWARMBOT_TEST"] = "1"

@pytest.fixture
def setup_config():
    """Setup a valid configuration for testing."""
    cfg = load_config()
    cfg.provider.base_url = "https://api.moonshot.cn/v1"
    # Note: Using key from env or config file
    cfg.provider.model = "kimi-k2-turbo-preview"
    cfg.provider.max_tokens = 126000
    save_config(cfg)
    return cfg

def test_long_horizon_planning(setup_config):
    """
    Verify Long Horizon middleware:
    1. Plan decomposition
    2. WorkMap skill matching
    3. Execution flow
    """
    print("\n[Test] Long Horizon Middleware")
    cfg = setup_config
    manager = SwarmManager.from_swarmbot_config(cfg)
    
    # Force architecture to verify routing
    manager._architecture = "long_horizon"
    
    # 1. Test WorkMap Loading
    work_map = WorkMapMemory(manager.llm)
    assert len(work_map.skills) > 0
    print(f"✓ WorkMap loaded {len(work_map.skills)} skills.")
    
    # 2. Test Planning (Mocked Response for Stability)
    # We patch the completion method to return a deterministic plan JSON
    # This avoids burning API tokens and flaky LLM responses in unit tests
    
    original_completion = manager.llm.completion
    
    def mock_completion(messages, **kwargs):
        content = messages[-1]["content"]
        if "分解为" in content: # Planning prompt
            return {
                "choices": [{
                    "message": {
                        "content": '[{"id": "t1", "description": "Step 1", "dependencies": []}, {"id": "t2", "description": "Step 2", "dependencies": ["t1"]}]'
                    }
                }]
            }
        elif "选择最合适的技能" in content: # Skill matching prompt
            return {
                "choices": [{
                    "message": {
                        "content": "llm_reasoning"
                    }
                }]
            }
        else: # Execution prompt
            return {
                "choices": [{
                    "message": {
                        "content": "Task Completed."
                    }
                }]
            }
            
    manager.llm.completion = mock_completion
    
    # Run the middleware logic
    planner = HierarchicalTaskGraph(manager.llm, work_map)
    planner.plan("Build a rocket")
    
    assert "t1" in planner.tasks
    assert "t2" in planner.tasks
    assert "t1" in planner.tasks["t2"].dependencies
    print("✓ Hierarchical Task Graph planning verified.")
    
    # Run execution
    # We use a real agent but with the mocked LLM client
    result = planner.execute(manager.agents[0].agent)
    
    assert "## Task [t1]" in result
    assert "## Task [t2]" in result
    assert "Task Completed" in result
    print("✓ Long Horizon execution flow verified.")
    
    # Restore original method
    manager.llm.completion = original_completion

if __name__ == "__main__":
    cfg = load_config()
    if not cfg.provider.api_key or cfg.provider.api_key == "dummy":
        print("Please set a valid API key before running tests.")
        sys.exit(1)
        
    try:
        test_long_horizon_planning(cfg)
        print("\nLong Horizon Middleware verification successful.")
    except Exception as e:
        print(f"\nVerification failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
