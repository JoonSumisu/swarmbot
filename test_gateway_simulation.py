import sys
import os
from pathlib import Path
import asyncio
import logging

# Setup path to import swarmbot and nanobot
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

# Mock nanobot module structure if needed, or rely on vendored one
try:
    import swarmbot.nanobot as vendored_nanobot
    sys.modules.setdefault("nanobot", vendored_nanobot)
    print("Bound vendored nanobot.")
except ImportError:
    print("Failed to bind vendored nanobot.")
    sys.exit(1)

from swarmbot.swarm.agent_adapter import SwarmAgentLoop
from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.session.manager import SessionManager
from nanobot.cron.service import CronService
from nanobot.providers.base import LLMProvider

# Mock provider
class DummyProvider(LLMProvider):
    async def generate(self, *args, **kwargs):
        return "Dummy response"
    async def generate_stream(self, *args, **kwargs):
        yield "Dummy response"
    async def chat(self, *args, **kwargs):
        return "Dummy chat response"
    def get_default_model(self):
        return "dummy-model"

from swarmbot.config_manager import load_config, WORKSPACE_PATH
from pathlib import Path
cfg = load_config()

async def test_gateway():
    print("Initializing SwarmAgentLoop...")
    
    bus = MessageBus()
    session_manager = SessionManager(Path(WORKSPACE_PATH))
    cron = CronService(Path("/tmp/cron.json"))
    
    agent = SwarmAgentLoop(
        bus=bus,
        provider=DummyProvider(), # Pass dummy provider to satisfy constructor
        workspace=Path(WORKSPACE_PATH),
        model="qwen3-coder-30b-a3b-instruct",
        temperature=0.6,
        max_tokens=4096,
        max_iterations=10,
        memory_window=10,
        brave_api_key=None,
        exec_config={},
        cron_service=cron,
        restrict_to_workspace=True,
        session_manager=session_manager,
        mcp_servers={}
    )
    
    print("SwarmAgentLoop initialized.")
    
    # Test 1: Basic Chat
    msg_content = "Hello, who are you?"
    print(f"\n[Test 1] Processing message: {msg_content}")
    
    response = await agent.process_direct(
        msg_content,
        session_key="test_chat_id",
        channel="feishu",
        chat_id="test_chat_id"
    )
    print(f"Response: {response}")
    
    if response and len(response) > 0:
        print("Test 1 Passed: Got response from Swarm.")
    else:
        print("Test 1 Failed: No response.")

    # Test 2: Skill Listing (Implicitly tests WorkMapMemory and local skill loading)
    # We ask the agent to list skills. If Swarm is working, it should be able to answer this 
    # either by general knowledge or by using a tool if one exists (skill_summary).
    # Since we removed 'nanobot skill list', we rely on 'skill_summary' tool or WorkMapMemory.
    
    msg_content = "List your available skills."
    print(f"\n[Test 2] Processing message: {msg_content}")
    
    response = await agent.process_direct(
        msg_content,
        session_key="test_chat_id",
        channel="feishu",
        chat_id="test_chat_id"
    )
    print(f"Response: {response}")
    
    if "skill" in response.lower() or "ability" in response.lower():
        print("Test 2 Passed: Agent responded about skills.")
    else:
        print("Test 2 Warning: Agent might not have understood or listed skills explicitly.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_gateway())
