import asyncio
import sys
import logging
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
from swarmbot.loops.overthinking import OverthinkingLoop
from swarmbot.loops.overaction import OveractionLoop

class GatewayServer:
    def __init__(self):
        self.config: SwarmbotConfig = load_config()
        self.bus = MessageBus()
        self.channels = []

        # Loops
        self.overthinking_loop = None
        self.overaction_loop = None

        self._stop_event = threading.Event()
        self._executor = ThreadPoolExecutor(max_workers=5)
        self._inflight = asyncio.Semaphore(5)
        self._subtasks = {}
        self._subtask_lock = asyncio.Lock()

    async def start(self):
        logger.info("Starting Swarmbot Gateway (v0.5.4)...")

        # 1. Initialize Channels
        await self._init_channels()

        if not self.channels:
            logger.warning("No channel initialized. Gateway will run but cannot send/receive external messages.")

        # 2. Start Background Loops
        if getattr(self.config.overthinking, "enabled", True):
            self.overthinking_loop = OverthinkingLoop(self._stop_event)
            self.overthinking_loop.start()
        if getattr(getattr(self.config, "overaction", None), "enabled", True):
            self.overaction_loop = OveractionLoop(self._stop_event)
            self.overaction_loop.start()

        # 3. Start Message Processing Loop
        asyncio.create_task(self.bus.dispatch_outbound())
        await self._run_message_loop()

    async def _init_channels(self):
        # Feishu
        feishu_conf = self.config.channels.get("feishu")
        if feishu_conf:
            # Handle both dict and object config
            if isinstance(feishu_conf, dict):
                # If it's a dict, it might be the raw config from json
                # In config_manager, channels are usually ChannelConfig objects
                # But let's be safe
                enabled = feishu_conf.get("enabled", False)
                conf_data = feishu_conf.get("config", {}) if "config" in feishu_conf else feishu_conf
            else:
                # It is a ChannelConfig object
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
                    # Support both snake_case (standard) and camelCase (legacy)
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
        """Async wrapper for blocking inference."""
        loop = asyncio.get_running_loop()
        async with self._inflight:
            raw = (message.content or "").strip()
            if raw in ["/jobs", "任务状态", "subtasks", "/subtasks"]:
                text = await self._format_subtask_status(message.chat_id or "unknown")
                await self._publish_reply(message, text)
                return
            try:
                inference_loop = InferenceLoop(self.config, WORKSPACE_PATH)
                route_decision = await loop.run_in_executor(
                    self._executor,
                    inference_loop.preview_route,
                    message.content,
                )
                route = str((route_decision or {}).get("route") or "reasoning_swarm")
                if route == "simple_direct_master":
                    response_text = await loop.run_in_executor(
                        self._executor,
                        inference_loop.run,
                        message.content,
                        message.chat_id or "unknown"
                    )
                else:
                    task_id = f"sb_{uuid.uuid4().hex[:10]}"
                    await self._register_subtask(task_id, message, route_decision)
                    asyncio.create_task(self._run_subtask_and_announce(task_id, message))
                    response_text = (
                        f"已启动后台子任务 {task_id}（route={route}）。\n"
                        "你可以继续聊天处理普通问题；完成后我会主动推送结果。\n"
                        "发送 /jobs 可查看任务状态。"
                    )
                if not isinstance(response_text, str) or not response_text.strip():
                    response_text = "已收到消息，但本次推理结果为空。请重试一次。"
            except Exception as e:
                logger.error(f"Inference processing failed: {e}")
                response_text = "系统处理消息时出现异常，请稍后重试。"
            await self._publish_reply(message, response_text)

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

    async def _register_subtask(self, task_id: str, message: InboundMessage, route_decision: dict):
        async with self._subtask_lock:
            self._subtasks[task_id] = {
                "task_id": task_id,
                "status": "running",
                "route": str((route_decision or {}).get("route") or ""),
                "reason": str((route_decision or {}).get("reason") or ""),
                "workers": int((route_decision or {}).get("workers") or 0),
                "chat_id": message.chat_id or "unknown",
                "channel": message.channel,
                "input_preview": (message.content or "")[:120],
                "created_at": int(time.time()),
                "updated_at": int(time.time()),
            }

    async def _run_subtask_and_announce(self, task_id: str, message: InboundMessage):
        loop = asyncio.get_running_loop()
        try:
            inference_loop = InferenceLoop(self.config, WORKSPACE_PATH)
            result = await loop.run_in_executor(
                self._executor,
                inference_loop.run,
                message.content,
                message.chat_id or "unknown",
            )
            async with self._subtask_lock:
                rec = self._subtasks.get(task_id, {})
                rec["status"] = "completed"
                rec["updated_at"] = int(time.time())
                rec["result_preview"] = (result or "")[:180]
                self._subtasks[task_id] = rec
            await self._publish_reply(
                message,
                f"[子任务 {task_id} 完成]\n{result}",
            )
        except Exception as e:
            async with self._subtask_lock:
                rec = self._subtasks.get(task_id, {})
                rec["status"] = "failed"
                rec["updated_at"] = int(time.time())
                rec["error"] = str(e)
                self._subtasks[task_id] = rec
            await self._publish_reply(
                message,
                f"[子任务 {task_id} 失败]\n{e}",
            )

    async def _format_subtask_status(self, chat_id: str) -> str:
        async with self._subtask_lock:
            rows = [v for v in self._subtasks.values() if str(v.get("chat_id")) == str(chat_id)]
        rows = sorted(rows, key=lambda x: int(x.get("created_at") or 0), reverse=True)[:8]
        if not rows:
            return "当前没有子任务记录。"
        lines = ["最近子任务状态："]
        for r in rows:
            lines.append(
                f"- {r.get('task_id')} | {r.get('status')} | {r.get('route')} | workers={r.get('workers')}"
            )
        return "\n".join(lines)

    def stop(self):
        logger.info("Stopping Gateway...")
        self._stop_event.set()
        if self.overthinking_loop: self.overthinking_loop.stop()
        if self.overaction_loop: self.overaction_loop.stop()
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
