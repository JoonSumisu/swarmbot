import os
import sys
import logging
from typing import Any, Dict

# 1. Monkeypatch nanobot agent loop BEFORE importing nanobot
# We need to intercept `nanobot.agent.loop.AgentLoop.process_message` or similar.

from swarmbot.config_manager import load_config
from swarmbot.swarm.manager import SwarmManager

# Setup Logger
logger = logging.getLogger("swarmbot.gateway")
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s | %(name)s | %(levelname)s | %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Initialize Swarm Manager globally
try:
    cfg = load_config()
    SWARM_MANAGER = SwarmManager.from_swarmbot_config(cfg)
    logger.info("SwarmManager initialized for Gateway interception.")
except Exception as e:
    logger.error(f"Failed to init SwarmManager: {e}")
    SWARM_MANAGER = None

def intercept_process_message(self, message: Dict[str, Any], **kwargs):
    """
    Interceptor for nanobot AgentLoop._process_message
    """
    user_input = message.get("content", "")
    sender_id = message.get("from_user", "unknown")
    channel_id = message.get("channel", "unknown")
    
    logger.info(f"Intercepted message from {sender_id}@{channel_id}: {user_input[:50]}...")
    
    if SWARM_MANAGER:
        try:
            # Route through SwarmManager
            response = SWARM_MANAGER.chat(user_input)
            logger.info(f"Swarm generated response: {response[:50]}...")
            return response
        except Exception as e:
            logger.error(f"Swarm execution failed: {e}")
            return f"Error in Swarm execution: {str(e)}"
    else:
        return "SwarmManager not available."

# Apply Monkeypatch
try:
    # Import nanobot modules to patch
    # Note: We need to find where _process_message is defined.
    # Based on user logs: nanobot.agent.loop:_process_message
    from nanobot.agent.loop import AgentLoop
    
    # We need to patch the method that generates the response string.
    # Looking at nanobot source (implied), there might be a `_generate_response` or similar.
    # If `_process_message` handles the full flow including sending, we might need to be careful.
    # User log: "Response to feishu: ... Error: Connection error"
    # This implies `_process_message` calls LLM and then sends.
    
    # We will wrap `_generate_response` if it exists, or `chat` method of the internal agent.
    # Let's try patching `AgentLoop._generate_response` which is common in such designs,
    # OR we patch the `llm` call.
    
    # Better approach: Nanobot likely has an `Agent` class that `AgentLoop` uses.
    # We can replace the Agent with our SwarmProxyAgent.
    
    # BUT, to be safe and quick without deep diving nanobot source code structure blindly:
    # We will patch `AgentLoop._process_message` but we need to know its signature exactly.
    # It likely takes `message` object.
    
    # Let's try to patch `nanobot.agent.loop.AgentLoop.chat` if it exists, or look at `_process_message`.
    # Since we can't see nanobot code, we'll try a safer high-level patch.
    # We will patch `nanobot.agent.core.Agent.chat` (hypothetical) or similar.
    
    # WAIT, `nanobot` is installed. We can inspect it or just patch the `gateway` entry point.
    # The `nanobot gateway` command starts the service.
    
    # Let's patch `nanobot.agent.loop.AgentLoop._get_response` (guessing name)
    # Or better: `nanobot.agent.loop.AgentLoop.process` 
    
    # Inspecting user logs: `nanobot.agent.loop:_process_message:347 - Response to ...`
    # It seems `_process_message` does the work.
    
    # Let's try to patch the LLM client that nanobot uses?
    # No, we want full Swarm control, not just LLM replacement.
    
    # We will try to patch `AgentLoop.handle_message` or similar public method.
    # Let's assume `AgentLoop` has a method that takes text and returns text.
    
    # REALITY CHECK: Nanobot 0.1.4 likely uses `Agent` class.
    # We will patch `nanobot.agent.loop.AgentLoop._process_message`.
    # But `_process_message` is internal.
    
    # Let's look at `nanobot.agent.loop`.
    # We will define a wrapper class that inherits from AgentLoop and overrides logic?
    # No, `nanobot gateway` instantiates it internally.
    
    # Strategy: Runtime patching of the class method.
    original_process = AgentLoop._process_message
    
    async def patched_process_message(self, message, *args, **kwargs):
        # We need to handle the message object which might be a dict or dataclass
        # Assuming dict or object with .content
        content = ""
        if isinstance(message, dict):
            content = message.get("content", "")
        elif hasattr(message, "content"):
            content = message.content
            
        logger.info(f"[SwarmRoute] Processing: {content[:30]}...")
        
        # Call Swarm
        if SWARM_MANAGER:
            try:
                # SwarmManager.chat is synchronous, but we are likely in async context
                # Run in executor to avoid blocking loop
                import asyncio
                loop = asyncio.get_running_loop()
                response_text = await loop.run_in_executor(None, SWARM_MANAGER.chat, content)
                
                # Now we need to send this response back.
                # `_process_message` in nanobot likely sends the response itself via `self.channels.send`.
                # If we just return, it might not do anything if `_process_message` returns void.
                
                # We need to call the sender logic manually.
                # `self.channels.send(message.from_user, response_text, message.channel)`
                # We need to inspect `self` (AgentLoop instance) to find channel manager.
                
                # Looking at logs: `nanobot.channels.feishu:send`
                # `self.channels` likely exists.
                
                # Let's try to send directly if we can find the method.
                if hasattr(self, "channels") and hasattr(self.channels, "send_text"):
                     await self.channels.send_text(message, response_text)
                elif hasattr(self, "channels") and hasattr(self.channels, "send"):
                     # message object might be needed or just ids
                     # Attempt to reverse engineer from common patterns
                     # Usually `send(to_id, text, channel_id)`
                     # We can try to use `message` object as context.
                     await self.channels.send(message, response_text)
                else:
                    logger.error("Could not find channel send method on AgentLoop instance.")
                    
            except Exception as e:
                logger.error(f"Swarm processing error: {e}")
        
        # Skip original processing to bypass default agent
        return

    # Apply the patch
    # AgentLoop._process_message = patched_process_message
    # ERROR: `_process_message` signature is unknown and might be complex.
    # Replacing it might break ack/reaction logic seen in logs.
    
    # SAFER STRATEGY:
    # Patch `AgentLoop._process_message` - this is the internal method used by `run()` loop.
    # The `run()` loop consumes messages from bus and calls `_process_message`.
    
    from nanobot.agent.loop import AgentLoop

    original_process_message = AgentLoop._process_message

    async def patched_process_message(self, msg, session_key=None, on_progress=None):
        logger.info(f"[SwarmRoute] Intercepted message from {msg.channel}:{msg.sender_id}: {msg.content[:50]}...")
        
        # System messages or commands might need bypass
        if msg.channel == "system":
             return await original_process_message(self, msg, session_key, on_progress)
             
        if SWARM_MANAGER:
            try:
                # INTEGRATION WITH NANOBOT LOOP
                # We need to respect nanobot's async loop. SwarmManager.chat is synchronous.
                # Running it in executor is correct.
                
                import asyncio
                loop = asyncio.get_running_loop()
                
                # OPTIONAL: Send "Thinking..." signal or reaction?
                # Nanobot uses on_progress callback if provided.
                if on_progress:
                    await on_progress("⏳ Swarm is thinking...")
                
                # Run SwarmManager in thread pool
                response_text = await loop.run_in_executor(None, SWARM_MANAGER.chat, msg.content)
                logger.info(f"[SwarmRoute] Swarm response generated: {len(response_text)} chars")
                
                # We need to return an OutboundMessage
                from nanobot.bus.events import OutboundMessage
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=response_text,
                    metadata=msg.metadata or {}
                )
            except Exception as e:
                logger.error(f"[SwarmRoute] Error: {e}", exc_info=True)
                # Fallback to original if swarm fails? Or return error
                return await original_process_message(self, msg, session_key, on_progress)
        else:
            return await original_process_message(self, msg, session_key, on_progress)

    AgentLoop._process_message = patched_process_message
    logger.info("Successfully patched AgentLoop._process_message")

except ImportError as e:
    logger.error(f"Failed to patch nanobot: {e}")
except Exception as e:
    logger.error(f"Unexpected error during patching: {e}")

# Run the actual gateway
try:
    from nanobot.cli.commands import app
    if __name__ == "__main__":
        # Mock sys.argv to run gateway command
        sys.argv = [sys.argv[0], "gateway"]
        app()
except ImportError:
    # Fallback if structure is different
    logger.error("Could not import nanobot.cli.commands.app")
