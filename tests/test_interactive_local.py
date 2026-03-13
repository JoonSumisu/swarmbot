import os
import sys
import asyncio
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from swarmbot.config_manager import load_config, SwarmbotConfig, WORKSPACE_PATH
from swarmbot.loops.inference import InferenceLoop

def test_interactive_flow():
    config: SwarmbotConfig = load_config()
    # Ensure config points to qwen3-coder-next as requested
    print(f"Using providers: {[p.model for p in config.providers]}")
    
    workspace_path = WORKSPACE_PATH
    session_id = "test_interactive_session_001"
    
    print("\n=== Test 1: Simple Query (Non-Interactive) ===")
    simple_loop = InferenceLoop(config, workspace_path)
    response = simple_loop.run("你好", session_id)
    print(f"Simple Response: {response[:100]}...")
    assert not simple_loop.is_suspended, "Simple query should not suspend"
    assert "DONE" in simple_loop.completed_stages, "Simple query should complete"
    
    print("\n=== Test 2: Complex Query (Interactive) ===")
    complex_loop = InferenceLoop(config, workspace_path)
    
    # 1. Initial Request
    complex_query = "我们要把单体系统拆成多服务并上线，要求包含CI/CD、回滚、限流与审计，给出完整工程实施方案"
    print(f"User: {complex_query}")
    response_1 = complex_loop.run(complex_query, session_id)
    print(f"Agent Response 1: {response_1}")
    
    # Check if it entered Complex mode (should be suspended)
    assert complex_loop.route_mode == "engineering_complex", f"Expected engineering_complex, got {complex_loop.route_mode}"
    assert complex_loop.is_suspended, "Complex query should suspend for Analysis Review"
    assert complex_loop.suspended_stage == "ANALYSIS_REVIEW", f"Expected ANALYSIS_REVIEW, got {complex_loop.suspended_stage}"
    assert "任务分析确认" in response_1, "Response should ask for analysis confirmation"
    
    # 2. Analysis Confirmation
    print("\nUser: 是")
    response_2 = complex_loop.run("是", session_id)
    print(f"Agent Response 2: {response_2}")
    
    assert complex_loop.is_suspended, "Complex query should suspend for Plan Review"
    assert complex_loop.suspended_stage == "PLAN_REVIEW", f"Expected PLAN_REVIEW, got {complex_loop.suspended_stage}"
    assert "执行计划确认" in response_2, "Response should ask for plan confirmation"

    # 3. Plan Confirmation -> Execution
    print("\nUser: 是，开始执行")
    response_3 = complex_loop.run("是，开始执行", session_id)
    print(f"Agent Response 3: {response_3[:200]}...")
    
    assert not complex_loop.is_suspended, "Execution should complete without further suspension"
    assert "DONE" in complex_loop.completed_stages, "Task should be marked DONE"
    print("\n=== Test 3: Balanced Query (Auto Swarm) ===")
    balanced_loop = InferenceLoop(config, workspace_path)
    
    # Reasoning/Balanced task: "Explain why the sky is blue"
    print("User: 为什么天空是蓝色的？请从物理学角度分析。")
    response_bal = balanced_loop.run("为什么天空是蓝色的？请从物理学角度分析。", session_id)
    print(f"Agent Response Balanced: {response_bal[:100]}...")
    
    assert not balanced_loop.is_suspended, "Balanced query should NOT suspend"
    assert balanced_loop.route_mode == "reasoning_swarm", f"Expected reasoning_swarm, got {balanced_loop.route_mode}"
    assert "DONE" in balanced_loop.completed_stages, "Balanced query should complete"
    assert "COLLECTION" not in balanced_loop.completed_stages, "Balanced should not enter COLLECTION stage"
    assert "PLANNING" not in balanced_loop.completed_stages, "Balanced should not enter PLANNING stage"
    assert balanced_loop.whiteboard.get("reasoning_swarm_strategy"), "Balanced should use swarms strategy decision"
    assert "散射" in response_bal or "Rayleigh" in response_bal, "Response should contain relevant content"

if __name__ == "__main__":
    try:
        test_interactive_flow()
        print("\nAll tests passed!")
    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback
        traceback.print_exc()
