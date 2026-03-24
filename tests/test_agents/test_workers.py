"""
Tests for Worker Agents
"""
import unittest
from unittest.mock import MagicMock, patch
from swarmbot.agents.workers import (
    BaseWorkerAgent, WorkerLoop,
    StandardWorkerAgent, StandardWorkerLoop,
    SupervisedWorkerAgent, SupervisedWorkerLoop,
    SwarmsWorkerAgent, SwarmsWorkerLoop
)
from swarmbot.agents.base import AgentContext, AgentConfig, BaseAgent


class MockWorkerAgent(BaseAgent):
    """Mock Worker Agent for testing"""

    def __init__(self):
        config = AgentConfig(
            agent_id="test-worker",
            role="worker",
            max_iterations=3
        )
        super().__init__(config)
        self.worker_type = "mock"

    def think(self, context: AgentContext) -> str:
        return "Worker response"

    def execute_tool(self, tool_name: str, arguments: dict) -> any:
        return {"executed": tool_name}

    def evaluate(self, output: str, context: AgentContext) -> dict:
        return {"quality": 0.7}


class TestWorkerLoop(unittest.TestCase):
    """Test WorkerLoop base"""

    def test_execution_recording(self):
        agent = MockWorkerAgent()
        loop = WorkerLoop(agent, {"max_iterations": 3})

        loop.record_execution({
            "step": 1,
            "name": "Test Step",
            "duration": 1.5,
            "quality": 0.8
        })

        self.assertEqual(len(loop.execution_history), 1)
        self.assertEqual(loop.get_quality_score(), 0.8)

    def test_metrics_aggregation(self):
        agent = MockWorkerAgent()
        loop = WorkerLoop(agent, {"max_iterations": 3})

        for i in range(3):
            loop.record_execution({
                "step": i + 1,
                "name": f"Step {i+1}",
                "duration": 1.0 + i * 0.5,
                "quality": 0.6 + i * 0.1,
                "accurate": i < 2
            })

        self.assertAlmostEqual(loop.calc_step_accuracy(), 2/3, places=2)
        self.assertAlmostEqual(loop.get_execution_time(), 1.5, places=2)


class TestStandardWorkerAgent(unittest.TestCase):
    """Test StandardWorkerAgent"""

    def test_step_counting(self):
        agent = StandardWorkerAgent()
        agent.reset_steps()

        self.assertEqual(agent.step(), 1)
        self.assertEqual(agent.step(), 2)
        self.assertEqual(agent.step(), 3)

        agent.reset_steps()
        self.assertEqual(agent.step(), 1)

    def test_worker_type(self):
        agent = StandardWorkerAgent()
        self.assertEqual(agent.worker_type, "standard")


class TestSupervisedWorkerAgent(unittest.TestCase):
    """Test SupervisedWorkerAgent"""

    def test_checkpoint_steps(self):
        agent = SupervisedWorkerAgent()
        self.assertIn("理解问题", agent.CHECKPOINT_STEPS)
        self.assertIn("制定计划", agent.CHECKPOINT_STEPS)

    def test_worker_type(self):
        agent = SupervisedWorkerAgent()
        self.assertEqual(agent.worker_type, "supervised")


class TestSwarmsWorkerAgent(unittest.TestCase):
    """Test SwarmsWorkerAgent"""

    def test_worker_type(self):
        agent = SwarmsWorkerAgent()
        self.assertEqual(agent.worker_type, "swarms")

    def test_result_integration(self):
        agent = SwarmsWorkerAgent()

        results = [
            {"task": "Task 1", "result": {"content": "Result 1", "duration": 1.0, "quality": 0.8}, "worker_id": "w1"},
            {"task": "Task 2", "result": {"content": "Result 2", "duration": 2.0, "quality": 0.9}, "worker_id": "w2"},
        ]

        integrated = agent._integrate_results(results)

        self.assertIn("content", integrated)
        self.assertEqual(integrated["worker_count"], 2)
        self.assertAlmostEqual(integrated["quality"], 0.85, places=2)


if __name__ == "__main__":
    unittest.main()
