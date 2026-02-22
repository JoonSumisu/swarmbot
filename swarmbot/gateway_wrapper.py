import os
import sys
import logging
from typing import Any, Dict

# 1. Monkeypatch nanobot agent loop BEFORE importing nanobot
# We need to intercept `nanobot.agent.loop.AgentLoop.process_message` or similar.

# --- CRITICAL: Ensure we load the local VENDORED nanobot, not system one ---
# The user wants to "get rid of import nanobot" dependency on pip package.
# We inject the path to `swarmbot/nanobot` (which is in `swarmbot/swarmbot/`) into sys.path[0].
# Current file is in /root/swarmbot/swarmbot/gateway_wrapper.py
# We want /root/swarmbot/swarmbot to be in sys.path so `import nanobot` works.
import sys
from pathlib import Path
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))
# --------------------------------------------------------------------------

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
    
    # Verify we are loading the local nanobot
    import nanobot
    logger.info(f"Loaded nanobot from: {nanobot.__file__}")
    
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.events import InboundMessage
    
    logger.info(f"InboundMessage fields: {list(InboundMessage.__dataclass_fields__.keys())}")
    
    original_process_message = AgentLoop._process_message
    
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
        logger.debug(f"[SwarmRoute] Full message details: chat_id={msg.chat_id}, session_key={session_key}")
        
        # System messages or commands might need bypass
        if msg.channel == "system":
             logger.info(f"[SwarmRoute] Bypassing system message")
             return await original_process_message(self, msg, session_key, on_progress)
             
        if SWARM_MANAGER:
            logger.info(f"[SwarmRoute] Routing to SwarmManager...")
            try:
                # 1. Force Sync Config: Ensure SwarmManager LLM config overrides any environment variables
                #    that might have been set by nanobot or previous runs.
                #    This is crucial if nanobot re-reads env vars or config files during its lifecycle.
                #    We re-assert our dominance here.
                if hasattr(SWARM_MANAGER.config, "llm"):
                    os.environ["OPENAI_API_BASE"] = SWARM_MANAGER.config.llm.base_url
                    os.environ["OPENAI_API_KEY"] = SWARM_MANAGER.config.llm.api_key
                    os.environ["LITELLM_MODEL"] = SWARM_MANAGER.config.llm.model
                    # Also force override litellm global state if possible, as litellm caches env vars
                    try:
                        import litellm
                        litellm.api_key = SWARM_MANAGER.config.llm.api_key
                        litellm.api_base = SWARM_MANAGER.config.llm.base_url
                    except ImportError:
                        pass
                
                # Integration with Nanobot Loop
                import asyncio
                loop = asyncio.get_running_loop()
                
                if on_progress:
                    await on_progress("⏳ Swarm is thinking...")
                
                # Run SwarmManager in thread pool
                response_text = await loop.run_in_executor(None, SWARM_MANAGER.chat, msg.content)
                logger.info(f"[SwarmRoute] Swarm response generated: {len(response_text)} chars")
                
                # Ensure response is a string
                if not response_text:
                    response_text = "(No response generated)"
                response_text = str(response_text)

                # --- Feishu Specific Cleaning ---
                if msg.channel == "feishu":
                    def clean_for_feishu(text):
                        # 1. Truncate if too long
                        if len(text) > 4000:
                            text = text[:4000] + "\n\n...（内容过长，已截断）"
                        
                        # 2. Fix JSON escaping issues in code blocks
                        # Feishu interactive cards use JSON payload.
                        # If the text contains unescaped quotes or backslashes inside a code block,
                        # it might break the card JSON structure if not handled by the SDK.
                        # However, nanobot SDK should handle basic escaping.
                        
                        # BUT, if the text is PURELY a code block with no surrounding text,
                        # some renderers fail.
                        # Let's ensure there is at least a zero-width space or newline before/after.
                        if text.strip().startswith("```") and text.strip().endswith("```"):
                            text = "\u200b\n" + text + "\n\u200b"
                            
                        # 3. Ensure not empty
                        if not text.strip():
                            text = "..."
                            
                        return text

                    response_text = clean_for_feishu(response_text)
                # --------------------------------

                # Check if response is empty string or None, which causes blank card
                if not response_text or not response_text.strip():
                     response_text = "..."
                     
                # Create OutboundMessage explicitly
                # IMPORTANT: We must use the OutboundMessage class from the nanobot we imported
                from nanobot.bus.events import OutboundMessage as LocalOutboundMessage
                
                # Try to get message_id from metadata if not direct attribute
                reply_message_id = getattr(msg, "message_id", None)
                if not reply_message_id and msg.metadata:
                    reply_message_id = msg.metadata.get("message_id")
                
                return LocalOutboundMessage(
                    chat_id=msg.chat_id,
                    content=response_text,
                    channel=msg.channel,
                    reply_to=reply_message_id, # Reply to original message if possible
                    metadata=msg.metadata or {}
                )
            except Exception as e:
                logger.error(f"[SwarmRoute] Error: {e}", exc_info=True)
                
                # Return error message to user so they know Swarm failed
                error_msg = f"Swarmbot Execution Error: {str(e)}"
                from nanobot.bus.events import OutboundMessage as LocalOutboundMessage
                
                reply_message_id = getattr(msg, "message_id", None)
                if not reply_message_id and msg.metadata:
                    reply_message_id = msg.metadata.get("message_id")
                    
                return LocalOutboundMessage(
                    chat_id=msg.chat_id,
                    content=error_msg,
                    channel=msg.channel,
                    reply_to=reply_message_id,
                    metadata=msg.metadata or {}
                )
        else:
            # If SwarmManager failed to init, return error instead of fallback
            reply_message_id = getattr(msg, "message_id", None)
            if not reply_message_id and msg.metadata:
                reply_message_id = msg.metadata.get("message_id")
                
            return OutboundMessage(
                chat_id=msg.chat_id,
                content="Swarmbot System Error: Manager not initialized.",
                channel=msg.channel,
                reply_to=reply_message_id
            )

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
        app()
except ImportError:
    logger.error("Could not import nanobot.cli.commands.app")
