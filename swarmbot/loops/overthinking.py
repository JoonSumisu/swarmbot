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
from .definitions import OVERTHINKING_PROMPT
from .overaction import OveractionLoop

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
        self._ext_state_path = os.path.join(workspace, "external_checks_state.json")

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
        prompt = OVERTHINKING_PROMPT.format(
            hot_content=hot_content[:2000],
            warm_content=warm_content[:4000]
        )
        
        res = self.agent.step(prompt)
        try:
            import re
            # Try to find JSON block first
            match = re.search(r"```json\s*(\{.*?\})\s*```", res, re.DOTALL)
            if not match:
                # Fallback to loose brace matching
                match = re.search(r"\{.*\}", res, re.DOTALL)
            
            if match:
                json_str = match.group(1) if "```json" in match.group(0) else match.group(0)
                data = json.loads(json_str)
                
                count = 0
                for entry in data.get("entries", []):
                    self.cold_memory.add(
                        content=entry.get("content"),
                        meta={
                            "source": "overthinking", 
                            "date": time.strftime("%Y-%m-%d"),
                            "collection": entry.get("type", "experience")
                        }
                    )
                    count += 1
                print(f"[Overthinking] Added {count} entries to Cold Memory.")
            else:
                print(f"[Overthinking] No JSON found in response: {res[:100]}...")
        except Exception as e:
            print(f"[Overthinking] Failed to parse compression result: {e}")
        self._run_external_checks()

    def _load_ext_state(self) -> dict:
        try:
            if os.path.exists(self._ext_state_path):
                with open(self._ext_state_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except:
            pass
        return {"last_check": {}}

    def _save_ext_state(self, state: dict) -> None:
        try:
            with open(self._ext_state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except:
            pass

    def _run_external_checks(self) -> None:
        ext_cfg = getattr(self.config.overthinking, "external_checks", {}) or {}
        if not bool(ext_cfg.get("enabled", False)):
            return
        state = self._load_ext_state()
        now = int(time.time())
        events = []
        source_file = os.path.join(os.path.expanduser("~/.swarmbot/workspace"), "external_events.json")
        if os.path.exists(source_file):
            try:
                with open(source_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data if isinstance(data, list) else []:
                    ts = int(item.get("ts", 0))
                    if ts > int(state.get("last_check", {}).get("events_file", 0)):
                        events.append(item)
                state.setdefault("last_check", {})["events_file"] = now
            except:
                pass
        urgent_keywords = [str(x).lower() for x in ext_cfg.get("urgent_keywords", [])]
        urgent = []
        for e in events:
            text = (str(e.get("title", "")) + " " + str(e.get("summary", ""))).lower()
            if any(k in text for k in urgent_keywords):
                urgent.append(e)
        self._save_ext_state(state)
        if urgent:
            try:
                over = OveractionLoop(self.stop_event)
                over.trigger(reason="external_event", events=urgent)
            except Exception as e:
                print(f"[Overthinking] Trigger overaction failed: {e}")
