from __future__ import annotations

import time
import threading
import asyncio
from typing import Any, Dict, Optional, Callable

from ..config_manager import load_config, save_config, SwarmbotConfig
from ..core.agent import CoreAgent, AgentContext
from ..llm_client import OpenAICompatibleClient
from ..memory.qmd import QMDMemoryStore

class OverthinkingLoop:
    """
    Overthinking Loop: 后台思考循环
    在空闲时自动运行，负责整理记忆、精简 QMD、拓展思考、网络搜索补充知识。
    """
    def __init__(self, stop_event: threading.Event) -> None:
        self.stop_event = stop_event
        self.last_activity_time = time.time()
        self.is_thinking = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # Initialize resources
        self.cfg = load_config()
        self.llm = OpenAICompatibleClient.from_provider(self.cfg.provider)
        self.memory = QMDMemoryStore()
        
        # Thinking Agent (Self-Reflector)
        self.thinker = CoreAgent(
            AgentContext("overthinker", "Reflective Thinker"),
            self.llm,
            self.memory,
            use_nanobot=False # Pure LLM logic for safety
        )

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def update_activity(self) -> None:
        """Called when user interacts, resetting the idle timer."""
        with self._lock:
            self.last_activity_time = time.time()
            if self.is_thinking:
                # Signal interruption logic if needed, but we check stop_event inside steps
                pass

    def _loop(self) -> None:
        while not self.stop_event.is_set():
            # Reload config to check enabled status
            self.cfg = load_config()
            if not self.cfg.overthinking.enabled:
                time.sleep(60)
                continue

            idle_threshold = 600 # 10 minutes default idle before thinking
            cycle_interval = self.cfg.overthinking.interval_minutes * 60
            
            with self._lock:
                idle_time = time.time() - self.last_activity_time
            
            if idle_time > idle_threshold:
                # Start Thinking Cycle
                self.is_thinking = True
                try:
                    self._run_thinking_cycle()
                except Exception as e:
                    print(f"[Overthinking] Cycle error: {e}")
                finally:
                    self.is_thinking = False
                    # Wait for next cycle interval
                    time.sleep(cycle_interval)
            else:
                # Check every minute
                time.sleep(60)

    def _run_thinking_cycle(self) -> None:
        max_steps = self.cfg.overthinking.max_steps
        if max_steps <= 0: max_steps = 10 # Default auto
        
        steps = [
            self._step_consolidate_short_term,
            self._step_compress_qmd,
            self._step_expand_thoughts,
            self._step_online_enrichment
        ]
        
        for step_fn in steps:
            # Check interruption
            with self._lock:
                if time.time() - self.last_activity_time < 10: # User active recently
                    print("[Overthinking] Interrupted by user activity.")
                    return
            
            # Execute step
            step_fn()

    def _step_consolidate_short_term(self) -> None:
        """1. 清理短期记忆写入 QMD"""
        # Get recent logs from LocalMD
        # For simplicity, we read today's log
        date_str = time.strftime("%Y-%m-%d")
        log_file = f"chat_log_{date_str}.md"
        content = self.memory.local_cache.read(log_file)
        
        if not content: return

        prompt = (
            "You are organizing memories. "
            "Extract key facts, decisions, and insights from the following chat log. "
            "Ignore trivial chit-chat. Format as concise notes.\n\n"
            f"{content[-2000:]}" # Process last chunk
        )
        summary = self.thinker.step(prompt)
        
        # Save to QMD
        self.memory.persist_to_qmd(f"# Memory Consolidation {date_str}\n\n{summary}", collection="core_memory")

    def _step_compress_qmd(self) -> None:
        """2. 精简压缩 QMD 记忆"""
        # Search for similar or redundant entries? 
        # This is complex. Simplified: Summarize the 'core_memory' collection recent entries.
        # Placeholder for advanced logic.
        pass

    def _step_expand_thoughts(self) -> None:
        """3. 基于以前的记忆进行思考拓展完善"""
        # Random reflection or goal-oriented?
        prompt = (
            "Based on your recent memories, what are the potential long-term implications? "
            "Are there any gaps in your knowledge or planning? "
            "Propose 3 questions to investigate."
        )
        reflection = self.thinker.step(prompt)
        self.memory.persist_to_qmd(f"# Reflection {int(time.time())}\n\n{reflection}", collection="thoughts")

    def _step_online_enrichment(self) -> None:
        """4. 使用本地网络工具在线引入新相关记忆"""
        # Check for knowledge gaps identified in step 3
        # Or just pick a topic from whiteboard
        topic = self.memory.whiteboard.get("current_topic")
        if not topic: return
        
        # Use browser tool
        search_query = f"{topic} latest developments"
        # We need to access tool adapter, usually injected.
        # Here we instantiate a fresh one or use agent's internal if exposed.
        # For now, we simulate the tool call via prompt
        
        prompt = (
            f"I need to learn more about '{topic}'. "
            "Please generate a 'web_search' tool call query for this."
        )
        # In a real loop, we would execute the tool call returned by the LLM.
        # Since this is a background loop, we can direct call adapter.
        # Simplified:
        # result = adapter.execute("web_search", {"query": search_query})
        # self.memory.persist_to_qmd(f"# Research {topic}\n\n{result}", collection="research")
        pass
