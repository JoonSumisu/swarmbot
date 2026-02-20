import os
import sys
import pytest
from io import StringIO
from swarmbot.config_manager import load_config, save_config
from swarmbot.swarm.manager import SwarmManager

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

def test_log_mode_output(setup_config, capsys):
    """Verify that log mode produces [SwarmLog] outputs."""
    print("\n[Test] Log Mode Output")
    
    cfg = setup_config
    cfg.swarm.display_mode = "log" # Enable log mode
    
    # Mock manager and agent step to avoid real API calls
    manager = SwarmManager.from_swarmbot_config(cfg)
    
    # Mock agent step
    for slot in manager.agents:
        slot.agent.step = lambda x: "Mock Response"
        
    # Run a simple sequential chat
    manager.chat("Hello")
    
    # Capture stdout
    captured = capsys.readouterr()
    
    # Verify logs
    assert "[SwarmLog] Starting Sequential flow" in captured.out
    assert "[SwarmLog] Agent [planner] is thinking..." in captured.out
    print("✓ Log mode output verified.")

def test_simple_mode_output(setup_config, capsys):
    """Verify that simple mode suppresses [SwarmLog] outputs."""
    print("\n[Test] Simple Mode Output")
    
    cfg = setup_config
    cfg.swarm.display_mode = "simple" # Disable log mode
    
    manager = SwarmManager.from_swarmbot_config(cfg)
    
    for slot in manager.agents:
        slot.agent.step = lambda x: "Mock Response"
        
    manager.chat("Hello")
    
    captured = capsys.readouterr()
    
    # Verify absence of logs
    assert "[SwarmLog]" not in captured.out
    print("✓ Simple mode suppression verified.")

if __name__ == "__main__":
    # Manual run wrapper
    class MockCapsys:
        def readouterr(self):
            class Result:
                out = sys.stdout.getvalue()
            return Result()
            
    # Capture stdout manually for manual run
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    
    try:
        cfg = load_config()
        test_log_mode_output(cfg, MockCapsys())
        
        # Reset buffer for next test
        sys.stdout = StringIO()
        test_simple_mode_output(cfg, MockCapsys())
        
        # Restore stdout
        sys.stdout = old_stdout
        print("\nAll log mode tests passed.")
    except Exception as e:
        sys.stdout = old_stdout
        print(f"\nTests failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
