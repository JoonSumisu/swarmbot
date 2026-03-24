from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .events import EventBus, AgentEvent, EventType, EventPhase
from .context import AgentContext

if TYPE_CHECKING:
    from ..llm_client import OpenAICompatibleClient


@dataclass
class AgentConfig:
    """Agent 配置"""
    agent_id: str
    role: str
    max_iterations: int = 10
    timeout_seconds: int = 300
    enable_tools: bool = True
    enable_memory: bool = True
    compact_threshold: int = 20


@dataclass
class RunResult:
    """运行结果"""
    success: bool
    content: str
    iterations: int
    duration: float
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class BaseAgent(ABC):
    """
    Agent 基类 - 所有 Agent 的抽象基类
    
    设计原则:
    1. Loop 与 Agent 分离 - Loop 负责流程控制，Agent 负责业务逻辑
    2. Hook 系统 - 各阶段可拦截、修改、注入
    3. Event 系统 - 可观测、可追踪
    """

    def __init__(self, config: AgentConfig):
        self.config = config
        self.agent_id = config.agent_id
        self.role = config.role
        self._event_bus = EventBus()
        self._hooks: Dict[str, List[callable]] = {}
        self._running = False
        self._start_time: Optional[float] = None

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    @abstractmethod
    def think(self, context: AgentContext) -> str:
        """思考 - 生成回复或决策"""
        raise NotImplementedError

    @abstractmethod
    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """执行工具"""
        raise NotImplementedError

    @abstractmethod
    def evaluate(self, output: str, context: AgentContext) -> Dict[str, Any]:
        """评估输出质量"""
        raise NotImplementedError

    def should_use_tools(self, context: AgentContext) -> bool:
        """判断是否需要使用工具"""
        return self.config.enable_tools

    def should_compact(self, context: AgentContext) -> bool:
        """判断是否需要压缩"""
        return len(context.messages) > self.config.compact_threshold

    def compact(self, context: AgentContext):
        """压缩上下文"""
        context.compact(keep_turns=10)

    def get_tools(self) -> Dict[str, callable]:
        """获取可用工具"""
        return {}

    def get_system_prompt(self) -> str:
        """获取系统提示词"""
        return ""

    def get_boot_files(self) -> Dict[str, str]:
        """获取 boot 文件"""
        return {}

    def register_hook(self, hook_name: str, callback: callable):
        """注册 Hook"""
        if hook_name not in self._hooks:
            self._hooks[hook_name] = []
        self._hooks[hook_name].append(callback)

    def run_hook(self, hook_name: str, *args, **kwargs) -> Any:
        """运行 Hook"""
        results = []
        for callback in self._hooks.get(hook_name, []):
            try:
                result = callback(self, *args, **kwargs)
                results.append(result)
                # 发射 hook 事件
                self._event_bus.emit(AgentEvent(
                    event_type=EventType.HOOK,
                    phase=EventPhase.THINK,
                    agent_id=self.agent_id,
                    data={"hook": hook_name, "result": result}
                ))
            except Exception as e:
                pass
        return results

    def emit_lifecycle(self, phase: EventPhase):
        """发射生命周期事件"""
        self._event_bus.emit(AgentEvent(
            event_type=EventType.LIFECYCLE,
            phase=phase,
            agent_id=self.agent_id
        ))

    def emit_metrics(self, metrics: Dict[str, Any]):
        """发射指标事件"""
        self._event_bus.emit(AgentEvent(
            event_type=EventType.METRICS,
            phase=EventPhase.EVALUATE,
            agent_id=self.agent_id,
            data=metrics
        ))

    def get_metrics(self) -> Dict[str, Any]:
        """获取指标摘要"""
        return self._event_bus.get_metrics_summary()

    def reset(self):
        """重置 Agent 状态"""
        self._event_bus.clear()
        self._running = False
        self._start_time = None
