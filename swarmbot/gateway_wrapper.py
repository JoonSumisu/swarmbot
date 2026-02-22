import os
import sys
import logging
from pathlib import Path
from typing import Any, Dict

# --- 1. Environment Setup & Vendoring ---
# Ensure we load the local VENDORED nanobot, not system one
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from swarmbot.config_manager import load_config
from swarmbot.swarm.manager import SwarmManager

# Setup Logger
logger = logging.getLogger("swarmbot.gateway")
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s | %(name)s | %(levelname)s | %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# --- 2. Initialize Swarm Manager ---
SWARM_MANAGER = None
try:
    cfg = load_config()
    SWARM_MANAGER = SwarmManager.from_swarmbot_config(cfg)
    logger.info("SwarmManager initialized for Gateway interception.")
except Exception as e:
    logger.error(f"Failed to init SwarmManager: {e}")

# --- 3. Define Patch Logic ---

async def patched_process_message(self, msg, session_key=None, on_progress=None):
    """
    Intercepts Nanobot's message processing loop to route requests through SwarmManager.
    This replaces the default agent logic with Swarm's MoE architecture.
    """
    logger.info(f"[SwarmRoute] Intercepted message from {msg.channel}:{msg.sender_id}")
    
    # 3.1 System Message Bypass
    if msg.channel == "system":
         # Use original if we could, but here we just ignore or log
         logger.info(f"[SwarmRoute] Bypassing system message")
         return None 
         
    if not SWARM_MANAGER:
        logger.error("SwarmManager is not initialized.")
        return None

    logger.info(f"[SwarmRoute] Routing to SwarmManager...")
    
    try:
        # 3.2 Context Synchronization
        # Ensure SwarmManager config overrides any env vars set by other parts
        if hasattr(SWARM_MANAGER.config, "llm"):
            os.environ["OPENAI_API_BASE"] = SWARM_MANAGER.config.llm.base_url
            os.environ["OPENAI_API_KEY"] = SWARM_MANAGER.config.llm.api_key
            os.environ["LITELLM_MODEL"] = SWARM_MANAGER.config.llm.model

        # 3.3 Session ID Extraction
        # Use chat_id as session_id to maintain context per conversation
        # Fallback to sender_id if chat_id is missing
        session_id = getattr(msg, "chat_id", None) or getattr(msg, "sender_id", "default")
        
        # 3.4 Progress Indicator
        if on_progress:
            await on_progress("⏳ Swarm is thinking...")
        
        # 3.5 Execute Swarm Logic (in ThreadPool to avoid blocking async loop)
        import asyncio
        loop = asyncio.get_running_loop()
        
        response_text = await loop.run_in_executor(
            None, 
            SWARM_MANAGER.chat, 
            msg.content, 
            session_id
        )
        
        logger.info(f"[SwarmRoute] Swarm response generated: {len(str(response_text))} chars")
        
        # 3.6 Response Sanitization
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

        # 3.7 Construct Outbound Message
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

# --- 4. Apply Monkeypatch ---
try:
    # Import AgentLoop to patch it
    from nanobot.agent.loop import AgentLoop
    
    # Verify InboundMessage structure for debugging
    from nanobot.bus.events import InboundMessage
    # logger.info(f"InboundMessage fields: {list(InboundMessage.__dataclass_fields__.keys())}")

    AgentLoop._process_message = patched_process_message
    logger.info("Successfully patched AgentLoop._process_message with SwarmSession support.")

except ImportError as e:
    logger.error(f"Failed to patch nanobot: {e}")
except Exception as e:
    logger.error(f"Unexpected error during patching: {e}")

# --- 5. Run Application ---
if __name__ == "__main__":
    try:
        from nanobot.cli.commands import app
        app()
    except ImportError:
        logger.error("Could not import nanobot.cli.commands.app")
