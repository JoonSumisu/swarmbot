
import sys
import asyncio
import logging
from pathlib import Path

# Inject path
CURRENT_DIR = Path("/root/swarmbot/swarmbot").resolve()
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_feishu")

async def _test_send_impl():
    from nanobot.config.schema import FeishuConfig
    from nanobot.channels.feishu import FeishuChannel
    from nanobot.bus.events import OutboundMessage
    from nanobot.bus.queue import MessageBus
    from swarmbot.config_manager import load_config

    # Load Config
    cfg = load_config()
    feishu_cfg = cfg.channels.get("feishu")
    if not feishu_cfg:
        print("Error: Feishu config not found")
        return
    
    print(f"App ID: {feishu_cfg.app_id}")
    print(f"App Secret: {feishu_cfg.app_secret[:5]}***")

    # Mock Bus
    bus = MessageBus()
    
    # Init Channel
    channel = FeishuChannel(feishu_cfg, bus)
    
    # Manually start client (partial start)
    import lark_oapi as lark
    channel._client = lark.Client.builder() \
            .app_id(feishu_cfg.app_id) \
            .app_secret(feishu_cfg.app_secret) \
            .log_level(lark.LogLevel.DEBUG) \
            .build()

    # Target Chat ID from previous logs
    target_chat_id = "oc_8956d2035dbe88ee6cb0eea711cb64e3"
    
    msg = OutboundMessage(
        channel="feishu",
        chat_id=target_chat_id,
        content="🔍 Swarmbot Connectivity Test: Active Send",
    )
    
    print(f"Sending message to {target_chat_id}...")
    await channel.send(msg)
    print("Send called. Check logs for result.")

def test_send():
    asyncio.run(_test_send_impl())

if __name__ == "__main__":
    asyncio.run(_test_send_impl())
