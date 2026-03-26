"""
Swarmbot Core - CoreAgent 统一核心

包含：
- CoreAgent: 统一 Agent 核心
- AgentConfig: Agent 配置
- Assessment: 自评估结果
- BootLoader: Boot 加载器
"""

from .agent import CoreAgent, AgentResult, AgentContext
from .agent_config import CoreAgentConfig
from .assessment import Assessment
from .boot_loader import BootLoader

__all__ = [
    "CoreAgent",
    "AgentResult",
    "AgentContext",
    "CoreAgentConfig",
    "Assessment",
    "BootLoader",
]
