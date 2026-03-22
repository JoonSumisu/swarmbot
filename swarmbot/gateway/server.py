import asyncio
import sys
import logging
import json
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import time
import uuid

# --- Path Setup ---
CURRENT_DIR = Path(__file__).resolve().parent.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

# Ensure nanobot compatibility
try:
    import nanobot
except ImportError:
    import swarmbot.nanobot
    sys.modules["nanobot"] = swarmbot.nanobot

from loguru import logger

# --- Imports ---
from swarmbot.config_manager import load_config, SwarmbotConfig, WORKSPACE_PATH
from nanobot.bus.queue import MessageBus, InboundMessage, OutboundMessage
from nanobot.channels.feishu import FeishuChannel
from nanobot.config.schema import FeishuConfig

from swarmbot.loops.inference import InferenceLoop
from swarmbot.autonomous import AutonomousEngine

class GatewayServer:
    def __init__(self):
        self.config: SwarmbotConfig = load_config()
        self.bus = MessageBus()
        self.channels = []

        # Loops
        self.autonomous_engine = None

        self._stop_event = threading.Event()
        self._executor = ThreadPoolExecutor(max_workers=10)
        self._inflight = asyncio.Semaphore(10)
        self._latest_inbound = {"channel": "", "chat_id": "", "message_id": ""}
        self._autonomous_report_pos = 0
        self._autonomous_report_path = Path(WORKSPACE_PATH) / "autonomous_gateway_reports.jsonl"
        
        # Interactive Session Storage
        self.active_loops = {}  # Dict[str, InferenceLoop] keyed by chat_id

    async def start(self):
        logger.info("Starting Swarmbot Gateway (v1.1.0 Interactive)...")

        # 1. Initialize Channels
        await self._init_channels()

        if not self.channels:
            logger.warning("No channel initialized. Gateway will run but cannot send/receive external messages.")

        # 2. Start Background Loops
        if bool(getattr(getattr(self.config, "autonomous", None), "enabled", True)):
            self.autonomous_engine = AutonomousEngine(self._stop_event)
            self.autonomous_engine.start()

        # 3. Start Message Processing Loop
        asyncio.create_task(self.bus.dispatch_outbound())
        asyncio.create_task(self._autonomous_report_poller())
        await self._run_message_loop()

    async def _init_channels(self):
        # Feishu
        feishu_conf = self.config.channels.get("feishu")
        if feishu_conf:
            # Handle both dict and object config
            if isinstance(feishu_conf, dict):
                enabled = feishu_conf.get("enabled", False)
                conf_data = feishu_conf.get("config", {}) if "config" in feishu_conf else feishu_conf
            else:
                enabled = feishu_conf.enabled
                conf_data = dict(feishu_conf.config or {})
                if getattr(feishu_conf, "app_id", "") and "app_id" not in conf_data:
                    conf_data["app_id"] = feishu_conf.app_id
                if getattr(feishu_conf, "app_secret", "") and "app_secret" not in conf_data:
                    conf_data["app_secret"] = feishu_conf.app_secret
                if getattr(feishu_conf, "encrypt_key", "") and "encrypt_key" not in conf_data:
                    conf_data["encrypt_key"] = feishu_conf.encrypt_key
                if getattr(feishu_conf, "verification_token", "") and "verification_token" not in conf_data:
                    conf_data["verification_token"] = feishu_conf.verification_token

            if enabled:
                logger.info("Initializing Feishu channel...")
                try:
                    app_id = conf_data.get("app_id") or conf_data.get("appId")
                    app_secret = conf_data.get("app_secret") or conf_data.get("appSecret")
                    encrypt_key = conf_data.get("encrypt_key") or conf_data.get("encryptKey") or ""
                    verification_token = conf_data.get("verification_token") or conf_data.get("verificationToken") or ""
                    
                    if not app_id or not app_secret:
                        logger.error("Feishu app_id or app_secret missing in config")
                        return

                    pydantic_conf = FeishuConfig(
                        enabled=True,
                        app_id=app_id,
                        app_secret=app_secret,
                        encrypt_key=encrypt_key,
                        verification_token=verification_token,
                        allow_from=conf_data.get("allow_from", [])
                    )
                    channel = FeishuChannel(pydantic_conf, self.bus)
                    self.channels.append(channel)
                except Exception as e:
                    logger.error(f"Failed to init Feishu channel: {e}")

        # Start channels
        for ch in self.channels:
            asyncio.create_task(ch.start())

    async def _run_message_loop(self):
        logger.info("Gateway is ready. Listening for messages...")
        
        try:
            while not self._stop_event.is_set():
                # Wait for message
                message: InboundMessage = await self.bus.consume_inbound()
                
                if not message:
                    continue
                    
                logger.info(f"Received message from {message.channel}: {message.content[:50]}...")
                
                # Launch async handler
                asyncio.create_task(self._handle_message_async(message))
                
        except asyncio.CancelledError:
            logger.info("Message loop cancelled.")
        finally:
            self.stop()

    async def _handle_message_async(self, message: InboundMessage):
        """Async wrapper for blocking inference with stateful interactive loop."""
        loop = asyncio.get_running_loop()
        chat_id = message.chat_id or "unknown"
        
        async with self._inflight:
            self._latest_inbound = {
                "channel": message.channel or "",
                "chat_id": chat_id,
                "message_id": message.message_id or "",
            }
            raw = (message.content or "").strip()
            
            # Command Handling
            if raw == "/clear":
                if chat_id in self.active_loops:
                    del self.active_loops[chat_id]
                    await self._publish_reply(message, "已清除当前会话状态。")
                else:
                    await self._publish_reply(message, "当前无活跃会话。")
                return

            try:
                # Retrieve existing loop or create new one
                if chat_id in self.active_loops:
                    inference_loop = self.active_loops[chat_id]
                    logger.info(f"Resuming interactive loop for {chat_id}")
                else:
                    inference_loop = InferenceLoop(self.config, WORKSPACE_PATH)
                    logger.info(f"Starting new inference loop for {chat_id}")

                # Run inference (blocking call in executor)
                response_text = await loop.run_in_executor(
                    self._executor,
                    inference_loop.run,
                    message.content,
                    chat_id
                )

                # Handle Result
                if inference_loop.is_suspended:
                    # Task paused for user input (Analysis/Plan Review)
                    self.active_loops[chat_id] = inference_loop
                    await self._publish_reply(message, response_text)
                else:
                    # Task completed
                    if chat_id in self.active_loops:
                        del self.active_loops[chat_id]
                    
                    if not isinstance(response_text, str) or not response_text.strip():
                        response_text = "（无内容返回）"
                    
                    # Split long responses
                    chunks = self._split_message(response_text)
                    for chunk in chunks:
                         await self._publish_reply(message, chunk)

            except Exception as e:
                logger.error(f"Inference processing failed: {e}")
                if chat_id in self.active_loops:
                    del self.active_loops[chat_id]
                await self._publish_reply(message, "系统处理消息时出现异常，会话已重置。")

    async def _autonomous_report_poller(self):
        while not self._stop_event.is_set():
            try:
                if self._autonomous_report_path.exists():
                    with open(self._autonomous_report_path, "r", encoding="utf-8") as f:
                        f.seek(self._autonomous_report_pos)
                        lines = f.readlines()
                        self._autonomous_report_pos = f.tell()
                    for ln in lines:
                        ln = (ln or "").strip()
                        if not ln:
                            continue
                        try:
                            row = json.loads(ln)
                        except Exception:
                            continue
                        content = str(row.get("content") or "").strip()
                        if not content:
                            continue
                        channel = str(self._latest_inbound.get("channel") or "")
                        chat_id = str(self._latest_inbound.get("chat_id") or "")
                        if not channel or not chat_id:
                            continue
                        outbound = OutboundMessage(
                            channel=channel,
                            chat_id=chat_id,
                            content=content,
                            reply_to=None,
                        )
                        await self.bus.publish_outbound(outbound)
            except Exception as e:
                logger.error(f"Autonomous report poller failed: {e}")
            await asyncio.sleep(3)

    async def _publish_reply(self, message: InboundMessage, text: str):
        try:
            reply = OutboundMessage(
                channel=message.channel,
                content=text,
                chat_id=message.chat_id,
                reply_to=message.message_id
            )
            await self.bus.publish_outbound(reply)
        except Exception as e:
            logger.error(f"Publish outbound failed: {e}")

    def _split_message(self, text: str, part_len: int = 1200) -> list[str]:
        raw = (text or "").strip()
        if not raw:
            return []
        chunks = []
        i = 0
        while i < len(raw):
            chunks.append(raw[i:i + part_len])
            i += part_len
        return chunks

    def stop(self):
        logger.info("Stopping Gateway...")
        self._stop_event.set()
        if self.autonomous_engine: self.autonomous_engine.stop()
        for ch in self.channels:
            asyncio.create_task(ch.stop())
        self._executor.shutdown(wait=False)

def run_gateway():
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
