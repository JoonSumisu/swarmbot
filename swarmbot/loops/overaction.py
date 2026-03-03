import threading
import time
import os
import json
from ..core.agent import CoreAgent, AgentContext
from ..llm_client import OpenAICompatibleClient
from ..memory.hot_memory import HotMemory
from ..memory.warm_memory import WarmMemory
from ..memory.cold_memory import ColdMemory
from ..config_manager import load_config

class OveractionLoop:
    """
    Overaction: Happens after Overthinking.
    - Refine QMD: Read Cold Memory, think, supplement with web data.
    - Memory Cleanup: Delete Warm Memory after confirmed QMD transfer.
    - Self-Adjustment: Optimize Boot and Hot Memory.
    - Self-Improvement: Add self-opt tasks to Hot Memory todo list.
    """
    def __init__(self, stop_event: threading.Event):
        self.stop_event = stop_event
        self.config = load_config()
        workspace = getattr(self.config, "workspace_path", os.path.expanduser("~/.swarmbot/workspace"))
        
        self.hot_memory = HotMemory(workspace)
        self.warm_memory = WarmMemory(workspace)
        self.cold_memory = ColdMemory()
        
        self.llm = OpenAICompatibleClient.from_provider(providers=self.config.providers)
        # Overaction agent needs web_search tools
        self.agent = CoreAgent(
            AgentContext("overactor", "Overaction Agent"),
            self.llm,
            self.cold_memory,
            hot_memory=self.hot_memory
        )

    def start(self):
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()
        print("[Overaction] Loop started.")

    def stop(self):
        self.stop_event.set()

    def _loop(self):
        while not self.stop_event.is_set():
            # Runs after Overthinking (simulated by offset or signal)
            # Default interval 60 mins
            if self.stop_event.wait(3600):
                break
            
            try:
                self._process_cycle()
            except Exception as e:
                print(f"[Overaction] Error: {e}")

    def _process_cycle(self):
        print("[Overaction] Cycle: Refining and Self-Optimizing...")
        
        # 1. Read QMD and Refine
        # Find recent entries that might need web supplementation
        recent_qmd = self.cold_memory.search_text("recent facts", limit=10)
        
        refine_prompt = (
            "Review these recent long-term memory entries.\n"
            "Identify any facts or theories that could be supplemented with web data.\n"
            "Use 'web_search' to verify and expand them.\n"
            "Then, rewrite them into QMD as refined Knowledge.\n\n"
            f"Recent QMD:\n{recent_qmd}"
        )
        # Agent will use web_search if it decides to
        self.agent.step(refine_prompt)
        
        # 2. Delete Warm Memory if archived
        # We delete files older than 1 day that have been processed
        all_warm = self.warm_memory.list_files()
        today_str = time.strftime("%Y-%m-%d")
        for f in all_warm:
            if today_str not in f.name:
                print(f"[Overaction] Cleaning up old Warm Memory: {f.name}")
                self.warm_memory.delete_file(f.name)
        
        # 3. Self-Adjustment (Boot/Hot)
        # Reflect on system performance and add optimizations
        opt_prompt = (
            "Analyze your recent performance and memory structure.\n"
            "Suggest one optimization for your 'swarmboot.md' or 'hot_memory.md'.\n"
            "If it's a todo, output JSON: {'todo': '...'}\n"
            "If it's a boot update, output JSON: {'boot_update': '...'}"
        )
        res = self.agent.step(opt_prompt)
        try:
            import re
            match = re.search(r"\{.*\}", res, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                if data.get("todo"):
                    self.hot_memory.append_todo(f"Self-Opt: {data['todo']}")
                # Boot update logic would involve writing to swarmboot.md
        except: pass
