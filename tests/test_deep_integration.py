
import os
import sys
import pytest
from swarmbot.config_manager import load_config, save_config
from swarmbot.swarm.manager import SwarmManager
from swarmbot.statemachine.engine import StateMachine, State
from swarmbot.core.agent import CoreAgent, AgentContext
from swarmbot.llm_client import OpenAICompatibleClient
from swarmbot.memory.qmd import QMDMemoryStore
from swarmbot.tools.adapter import NanobotSkillAdapter

# Setup environment variables for test
os.environ["SWARMBOT_TEST"] = "1"

@pytest.fixture
def setup_config():
    """Setup a valid configuration for testing."""
    cfg = load_config()
    cfg.provider.base_url = "http://127.0.0.1:11434/v1"
    cfg.provider.api_key = "dummy"
    cfg.provider.model = "openai/local-model"
    cfg.provider.max_tokens = 8192
    save_config(cfg)
    return cfg

def test_skill_adapter_loading():
    """Test if NanobotSkillAdapter can load skills."""
    print("\n[Test] Nanobot Skill Adapter")
    adapter = NanobotSkillAdapter()
    
    # Check if built-ins are present
    assert "web_search" in adapter.skills
    assert "file_read" in adapter.skills
    
    # Check tool definitions format
    defs = adapter.get_tool_definitions()
    assert len(defs) > 0
    assert defs[0]["type"] == "function"
    print("✓ Skill Adapter loaded successfully.")

def test_agent_tool_execution(setup_config):
    """Test if CoreAgent can execute a mocked tool call via adapter."""
    print("\n[Test] Agent Tool Execution")
    cfg = setup_config
    
    # Create Agent
    llm = OpenAICompatibleClient.from_provider(cfg.provider)
    memory = QMDMemoryStore()
    ctx = AgentContext("tester", "tester")
    agent = CoreAgent(ctx, llm, memory, use_nanobot=False) # Use internal adapter logic
    
    # Inject a mock tool execution into adapter to avoid real subprocess calls in test
    agent._tool_adapter._run_nanobot_cmd = lambda *args: "MOCK_TOOL_OUTPUT: success"
    
    # Prompt that triggers a tool (we force it by instruction if model is smart enough, 
    # or just trust the logic path if we mock LLM response. 
    # Here we assume the model *might* call it if asked).
    # Since we can't guarantee LLM behavior in unit test without mocking LLM, 
    # we'll test the adapter logic directly here for stability.
    
    result = agent._tool_adapter.execute("web_search", {"query": "test"})
    assert "MOCK_TOOL_OUTPUT" in result
    print("✓ Tool execution path verified.")

def test_state_machine_logic(setup_config):
    """Test StateMachine flow with a mocked agent response."""
    print("\n[Test] State Machine Logic")
    
    class MockAgent:
        def __init__(self, responses):
            self.responses = responses
            self.idx = 0
        def step(self, prompt):
            res = self.responses[self.idx]
            self.idx = (self.idx + 1) % len(self.responses)
            return res

    # Scenario: Start -> Check(FAIL) -> Start -> Check(PASS) -> End
    agent_coder = MockAgent(["Code v1", "Code v2"])
    agent_checker = MockAgent(["FAIL", "PASS"])
    agent_summary = MockAgent(["Summary"])
    
    # Ensure transition logic uses exact match for mocked responses
    # The router prompt asks the agent to choose from options.
    # Our MockAgent returns the *next* response in its list when called.
    # So:
    # 1. coding -> agent_coder returns "Code v1"
    #    transitions: default -> review
    # 2. review -> agent_checker returns "FAIL"
    #    transitions: PASS, FAIL. 
    #    Router logic calls agent_checker AGAIN for decision? 
    #    WAIT. In engine.py: decision = current_node.agent.step(router_prompt)
    #    So agent_checker is called TWICE per step if routing is needed.
    #    First for task ("FAIL"), second for routing ("FAIL" -> "FAIL")?
    #    We need to align MockAgent responses with this double-call structure.
    
    # Revised Mock Sequence:
    # State: coding (default transition, no router call)
    #   - Task: "Code v1"
    # State: review
    #   - Task: "FAIL"
    #   - Router: "FAIL" (to match transition key)
    # State: coding (default transition)
    #   - Task: "Code v2"
    # State: review
    #   - Task: "PASS"
    #   - Router: "PASS"
    # State: summary (no transition)
    #   - Task: "Summary"
    
    agent_coder = MockAgent(["Code v1", "Code v2"]) # Only task calls
    agent_checker = MockAgent(["FAIL", "FAIL", "PASS", "PASS"]) # Task, Router, Task, Router
    agent_summary = MockAgent(["Summary"])
    
    sm = StateMachine("coding")
    sm.add_state(State("coding", agent_coder, "Write code", {"default": "review"}))
    sm.add_state(State("review", agent_checker, "Review code", {"PASS": "summary", "FAIL": "coding"}))
    sm.add_state(State("summary", agent_summary, "Summarize", {}))
    
    output = sm.run("Build app", max_steps=10)
    print(output)
    
    assert "[coding] Code v1" in output
    assert "[review] FAIL" in output
    assert "[coding] Code v2" in output
    assert "[review] PASS" in output
    assert "[summary] Summary" in output
    print("✓ State Machine dynamic routing verified.")

if __name__ == "__main__":
    cfg = load_config()
    if not cfg.provider.api_key or cfg.provider.api_key == "dummy":
        print("Please set a valid API key before running tests.")
        sys.exit(1)
        
    try:
        test_skill_adapter_loading()
        test_agent_tool_execution(cfg)
        test_state_machine_logic(cfg)
        print("\nAll integration tests passed.")
    except Exception as e:
        print(f"\nTests failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
