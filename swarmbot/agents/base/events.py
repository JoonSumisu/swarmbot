from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class EventPhase(str, Enum):
    """Loop 生命周期阶段"""
    START = "start"
    THINK = "think"
    EXECUTE = "execute"
    EVALUATE = "evaluate"
    COMPACT = "compact"
    END = "end"
    ERROR = "error"


class EventType(str, Enum):
    """Event 类型"""
    LIFECYCLE = "lifecycle"
    ASSISTANT = "assistant"
    TOOL = "tool"
    HOOK = "hook"
    METRICS = "metrics"


@dataclass
class AgentEvent:
    """Agent Event"""
    event_type: EventType
    phase: EventPhase
    agent_id: str
    timestamp: float = field(default_factory=time.time)
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "phase": self.phase.value,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp,
            "data": self.data,
            "metadata": self.metadata,
        }


class EventBus:
    """Event 总线 - 收集和分发事件"""

    def __init__(self):
        self._events: List[AgentEvent] = []
        self._subscribers: Dict[EventType, List[callable]] = {}

    def emit(self, event: AgentEvent):
        """发射事件"""
        self._events.append(event)
        
        # 通知订阅者
        subscribers = self._subscribers.get(event.event_type, [])
        for callback in subscribers:
            try:
                callback(event)
            except Exception:
                pass

    def subscribe(self, event_type: EventType, callback: callable):
        """订阅事件"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    def get_events(self, event_type: Optional[EventType] = None) -> List[AgentEvent]:
        """获取事件列表"""
        if event_type is None:
            return list(self._events)
        return [e for e in self._events if e.event_type == event_type]

    def clear(self):
        """清空事件"""
        self._events.clear()

    def get_lifecycle_events(self) -> List[AgentEvent]:
        """获取生命周期事件"""
        return self.get_events(EventType.LIFECYCLE)

    def get_metrics_summary(self) -> Dict[str, Any]:
        """获取指标摘要"""
        events = self._events
        return {
            "total_events": len(events),
            "by_type": {
                et.value: len([e for e in events if e.event_type == et])
                for et in EventType
            },
            "start_time": events[0].timestamp if events else None,
            "end_time": events[-1].timestamp if events else None,
            "duration": (events[-1].timestamp - events[0].timestamp) if len(events) > 1 else 0,
        }
