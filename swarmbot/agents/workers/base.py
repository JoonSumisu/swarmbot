from __future__ import annotations

import time
from abc import abstractmethod
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..base import BaseAgent, AgentConfig, AgentContext
from ..base.loop import AgentLoop, Hook
from ..research import AutoresearchMixin, MetricsEvaluator

if TYPE_CHECKING:
    from ...llm_client import OpenAICompatibleClient


class WorkerLoop(AgentLoop, AutoresearchMixin):
    """
    Worker Loop 基类
    
    所有 Worker Loop 的通用实现:
    - 融合 AutoresearchMixin 用于执行优化
    - 最大 3 次迭代
    - 支持中间结果评估
    """

    MAX_ITERATIONS = 3

    def __init__(self, agent: "BaseWorkerAgent", config: Dict[str, Any]):
        AgentLoop.__init__(self, agent, config)
        AutoresearchMixin.__init__(self)
        
        self.max_iterations = self.MAX_ITERATIONS
        
        # 指标评估器
        self.metrics_evaluator = MetricsEvaluator(smoothing_window=5)
        
        # 执行历史
        self.execution_history: List[Dict[str, Any]] = []

    @abstractmethod
    def execute_step(self, context: AgentContext, step: int) -> Dict[str, Any]:
        """执行单个步骤 - 子类实现"""
        raise NotImplementedError

    def evaluate(self) -> Dict[str, Any]:
        """评估当前状态"""
        return {
            "step_accuracy": self.calc_step_accuracy(),
            "execution_time": self.get_execution_time(),
            "quality_score": self.get_quality_score()
        }

    def is_improvement(self, current: Dict[str, Any], baseline: Dict[str, Any]) -> bool:
        """判断是否有改进"""
        # 综合评分
        current_score = (
            current.get("step_accuracy", 0) * 0.4 +
            current.get("quality_score", 0) * 0.4 +
            (1 - min(1, current.get("execution_time", 1) / 60)) * 0.2
        )
        baseline_score = (
            baseline.get("step_accuracy", 0) * 0.4 +
            baseline.get("quality_score", 0) * 0.4 +
            (1 - min(1, baseline.get("execution_time", 1) / 60)) * 0.2
        )
        return current_score > baseline_score

    def apply_experiment(self, suggestion: List[Dict[str, Any]]) -> bool:
        """应用实验修改"""
        return True

    def revert_experiment(self):
        """回退实验"""
        pass

    def get_primary_metric(self) -> str:
        return "quality_score"

    def get_metric_direction(self) -> str:
        return "maximize"

    def calc_step_accuracy(self) -> float:
        """计算步骤准确率"""
        if not self.execution_history:
            return 0.5
        accurate = sum(1 for e in self.execution_history if e.get("accurate", False))
        return accurate / len(self.execution_history)

    def get_execution_time(self) -> float:
        """获取执行时间"""
        if not self.execution_history:
            return 0
        times = [e.get("duration", 0) for e in self.execution_history]
        return sum(times) / len(times)

    def get_quality_score(self) -> float:
        """获取质量分数"""
        if not self.execution_history:
            return 0.5
        scores = [e.get("quality", 0.5) for e in self.execution_history]
        return sum(scores) / len(scores)

    def record_execution(self, record: Dict[str, Any]):
        """记录执行"""
        self.execution_history.append(record)
        
        # 更新指标
        self.metrics_evaluator.record("step_accuracy", self.calc_step_accuracy())
        self.metrics_evaluator.record("quality_score", self.get_quality_score())
        
        # 限制历史
        if len(self.execution_history) > 100:
            self.execution_history = self.execution_history[-50:]


class BaseWorkerAgent(BaseAgent):
    """
    Worker Agent 基类
    
    每个推理工具对应一个 Worker:
    - Standard Worker: 标准 8 步推理
    - Supervised Worker: 人在回路推理
    - Swarms Worker: 多 Worker 协作
    """

    def __init__(self, config: AgentConfig, worker_type: str):
        super().__init__(config)
        self.worker_type = worker_type
        
        # Worker Loop
        self.loop = WorkerLoop(self, {"max_iterations": WorkerLoop.MAX_ITERATIONS})
        
        # 步骤计数
        self.step_count = 0

    @abstractmethod
    def execute_task(self, user_input: str, context: AgentContext) -> Dict[str, Any]:
        """执行任务 - 子类实现"""
        raise NotImplementedError

    def think(self, context: AgentContext) -> str:
        """思考"""
        result = self.execute_task(
            context.messages[-1].content if context.messages else "",
            context
        )
        return result.get("content", str(result))

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """执行工具"""
        return {"status": "ok"}

    def evaluate(self, output: str, context: AgentContext) -> Dict[str, Any]:
        """评估"""
        return {
            "quality": self.loop.get_quality_score(),
            "step_accuracy": self.loop.calc_step_accuracy(),
            "tool_executed": False,
            "needs_continue": self.step_count < WorkerLoop.MAX_ITERATIONS
        }

    def step(self) -> int:
        """执行一步"""
        self.step_count += 1
        return self.step_count

    def reset_steps(self):
        """重置步骤计数"""
        self.step_count = 0
