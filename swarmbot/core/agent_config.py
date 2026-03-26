from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CoreAgentConfig:
    """CoreAgent 配置
    
    控制 Agent 的行为、资源加载和循环策略。
    """
    
    # === 身份配置 ===
    agent_id: str = ""
    role: str = "master"  # master, analyst, planner, worker, autonomous
    
    # === Boot 配置 ===
    boot_mode: str = "master"  # master, inference, autonomous, custom
    custom_boot_files: List[str] = field(default_factory=list)
    
    # === 工具配置 ===
    enable_tools: bool = True
    allowed_tools: List[str] = field(default_factory=list)
    enable_parallel_tools: bool = True
    max_parallel_tools: int = 5
    
    # === 循环配置 ===
    max_iterations: int = 20  # 安全上限
    assessment_temperature: float = 0.3  # 自评估温度
    
    # === 记忆配置 ===
    session_id: str = ""
    context_limit: int = 8
    enable_memory_search: bool = True
    
    # === 日志配置 ===
    verbose: bool = True
    log_assessment: bool = True
    log_to_file: bool = False
    log_file: str = ""
    
    def get_log_file(self) -> str:
        """获取日志文件路径"""
        if self.log_file:
            return self.log_file
        import os
        from pathlib import Path
        workspace = os.path.expanduser("~/.swarmbot")
        return str(Path(workspace) / "logs" / f"{self.agent_id}_agent.log")
