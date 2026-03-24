from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..base.loop import AgentLoop, Hook
from ..base import AgentContext
from ..research import AutoresearchMixin, MetricsEvaluator, AntiOverOptimization

if TYPE_CHECKING:
    from .engine import AutonomousEngine


class AutonomousLoop(AgentLoop, AutoresearchMixin):
    """
    Autonomous Loop - Bundle Research Loop
    
    参考 autoresearch 理念:
    - 固定时间预算 (默认 5 分钟)
    - 评估 → 修改 → 验证 → 保留/丢弃
    - 最多 5 次迭代
    - Anti-Over-Optimization 保护
    """

    MAX_ITERATIONS = 5

    def __init__(self, engine: "AutonomousEngine", config: Dict[str, Any]):
        AgentLoop.__init__(self, engine, config)
        AutoresearchMixin.__init__(self)
        
        self.max_iterations = self.MAX_ITERATIONS
        self.time_budget = config.get("time_budget", 300)  # 5 分钟
        
        # Anti-Over-Optimization
        anti_opt_config = config.get("anti_over_optimization", {})
        self.anti_opt = AntiOverOptimization(
            min_interval=anti_opt_config.get("min_interval", 3600),
            max_per_hour=anti_opt_config.get("max_per_hour", 2),
            stability_threshold=anti_opt_config.get("stability_threshold", 0.2),
            pause_on_instability=anti_opt_config.get("pause_on_instability", True)
        )
        
        # 指标评估器
        self.metrics_evaluator = MetricsEvaluator(smoothing_window=5)
        
        # Bundle 历史
        self.bundle_history: List[Dict[str, Any]] = []

    def evaluate(self) -> Dict[str, Any]:
        """评估 Bundle 状态"""
        engine = self.agent
        return {
            "bundle_efficiency": engine.calc_bundle_efficiency(),
            "success_rate": engine.calc_success_rate(),
            "resource_usage": engine.calc_resource_usage(),
            "conflict_rate": engine.calc_conflict_rate()
        }

    def is_improvement(self, current: Dict[str, Any], baseline: Dict[str, Any]) -> bool:
        """判断是否有改进"""
        # 综合评分
        current_score = (
            current.get("bundle_efficiency", 0) * 0.4 +
            current.get("success_rate", 0) * 0.4 +
            (1 - current.get("conflict_rate", 0)) * 0.2
        )
        baseline_score = (
            baseline.get("bundle_efficiency", 0) * 0.4 +
            baseline.get("success_rate", 0) * 0.4 +
            (1 - baseline.get("conflict_rate", 0)) * 0.2
        )
        return current_score > baseline_score

    def apply_experiment(self, suggestion: List[Dict[str, Any]]) -> bool:
        """应用实验修改"""
        engine = self.agent
        
        for s in suggestion:
            if s.get("type") == "bundle_modification":
                bundle_id = s.get("bundle_id")
                modifications = s.get("modifications", {})
                return engine.apply_bundle_modification(bundle_id, modifications)
        
        return True

    def revert_experiment(self):
        """回退实验"""
        engine = self.agent
        engine.revert_bundle_modification()

    def generate_suggestions(self, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成修改建议"""
        suggestions = []
        
        # 基于指标的优化建议
        if metrics.get("bundle_efficiency", 0) < 0.5:
            suggestions.append({
                "type": "bundle_modification",
                "bundle_id": "core.memory_foundation",
                "modifications": {"interval_seconds": 3600},
                "reason": "低效率，需要增加执行间隔"
            })
        
        if metrics.get("conflict_rate", 0) > 0.1:
            suggestions.append({
                "type": "bundle_modification",
                "bundle_id": "core.bundle_governor",
                "modifications": {"interval_seconds": 180},
                "reason": "高冲突率，需要更频繁检测"
            })
        
        return suggestions

    def get_primary_metric(self) -> str:
        return "bundle_efficiency"

    def get_metric_direction(self) -> str:
        return "maximize"

    def can_bundle_optimize(self, bundle_id: str) -> tuple[bool, str]:
        """检查 Bundle 是否可以优化"""
        return self.anti_opt.can_optimize(bundle_id)

    def record_bundle_execution(self, bundle_id: str, metrics: Dict[str, Any]):
        """记录 Bundle 执行"""
        record = {
            "bundle_id": bundle_id,
            "timestamp": time.time(),
            "metrics": metrics
        }
        self.bundle_history.append(record)
        
        # 更新 Anti-Over-Optimization
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                self.anti_opt.record_metric(key, value)
        
        # 限制历史
        if len(self.bundle_history) > 200:
            self.bundle_history = self.bundle_history[-100:]

    def research_cycle(self) -> bool:
        """执行研究循环"""
        # 检查 Anti-Over-Optimization
        can_opt, reason = self.can_bundle_optimize("general")
        
        if not can_opt:
            return False
        
        # 执行研究
        result = AutoresearchMixin.research_cycle(self)
        
        if result:
            self.anti_opt.record_optimization()
        
        return result

    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            "max_iterations": self.max_iterations,
            "time_budget": self.time_budget,
            "time_remaining": self.time_budget - (time.time() - (self._start_time or time.time())) if self._start_time else self.time_budget,
            "experiments_count": len(self.experiment_history),
            "anti_opt_status": self.anti_opt.get_status(),
            "bundle_count": len(self.bundle_history)
        }


class BundleOptimizationHook:
    """Bundle 优化 Hook"""

    def __call__(self, loop: AgentLoop, context: AgentContext) -> AgentContext:
        """在 Think 前检查是否需要优化"""
        autonomous_loop = loop
        
        if isinstance(autonomous_loop, AutonomousLoop):
            # 检查优化条件
            can_opt, reason = autonomous_loop.can_bundle_optimize("general")
            
            context.metadata["optimization_allowed"] = can_opt
            context.metadata["optimization_blocked_reason"] = reason if not can_opt else None
        
        return context
