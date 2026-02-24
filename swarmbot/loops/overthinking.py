from __future__ import annotations

import os
import time
import threading
import asyncio
from typing import Any, Dict, Optional, Callable

from ..config_manager import load_config, save_config, SwarmbotConfig, WORKSPACE_PATH
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
        )

    def start(self) -> None:
        """Starts the loop in a background thread."""
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[Overthinking] Started. Interval: {self.cfg.overthinking.interval_minutes}m, Max Steps: {self.cfg.overthinking.max_steps}")

    def stop(self) -> None:
        """Stops the loop."""
        self.stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        print("[Overthinking] Stopped.")

    def update_activity(self) -> None:
        """Called when user interacts, resetting the idle timer."""
        with self._lock:
            self.last_activity_time = time.time()
            if self.is_thinking:
                # Signal interruption logic if needed, but we check stop_event inside steps
                pass

    def _loop(self) -> None:
        """
        Main loop for overthinking.
        """
        while not self.stop_event.is_set():
            try:
                # 1. Wait for interval (check stop_event periodically)
                interval = self.cfg.overthinking.interval_minutes * 60
                # Use wait with timeout to be responsive
                if self.stop_event.wait(interval):
                    break

                # 2. Check user activity (Idle check)
                # If active recently, skip this cycle
                if time.time() - self.last_activity_time < 60: # 1 min idle minimum
                    continue

                # 3. Execute Overthinking Steps
                self._step_consolidate_short_term()
                self._step_expand_thoughts()
                
                # 4. Autonomous Exploration (New)
                max_steps = getattr(self.cfg.overthinking, "max_steps", 0)
                if max_steps > 0:
                    self._step_autonomous_exploration(max_steps)

            except Exception as e:
                print(f"[Overthinking] Loop Error: {e}")
                time.sleep(60) # Backoff

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

        # Autonomous Exploration
        with self._lock:
            if time.time() - self.last_activity_time < 10:
                print("[Overthinking] Interrupted by user activity.")
                return
        
        if max_steps > 0:
            self._step_autonomous_exploration(max_steps)

    def _step_consolidate_short_term(self) -> None:
        """1. 清理短期记忆写入 QMD"""
        date_str = time.strftime("%Y-%m-%d")
        cache_root = self.memory.local_cache.root
        try:
            files = []
            for name in os.listdir(cache_root):
                if name.startswith("chat_log_") and name.endswith(f"_{date_str}.md"):
                    files.append(os.path.join(cache_root, name))
        except FileNotFoundError:
            files = []

        chunks = []
        for path in files:
            text = self.memory.local_cache.read(os.path.basename(path))
            if text:
                chunks.append(text)

        if not chunks:
            return

        joined = "\n\n".join(chunks)

        prompt = (
            "You are organizing memories from recent chat logs.\n"
            "1) Extract objective facts only under a heading 'Facts'.\n"
            "2) Extract concrete actions and outcomes under 'Experiences'.\n"
            "3) Extract generalized principles or hypotheses under 'Theories'.\n"
            "Be concise and avoid duplication.\n\n"
            f"{joined[-4000:]}"
        )
        summary = self.thinker.step(prompt)

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
            "Based on your recent memories, reflect in three parts:\n"
            "1) Facts: list undisputed facts you rely on.\n"
            "2) Experiences: list concrete scenarios that taught you something.\n"
            "3) Theories: list 3–5 generalized principles or hypotheses derived from这些经验，标记哪些需要进一步验证。\n"
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

    def _step_autonomous_exploration(self, max_steps: int) -> None:
        """
        Autonomous exploration phase.
        1. Read current memory/state.
        2. Generate a self-directed task (e.g. "Optimize soul", "Verify tool").
        3. Execute task using SwarmManager.
        4. Log results and save to QMD.
        """
        print(f"[Overthinking] --- Starting Autonomous Exploration (Max Steps: {max_steps}) ---")
        
        # We need a SwarmManager instance. Ideally reuse or create new.
        # Since we are in a thread, creating new is safe if stateless.
        # But we need access to the same memory/config.
        
        from ..swarm.manager import SwarmManager
        manager = SwarmManager.from_swarmbot_config(self.cfg)
        
        # Generate exploration prompt
        exploration_prompt = (
            f"SYSTEM_OVERTHINKING_MODE: You are in autonomous exploration mode.\n"
            f"Max Steps: {max_steps}\n"
            f"Goal: Based on your current memory (QMD) and configuration (Boot files),\n"
            f"identify 1 area for improvement (e.g. clarify SOUL, test a tool, organize knowledge).\n"
            f"Execute this improvement action.\n"
            f"IMPORTANT: Output a structured log of your action."
        )
        
        try:
            result = manager.chat(exploration_prompt)
            print(f"[Overthinking] Exploration Result: {result[:200]}...")
            
            # Backup Log
            log_dir = os.path.join(WORKSPACE_PATH, "exploration_logs")
            os.makedirs(log_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            log_file = os.path.join(log_dir, f"explore_{timestamp}.md")
            with open(log_file, "w", encoding="utf-8") as f:
                f.write(f"# Exploration Log {timestamp}\n\n{result}")
            
        except Exception as e:
            print(f"[Overthinking] Exploration failed: {e}")
