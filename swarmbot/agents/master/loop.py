from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..base import AgentLoop, Hook, AgentContext, BaseAgent, AgentConfig, RunResult
from ..research import AutoresearchMixin, MetricsEvaluator

if TYPE_CHECKING:
    from ...llm_client import OpenAICompatibleClient


class RoutingDecisionHook:
    """路由决策 Hook"""

    def __call__(self, loop: AgentLoop, context: AgentContext) -> AgentContext:
        """决定走简单回复还是复杂推理"""
        user_input = context.messages[-1].content if context.messages else ""
        
        routing = {
            "type": "complex",  # 默认复杂
            "tool_id": "standard"
        }
        
        # 简单问题判断
        simple_patterns = [
            r"^(你好|hi|hello|嗨|您好)",
            r"^(谢谢|感谢|多谢)",
            r"^(再见|拜拜|bye|quit)",
            r"^(好的|好|是的|嗯|ok|okay)",
            r"^(你是谁|介绍一下你|关于你)",
            r"^(最近怎么样|怎么样)",
            r"^.{0,20}[?？]$",  # 20字以内的问句
        ]
        
        for pattern in simple_patterns:
            if re.match(pattern, user_input.lower().strip()):
                routing["type"] = "simple"
                break
        
        context.metadata["routing"] = routing
        return context


class ToolSelectionHook:
    """工具选择 Hook"""

    def __call__(self, loop: AgentLoop, context: AgentContext) -> AgentContext:
        """选择合适的推理工具"""
        routing = context.metadata.get("routing", {})
        
        if routing.get("type") == "simple":
            return context
        
        user_input = context.messages[-1].content if context.messages else ""
        
        # 默认工具
        tool_id = "standard"
        
        # 复杂任务判断
        high_risk_keywords = ["钱", "法律", "安全", "删除", "转账", "付费"]
        multi_step_keywords = ["分析", "对比", "研究", "调查"]
        parallel_keywords = ["并行", "同时", "多个", "分别"]
        
        if any(kw in user_input for kw in high_risk_keywords):
            tool_id = "supervised"
        elif any(kw in user_input for kw in parallel_keywords):
            tool_id = "swarms"
        elif sum(1 for kw in multi_step_keywords if kw in user_input) >= 2:
            tool_id = "swarms"
        
        routing["tool_id"] = tool_id
        context.metadata["routing"] = routing
        return context


class ResultInterpretationHook:
    """结果演绎 Hook"""

    def __call__(self, loop: AgentLoop, output: str, context: AgentContext) -> str:
        """演绎 LLM 输出"""
        return output  # 默认直接返回，可扩展


class MasterLoop(AgentLoop, AutoresearchMixin):
    """
    MasterAgent Loop
    
    特点:
    - 融合 AutoresearchMixin 用于路由优化
    - 内置 Hook 系统
    - 最大 2 次迭代 (简单/复杂)
    """

    MAX_ITERATIONS = 2

    def __init__(self, agent: BaseAgent, config: Dict[str, Any]):
        AgentLoop.__init__(self, agent, config)
        AutoresearchMixin.__init__(self)
        
        self.max_iterations = self.MAX_ITERATIONS
        
        # 注册默认 Hooks
        self.register_hook(Hook.BEFORE_THINK, RoutingDecisionHook())
        self.register_hook(Hook.BEFORE_THINK, ToolSelectionHook())
        self.register_hook(Hook.AFTER_THINK, ResultInterpretationHook())
        
        # 指标评估器
        self.metrics_evaluator = MetricsEvaluator(smoothing_window=5)
        
        # 路由历史
        self.routing_history: List[Dict[str, Any]] = []

    def evaluate(self) -> Dict[str, Any]:
        """评估当前状态 - 用于 Autoresearch"""
        return {
            "routing_accuracy": self.calc_routing_accuracy(),
            "tool_efficiency": self.calc_tool_efficiency(),
            "response_time": self.get_avg_response_time()
        }

    def is_improvement(self, current: Dict[str, Any], baseline: Dict[str, Any]) -> bool:
        """判断是否有改进"""
        current_score = (
            current.get("routing_accuracy", 0) * 0.5 +
            current.get("tool_efficiency", 0) * 0.3 +
            (1 - min(1, current.get("response_time", 1))) * 0.2
        )
        baseline_score = (
            baseline.get("routing_accuracy", 0) * 0.5 +
            baseline.get("tool_efficiency", 0) * 0.3 +
            (1 - min(1, baseline.get("response_time", 1))) * 0.2
        )
        return current_score > baseline_score

    def apply_experiment(self, suggestion: List[Dict[str, Any]]) -> bool:
        """应用实验修改"""
        # 路由策略调整
        for s in suggestion:
            if s.get("type") == "routing_adjustment":
                # 应用路由策略
                return True
        return True

    def revert_experiment(self):
        """回退实验"""
        pass

    def get_primary_metric(self) -> str:
        return "routing_accuracy"

    def get_metric_direction(self) -> str:
        return "maximize"

    def calc_routing_accuracy(self) -> float:
        """计算路由准确率"""
        if not self.routing_history:
            return 0.5  # 无历史，返回中性
        
        correct = sum(1 for r in self.routing_history if r.get("correct", False))
        return correct / len(self.routing_history)

    def calc_tool_efficiency(self) -> float:
        """计算工具使用效率"""
        if not self.routing_history:
            return 0.5
        
        # 简单问题用了复杂工具 = 低效
        # 复杂问题用了合适工具 = 高效
        efficient = sum(
            1 for r in self.routing_history
            if (r.get("simple") and r.get("tool") == "direct") or
               (not r.get("simple") and r.get("tool") != "direct")
        )
        return efficient / len(self.routing_history)

    def get_avg_response_time(self) -> float:
        """获取平均响应时间"""
        if not self.routing_history:
            return 1.0
        
        times = [r.get("response_time", 1) for r in self.routing_history]
        return sum(times) / len(times)

    def record_routing(self, routing: Dict[str, Any], correct: bool = None):
        """记录路由决策"""
        record = {
            "timestamp": time.time(),
            "type": routing.get("type"),
            "tool_id": routing.get("tool_id"),
            "correct": correct,
            "simple": routing.get("type") == "simple",
            "response_time": routing.get("response_time", 0)
        }
        self.routing_history.append(record)
        
        # 更新指标评估器
        self.metrics_evaluator.record("routing_accuracy", self.calc_routing_accuracy())
        
        # 限制历史长度
        if len(self.routing_history) > 100:
            self.routing_history = self.routing_history[-50:]
