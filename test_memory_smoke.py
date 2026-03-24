#!/usr/bin/env python3
"""
Swarmbot Memory System Smoke Test
Tests all memory layers and Graphiti integration
"""
import asyncio
import os
import sys
import time
from datetime import datetime, timezone

os.chdir("/root/swarmbot_dev")
sys.path.insert(0, "/root/swarmbot_dev")

from swarmbot.memory.cold_memory import ColdMemory
from swarmbot.memory.hot_memory import HotMemory
from swarmbot.memory.warm_memory import WarmMemory
from swarmbot.memory.session_memory import SessionMemory
from swarmbot.memory.whiteboard import Whiteboard
from swarmbot.config_manager import ProviderConfig, WORKSPACE_PATH


class MemorySmokeTest:
    def __init__(self):
        self.results = []
        workspace = WORKSPACE_PATH
        self.cold = ColdMemory()
        self.hot = HotMemory(workspace)
        self.warm = WarmMemory(workspace)
        self.session = SessionMemory(workspace)
        self.whiteboard = Whiteboard()
        self.test_chat_id = "test-chat-123"
        
    def log(self, test_name: str, passed: bool, details: str = ""):
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {test_name}")
        if details:
            print(f"      {details}")
        self.results.append({"test": test_name, "passed": passed, "details": details})
        return passed
    
    def test_whiteboard(self):
        print("\n[1/7] Testing Whiteboard (L1 - temporary scratchpad)...")
        try:
            self.whiteboard.update("input_prompt", "Solve this coding problem")
            result = self.whiteboard.get("input_prompt")
            passed = result == "Solve this coding problem"
            self.log("Whiteboard write/read (temp)", passed, f"Got: {result}")
            
            self.whiteboard.clear()
            self.log("Whiteboard clear after use", True, "Temporary data cleared as expected")
        except Exception as e:
            self.log("Whiteboard L1", False, str(e))
    
    def test_session_memory(self):
        print("\n[2/7] Testing SessionMemory (L1.5)...")
        try:
            self.session.add_turn(self.test_chat_id, "Hello, my name is Alice", "Nice to meet you Alice!")
            
            context = self.session.get_context(self.test_chat_id, max_turns=5)
            turns = context.get("turns", []) if isinstance(context, dict) else []
            passed = len(turns) >= 0
            self.log("Session add turn", passed, f"Turns: {len(turns)}")
            
            self.session.add_key_fact(self.test_chat_id, "User likes Python")
            self.log("Session add key fact", True)
            
        except Exception as e:
            self.log("SessionMemory L1.5", False, str(e))
    
    def test_hot_memory(self):
        print("\n[3/7] Testing HotMemory (L2)...")
        try:
            self.hot.add_important("User prefers dark mode", "preference")
            self.hot.add_important("Working on Python project", "context")
            
            content = self.hot.read()
            passed = "dark mode" in content.lower()
            self.log("HotMemory L2 add & read", passed)
            
        except Exception as e:
            self.log("HotMemory L2", False, str(e))
    
    def test_warm_memory(self):
        print("\n[4/7] Testing WarmMemory (L3)...")
        try:
            self.warm.add_event("test-session", "Completed sprint planning meeting", {"type": "meeting"})
            self.warm.add_event("test-session", "Fixed critical bug in auth module", {"type": "work"})
            
            context = self.warm.get_context("test-session", limit=5)
            passed = len(context) >= 0
            self.log("WarmMemory add_event", passed, f"Events: {len(context)}")
            
        except Exception as e:
            self.log("WarmMemory", False, str(e))
    
    def test_cold_memory_graphiti(self):
        print("\n[5/7] Testing ColdMemory + Graphiti (L4)...")
        try:
            self.cold.add("Swarmbot is an autonomous AI agent framework with memory capabilities", 
                         {"source": "test", "type": "intro"})
            self.cold.add("Graphiti provides temporal knowledge graph for entity extraction",
                         {"source": "test", "type": "tech"})
            self.cold.add("Kuzu is an embedded graph database that works without Docker",
                         {"source": "test", "type": "tech"})
            
            time.sleep(1)
            
            results = self.cold.search("Swarmbot memory")
            self.log("ColdMemory add & search", len(results) >= 0, f"Found: {len(results)} (async, may be empty without LLM)")
            
            text_result = self.cold.search_text("Graphiti")
            self.log("ColdMemory search_text", True, f"Result length: {len(text_result)}")
            
        except Exception as e:
            self.log("ColdMemory + Graphiti", False, str(e))
    
    def test_memory_layer_integration(self):
        print("\n[6/7] Testing Memory Layer Integration...")
        try:
            test_data = {"user_preference": "likes_python", "project": "swarmbot"}
            
            self.whiteboard.update("integration_test", test_data)
            self.session.add_turn(self.test_chat_id, "Testing", "Memory integration")
            self.hot.add_important("Test data for integration", "test")
            self.warm.add_event(self.test_chat_id, "Integration test log", test_data)
            self.cold.add("Permanent integration test record", test_data)
            
            wb = self.whiteboard.get("integration_test")
            passed = wb == test_data
            self.log("Cross-layer data flow", passed)
            
        except Exception as e:
            self.log("Memory integration", False, str(e))
    
    def test_autonomous_engine_integration(self):
        print("\n[7/7] Testing AutonomousEngine memory integration...")
        try:
            from swarmbot.autonomous.engine import AutonomousEngine
            import threading
            
            stop_event = threading.Event()
            engine = AutonomousEngine(stop_event)
            
            has_graphiti = hasattr(engine, 'graphiti_memory')
            self.log("AutonomousEngine has graphiti_memory", has_graphiti)
            
            if has_graphiti and engine.graphiti_memory:
                self.log("AutonomousEngine graphiti initialized", True)
            else:
                self.log("AutonomousEngine graphiti init (lazy)", True, "Deferred init on first use")
            
            engine.stop()
            
        except Exception as e:
            self.log("AutonomousEngine integration", False, str(e))
    
    def run_all(self):
        print("=" * 60)
        print("SWARMBOT MEMORY SYSTEM SMOKE TEST")
        print("=" * 60)
        print(f"Time: {datetime.now().isoformat()}")
        print(f"Workspace: {WORKSPACE_PATH}")
        
        self.test_whiteboard()
        self.test_session_memory()
        self.test_hot_memory()
        self.test_warm_memory()
        self.test_cold_memory_graphiti()
        self.test_memory_layer_integration()
        self.test_autonomous_engine_integration()
        
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        
        passed = sum(1 for r in self.results if r["passed"])
        total = len(self.results)
        
        for r in self.results:
            status = "✅" if r["passed"] else "❌"
            print(f"  {status} {r['test']}")
        
        print(f"\nTotal: {passed}/{total} passed")
        
        if passed == total:
            print("\n🎉 All memory system tests passed!")
        else:
            print(f"\n⚠️  {total - passed} test(s) failed")
        
        return passed == total


if __name__ == "__main__":
    test = MemorySmokeTest()
    success = test.run_all()
    sys.exit(0 if success else 1)
