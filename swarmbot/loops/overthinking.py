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

class OverthinkingLoop:
    """
    Overthinking: Cycle through historical memory to archive and compress.
    - Facing Past: Archive and compress historical memory.
    - Read-only: Read hot_memory and warm_memory, DO NOT modify them.
    - Compression: Convert Hot/Warm into QMD (Cold Memory).
    """
    def __init__(self, stop_event: threading.Event):
        self.stop_event = stop_event
        self.config = load_config()
        workspace = getattr(self.config, "workspace_path", os.path.expanduser("~/.swarmbot/workspace"))
        
        self.hot_memory = HotMemory(workspace)
        self.warm_memory = WarmMemory(workspace)
        self.cold_memory = ColdMemory()
        
        self.llm = OpenAICompatibleClient.from_provider(providers=self.config.providers)
        self.agent = CoreAgent(
            AgentContext("overthinker", "Overthinker"),
            self.llm,
            self.cold_memory
        )

    def start(self):
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()
        print("[Overthinking] Loop started.")

    def stop(self):
        self.stop_event.set()

    def _loop(self):
        while not self.stop_event.is_set():
            # Customizable interval (default 30 mins)
            interval = getattr(self.config.overthinking, "interval_minutes", 30) * 60
            if self.stop_event.wait(interval):
                break
            
            try:
                self._process_cycle()
            except Exception as e:
                print(f"[Overthinking] Error: {e}")

    def _process_cycle(self):
        print("[Overthinking] Cycle: Archiving and Compressing...")
        
        # 1. Read Hot Memory
        hot_content = self.hot_memory.read()
        
        # 2. Read Warm Memory (Today's)
        warm_content = self.warm_memory.read_today()
        
        # 3. Compress into QMD
        # Identify high-value facts/experience/theories
        prompt = (
            "Analyze the following short-term and sequential memories.\n"
            "Extract valuable Facts, Experiences, and Theories for long-term storage.\n\n"
            f"Hot Memory:\n{hot_content[:2000]}\n\n"
            f"Warm Memory (Today):\n{warm_content[:4000]}\n\n"
            "Output JSON with a list of 'entries' to add to QMD."
        )
        
        res = self.agent.step(prompt)
        try:
            import re
            match = re.search(r"\{.*\}", res, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                for entry in data.get("entries", []):
                    self.cold_memory.add(
                        content=entry.get("content"),
                        collection=entry.get("type", "experience"),
                        meta={"source": "overthinking", "date": time.strftime("%Y-%m-%d")}
                    )
                print(f"[Overthinking] Added {len(data.get('entries', []))} entries to Cold Memory.")
        except:
            print("[Overthinking] Failed to parse compression result.")
