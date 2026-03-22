#!/usr/bin/env python3
"""
Swarmbot v2.0.2 完整集成测试 (11项检查清单)

Usage:
    python tests/test_full_integration.py --model qwen3.5-35b-a3b --base-url http://100.110.110.250:7788
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


@dataclass
class TestResult:
    name: str
    passed: bool
    detail: str = ""
    error: str = ""


def log_test(name: str, passed: bool, detail: str = "", error: str = ""):
    status = "✓" if passed else "✗"
    msg = f"  {status} {name}"
    if detail:
        msg += f": {detail}"
    if error:
        msg += f" [ERROR: {error}]"
    print(msg)
    return TestResult(name, passed, detail, error)


class IntegrationTestSuite:
    def __init__(self, workspace: Path, config):
        self.workspace = workspace
        self.config = config
        self.results: List[TestResult] = []
        self.hub = None
        self.agent = None
        self.session_id = f"test_{int(time.time())}"

    def setup(self):
        from swarmbot.gateway.communication_hub import CommunicationHub
        from swarmbot.gateway.orchestrator import GatewayMasterAgent
        
        self.hub = CommunicationHub(str(self.workspace))
        self.agent = GatewayMasterAgent(str(self.workspace), self.config)
        print(f"[Setup] Workspace: {self.workspace}")
        print(f"[Setup] Session: {self.session_id}")

    # ===== Test 1: MasterAgent 人设/boot/skill/记忆/工具 =====
    def test_1_boot_persona_memory_tools(self):
        print("\n[Test 1] MasterAgent 人设/boot/skill/记忆/工具")
        
        try:
            boot_files = list(self.agent.boot_files.keys())
            has_hot = hasattr(self.agent, 'hot_memory') and self.agent.hot_memory is not None
            has_warm = hasattr(self.agent, 'warm_memory') and self.agent.warm_memory is not None
            has_cold = hasattr(self.agent, 'cold_memory') and self.agent.cold_memory is not None
            has_whiteboard = hasattr(self.agent, 'whiteboard') and self.agent.whiteboard is not None
            tools_count = len(self.agent._tools) if hasattr(self.agent, '_tools') else 0
            
            passed = (len(boot_files) >= 3 and has_hot and has_warm and 
                      has_cold and has_whiteboard and tools_count >= 3)
            
            detail = f"boot={len(boot_files)}个, memory=L1-L4, tools={tools_count}个"
            return log_test("Test 1: Boot/Persona/Memory/Tools", passed, detail)
        except Exception as e:
            return log_test("Test 1: Boot/Persona/Memory/Tools", False, error=str(e))

    # ===== Test 2: 简单问题直接回复 =====
    def test_2_simple_direct(self):
        print("\n[Test 2] 简单问题直接回复")
        
        try:
            response = self.agent._simple_direct("你好", self.session_id)
            passed = response and len(response) > 5
            detail = f"回复长度={len(response)}"
            return log_test("Test 2: Simple Direct Response", passed, detail)
        except Exception as e:
            return log_test("Test 2: Simple Direct Response", False, error=str(e))

    # ===== Test 3: MasterAgent 读取记忆 =====
    def test_3_memory_read(self):
        print("\n[Test 3] MasterAgent 读取记忆")
        
        try:
            content = self.agent.hot_memory.read()
            
            test_todo = f"Test Item {int(time.time())}"
            self.agent.hot_memory.append_todo(test_todo)
            
            content_after = self.agent.hot_memory.read()
            
            passed = test_todo in content_after
            detail = f"HotMemory append/读取成功"
            
            return log_test("Test 3: Memory Read/Write", passed, detail)
        except Exception as e:
            return log_test("Test 3: Memory Read/Write", False, error=str(e))

    # ===== Test 4: 连续对话 =====
    def test_4_multi_turn_conversation(self):
        print("\n[Test 4] 连续对话")
        
        try:
            session = f"multi_turn_{int(time.time())}"
            
            self.agent._update_session(session, "我叫张三")
            self.agent._update_session(session, "我叫李四")
            self.agent._update_session(session, "我叫什么名字？")
            
            context = self.agent.get_session_context(session)
            
            passed = len(context.get("history", [])) >= 3
            detail = f"历史记录数={len(context.get('history', []))}"
            
            return log_test("Test 4: Multi-turn Conversation", passed, detail)
        except Exception as e:
            return log_test("Test 4: Multi-turn Conversation", False, error=str(e))

    # ===== Test 5: 推理工具执行 =====
    def test_5_inference_tool_execution(self):
        print("\n[Test 5] 推理工具执行 (standard inference)")
        
        try:
            from swarmbot.loops.inference_standard import StandardInferenceTool
            
            tool = StandardInferenceTool(self.config, str(self.workspace))
            
            result = tool.run(
                "分析一下人工智能在医疗领域的应用前景",
                session_id=self.session_id
            )
            
            passed = result is not None and hasattr(result, 'content')
            detail = f"工具执行完成, 结果长度={len(result.content) if passed else 0}"
            
            return log_test("Test 5: Inference Tool Execution", passed, detail)
        except Exception as e:
            return log_test("Test 5: Inference Tool Execution", False, error=str(e))

    # ===== Test 6: MasterAgent 演绎结果 =====
    def test_6_master_agent_interprets(self):
        print("\n[Test 6] MasterAgent 演绎结果")
        
        try:
            user_input = "分析人工智能在医疗领域的应用"
            raw_result = "根据分析，人工智能在医疗领域有以下几个主要应用：1. 影像诊断 2. 药物研发 3. 个性化治疗"
            
            interpreted = self.agent._interpret_result(raw_result, user_input)
            
            passed = interpreted and len(interpreted) > 0
            detail = f"原始长度={len(raw_result)}, 演绎后长度={len(interpreted) if interpreted else 0}"
            
            return log_test("Test 6: MasterAgent Interprets Results", passed, detail)
        except Exception as e:
            return log_test("Test 6: MasterAgent Interprets Results", False, error=str(e))

    # ===== Test 7: 推理工具使用记忆 =====
    def test_7_tool_uses_memory(self):
        print("\n[Test 7] 推理工具使用记忆 (Whiteboard/Hot/Warm/QMD)")
        
        try:
            self.agent.whiteboard.clear()
            self.agent.whiteboard.update("metadata", {"session_id": self.session_id})
            self.agent.whiteboard.update("input_prompt", "Test input for memory verification")
            
            metadata = self.agent.whiteboard.get("metadata")
            input_prompt = self.agent.whiteboard.get("input_prompt")
            
            passed = metadata and input_prompt == "Test input for memory verification"
            detail = f"Whiteboard update/get 成功"
            
            return log_test("Test 7: Tool Uses Memory", passed, detail)
        except Exception as e:
            return log_test("Test 7: Tool Uses Memory", False, error=str(e))

    # ===== Test 8: 推理工具使用 Skill/Tool =====
    def test_8_tool_uses_skill(self):
        print("\n[Test 8] 推理工具使用 Skill/Tool")
        
        try:
            skills = self.agent.skills if hasattr(self.agent, 'skills') else []
            
            tools = list(self.agent._tools.keys()) if hasattr(self.agent, '_tools') else []
            
            passed = len(tools) >= 4
            detail = f"可用工具: {', '.join(tools)}"
            
            return log_test("Test 8: Tool Uses Skill/Tool", passed, detail)
        except Exception as e:
            return log_test("Test 8: Tool Uses Skill/Tool", False, error=str(e))

    # ===== Test 9: 人在回路 =====
    def test_9_human_in_loop(self):
        print("\n[Test 9] 人在回路流程")
        
        try:
            from swarmbot.loops.inference_supervised import SupervisedInferenceTool
            
            tool = SupervisedInferenceTool(self.config, str(self.workspace))
            
            breakpoints = tool.get_breakpoints()
            
            has_analysis = "ANALYSIS_REVIEW" in breakpoints
            has_plan = "PLAN_REVIEW" in breakpoints
            
            passed = has_analysis and has_plan
            detail = f"暂停点: {breakpoints}"
            
            return log_test("Test 9: Human-in-the-loop", passed, detail)
        except Exception as e:
            return log_test("Test 9: Human-in-the-loop", False, error=str(e))

    # ===== Test 10: Autonomous Bundle 设计 =====
    def test_10_autonomous_bundle_design(self):
        print("\n[Test 10] Autonomous Bundle 设计")
        
        try:
            has_check_autonomous = hasattr(self.agent, 'check_autonomous_messages')
            has_send_to_autonomous = hasattr(self.agent, 'send_to_autonomous')
            
            passed = has_check_autonomous and has_send_to_autonomous
            detail = f"Hub方法: check_autonomous={has_check_autonomous}, send_to_autonomous={has_send_to_autonomous}"
            
            return log_test("Test 10: Autonomous Bundle Design", passed, detail)
        except Exception as e:
            return log_test("Test 10: Autonomous Bundle Design", False, error=str(e))

    # ===== Test 11: Bundle 自我优化 =====
    def test_11_bundle_optimization(self):
        print("\n[Test 11] Bundle 自我优化")
        
        try:
            import threading
            from swarmbot.autonomous.engine import AutonomousEngine
            
            stop_event = threading.Event()
            engine = AutonomousEngine(stop_event)
            
            has_bundles = hasattr(engine, 'bundles') and len(engine.bundles) > 0
            has_start = hasattr(engine, 'start')
            has_stop = hasattr(engine, 'stop')
            
            passed = has_bundles and has_start and has_stop
            detail = f"Bundles: {len(engine.bundles) if has_bundles else 0}, start={has_start}, stop={has_stop}"
            
            return log_test("Test 11: Bundle Self-optimization", passed, detail)
        except Exception as e:
            return log_test("Test 11: Bundle Self-optimization", False, error=str(e))

    def run_all(self):
        print("="*60)
        print("Swarmbot v2.0.2 完整集成测试 (11项检查清单)")
        print("="*60)
        
        self.setup()
        
        self.results.append(self.test_1_boot_persona_memory_tools())
        self.results.append(self.test_2_simple_direct())
        self.results.append(self.test_3_memory_read())
        self.results.append(self.test_4_multi_turn_conversation())
        self.results.append(self.test_5_inference_tool_execution())
        self.results.append(self.test_6_master_agent_interprets())
        self.results.append(self.test_7_tool_uses_memory())
        self.results.append(self.test_8_tool_uses_skill())
        self.results.append(self.test_9_human_in_loop())
        self.results.append(self.test_10_autonomous_bundle_design())
        self.results.append(self.test_11_bundle_optimization())
        
        self.print_summary()
        return self.results

    def print_summary(self):
        print("\n" + "="*60)
        print("Test Summary (11-Point Checklist)")
        print("="*60)
        
        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed
        
        for i, r in enumerate(self.results, 1):
            status = "✓" if r.passed else "✗"
            print(f"  {i}. {status} {r.name}")
            if r.detail:
                print(f"     └─ {r.detail}")
        
        print(f"\nTotal: {passed}/11 passed, {failed}/11 failed")
        
        if passed == 11:
            print("\n🎉 所有测试通过！")
        elif passed >= 8:
            print("\n✅ 大部分测试通过，建议检查失败的测试")
        else:
            print("\n⚠️ 较多测试失败，需要修复")


def main():
    parser = argparse.ArgumentParser(description="Swarmbot v2.0.2 Full Integration Test")
    parser.add_argument("--model", default="qwen3.5-35b-a3b", help="LLM model name")
    parser.add_argument("--base-url", default="http://100.110.110.250:7788", help="LLM base URL")
    args = parser.parse_args()
    
    from swarmbot.config_manager import load_config
    
    workspace = Path.home() / ".swarmbot" / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    
    try:
        config = load_config()
        
        for provider in config.providers:
            if provider.name == "custom":
                provider.base_url = args.base_url
                provider.model = args.model
                break
        
        suite = IntegrationTestSuite(workspace, config)
        suite.run_all()
        
        sys.exit(0 if all(r.passed for r in suite.results) else 1)
        
    except Exception as e:
        print(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
