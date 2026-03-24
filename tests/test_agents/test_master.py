"""
Tests for MasterAgent and MasterLoop
"""
import unittest
from unittest.mock import MagicMock, patch
from swarmbot.agents.master import (
    MasterAgent, MasterLoop,
    RoutingDecisionHook, ToolSelectionHook
)
from swarmbot.agents.base import AgentContext, AgentConfig


class TestRoutingDecisionHook(unittest.TestCase):
    """Test RoutingDecisionHook"""

    def test_simple_greeting(self):
        hook = RoutingDecisionHook()
        loop = MagicMock()
        ctx = AgentContext(agent_id="test", session_id="session1")
        ctx.add_message("user", "你好")

        result = hook(loop, ctx)

        self.assertEqual(ctx.metadata["routing"]["type"], "simple")

    def test_complex_question(self):
        hook = RoutingDecisionHook()
        loop = MagicMock()
        ctx = AgentContext(agent_id="test", session_id="session1")
        ctx.add_message("user", "请详细解释一下Python中的装饰器是什么以及如何使用它")

        result = hook(loop, ctx)

        # Long questions should be complex
        self.assertEqual(ctx.metadata["routing"]["type"], "complex")


class TestToolSelectionHook(unittest.TestCase):
    """Test ToolSelectionHook"""

    def test_standard_for_normal_task(self):
        hook = ToolSelectionHook()
        loop = MagicMock()
        ctx = AgentContext(agent_id="test", session_id="session1")
        ctx.add_message("user", "请帮我写一个排序算法")
        ctx.metadata["routing"] = {"type": "complex"}

        result = hook(loop, ctx)

        self.assertEqual(ctx.metadata["routing"]["tool_id"], "standard")

    def test_supervised_for_high_risk(self):
        hook = ToolSelectionHook()
        loop = MagicMock()
        ctx = AgentContext(agent_id="test", session_id="session1")
        ctx.add_message("user", "帮我转账10000元到账户X")
        ctx.metadata["routing"] = {"type": "complex"}

        result = hook(loop, ctx)

        self.assertEqual(ctx.metadata["routing"]["tool_id"], "supervised")

    def test_swarms_for_multi_step(self):
        hook = ToolSelectionHook()
        loop = MagicMock()
        ctx = AgentContext(agent_id="test", session_id="session1")
        ctx.add_message("user", "分析对比A公司的财务状况和市场表现")
        ctx.metadata["routing"] = {"type": "complex"}

        result = hook(loop, ctx)

        self.assertEqual(ctx.metadata["routing"]["tool_id"], "swarms")


class TestMasterLoop(unittest.TestCase):
    """Test MasterLoop"""

    def test_routing_recording(self):
        agent = MagicMock()
        agent.agent_id = "test"
        agent.config = AgentConfig("test", "master")
        agent.evaluate = lambda: {"routing_accuracy": 0.8}

        loop = MasterLoop(agent, {"max_iterations": 2})

        loop.record_routing({"type": "simple", "tool_id": "direct"}, correct=True)
        loop.record_routing({"type": "complex", "tool_id": "standard"}, correct=False)

        self.assertEqual(len(loop.routing_history), 2)
        self.assertEqual(loop.calc_routing_accuracy(), 0.5)

    def test_routing_accuracy_calculation(self):
        agent = MagicMock()
        agent.agent_id = "test"
        agent.config = AgentConfig("test", "master")

        loop = MasterLoop(agent, {"max_iterations": 2})

        # All correct
        loop.routing_history = [
            {"correct": True},
            {"correct": True},
            {"correct": True},
        ]
        self.assertEqual(loop.calc_routing_accuracy(), 1.0)

        # Mixed
        loop.routing_history = [
            {"correct": True},
            {"correct": False},
        ]
        self.assertEqual(loop.calc_routing_accuracy(), 0.5)


if __name__ == "__main__":
    unittest.main()
