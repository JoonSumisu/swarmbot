"""
Tests for AutoresearchMixin and Evaluators
"""
import unittest
import time
from swarmbot.agents.research import (
    AutoresearchMixin, ExperimentRecord,
    MetricsEvaluator, AntiOverOptimization
)


class TestAutoresearchMixin(unittest.TestCase):
    """Test AutoresearchMixin"""

    def setUp(self):
        class TestAgent(AutoresearchMixin):
            def __init__(self):
                AutoresearchMixin.__init__(self)
                self.eval_count = 0
                self.best_score = 0

            def evaluate(self):
                self.eval_count += 1
                # Simulate improving score
                return {"score": 0.5 + (self.eval_count * 0.1), "accuracy": 0.8}

            def is_improvement(self, current, baseline):
                return current["score"] > baseline["score"]

            def apply_experiment(self, suggestion):
                return True

        self.agent = TestAgent()

    def test_baseline(self):
        result = self.agent.research_cycle()
        self.assertTrue(result)
        self.assertIsNotNone(self.agent.baseline)
        self.assertEqual(len(self.agent.experiment_history), 1)
        self.assertEqual(self.agent.experiment_history[0].status, "baseline")

    def test_research_cycles(self):
        for _ in range(3):
            self.agent.research_cycle()

        self.assertEqual(len(self.agent.experiment_history), 3)

    def test_improvement_detection(self):
        self.agent.best = {"score": 0.7}
        current = {"score": 0.8}
        self.assertTrue(self.agent.is_improvement(current, self.agent.best))

    def test_research_summary(self):
        self.agent.research_cycle()
        summary = self.agent.get_research_summary()

        self.assertIn("total_experiments", summary)
        self.assertEqual(summary["total_experiments"], 1)


class TestMetricsEvaluator(unittest.TestCase):
    """Test MetricsEvaluator"""

    def test_record_and_get(self):
        evaluator = MetricsEvaluator(smoothing_window=5)

        evaluator.record("accuracy", 0.8)
        evaluator.record("accuracy", 0.85)

        self.assertEqual(evaluator.get_latest("accuracy"), 0.85)
        self.assertIsNotNone(evaluator.get_moving_average("accuracy"))

    def test_variance_calculation(self):
        evaluator = MetricsEvaluator(smoothing_window=3)

        evaluator.record("test", 1.0)
        evaluator.record("test", 2.0)
        evaluator.record("test", 3.0)

        variance = evaluator.get_variance("test")
        self.assertGreater(variance, 0)

    def test_stability_detection(self):
        evaluator = MetricsEvaluator(smoothing_window=5)

        # Stable data
        for v in [0.8, 0.81, 0.79, 0.82, 0.80]:
            evaluator.record("stable_metric", v)

        self.assertTrue(evaluator.is_stable("stable_metric", threshold=0.2))

    def test_trend_detection(self):
        evaluator = MetricsEvaluator(smoothing_window=5)

        # Increasing trend
        for v in [0.5, 0.6, 0.7, 0.8, 0.9]:
            evaluator.record("increasing", v)

        self.assertEqual(evaluator.get_trend("increasing"), "increasing")

    def test_improvement_percent(self):
        evaluator = MetricsEvaluator()

        percent = evaluator.get_improvement_percent("test", 0.6, 0.5, "maximize")
        self.assertAlmostEqual(percent, 20.0, places=5)

        percent = evaluator.get_improvement_percent("test", 0.4, 0.5, "minimize")
        self.assertAlmostEqual(percent, 20.0, places=5)


class TestAntiOverOptimization(unittest.TestCase):
    """Test AntiOverOptimization"""

    def test_initial_state(self):
        anti_opt = AntiOverOptimization(
            min_interval=60,
            max_per_hour=2
        )

        # Check initial state (after initialization, can optimize)
        status = anti_opt.get_status()
        self.assertIn("min_interval", status)

    def test_record_and_check(self):
        anti_opt = AntiOverOptimization(
            max_per_hour=2
        )

        # Record an optimization
        anti_opt.record_optimization()
        
        # Should still be able to optimize
        status = anti_opt.get_status()
        self.assertEqual(status["optimization_count_this_hour"], 1)

    def test_status(self):
        anti_opt = AntiOverOptimization(
            min_interval=3600,
            max_per_hour=2,
            stability_threshold=0.2
        )

        status = anti_opt.get_status()
        
        self.assertEqual(status["min_interval"], 3600)
        self.assertEqual(status["max_per_hour"], 2)
        self.assertEqual(status["stability_threshold"], 0.2)


if __name__ == "__main__":
    unittest.main()
