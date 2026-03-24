"""
Tests for Agent Loop Base Framework
"""
import unittest
import time
from swarmbot.agents.base import (
    BaseAgent, AgentConfig, AgentContext, RunResult,
    EventBus, AgentEvent, EventType, EventPhase,
    AgentLoop, Hook
)


class MockAgent(BaseAgent):
    """Mock Agent for testing"""

    def __init__(self):
        config = AgentConfig(
            agent_id="test-agent",
            role="test",
            max_iterations=3
        )
        super().__init__(config)

    def think(self, context: AgentContext) -> str:
        return f"Response to: {context.messages[-1].content if context.messages else 'empty'}"

    def execute_tool(self, tool_name: str, arguments: dict) -> any:
        return {"executed": tool_name, "args": arguments}

    def evaluate(self, output: str, context: AgentContext) -> dict:
        return {
            "quality": 0.8 if len(output) > 10 else 0.5,
            "tool_executed": False,
            "needs_continue": False
        }


class TestAgentContext(unittest.TestCase):
    """Test AgentContext"""

    def test_create_context(self):
        ctx = AgentContext(agent_id="test", session_id="session1")
        self.assertEqual(ctx.agent_id, "test")
        self.assertEqual(ctx.session_id, "session1")
        self.assertEqual(len(ctx.messages), 0)

    def test_add_message(self):
        ctx = AgentContext(agent_id="test", session_id="session1")
        ctx.add_message("user", "Hello")
        self.assertEqual(len(ctx.messages), 1)
        self.assertEqual(ctx.messages[0].role, "user")
        self.assertEqual(ctx.messages[0].content, "Hello")

    def test_compact(self):
        ctx = AgentContext(agent_id="test", session_id="session1")
        for i in range(25):
            ctx.add_message("user", f"Message {i}")
        ctx.compact(keep_turns=5)
        # Should keep system + summary + 10 recent messages
        self.assertLess(len(ctx.messages), 25)


class TestEventBus(unittest.TestCase):
    """Test EventBus"""

    def test_emit_event(self):
        bus = EventBus()
        event = AgentEvent(
            event_type=EventType.LIFECYCLE,
            phase=EventPhase.START,
            agent_id="test"
        )
        bus.emit(event)
        events = bus.get_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].agent_id, "test")

    def test_subscribe(self):
        bus = EventBus()
        received = []

        def callback(event):
            received.append(event)

        bus.subscribe(EventType.LIFECYCLE, callback)
        bus.emit(AgentEvent(EventType.LIFECYCLE, EventPhase.START, "test"))
        self.assertEqual(len(received), 1)


class TestAgentLoop(unittest.TestCase):
    """Test AgentLoop"""

    def test_loop_execution(self):
        agent = MockAgent()
        loop = AgentLoop(agent, {"max_iterations": 2})

        result = loop.run("Hello, agent!")

        self.assertTrue(result.success)
        self.assertGreater(result.iterations, 0)
        self.assertIn("Hello", result.content)

    def test_hook_registration(self):
        agent = MockAgent()
        loop = AgentLoop(agent, {"max_iterations": 1})

        hook_called = []

        def test_hook(loop, *args):
            hook_called.append(True)
            return args[0] if args else None

        loop.register_hook(Hook.BEFORE_THINK, test_hook)
        loop.run("Test input")

        self.assertEqual(len(hook_called), 1)

    def test_tool_execution(self):
        agent = MockAgent()
        loop = AgentLoop(agent, {"max_iterations": 1})

        result = loop.run('{"tool": "test_tool", "args": {"key": "value"}}')

        # Should have executed the tool
        self.assertTrue(result.success)


if __name__ == "__main__":
    unittest.main()
