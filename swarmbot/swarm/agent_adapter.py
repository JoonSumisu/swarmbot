from typing import Any, Awaitable, Callable, Optional, Dict
import asyncio
from loguru import logger

from nanobot.agent.loop import AgentLoop
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.providers.base import LLMProvider
from nanobot.agent.context import ContextBuilder
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.memory import MemoryStore
from nanobot.session.manager import SessionManager

from swarmbot.swarm.manager import SwarmManager
from swarmbot.config_manager import load_config

class SwarmAgentLoop(AgentLoop):
    """
    A Swarmbot-enhanced version of nanobot's AgentLoop.
    Instead of a single LLM processing messages, it delegates to the SwarmManager
    to coordinate multiple agents.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.swarm_manager = None
        self._init_swarm()
        
    def _init_swarm(self):
        try:
            cfg = load_config()
            self.swarm_manager = SwarmManager.from_swarmbot_config(cfg)
            logger.info("SwarmAgentLoop: SwarmManager initialized successfully.")
        except Exception as e:
            logger.error(f"SwarmAgentLoop: Failed to init SwarmManager: {e}")
            
    async def _run_agent_loop(
        self,
        initial_messages: list[dict],
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> tuple[str | None, list[str]]:
        """
        Override the core LLM loop to use SwarmManager.
        
        This replaces the standard single-agent thought loop with our 
        multi-agent swarm coordination.
        """
        if not self.swarm_manager:
            logger.warning("SwarmManager not available, falling back to default behavior.")
            return await super()._run_agent_loop(initial_messages, on_progress)
            
        # Extract the latest user message from initial_messages
        # initial_messages structure is typically [{"role": "system", ...}, ..., {"role": "user", "content": ...}]
        user_input = ""
        for msg in reversed(initial_messages):
            if msg.get("role") == "user":
                user_input = msg.get("content", "")
                break
        
        if not user_input:
            return "No input found.", []
            
        logger.info(f"SwarmAgentLoop: Delegating task to Swarm: {user_input[:50]}...")
        
        # Notify user that Swarm is starting
        if on_progress:
            await on_progress("🚀 Swarm activated. Dispatching agents...")
            
        try:
            # Run SwarmManager in a thread pool to avoid blocking the asyncio loop
            loop = asyncio.get_running_loop()
            
            # SwarmManager.chat is synchronous and handles its own agent loops
            response_text = await loop.run_in_executor(None, self.swarm_manager.chat, user_input)
            
            # We don't easily track granular tool usage from SwarmManager back to here yet,
            # so we return an empty list for tools_used or a placeholder.
            return response_text, ["swarm_coordination"]
            
        except Exception as e:
            logger.error(f"Swarm execution failed: {e}", exc_info=True)
            return f"Swarm Error: {str(e)}", []

# Factory function to patch into nanobot if needed
def create_swarm_loop(*args, **kwargs):
    return SwarmAgentLoop(*args, **kwargs)
