from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MetricValue:
    """指标值"""
    value: float
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class MetricsEvaluator:
    """
    指标评估器
    
    功能:
    1. 追踪历史指标
    2. 计算移动平均
    3. 检测趋势
    4. 异常检测
    """

    def __init__(self, smoothing_window: int = 5):
        self.smoothing_window = smoothing_window
        self._history: Dict[str, List[MetricValue]] = {}

    def record(self, metric_name: str, value: float, metadata: Optional[Dict[str, Any]] = None):
        """记录指标值"""
        if metric_name not in self._history:
            self._history[metric_name] = []
        
        self._history[metric_name].append(MetricValue(
            value=value,
            timestamp=time.time(),
            metadata=metadata or {}
        ))
        
        # 限制历史长度
        if len(self._history[metric_name]) > self.smoothing_window * 3:
            self._history[metric_name] = self._history[metric_name][-self.smoothing_window * 2:]

    def get_latest(self, metric_name: str) -> Optional[float]:
        """获取最新值"""
        history = self._history.get(metric_name, [])
        return history[-1].value if history else None

    def get_moving_average(self, metric_name: str, window: Optional[int] = None) -> Optional[float]:
        """获取移动平均"""
        window = window or self.smoothing_window
        history = self._history.get(metric_name, [])
        
        if not history:
            return None
            
        recent = history[-window:]
        return sum(m.value for m in recent) / len(recent)

    def get_variance(self, metric_name: str, window: Optional[int] = None) -> float:
        """获取方差"""
        window = window or self.smoothing_window
        history = self._history.get(metric_name, [])
        
        if len(history) < 2:
            return 0.0
            
        recent = history[-window:]
        values = [m.value for m in recent]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return variance

    def get_std_dev(self, metric_name: str, window: Optional[int] = None) -> float:
        """获取标准差"""
        return self.get_variance(metric_name, window) ** 0.5

    def get_coefficient_of_variation(self, metric_name: str, window: Optional[int] = None) -> float:
        """获取变异系数 (CV = std_dev / mean)"""
        mean = self.get_moving_average(metric_name, window)
        std = self.get_std_dev(metric_name, window)
        
        if mean == 0:
            return 0.0
        return std / abs(mean)

    def is_stable(self, metric_name: str, threshold: float = 0.2) -> bool:
        """判断是否稳定 (CV < threshold)"""
        cv = self.get_coefficient_of_variation(metric_name)
        return cv < threshold

    def get_trend(self, metric_name: str, window: Optional[int] = None) -> str:
        """
        获取趋势方向
        
        Returns:
            "increasing", "decreasing", "stable"
        """
        window = window or self.smoothing_window
        history = self._history.get(metric_name, [])
        
        if len(history) < 3:
            return "stable"
        
        recent = history[-window:]
        if len(recent) < 3:
            return "stable"
            
        # 简单线性回归
        n = len(recent)
        x_mean = (n - 1) / 2
        y_values = [m.value for m in recent]
        y_mean = sum(y_values) / n
        
        numerator = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(y_values))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return "stable"
            
        slope = numerator / denominator
        
        # 判断趋势
        threshold = abs(y_mean) * 0.01  # 1% 变化阈值
        if slope > threshold:
            return "increasing"
        elif slope < -threshold:
            return "decreasing"
        return "stable"

    def compare(self, metric_name: str, value: float, baseline: float, direction: str = "maximize") -> bool:
        """
        比较值与基线
        
        Args:
            metric_name: 指标名
            value: 当前值
            baseline: 基线值
            direction: "maximize" 或 "minimize"
            
        Returns:
            True 如果有改进
        """
        if direction == "maximize":
            return value > baseline
        else:
            return value < baseline

    def get_improvement_percent(self, metric_name: str, current: float, baseline: float, direction: str = "maximize") -> float:
        """获取改进百分比"""
        if baseline == 0:
            return 0.0
        
        if direction == "maximize":
            return ((current - baseline) / baseline) * 100
        else:
            return ((baseline - current) / baseline) * 100

    def get_summary(self, metric_name: str) -> Dict[str, Any]:
        """获取指标摘要"""
        history = self._history.get(metric_name, [])
        
        if not history:
            return {"status": "no_data"}
        
        values = [m.value for m in history]
        
        return {
            "count": len(values),
            "latest": values[-1],
            "mean": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "moving_average": self.get_moving_average(metric_name),
            "variance": self.get_variance(metric_name),
            "std_dev": self.get_std_dev(metric_name),
            "cv": self.get_coefficient_of_variation(metric_name),
            "trend": self.get_trend(metric_name),
            "stable": self.is_stable(metric_name)
        }

    def get_all_summaries(self) -> Dict[str, Dict[str, Any]]:
        """获取所有指标摘要"""
        return {
            name: self.get_summary(name)
            for name in self._history
        }


class AntiOverOptimization:
    """
    Anti-Over-Optimization 保护
    
    防止过度优化导致的不稳定
    """

    def __init__(
        self,
        min_interval: int = 3600,
        max_per_hour: int = 2,
        stability_threshold: float = 0.2,
        pause_on_instability: bool = True
    ):
        self.min_interval = min_interval
        self.max_per_hour = max_per_hour
        self.stability_threshold = stability_threshold
        self.pause_on_instability = pause_on_instability
        
        self._last_optimization_ts = 0
        self._optimization_count_this_hour = 0
        self._hourly_reset_ts = int(time.time()) // 3600
        
        self.evaluator = MetricsEvaluator()

    def can_optimize(self, metric_name: str) -> tuple[bool, str]:
        """
        检查是否可以优化
        
        Returns:
            (can_optimize, reason)
        """
        # 检查冷却时间
        if time.time() - self._last_optimization_ts < self.min_interval:
            return False, f"cooldown (min_interval={self.min_interval})"
        
        # 检查小时限制
        current_hour = int(time.time()) // 3600
        if current_hour > self._hourly_reset_ts:
            self._optimization_count_this_hour = 0
            self._hourly_reset_ts = current_hour
            
        if self._optimization_count_this_hour >= self.max_per_hour:
            return False, f"hourly_limit (max={self.max_per_hour})"
        
        # 检查稳定性
        if self.pause_on_instability and not self.evaluator.is_stable(metric_name, self.stability_threshold):
            return False, f"instability (cv={self.evaluator.get_coefficient_of_variation(metric_name):.3f})"
        
        return True, "ok"

    def record_optimization(self):
        """记录一次优化"""
        self._last_optimization_ts = time.time()
        self._optimization_count_this_hour += 1

    def record_metric(self, metric_name: str, value: float):
        """记录指标"""
        self.evaluator.record(metric_name, value)

    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            "min_interval": self.min_interval,
            "max_per_hour": self.max_per_hour,
            "stability_threshold": self.stability_threshold,
            "pause_on_instability": self.pause_on_instability,
            "last_optimization_ts": self._last_optimization_ts,
            "optimization_count_this_hour": self._optimization_count_this_hour,
            "time_until_next_optimization": max(0, self.min_interval - (time.time() - self._last_optimization_ts))
        }
