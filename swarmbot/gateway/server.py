import asyncio
import sys
import logging
from pathlib import Path

# --- Path Setup for Vendored Nanobot ---
# Ensure 'nanobot' can be imported as a top-level package
CURRENT_DIR = Path(__file__).resolve().parent.parent # swarmbot/swarmbot
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

# Also ensure 'nanobot' is importable if it's not already
try:
    import nanobot
except ImportError:
    # Fallback: alias swarmbot.nanobot to nanobot in sys.modules
    import swarmbot.nanobot
    sys.modules["nanobot"] = swarmbot.nanobot

from loguru import logger

# --- Imports ---
from swarmbot.config_manager import load_config, SwarmbotConfig
from swarmbot.swarm.agent_adapter import SwarmAgentLoop
from nanobot.bus.queue import MessageBus
from nanobot.channels.feishu import FeishuChannel
from nanobot.config.schema import FeishuConfig
from nanobot.providers.base import LLMProvider, LLMResponse

# --- Dummy Provider for AgentLoop compatibility ---
class NoOpProvider(LLMProvider):
    async def chat(self, messages, tools=None, **kwargs):
        # This should never be called if SwarmAgentLoop intercepts correctly.
        # But if it is called, return a safe dummy response.
        return LLMResponse(content="SwarmAgentLoop should intercept this.")

    def get_default_model(self):
        return "noop-model"

class GatewayServer:
    def __init__(self):
        self.config: SwarmbotConfig = load_config()
        self.bus = MessageBus()
        self.channels = []
        self.agent = None
        
    async def start(self):
        logger.info("Starting Swarmbot Gateway (Native Mode)...")
        
        # 1. Initialize Channels
        await self._init_channels()
        
        # 2. Initialize Swarm Agent Loop
        await self._init_agent()
        
        # 3. Start Components
        await self._run_loop()

    async def _init_channels(self):
        # Feishu
        feishu_conf = self.config.channels.get("feishu")
        # Check if feishu_conf is a dict or ChannelConfig object
        if feishu_conf:
            is_enabled = False
            if isinstance(feishu_conf, dict):
                is_enabled = feishu_conf.get("enabled", False)
                app_id = feishu_conf.get("app_id", "")
                app_secret = feishu_conf.get("app_secret", "")
                encrypt_key = feishu_conf.get("encrypt_key", "")
                verification_token = feishu_conf.get("verification_token", "")
                allow_from = feishu_conf.get("config", {}).get("allow_from", [])
            else: # Dataclass
                is_enabled = feishu_conf.enabled
                app_id = feishu_conf.app_id
                app_secret = feishu_conf.app_secret
                encrypt_key = feishu_conf.encrypt_key
                verification_token = feishu_conf.verification_token
                # allow_from might be in 'config' dict or direct field depending on ChannelConfig definition
                # ChannelConfig has 'config' dict field, but FeishuConfig expects 'allow_from'
                # Let's assume it's in config dict for now as ChannelConfig doesn't have allow_from field explicitly
                # Wait, looking at ChannelConfig in previous turn, it has `config: Dict[str, Any]`.
                allow_from = feishu_conf.config.get("allow_from", [])

            if is_enabled:
                logger.info("Initializing Feishu channel...")
                try:
                    pydantic_conf = FeishuConfig(
                        enabled=True,
                        app_id=app_id,
                        app_secret=app_secret,
                        encrypt_key=encrypt_key,
                        verification_token=verification_token,
                        allow_from=allow_from
                    )
                    
                    channel = FeishuChannel(pydantic_conf, self.bus)
                    self.channels.append(channel)
                    logger.info("Feishu channel initialized.")
                except Exception as e:
                    logger.error(f"Failed to init Feishu channel: {e}")

    async def _init_agent(self):
        logger.info("Initializing SwarmAgentLoop...")
        
        # SwarmAgentLoop needs to be initialized with parameters expected by AgentLoop
        # We pass a NoOpProvider because SwarmAgentLoop delegates to SwarmManager
        
        workspace = Path(self.config.workspace_path)
        
        self.agent = SwarmAgentLoop(
            bus=self.bus,
            provider=NoOpProvider(),
            workspace=workspace,
            model="swarm-v1", # Placeholder
            max_iterations=10,
            # Pass other required args with defaults
            temperature=0.7,
            max_tokens=4096,
            memory_window=10,
            brave_api_key=None,
            exec_config=None,
            cron_service=None,
            restrict_to_workspace=True,
            session_manager=None, # Will use default
            mcp_servers={}
        )

    async def _run_loop(self):
        # Start all channels
        for channel in self.channels:
            asyncio.create_task(channel.start())
        
        # Run agent loop (blocking)
        logger.info("Gateway is running. Press Ctrl+C to stop.")
        try:
            await self.agent.run()
        except asyncio.CancelledError:
            logger.info("Gateway stopping...")
        finally:
            # Cleanup
            for channel in self.channels:
                await channel.stop()
            if self.agent:
                self.agent.stop()

def run_gateway():
    """Entry point for CLI."""
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    
    try:
        server = GatewayServer()
        asyncio.run(server.start())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.exception(f"Gateway crashed: {e}")

if __name__ == "__main__":
    run_gateway()
