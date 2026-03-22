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
            
    async def _process_message(self, msg, session_key=None, on_progress=None):
        """
        Intercepts Nanobot's message processing loop to route requests through SwarmManager.
        This replaces the default agent logic with Swarm's MoE architecture.
        """
        logger.info(f"[SwarmRoute] Intercepted message from {msg.channel}:{msg.sender_id}")
        
        # System Message Bypass
        if msg.channel == "system":
             logger.info(f"[SwarmRoute] Bypassing system message")
             return None 
             
        if not self.swarm_manager:
            logger.error("SwarmManager is not initialized.")
            return None

        logger.info(f"[SwarmRoute] Routing to SwarmManager...")
        
        try:
            # Context Synchronization
            if hasattr(self.swarm_manager.config, "llm"):
                import os
                os.environ["OPENAI_API_BASE"] = self.swarm_manager.config.llm.base_url
                os.environ["OPENAI_API_KEY"] = self.swarm_manager.config.llm.api_key
                os.environ["LITELLM_MODEL"] = self.swarm_manager.config.llm.model

            # Session ID Extraction
            session_id = getattr(msg, "chat_id", None) or getattr(msg, "sender_id", "default")
            
            # Progress Indicator
            if on_progress:
                await on_progress("⏳ Swarm is thinking...")
            
            # Execute Swarm Logic (in ThreadPool to avoid blocking async loop)
            loop = asyncio.get_running_loop()
            
            response_text = await loop.run_in_executor(
                None, 
                self.swarm_manager.chat, 
                msg.content, 
                session_id
            )
            
            logger.info(f"[SwarmRoute] Swarm response generated: {len(str(response_text))} chars")
            
            # Response Sanitization
            if not response_text:
                response_text = "(No response generated)"
            response_text = str(response_text)

            # Feishu specific cleaning
            if msg.channel == "feishu":
                if len(response_text) > 4000:
                    response_text = response_text[:4000] + "\n\n...（内容过长，已截断）"
                # Ensure code blocks have spacing to prevent JSON errors
                if response_text.strip().startswith("```") and response_text.strip().endswith("```"):
                    response_text = "\u200b\n" + response_text + "\n\u200b"
                if not response_text.strip():
                    response_text = "..."

            # Construct Outbound Message
            from nanobot.bus.events import OutboundMessage
            
            reply_message_id = getattr(msg, "message_id", None)
            if not reply_message_id and msg.metadata:
                reply_message_id = msg.metadata.get("message_id")
            
            return OutboundMessage(
                chat_id=msg.chat_id,
                content=response_text,
                channel=msg.channel,
                reply_to=reply_message_id,
                metadata=msg.metadata or {}
            )

        except Exception as e:
            logger.error(f"[SwarmRoute] Error: {e}", exc_info=True)
            from nanobot.bus.events import OutboundMessage
            
            reply_message_id = getattr(msg, "message_id", None)
            if not reply_message_id and msg.metadata:
                reply_message_id = msg.metadata.get("message_id")
                
            return OutboundMessage(
                chat_id=msg.chat_id,
                content=f"Swarmbot Execution Error: {str(e)}",
                channel=msg.channel,
                reply_to=reply_message_id,
                metadata=msg.metadata or {}
            )

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
