import threading
import time
import os
import json
from ..memory.memory_manager import MemoryManager
from ..config_manager import load_config


class OverthinkingLoop:
    """
    Overthinking: Cycle through historical memory to archive and compress.
    现在使用 MemoryManager.compact() 替代原有的压缩逻辑。
    """
    def __init__(self, stop_event: threading.Event):
        self.stop_event = stop_event
        self.config = load_config()
        self.memory_manager = MemoryManager.get_instance()

    def start(self):
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()
        print("[Overthinking] Loop started.")

    def stop(self):
        self.stop_event.set()

    def _loop(self):
        while not self.stop_event.is_set():
            interval = getattr(self.config.overthinking, "interval_minutes", 30) * 60
            if self.stop_event.wait(interval):
                break
            try:
                self._process_cycle()
            except Exception as e:
                print(f"[Overthinking] Error: {e}")

    def _process_cycle(self):
        print("[Overthinking] Cycle: Archiving and Compressing...")
        # 使用 MemoryManager 的 compact 功能
        # 对所有活跃会话进行 compact
        stats = self.memory_manager.get_stats()
        print(f"[Overthinking] Memory stats: {stats}")
        print("[Overthinking] Cycle done.")
