from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Assessment:
    """自评估结果 - 大而全版本
    
    用于 Agent 的自评估循环，评估任务完成度、角色符合度、质量等。
    """
    
    # === 任务完成度 ===
    complete: bool = False              # 任务是否完成
    completion_percentage: float = 0.0  # 完成百分比 0-100
    confidence: float = 0.0             # 置信度 0-1
    
    # === 角色定位评估 ===
    fits_persona: bool = True           # 是否符合角色定位/语气
    in_scope: bool = True               # 是否在角色能力范围内
    persona_alignment_score: float = 0.0  # 角色符合度 0-1
    
    # === 质量评估 ===
    quality: str = "good"               # good, acceptable, needs_improvement, poor
    quality_score: float = 0.0          # 质量分数 0-1
    issues: List[str] = field(default_factory=list)  # 发现的问题
    
    # === 优化建议 ===
    should_optimize: bool = False       # 是否需要继续优化
    optimization_areas: List[str] = field(default_factory=list)  # 需要优化的方面
    next_action: str = ""               # 建议的下一步
    
    # === 资源需求评估 ===
    skill_needed: List[str] = field(default_factory=list)     # 需要引入的 skill
    memory_needed: bool = False         # 是否需要读取更多记忆
    memory_query: str = ""              # 记忆查询建议
    tool_needed: List[str] = field(default_factory=list)      # 需要使用的工具
    
    # === 委托评估 ===
    should_delegate: bool = False       # 是否需要委托给推理工具
    delegate_reason: str = ""           # 委托原因
    delegate_tool: str = ""             # 建议的推理工具
    delegate_target: str = ""           # 委托目标：inference/autonomous/None
    
    # === 之前状态（用于对比）===
    previous_iteration: int = 0
    previous_completion: float = 0.0
    improvement_made: bool = False      # 相比上次是否有改进
    
    # === 决策 ===
    decision: str = "continue"          # continue, stop, delegate, escalate
    decision_reason: str = ""           # 决策原因
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "complete": self.complete,
            "completion_percentage": self.completion_percentage,
            "confidence": self.confidence,
            "fits_persona": self.fits_persona,
            "in_scope": self.in_scope,
            "persona_alignment_score": self.persona_alignment_score,
            "quality": self.quality,
            "quality_score": self.quality_score,
            "issues": self.issues,
            "should_optimize": self.should_optimize,
            "optimization_areas": self.optimization_areas,
            "next_action": self.next_action,
            "skill_needed": self.skill_needed,
            "memory_needed": self.memory_needed,
            "memory_query": self.memory_query,
            "tool_needed": self.tool_needed,
            "should_delegate": self.should_delegate,
            "delegate_reason": self.delegate_reason,
            "delegate_tool": self.delegate_tool,
            "previous_iteration": self.previous_iteration,
            "previous_completion": self.previous_completion,
            "improvement_made": self.improvement_made,
            "decision": self.decision,
            "decision_reason": self.decision_reason,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Assessment:
        """从字典创建 Assessment"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
    
    def __str__(self) -> str:
        """格式化输出"""
        return f"""Assessment(iteration={self.previous_iteration + 1}):
  完成度: {self.completion_percentage:.1f}% (confidence: {self.confidence:.2f})
  角色: fits={'✓' if self.fits_persona else '✗'} scope={'✓' if self.in_scope else '✗'} score={self.persona_alignment_score:.2f}
  质量: {self.quality} ({self.quality_score:.2f})
  决策: {self.decision} - {self.decision_reason}
  优化: should_optimize={'yes' if self.should_optimize else 'no'}
  委托: should_delegate={'yes' if self.should_delegate else 'no'} {f'→ {self.delegate_tool}' if self.should_delegate else ''}
  资源: skills={self.skill_needed}, memory={self.memory_needed}, tools={self.tool_needed}
  问题: {self.issues if self.issues else '无'}
  下一步: {self.next_action if self.next_action else '无'}
"""
