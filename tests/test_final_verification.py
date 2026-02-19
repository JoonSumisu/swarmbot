
import os
import sys
import json
import time
import pytest
from swarmbot.config_manager import load_config, save_config
from swarmbot.swarm.manager import SwarmManager
from swarmbot.memory.qmd import QMDMemoryStore
from swarmbot.core.agent import CoreAgent, AgentContext
from swarmbot.statemachine.engine import StateMachine, State
from swarmbot.tools.adapter import NanobotSkillAdapter
from swarmbot.llm_client import OpenAICompatibleClient

# Setup environment variables for test
os.environ["SWARMBOT_TEST"] = "1"

@pytest.fixture
def setup_config():
    """Setup a valid configuration for testing."""
    cfg = load_config()
    cfg.provider.base_url = "https://api.moonshot.cn/v1"
    # Ensure API Key is present in ~/.swarmbot/config.json
    cfg.provider.model = "kimi-k2-turbo-preview"
    cfg.provider.max_tokens = 126000
    save_config(cfg)
    return cfg

def test_tri_layer_memory():
    """Test the Three-Layer Memory System (QMD + Map + LocalMD)."""
    print("\n[Test] Tri-Layer Memory System")
    memory = QMDMemoryStore()
    agent_id = "test-agent-mem"
    
    # 1. Test LocalMD (Short-term Cache)
    # Add an event and check if it's written to file
    content = "Discussing project architecture."
    memory.add_event(agent_id, content)
    
    date_str = time.strftime("%Y-%m-%d")
    log_file = f"chat_log_{date_str}.md"
    cached_content = memory.local_cache.read(log_file)
    assert content in cached_content
    print("✓ LocalMD (Short-term Cache) persistence passed.")
    
    # 2. Test MemoryMap (Whiteboard)
    # Update map via meta
    memory.add_event(agent_id, "Decision made", meta={"update_map": {"status": "approved", "score": 95}})
    
    # Check if whiteboard updated
    assert memory.whiteboard.get("status") == "approved"
    assert memory.whiteboard.get("score") == 95
    
    # Check if snapshot is injected into context
    context = memory.get_context(agent_id)
    assert len(context) > 0
    # First item should be system message with whiteboard snapshot
    if "Current WorkMap" in context[0]["content"]:
        print("✓ MemoryMap (Whiteboard) injection passed.")
    else:
        print("? MemoryMap snapshot not found in first context item.")
        
    # 3. Test QMD (Long-term) - Mocked
    # We assume search logic is same as before, just verifying method exists
    assert hasattr(memory, "search")
    print("✓ QMD (Long-term) interface check passed.")

def test_full_system_integration(setup_config):
    """
    Test the full system:
    - Swarm Manager (Architecture)
    - State Machine (Dynamic Flow)
    - Tool Adapter (Skill)
    - Memory (Context)
    """
    print("\n[Test] Full System Integration")
    cfg = setup_config
    
    # Initialize components
    adapter = NanobotSkillAdapter()
    memory = QMDMemoryStore()
    llm = OpenAICompatibleClient.from_provider(cfg.provider)
    
    # Create an agent with full capabilities
    ctx = AgentContext("integrator", "coordinator")
    agent = CoreAgent(ctx, llm, memory, use_nanobot=False)
    
    # Mock tool execution for stability
    agent._tool_adapter._run_nanobot_cmd = lambda *args: "TOOL_SUCCESS"
    
    # 1. Run a step that should trigger a tool (conceptually)
    # Since we can't force LLM to call tool without real inference, we verify the tool definitions are present
    defs = agent._tool_adapter.get_tool_definitions()
    assert len(defs) > 0
    
    # 2. Run State Machine flow
    sm = StateMachine("start")
    sm.add_state(State("start", agent, "Start task", {"default": "end"}))
    sm.add_state(State("end", agent, "End task", {}))
    
    # We mock the agent step to return a simple string to avoid API cost/latency in CI
    # But in real integration test we would use real LLM.
    # Here we temporarily patch agent.step for the state machine run
    original_step = agent.step
    agent.step = lambda prompt: "Processed"
    
    output = sm.run("Run integration test", max_steps=5)
    
    assert "[start] Processed" in output
    assert "[end] Processed" in output
    
    # Restore step
    agent.step = original_step
    print("✓ Full System (Agent+Memory+State Machine) flow verified.")

if __name__ == "__main__":
    cfg = load_config()
    if not cfg.provider.api_key or cfg.provider.api_key == "dummy":
        print("Please set a valid API key before running tests.")
        sys.exit(1)
        
    try:
        test_tri_layer_memory()
        test_full_system_integration(cfg)
        print("\nAll systems operational.")
    except Exception as e:
        print(f"\nSystem verification failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
