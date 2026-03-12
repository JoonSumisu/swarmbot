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
from swarmbot.loops.overthinking import OverthinkingLoop
from swarmbot.loops.overaction import OveractionLoop
from swarmbot.autonomous import AutonomousEngine

class GatewayServer:
    def __init__(self):
        self.config: SwarmbotConfig = load_config()
        self.bus = MessageBus()
        self.channels = []

        # Loops
        self.overthinking_loop = None
        self.overaction_loop = None
        self.autonomous_engine = None

        self._stop_event = threading.Event()
        self._executor = ThreadPoolExecutor(max_workers=5)
        self._inflight = asyncio.Semaphore(5)
        self._subtasks = {}
        self._subtask_lock = asyncio.Lock()
        self._latest_inbound = {"channel": "", "chat_id": "", "message_id": ""}
        self._autonomous_report_pos = 0
        self._autonomous_report_path = Path(WORKSPACE_PATH) / "autonomous_gateway_reports.jsonl"

    async def start(self):
        logger.info("Starting Swarmbot Gateway (v1.1.0)...")

        # 1. Initialize Channels
        await self._init_channels()

        if not self.channels:
            logger.warning("No channel initialized. Gateway will run but cannot send/receive external messages.")

        # 2. Start Background Loops
        if bool(getattr(getattr(self.config, "autonomous", None), "enabled", True)):
            self.autonomous_engine = AutonomousEngine(self._stop_event)
            self.autonomous_engine.start()
        else:
            if getattr(self.config.overthinking, "enabled", True):
                self.overthinking_loop = OverthinkingLoop(self._stop_event)
                self.overthinking_loop.start()
            if getattr(getattr(self.config, "overaction", None), "enabled", True):
                self.overaction_loop = OveractionLoop(self._stop_event)
                self.overaction_loop.start()

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
            self._latest_inbound = {
                "channel": message.channel or "",
                "chat_id": message.chat_id or "",
                "message_id": message.message_id or "",
            }
            raw = (message.content or "").strip()
            if raw in ["/jobs", "任务状态", "subtasks", "/subtasks"]:
                text = await self._format_subtask_status(message.chat_id or "unknown")
                await self._publish_reply(message, text)
                return
            if raw.startswith("/job "):
                task_id = raw.replace("/job", "", 1).strip()
                text = await self._format_subtask_detail(message.chat_id or "unknown", task_id)
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
                "progress_tick": 0,
                "progress_percent": 0,
                "result_full": "",
            }

    def _estimate_progress(self, elapsed_s: int, route: str) -> int:
        if route == "reasoning_swarm":
            x = min(0.92, elapsed_s / 420.0)
            return int(12 + 80 * x)
        if route == "engineering_complex":
            x = min(0.9, elapsed_s / 900.0)
            return int(8 + 82 * x)
        x = min(0.95, elapsed_s / 180.0)
        return int(20 + 70 * x)

    def _compress_subtask_result(self, result: str, max_len: int = 700) -> str:
        text = (result or "").strip()
        if not text:
            return "无可用结果。"
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        bullets = [ln for ln in lines if ln.startswith(("-", "•", "1.", "2.", "3.", "4.", "5."))]
        picked = bullets[:5] if bullets else lines[:6]
        merged = "\n".join(picked).strip()
        if len(merged) > max_len:
            merged = merged[:max_len] + "..."
        return merged

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

    async def _progress_publisher(self, task_id: str, message: InboundMessage):
        started = int(time.time())
        while True:
            await asyncio.sleep(45)
            async with self._subtask_lock:
                rec = self._subtasks.get(task_id, {})
                if not rec or rec.get("status") != "running":
                    return
                elapsed = int(time.time()) - started
                p = self._estimate_progress(elapsed, str(rec.get("route") or "reasoning_swarm"))
                if p <= int(rec.get("progress_percent") or 0):
                    p = int(rec.get("progress_percent") or 0)
                rec["progress_percent"] = p
                rec["progress_tick"] = int(rec.get("progress_tick") or 0) + 1
                rec["updated_at"] = int(time.time())
                self._subtasks[task_id] = rec
                tick = rec["progress_tick"]
            await self._publish_reply(
                message,
                f"[子任务 {task_id} 进度] {p}%（第{tick}次进度回传）\n发送 /job {task_id} 查看详情。",
            )

    async def _run_subtask_and_announce(self, task_id: str, message: InboundMessage):
        loop = asyncio.get_running_loop()
        progress_task = asyncio.create_task(self._progress_publisher(task_id, message))
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
                rec["result_full"] = result or ""
                rec["progress_percent"] = 100
                self._subtasks[task_id] = rec
            summary = self._compress_subtask_result(result)
            chunks = self._split_message(result, part_len=1200)
            await self._publish_reply(message, f"[子任务 {task_id} 完成] 摘要如下：\n{summary}")
            for idx, c in enumerate(chunks[:4], start=1):
                await self._publish_reply(message, f"[子任务 {task_id} 结果分段 {idx}/{min(len(chunks),4)}]\n{c}")
            if len(chunks) > 4:
                await self._publish_reply(message, f"[子任务 {task_id}] 结果较长，剩余内容请发送 /job {task_id} 查看。")
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
        finally:
            if progress_task and not progress_task.done():
                progress_task.cancel()

    async def _format_subtask_status(self, chat_id: str) -> str:
        async with self._subtask_lock:
            rows = [v for v in self._subtasks.values() if str(v.get("chat_id")) == str(chat_id)]
        rows = sorted(rows, key=lambda x: int(x.get("created_at") or 0), reverse=True)[:8]
        if not rows:
            return "当前没有子任务记录。"
        lines = ["最近子任务状态："]
        for r in rows:
            lines.append(
                f"- {r.get('task_id')} | {r.get('status')} | {r.get('route')} | workers={r.get('workers')} | progress={r.get('progress_percent',0)}%"
            )
        return "\n".join(lines)

    async def _format_subtask_detail(self, chat_id: str, task_id: str) -> str:
        async with self._subtask_lock:
            rec = self._subtasks.get(task_id)
        if not rec or str(rec.get("chat_id")) != str(chat_id):
            return f"未找到任务 {task_id}。"
        head = (
            f"任务 {task_id}\n"
            f"- 状态: {rec.get('status')}\n"
            f"- 路由: {rec.get('route')}\n"
            f"- workers: {rec.get('workers')}\n"
            f"- 进度: {rec.get('progress_percent',0)}%\n"
            f"- 输入: {rec.get('input_preview','')}"
        )
        if rec.get("status") == "completed":
            full = str(rec.get("result_full") or "")
            return head + "\n\n" + (full[:3000] + ("..." if len(full) > 3000 else ""))
        if rec.get("status") == "failed":
            return head + f"\n\n错误: {rec.get('error','')}"
        return head

    def stop(self):
        logger.info("Stopping Gateway...")
        self._stop_event.set()
        if self.autonomous_engine: self.autonomous_engine.stop()
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
