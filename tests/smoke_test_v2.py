#!/usr/bin/env python3
"""
Swarmbot v2.0.2 Smoke Test
验证 GatewayMasterAgent + CommunicationHub + 推理工具 架构

Usage:
    python tests/smoke_test_v2.py --model qwen3.5-35b-a3b --base-url http://100.110.110.250:7788 --quick
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, List, Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.error: str = ""

    def add_pass(self, detail: str = ""):
        self.passed = True
        print(f"  ✓ {self.name}" + (f": {detail}" if detail else ""))

    def add_fail(self, detail: str = ""):
        self.passed = False
        print(f"  ✗ {self.name}" + (f": {detail}" if detail else ""))


def test_gateway_import():
    result = TestResult("GatewayMasterAgent 导入")
    try:
        from swarmbot.gateway.orchestrator import GatewayMasterAgent
        from swarmbot.gateway.communication_hub import CommunicationHub, MessageType, MessageSender
        result.add_pass("导入成功")
    except Exception as e:
        result.add_fail(str(e))
    return result


def test_base_inference_tool():
    result = TestResult("BaseInferenceTool 导入")
    try:
        from swarmbot.loops.base import BaseInferenceTool, InferenceResult
        result.add_pass("导入成功")
    except Exception as e:
        result.add_fail(str(e))
    return result


def test_inference_tools():
    result = TestResult("推理工具导入")
    try:
        from swarmbot.loops.inference_standard import StandardInferenceTool
        from swarmbot.loops.inference_supervised import SupervisedInferenceTool
        from swarmbot.loops.inference_swarms import SwarmsInferenceTool
        result.add_pass("standard, supervised, swarms 导入成功")
    except Exception as e:
        result.add_fail(str(e))
    return result


def test_communication_hub(workspace: Path):
    result = TestResult("CommunicationHub 基本功能")
    try:
        from swarmbot.gateway.communication_hub import CommunicationHub, MessageType, MessageSender
        
        hub = CommunicationHub(str(workspace))
        
        # 测试发送消息
        msg_id = hub.send(
            MessageType.TASK_REQUEST,
            "test message",
            MessageSender.MASTER_AGENT,
            "test_recipient",
            "test_session"
        )
        
        if not msg_id:
            result.add_fail("发送消息失败")
            return result
        
        # 测试接收消息
        messages = hub.get_unconsumed_messages("test_recipient", "test_session")
        if len(messages) == 0:
            result.add_fail("接收消息失败")
            return result
        
        # 测试标记消费
        hub.mark_consumed(msg_id)
        
        result.add_pass(f"发送/接收/消费功能正常 (msg_id={msg_id[:20]}...)")
    except Exception as e:
        result.add_fail(str(e))
    return result


def test_master_agent_boot_load(workspace: Path, config):
    result = TestResult("MasterAgent 加载 Boot 和记忆")
    try:
        from swarmbot.gateway.orchestrator import GatewayMasterAgent
        
        agent = GatewayMasterAgent(str(workspace), config)
        
        # 检查 boot 文件
        if not hasattr(agent, 'boot_files'):
            result.add_fail("boot_files 属性不存在")
            return result
        
        # 检查记忆系统
        if not hasattr(agent, 'hot_memory'):
            result.add_fail("hot_memory 属性不存在")
            return result
        
        if not hasattr(agent, 'warm_memory'):
            result.add_fail("warm_memory 属性不存在")
            return result
        
        if not hasattr(agent, 'cold_memory'):
            result.add_fail("cold_memory 属性不存在")
            return result
        
        if not hasattr(agent, 'whiteboard'):
            result.add_fail("whiteboard 属性不存在")
            return result
        
        result.add_pass(f"Boot文件: {list(agent.boot_files.keys())}, 记忆系统已初始化")
    except Exception as e:
        result.add_fail(str(e))
    return result


def test_master_agent_routing(workspace: Path, config):
    result = TestResult("MasterAgent 路由决策 (简单/复杂)")
    try:
        from swarmbot.gateway.orchestrator import GatewayMasterAgent
        
        agent = GatewayMasterAgent(str(workspace), config)
        
        # 测试简单问题
        simple = agent._think_then_decide("你好")
        if simple not in ["simple", "complex"]:
            result.add_fail(f"路由返回异常值: {simple}")
            return result
        
        # 测试复杂问题
        complex = agent._think_then_decide("帮我分析一下苹果股票的投资价值")
        if complex not in ["simple", "complex"]:
            result.add_fail(f"路由返回异常值: {complex}")
            return result
        
        result.add_pass(f"简单问题: {simple}, 复杂问题: {complex}")
    except Exception as e:
        result.add_fail(str(e))
    return result


def test_simple_direct(workspace: Path, config):
    result = TestResult("MasterAgent simple_direct 回复")
    try:
        from swarmbot.gateway.orchestrator import GatewayMasterAgent
        
        agent = GatewayMasterAgent(str(workspace), config)
        
        response = agent._simple_direct("你好", "test_session")
        
        if not response or len(response) < 2:
            result.add_fail("回复为空或过短")
            return result
        
        result.add_pass(f"回复长度: {len(response)}")
    except Exception as e:
        result.add_fail(str(e))
    return result


def test_inference_tools_config():
    result = TestResult("inference_tools.md 配置文件")
    try:
        config_path = Path.home() / ".swarmbot" / "boot" / "inference_tools.md"
        if not config_path.exists():
            # 使用包内默认配置
            config_path = REPO_ROOT / "swarmbot" / "boot" / "inference_tools.md"
        
        if not config_path.exists():
            result.add_fail("配置文件不存在")
            return result
        
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 检查必要的工具
        if "standard" not in content:
            result.add_fail("缺少 standard 工具配置")
            return result
        
        if "supervised" not in content:
            result.add_fail("缺少 supervised 工具配置")
            return result
        
        if "swarms" not in content:
            result.add_fail("缺少 swarms 工具配置")
            return result
        
        result.add_pass("工具配置完整 (standard, supervised, swarms)")
    except Exception as e:
        result.add_fail(str(e))
    return result


def test_master_agent_tools_loaded(workspace: Path, config):
    result = TestResult("MasterAgent 工具加载")
    try:
        from swarmbot.gateway.orchestrator import GatewayMasterAgent
        
        agent = GatewayMasterAgent(str(workspace), config)
        
        if not hasattr(agent, '_tools'):
            result.add_fail("_tools 属性不存在")
            return result
        
        if len(agent._tools) == 0:
            result.add_fail("未加载任何工具")
            return result
        
        result.add_pass(f"已加载工具: {list(agent._tools.keys())}")
    except Exception as e:
        result.add_fail(str(e))
    return result


def test_human_in_loop_flow(workspace: Path, config):
    result = TestResult("人在回路流程 (supervised 暂停点)")
    try:
        from swarmbot.loops.inference_supervised import SupervisedInferenceTool
        from swarmbot.loops.base import InferenceResult
        
        tool = SupervisedInferenceTool(config, str(workspace))
        
        # 检查 breakpoints
        breakpoints = tool.get_breakpoints()
        if "ANALYSIS_REVIEW" not in breakpoints:
            result.add_fail("缺少 ANALYSIS_REVIEW 暂停点")
            return result
        
        if "PLAN_REVIEW" not in breakpoints:
            result.add_fail("缺少 PLAN_REVIEW 暂停点")
            return result
        
        result.add_pass(f"暂停点: {breakpoints}")
    except Exception as e:
        result.add_fail(str(e))
    return result


def test_session_context(workspace: Path, config):
    result = TestResult("MasterAgent 连续对话 (会话上下文)")
    try:
        from swarmbot.gateway.orchestrator import GatewayMasterAgent
        
        agent = GatewayMasterAgent(str(workspace), config)
        
        # 模拟对话
        session_id = "test_session_001"
        
        # 第一条消息
        agent._update_session(session_id, "你好")
        
        # 第二条消息
        agent._update_session(session_id, "今天天气怎么样")
        
        # 获取上下文
        context = agent.get_session_context(session_id)
        
        if len(context.get("history", [])) != 2:
            result.add_fail(f"历史记录数量错误: {len(context.get('history', []))}")
            return result
        
        result.add_pass(f"连续对话正常, 历史记录: {len(context['history'])}")
    except Exception as e:
        result.add_fail(str(e))
    return result


def test_version():
    result = TestResult("版本号检查")
    try:
        from swarmbot import __version__
        if __version__ != "2.0.2":
            result.add_fail(f"版本号错误: {__version__}")
            return result
        result.add_pass(f"版本: {__version__}")
    except Exception as e:
        result.add_fail(str(e))
    return result


def run_tests(quick: bool = False, model: str = "", base_url: str = ""):
    from swarmbot.config_manager import load_config
    
    print("\n" + "="*60)
    print("Swarmbot v2.0.2 Smoke Test")
    print("="*60 + "\n")
    
    workspace = Path.home() / ".swarmbot" / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    
    results: List[TestResult] = []
    
    # 基础测试
    print("Phase 1: 基础导入测试")
    results.append(test_gateway_import())
    results.append(test_base_inference_tool())
    results.append(test_inference_tools())
    results.append(test_version())
    
    # 配置测试
    print("\nPhase 2: 配置测试")
    results.append(test_inference_tools_config())
    
    # 组件测试
    print("\nPhase 3: 组件测试")
    try:
        config = load_config()
        
        # 如果提供了模型配置，更新它
        if model and base_url:
            for provider in config.providers:
                if provider.name == "custom":
                    provider.base_url = base_url
                    provider.model = model
                    break
        
        results.append(test_communication_hub(workspace))
        results.append(test_master_agent_boot_load(workspace, config))
        results.append(test_master_agent_tools_loaded(workspace, config))
        
        if not quick:
            results.append(test_master_agent_routing(workspace, config))
            results.append(test_simple_direct(workspace, config))
            results.append(test_session_context(workspace, config))
            results.append(test_human_in_loop_flow(workspace, config))
        
    except Exception as e:
        print(f"\n  配置加载失败: {e}")
    
    # 总结
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    
    for r in results:
        status = "✓" if r.passed else "✗"
        print(f"  {status} {r.name}")
    
    print(f"\nTotal: {passed}/{len(results)} passed, {failed} failed")
    
    return 0 if failed == 0 else 1


def main():
    parser = argparse.ArgumentParser(description="Swarmbot v2.0.2 Smoke Test")
    parser.add_argument("--model", default="", help="LLM model name")
    parser.add_argument("--base-url", default="", help="LLM base URL")
    parser.add_argument("--quick", action="store_true", help="Quick test (skip LLM calls)")
    args = parser.parse_args()
    
    sys.exit(run_tests(quick=args.quick, model=args.model, base_url=args.base_url))


if __name__ == "__main__":
    main()
