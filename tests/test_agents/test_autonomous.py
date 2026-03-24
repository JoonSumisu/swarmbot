"""
Tests for AutonomousLoop
"""
import unittest
import time
from unittest.mock import MagicMock, patch
from swarmbot.agents.autonomous import AutonomousLoop, BundleOptimizationHook
from swarmbot.agents.base import AgentContext, AgentConfig


class MockAutonomousEngine:
    """Mock AutonomousEngine for testing"""
    
    agent_id = "autonomous"
    config = None

    def __init__(self):
        self.execution_count = 0
        self.success_count = 0

    def calc_bundle_efficiency(self):
        if self.execution_count == 0:
            return 0.5
        return self.success_count / self.execution_count

    def calc_success_rate(self):
        return self.calc_bundle_efficiency()

    def calc_resource_usage(self):
        return 0.3

    def calc_conflict_rate(self):
        return 0.05

    def apply_bundle_modification(self, bundle_id, modifications):
        return True

    def revert_bundle_modification(self):
        pass


class TestAutonomousLoop(unittest.TestCase):
    """Test AutonomousLoop"""

    def test_initialization(self):
        engine = MockAutonomousEngine()
        loop = AutonomousLoop(engine, {"max_iterations": 5, "time_budget": 300})

        self.assertEqual(loop.max_iterations, 5)
        self.assertEqual(loop.time_budget, 300)

    def test_evaluation(self):
        engine = MockAutonomousEngine()
        loop = AutonomousLoop(engine, {"max_iterations": 5})

        metrics = loop.evaluate()

        self.assertIn("bundle_efficiency", metrics)
        self.assertIn("success_rate", metrics)
        self.assertIn("resource_usage", metrics)

    def test_is_improvement(self):
        engine = MockAutonomousEngine()
        loop = AutonomousLoop(engine, {"max_iterations": 5})

        baseline = {"bundle_efficiency": 0.5, "success_rate": 0.5, "conflict_rate": 0.1}
        current = {"bundle_efficiency": 0.6, "success_rate": 0.6, "conflict_rate": 0.1}

        self.assertTrue(loop.is_improvement(current, baseline))

    def test_bundle_execution_recording(self):
        engine = MockAutonomousEngine()
        loop = AutonomousLoop(engine, {"max_iterations": 5})

        loop.record_bundle_execution("core.memory_foundation", {
            "bundle_efficiency": 0.8,
            "success_rate": 0.9
        })

        self.assertEqual(len(loop.bundle_history), 1)
        self.assertEqual(loop.bundle_history[0]["bundle_id"], "core.memory_foundation")

    def test_suggestion_generation(self):
        engine = MockAutonomousEngine()
        loop = AutonomousLoop(engine, {"max_iterations": 5})

        # Low efficiency metrics
        metrics = {"bundle_efficiency": 0.3, "conflict_rate": 0.2}
        suggestions = loop.generate_suggestions(metrics)

        self.assertGreater(len(suggestions), 0)

    def test_status(self):
        engine = MockAutonomousEngine()
        loop = AutonomousLoop(engine, {"max_iterations": 5, "time_budget": 300})

        status = loop.get_status()

        self.assertIn("max_iterations", status)
        self.assertIn("time_budget", status)
        self.assertIn("anti_opt_status", status)


class TestBundleOptimizationHook(unittest.TestCase):
    """Test BundleOptimizationHook"""

    def test_optimization_hook_exists(self):
        hook = BundleOptimizationHook()
        self.assertIsNotNone(hook)
        self.assertTrue(callable(hook))


if __name__ == "__main__":
    unittest.main()
