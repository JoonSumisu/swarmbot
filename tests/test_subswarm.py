#!/usr/bin/env python3
"""
Swarmbot v2.0.2 SubSwarms Smoke Test
验证 SubSwarms 功能：异步分发多个子任务，通过 Hub 协调

Usage:
    python tests/test_subswarm.py --quick
    python tests/test_subswarm.py --model qwen3.5-35b-a3b --base-url http://100.110.110.250:7788
"""

from __future__ import annotations

import argparse
import sys
import time
import threading
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


def test_hub_topic_support():
    """测试 Hub 的 topic 和 swarm_id 支持"""
    result = TestResult("Hub Topic/SwarmId 支持")
    try:
        from swarmbot.gateway.communication_hub import (
            CommunicationHub, MessageType, MessageSender, HubMessage
        )
        
        hub = CommunicationHub(str(REPO_ROOT / "hub_test"))
        
        # 发送带 topic 和 swarm_id 的消息
        msg_id = hub.send(
            MessageType.SUBSWARM_REQUEST,
            "test task",
            MessageSender.MASTER_AGENT,
            "worker-1",
            "session-1",
            topic="research",
            swarm_id="swarm-123",
        )
        
        # 验证消息已发送
        messages = hub.get_messages_by_swarm("swarm-123", "session-1")
        
        if not messages:
            result.add_fail("无法通过 swarm_id 获取消息")
            return result
        
        # 验证 topic
        if messages[0].topic != "research":
            result.add_fail(f"Topic 不匹配: {messages[0].topic}")
            return result
        
        # 验证 swarm_id
        if messages[0].swarm_id != "swarm-123":
            result.add_fail(f"SwarmId 不匹配: {messages[0].swarm_id}")
            return result
        
        # 清理
        import shutil
        shutil.rmtree(REPO_ROOT / "hub_test", ignore_errors=True)
        
        result.add_pass(f"Topic={messages[0].topic}, SwarmId={messages[0].swarm_id}")
    except Exception as e:
        result.add_fail(str(e))
    return result


def test_subswarm_manager_basic():
    """测试 SubSwarmManager 基本功能"""
    result = TestResult("SubSwarmManager 基本功能")
    try:
        from swarmbot.gateway.communication_hub import CommunicationHub
        from swarmbot.gateway.subswarm_manager import SubSwarmManager, SubSwarmConfig
        
        hub = CommunicationHub(str(REPO_ROOT / "hub_test2"))
        config = SubSwarmConfig(max_concurrent=2, timeout_seconds=10)
        manager = SubSwarmManager(hub, "session-test", config)
        
        # 添加任务
        task1_id = manager.add_task("topic1", "任务1描述", priority=1)
        task2_id = manager.add_task("topic2", "任务2描述", priority=0)
        
        if len(manager.tasks) != 2:
            result.add_fail(f"任务数量错误: {len(manager.tasks)}")
            return result
        
        # 验证 swarm_id 生成
        if not manager.swarm_id.startswith("swarm-"):
            result.add_fail(f"SwarmId 格式错误: {manager.swarm_id}")
            return result
        
        result.add_pass(f"添加了 2 个任务, swarm_id={manager.swarm_id}")
        
        # 清理
        import shutil
        shutil.rmtree(REPO_ROOT / "hub_test2", ignore_errors=True)
        
    except Exception as e:
        result.add_fail(str(e))
    return result


def test_subswarm_execution():
    """测试 SubSwarm 执行和心跳"""
    result = TestResult("SubSwarm 异步执行")
    try:
        from swarmbot.gateway.communication_hub import CommunicationHub
        from swarmbot.gateway.subswarm_manager import SubSwarmManager, SubSwarmConfig
        
        hub = CommunicationHub(str(REPO_ROOT / "hub_test3"))
        config = SubSwarmConfig(max_concurrent=3, timeout_seconds=30)
        manager = SubSwarmManager(hub, "session-test", config)
        
        # 添加任务
        manager.add_task("research", "研究苹果公司", priority=1)
        manager.add_task("analysis", "分析市场趋势", priority=0)
        manager.add_task("coding", "编写代码示例", priority=0)
        
        # 定义简单的执行函数
        def executor(task_desc: str, task_id: str) -> str:
            return f"完成: {task_desc}"
        
        # 执行
        manager.dispatch(executor)
        
        # 等待完成
        results = manager.wait_for_completion(timeout=30)
        
        if len(results) != 3:
            result.add_fail(f"结果数量错误: {len(results)}")
            return result
        
        success_count = sum(1 for r in results if r.success)
        if success_count != 3:
            result.add_fail(f"成功数量错误: {success_count}")
            return result
        
        # 检查 Hub 中的心跳
        heartbeats = hub.get_subswarm_heartbeats(manager.swarm_id, "session-test")
        
        result.add_pass(f"执行了 3 个任务, {success_count} 成功, {len(heartbeats)} 个心跳")
        
        # 清理
        import shutil
        shutil.rmtree(REPO_ROOT / "hub_test3", ignore_errors=True)
        
    except Exception as e:
        result.add_fail(str(e))
    return result


def test_subswarm_result_grouping():
    """测试按 topic 分组结果"""
    result = TestResult("SubSwarm 按 Topic 分组")
    try:
        from swarmbot.gateway.communication_hub import CommunicationHub
        from swarmbot.gateway.subswarm_manager import SubSwarmManager, SubSwarmConfig
        
        hub = CommunicationHub(str(REPO_ROOT / "hub_test4"))
        config = SubSwarmConfig(max_concurrent=3)
        manager = SubSwarmManager(hub, "session-test", config)
        
        # 添加不同 topic 的任务
        manager.add_task("topic1", "任务A", priority=1)
        manager.add_task("topic1", "任务B", priority=1)
        manager.add_task("topic2", "任务C", priority=0)
        
        def executor(task_desc: str, task_id: str) -> str:
            return f"完成: {task_desc}"
        
        manager.dispatch(executor)
        results = manager.wait_for_completion(timeout=30)
        
        # 手动设置结果用于测试分组
        from swarmbot.gateway.subswarm_manager import SubSwarmResult
        manager.results = [
            SubSwarmResult(task_id="1", topic="topic1", success=True, content="结果A"),
            SubSwarmResult(task_id="2", topic="topic1", success=True, content="结果B"),
            SubSwarmResult(task_id="3", topic="topic2", success=True, content="结果C"),
        ]
        
        grouped = manager.group_results_by_topic()
        
        if len(grouped) != 2:
            result.add_fail(f"分组数量错误: {len(grouped)}")
            return result
        
        if len(grouped.get("topic1", [])) != 2:
            result.add_fail(f"topic1 分组数量错误: {len(grouped.get('topic1', []))}")
            return result
        
        if len(grouped.get("topic2", [])) != 1:
            result.add_fail(f"topic2 分组数量错误: {len(grouped.get('topic2', []))}")
            return result
        
        result.add_pass(f"分组正确: topic1={len(grouped['topic1'])}, topic2={len(grouped['topic2'])}")
        
        # 清理
        import shutil
        shutil.rmtree(REPO_ROOT / "hub_test4", ignore_errors=True)
        
    except Exception as e:
        result.add_fail(str(e))
    return result


def test_subswarm_message_types():
    """测试新的消息类型"""
    result = TestResult("SubSwarm 消息类型")
    try:
        from swarmbot.gateway.communication_hub import MessageType, MessageSender
        
        # 验证新消息类型存在
        required_types = [
            "SUBSWARM_REQUEST",
            "SUBSWARM_RESULT", 
            "SUBSWARM_STATUS",
            "COORDINATION_REQUEST",
            "HEARTBEAT",
        ]
        
        for type_name in required_types:
            if not hasattr(MessageType, type_name):
                result.add_fail(f"缺少消息类型: {type_name}")
                return result
        
        # 验证新发送者存在
        if not hasattr(MessageSender, "SUBSWARM"):
            result.add_fail("缺少发送者: SUBSWARM")
            return result
        
        result.add_pass(f"所有 {len(required_types)} 个消息类型和发送者已定义")
    except Exception as e:
        result.add_fail(str(e))
    return result


def test_master_agent_subswarm_methods():
    """测试 MasterAgent 的 SubSwarm 方法"""
    result = TestResult("MasterAgent SubSwarm 方法")
    try:
        from swarmbot.gateway.orchestrator import GatewayMasterAgent
        
        # 创建 MasterAgent
        agent = GatewayMasterAgent(str(REPO_ROOT / "hub_test5"), None)
        
        # 检查方法存在
        if not hasattr(agent, 'dispatch_subswarms'):
            result.add_fail("缺少 dispatch_subswarms 方法")
            return result
        
        if not hasattr(agent, 'wait_and_coordinate_subswarms'):
            result.add_fail("缺少 wait_and_coordinate_subswarms 方法")
            return result
        
        if not hasattr(agent, 'coordinate_subswarms_results'):
            result.add_fail("缺少 coordinate_subswarms_results 方法")
            return result
        
        result.add_pass("所有 SubSwarm 方法已定义")
        
        # 清理
        import shutil
        shutil.rmtree(REPO_ROOT / "hub_test5", ignore_errors=True)
        
    except Exception as e:
        result.add_fail(str(e))
    return result


def test_coordination_flow():
    """测试协调流程"""
    result = TestResult("SubSwarm 协调流程")
    try:
        from swarmbot.gateway.communication_hub import CommunicationHub, MessageType
        from swarmbot.gateway.subswarm_manager import SubSwarmManager, SubSwarmConfig
        
        hub = CommunicationHub(str(REPO_ROOT / "hub_test6"))
        config = SubSwarmConfig(max_concurrent=2)
        manager = SubSwarmManager(hub, "session-test", config)
        
        # 添加任务
        manager.add_task("task1", "子任务1", priority=1)
        manager.add_task("task2", "子任务2", priority=0)
        
        def executor(task_desc: str, task_id: str) -> str:
            return f"完成: {task_desc}"
        
        # 执行
        manager.dispatch(executor)
        
        # 等待
        manager.wait_for_completion(timeout=30)
        
        # 模拟 MasterAgent 协调
        status = hub.get_swarm_status(manager.swarm_id, "session-test")
        
        if status.get("result_count", 0) != 2:
            result.add_fail(f"结果数量不匹配: {status}")
            return result
        
        # 获取协调请求
        coords = hub.get_coordination_requests(manager.swarm_id, "session-test")
        
        result.add_pass(f"协调流程完成, status={status}")
        
        # 清理
        import shutil
        shutil.rmtree(REPO_ROOT / "hub_test6", ignore_errors=True)
        
    except Exception as e:
        result.add_fail(str(e))
    return result


def test_max_concurrent_limit():
    """测试最大并发限制"""
    result = TestResult("SubSwarm 最大并发限制")
    try:
        from swarmbot.gateway.communication_hub import CommunicationHub
        from swarmbot.gateway.subswarm_manager import SubSwarmManager, SubSwarmConfig
        
        hub = CommunicationHub(str(REPO_ROOT / "hub_test7"))
        config = SubSwarmConfig(max_concurrent=2)  # 最大 2 个并发
        manager = SubSwarmManager(hub, "session-test", config)
        
        # 添加 5 个任务
        for i in range(5):
            manager.add_task(f"task{i}", f"任务{i}", priority=0)
        
        if len(manager.tasks) != 5:
            result.add_fail(f"任务数量错误: {len(manager.tasks)}")
            return result
        
        def executor(task_desc: str, task_id: str) -> str:
            time.sleep(0.5)
            return f"完成: {task_desc}"
        
        # 执行
        start = time.time()
        manager.dispatch(executor)
        results = manager.wait_for_completion(timeout=30)
        elapsed = time.time() - start
        
        if len(results) != 5:
            result.add_fail(f"结果数量错误: {len(results)}")
            return result
        
        # 由于并发限制为 2，5 个任务理论上需要 ceil(5/2) * 0.5 = 1.5 秒
        # 允许一些误差，检查是否大于单并发时间 (2.5s)
        if elapsed > 2.5:
            result.add_fail(f"执行时间过长，可能未并发: {elapsed:.2f}s")
            return result
        
        result.add_pass(f"5 个任务在 max_concurrent=2 下执行, 耗时 {elapsed:.2f}s")
        
        # 清理
        import shutil
        shutil.rmtree(REPO_ROOT / "hub_test7", ignore_errors=True)
        
    except Exception as e:
        result.add_fail(str(e))
    return result


def run_tests(quick: bool = False):
    print("\n" + "="*60)
    print("Swarmbot v2.0.2 SubSwarms Smoke Test")
    print("="*60 + "\n")
    
    results: List[TestResult] = []
    
    print("Phase 1: 基础测试")
    results.append(test_subswarm_message_types())
    results.append(test_hub_topic_support())
    results.append(test_subswarm_manager_basic())
    
    if not quick:
        print("\nPhase 2: 执行测试")
        results.append(test_subswarm_execution())
        results.append(test_subswarm_result_grouping())
        results.append(test_coordination_flow())
        results.append(test_max_concurrent_limit())
    
    print("\nPhase 3: MasterAgent 集成")
    results.append(test_master_agent_subswarm_methods())
    
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
    parser = argparse.ArgumentParser(description="Swarmbot SubSwarms Smoke Test")
    parser.add_argument("--quick", action="store_true", help="Quick test (skip slow tests)")
    args = parser.parse_args()
    
    sys.exit(run_tests(quick=args.quick))


if __name__ == "__main__":
    main()
