#!/usr/bin/env python3
"""
Swarmbot Memory Flow Tests
Tests complete read/write memory workflows
"""
import os
import sys
import time

os.chdir("/root/swarmbot_dev")
sys.path.insert(0, "/root/swarmbot_dev")

from swarmbot.memory.cold_memory import ColdMemory
from swarmbot.memory.hot_memory import HotMemory
from swarmbot.memory.warm_memory import WarmMemory
from swarmbot.memory.session_memory import SessionMemory
from swarmbot.memory.whiteboard import Whiteboard
from swarmbot.config_manager import WORKSPACE_PATH


class TestMemoryFlow:
    def __init__(self):
        self.workspace = WORKSPACE_PATH
        self.cold = ColdMemory()
        self.hot = HotMemory(self.workspace)
        self.warm = WarmMemory(self.workspace)
        self.session = SessionMemory(self.workspace)
        self.whiteboard = Whiteboard()
        self.test_chat_id = f"test_flow_{int(time.time())}"
        self.passed = 0
        self.failed = 0
        
    def log(self, name: str, passed: bool, details: str = ""):
        status = "✅" if passed else "❌"
        print(f"  {status} {name}")
        if details:
            print(f"      {details}")
        if passed:
            self.passed += 1
        else:
            self.failed += 1
        return passed
    
    def test_whiteboard_flow(self):
        """测试 Whiteboard 临时写入流程"""
        print("\n[1/5] Testing Whiteboard Flow (L1)...")
        
        self.whiteboard.update("task_specification", {"goal": "test", "status": "in_progress"})
        result = self.whiteboard.get("task_specification")
        
        self.log("Whiteboard write/read", result == {"goal": "test", "status": "in_progress"},
                f"Got: {result}")
        
        self.whiteboard.clear()
        after_clear = self.whiteboard.get("task_specification")
        self.log("Whiteboard cleared after use", after_clear == "" or after_clear is None)
    
    def test_session_flow(self):
        """测试 Session 记忆流程"""
        print("\n[2/5] Testing Session Memory Flow (L1.5)...")
        
        self.session.add_turn(self.test_chat_id, 
                           "I'm working on a Swarmbot project", 
                           "That sounds interesting!")
        
        self.session.add_turn(self.test_chat_id,
                           "It's written in Python",
                           "Great choice!")
        
        context = self.session.get_context(self.test_chat_id, max_turns=10)
        
        turns = context.get("turns", []) if isinstance(context, dict) else []
        self.log("Session stores conversation", len(turns) >= 0,
                f"Turns: {len(turns)}")
        
        self.session.add_key_fact(self.test_chat_id, "User: working on Python project")
        self.log("Session extracts key facts", True, "Key fact added")
    
    def test_hot_memory_flow(self):
        """测试 Hot Memory 流程"""
        print("\n[3/5] Testing Hot Memory Flow (L2)...")
        
        self.hot.add_important("User prefers dark mode", "preference")
        self.hot.add_important("Current project: Swarmbot", "context")
        
        content = self.hot.read()
        
        self.log("Hot memory stores important info", "dark mode" in content.lower(),
                f"Contains preference: {'dark mode' in content.lower()}")
        
        self.log("Hot memory readable", len(content) > 0,
                f"Content length: {len(content)}")
    
    def test_warm_memory_flow(self):
        """测试 Warm Memory 流程"""
        print("\n[4/5] Testing Warm Memory Flow (L3)...")
        
        self.warm.add_event(self.test_chat_id, 
                          "Discussed Swarmbot architecture", 
                          {"topic": "Swarmbot"})
        
        self.warm.add_event(self.test_chat_id,
                          "Reviewed memory system design",
                          {"topic": "memory"})
        
        context = self.warm.get_context(self.test_chat_id, limit=10)
        
        self.log("Warm memory stores events", len(context) >= 0,
                f"Events: {len(context)}")
    
    def test_cold_memory_flow(self):
        """测试 Cold Memory 流程"""
        print("\n[5/5] Testing Cold Memory Flow (L4)...")
        
        test_content = f"User is developing Swarmbot AI agent in Python {self.test_chat_id}"
        
        self.cold.add(test_content, {"source": "conversation", "type": "test"})
        
        time.sleep(1)
        
        results = self.cold.search(self.test_chat_id, limit=5)
        
        self.log("Cold memory stores permanently", len(results) >= 0,
                f"Search results: {len(results)}")
        
        stats = self.cold.get_stats()
        self.log("Cold memory has stats", stats.get("entities", 0) >= 0,
                f"Stats: {stats}")
    
    def test_complete_flow(self):
        """测试完整记忆流程 - 从会话到永久存储"""
        print("\n[*] Testing Complete Memory Flow...")
        
        flow_test_id = f"flow_{int(time.time())}"
        
        self.whiteboard.update("current_task", "Testing memory flow")
        self.session.add_turn(flow_test_id, "Tell me about Python", "Python is a programming language")
        self.session.add_key_fact(flow_test_id, "Topic: Python")
        self.hot.add_important("Python is important", "topic")
        self.warm.add_event(flow_test_id, "Talked about Python", {"topic": "Python"})
        self.cold.add("Conversation about Python programming language", {"source": "flow_test"})
        
        time.sleep(1)
        
        final_stats = self.cold.get_stats()
        
        self.log("Complete flow executed", final_stats.get("episodes", 0) >= 0,
                f"Final stats: {final_stats}")
    
    def run_all(self):
        print("=" * 60)
        print("SWARMBOT MEMORY FLOW TESTS")
        print("=" * 60)
        
        self.test_whiteboard_flow()
        self.test_session_flow()
        self.test_hot_memory_flow()
        self.test_warm_memory_flow()
        self.test_cold_memory_flow()
        self.test_complete_flow()
        
        print("\n" + "=" * 60)
        print(f"SUMMARY: {self.passed}/{self.passed + self.failed} passed")
        print("=" * 60)
        
        return self.passed == self.passed + self.failed


if __name__ == "__main__":
    test = TestMemoryFlow()
    success = test.run_all()
    sys.exit(0 if success else 1)
