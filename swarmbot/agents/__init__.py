"""
Swarmbot Agents Framework

提供 Agent Loop 架构:
- Base: Agent 基类、Loop、Context、Events、Hooks
- Research: AutoresearchMixin、评估器
- Master: MasterAgent、MasterLoop
- Workers: 各推理工具 Worker
- Autonomous: AutonomousEngine、AutonomousLoop
"""

from .base import (
    BaseAgent,
    AgentConfig,
    RunResult,
    AgentContext,
    Message,
    ToolCall,
    MemoryRefs,
    ContextBuilder,
    EventBus,
    AgentEvent,
    EventType,
    EventPhase,
    AgentLoop,
    Hook,
)

from .research import (
    AutoresearchMixin,
    ExperimentRecord,
    MetricsEvaluator,
    AntiOverOptimization,
)

from .master import (
    MasterAgent,
    MasterLoop,
)

from .workers import (
    BaseWorkerAgent,
    WorkerLoop,
    StandardWorkerAgent,
    StandardWorkerLoop,
    SupervisedWorkerAgent,
    SupervisedWorkerLoop,
    SwarmsWorkerAgent,
    SwarmsWorkerLoop,
)

from .autonomous import (
    AutonomousAgent,
    AutonomousEngine,
    create_autonomous_engine,
    AutonomousLoop,
)

__all__ = [
    # Base
    "BaseAgent",
    "AgentConfig",
    "RunResult",
    "AgentContext",
    "Message",
    "ToolCall",
    "MemoryRefs",
    "ContextBuilder",
    "EventBus",
    "AgentEvent",
    "EventType",
    "EventPhase",
    "AgentLoop",
    "Hook",
    # Research
    "AutoresearchMixin",
    "ExperimentRecord",
    "MetricsEvaluator",
    "AntiOverOptimization",
    # Master
    "MasterAgent",
    "MasterLoop",
    # Workers
    "BaseWorkerAgent",
    "WorkerLoop",
    "StandardWorkerAgent",
    "StandardWorkerLoop",
    "SupervisedWorkerAgent",
    "SupervisedWorkerLoop",
    "SwarmsWorkerAgent",
    "SwarmsWorkerLoop",
    # Autonomous
    "AutonomousAgent",
    "AutonomousEngine",
    "create_autonomous_engine",
    "AutonomousLoop",
]
