from __future__ import annotations

import time
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    from ..base.base_agent import BaseAgent


@dataclass
class ExperimentRecord:
    """实验记录"""
    iteration: int
    timestamp: float
    metrics: Dict[str, Any]
    status: str  # "baseline", "keep", "discard", "crash"
    description: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


class AutoresearchMixin:
    """
    Autoresearch 逻辑混入
    
    参考 karpathy/autoresearch 理念:
    - 固定时间预算
    - 评估 → 修改 → 验证 → 保留/丢弃
    - 持续实验直到被中断
    
    使用方式:
        class MyAgent(BaseAgent, AutoresearchMixin):
            def __init__(self, config):
                BaseAgent.__init__(self, config)
                AutoresearchMixin.__init__(self)
    """

    def __init__(self):
        self.baseline: Optional[Dict[str, Any]] = None
        self.best: Optional[Dict[str, Any]] = None
        self.experiment_history: List[ExperimentRecord] = []
        self.time_budget: int = 300  # 5分钟默认
        self._current_experiment: Optional[Dict[str, Any]] = None
        self._start_time: Optional[float] = None
        self._log_dir: Optional[Path] = None

    def set_log_dir(self, log_dir: Path):
        """设置日志目录"""
        self._log_dir = log_dir
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def set_time_budget(self, seconds: int):
        """设置时间预算"""
        self.time_budget = seconds

    def evaluate(self) -> Dict[str, Any]:
        """
        评估当前状态 - 子类必须实现
        
        Returns:
            Dict 包含关键指标，如 {"accuracy": 0.85, "latency": 0.2, ...}
        """
        raise NotImplementedError

    def is_improvement(self, current: Dict[str, Any], baseline: Dict[str, Any]) -> bool:
        """
        判断是否有改进 - 子类必须实现
        
        Args:
            current: 当前评估结果
            baseline: 基线结果
            
        Returns:
            True 如果有改进
        """
        raise NotImplementedError

    def apply_experiment(self, suggestion: Dict[str, Any]) -> bool:
        """
        应用实验修改 - 子类必须实现
        
        Args:
            suggestion: 来自 generate_suggestions 的修改建议
            
        Returns:
            True 如果应用成功
        """
        raise NotImplementedError

    def revert_experiment(self):
        """回退实验 - 子类可选实现"""
        pass

    def generate_suggestions(self, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        基于当前指标生成修改建议 - 子类可选实现
        
        Args:
            metrics: 当前评估指标
            
        Returns:
            修改建议列表
        """
        return []

    def get_primary_metric(self) -> str:
        """获取主要指标名 - 子类可选实现"""
        return "score"

    def get_metric_direction(self) -> str:
        """
        获取指标方向 - 子类可选实现
        Returns: "maximize" 或 "minimize"
        """
        return "maximize"

    def research_cycle(self) -> bool:
        """
        执行一次研究循环
        
        Returns:
            True 如果实验被保留 (improved)
            False 如果实验被丢弃
        """
        if self._start_time is None:
            self._start_time = time.time()

        # 检查时间预算
        elapsed = time.time() - (self._start_time or time.time())
        if elapsed >= self.time_budget:
            return False

        # 评估当前状态
        current = self.evaluate()

        # 首次运行，记录 baseline
        if self.baseline is None:
            self.baseline = current.copy()
            self.best = current.copy()
            record = ExperimentRecord(
                iteration=len(self.experiment_history) + 1,
                timestamp=time.time(),
                metrics=current,
                status="baseline",
                description="Initial baseline"
            )
            self.experiment_history.append(record)
            self._log_record(record)
            return True

        # 生成修改建议
        suggestions = self.generate_suggestions(current)
        
        # 记录实验
        if suggestions:
            self._current_experiment = {
                "iteration": len(self.experiment_history) + 1,
                "suggestions": suggestions,
                "before_metrics": current.copy()
            }
            
            # 应用实验
            applied = self.apply_experiment(suggestions)
            if not applied:
                record = ExperimentRecord(
                    iteration=len(self.experiment_history) + 1,
                    timestamp=time.time(),
                    metrics=current,
                    status="crash",
                    description="Failed to apply experiment"
                )
                self.experiment_history.append(record)
                self._log_record(record)
                return False

        # 重新评估
        after_metrics = self.evaluate()
        
        # 判断是否有改进
        improved = self.is_improvement(after_metrics, self.baseline)

        if improved:
            self.best = after_metrics.copy()
            status = "keep"
        else:
            self.revert_experiment()
            status = "discard"

        record = ExperimentRecord(
            iteration=len(self.experiment_history) + 1,
            timestamp=time.time(),
            metrics=after_metrics,
            status=status,
            description=self._describe_experiment(after_metrics, improved),
            details={
                "before": current,
                "after": after_metrics,
                "suggestions": suggestions if suggestions else []
            }
        )
        self.experiment_history.append(record)
        self._log_record(record)
        
        self._current_experiment = None
        return improved

    def _describe_experiment(self, metrics: Dict[str, Any], improved: bool) -> str:
        """描述实验结果"""
        primary = self.get_primary_metric()
        direction = self.get_metric_direction()
        
        if self.baseline and primary in metrics and primary in self.baseline:
            before = self.baseline[primary]
            after = metrics[primary]
            delta = after - before
            
            if direction == "maximize":
                direction_str = "increased" if delta > 0 else "decreased"
            else:
                direction_str = "decreased" if delta > 0 else "increased"
                
            return f"{primary} {direction_str} from {before:.4f} to {after:.4f} ({'+' if delta > 0 else ''}{delta:.4f})"
        
        return f"Result: {'improved' if improved else 'not improved'}"

    def _log_record(self, record: ExperimentRecord):
        """记录到日志文件"""
        if self._log_dir is None:
            return
            
        try:
            log_file = self._log_dir / "research_log.jsonl"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.__dict__, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def get_research_summary(self) -> Dict[str, Any]:
        """获取研究摘要"""
        if not self.experiment_history:
            return {"status": "no_experiments"}
            
        kept = [r for r in self.experiment_history if r.status == "keep"]
        discarded = [r for r in self.experiment_history if r.status == "discard"]
        
        return {
            "total_experiments": len(self.experiment_history),
            "kept": len(kept),
            "discarded": len(discarded),
            "keep_rate": len(kept) / max(1, len(kept) + len(discarded)),
            "best_metrics": self.best,
            "baseline_metrics": self.baseline,
            "duration": time.time() - (self._start_time or time.time()) if self._start_time else 0,
            "time_budget_remaining": self.time_budget - (time.time() - (self._start_time or time.time())) if self._start_time else self.time_budget
        }

    def reset_research(self):
        """重置研究状态"""
        self.baseline = None
        self.best = None
        self.experiment_history = []
        self._current_experiment = None
        self._start_time = None
