from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MemoryRefs:
    """记忆引用"""
    whiteboard: Dict[str, Any] = field(default_factory=dict)
    hot: List[Any] = field(default_factory=list)
    warm: List[Any] = field(default_factory=list)
    cold: List[Any] = field(default_factory=list)


@dataclass
class Message:
    """对话消息"""
    role: str
    content: str
    name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCall:
    """工具调用"""
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    result: Any = None
    success: bool = True
    error: Optional[str] = None


@dataclass
class AgentContext:
    """Agent 上下文"""
    agent_id: str
    session_id: str
    messages: List[Message] = field(default_factory=list)
    skills: Dict[str, Any] = field(default_factory=dict)
    memory: MemoryRefs = field(default_factory=MemoryRefs)
    system_prompt: str = ""
    bootstrap_files: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    tool_calls: List[ToolCall] = field(default_factory=list)

    def add_message(self, role: str, content: str, **kwargs):
        """添加消息"""
        self.messages.append(Message(role=role, content=content, **kwargs))

    def add_tool_call(self, name: str, arguments: Dict[str, Any], result: Any = None, success: bool = True, error: Optional[str] = None):
        """添加工具调用"""
        self.tool_calls.append(ToolCall(
            name=name,
            arguments=arguments,
            result=result,
            success=success,
            error=error
        ))

    def get_conversation_history(self, max_turns: int = 20) -> List[Dict[str, str]]:
        """获取对话历史"""
        history = []
        for msg in self.messages[-max_turns * 2:]:
            history.append({"role": msg.role, "content": msg.content})
        return history

    def compact(self, keep_turns: int = 10):
        """压缩历史"""
        if len(self.messages) > keep_turns * 2:
            # 保留系统消息和最近的消息
            system_msgs = [m for m in self.messages if m.role == "system"]
            recent = self.messages[-(keep_turns * 2):]
            
            # 添加摘要消息
            summary = Message(
                role="system",
                content=f"[对话已压缩，保留最近 {keep_turns} 轮对话]"
            )
            
            self.messages = system_msgs + [summary] + recent[-keep_turns * 2:]


class ContextBuilder:
    """Context 组装器"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._assemblers: List[ContextAssembler] = []

    def add_assembler(self, assembler: ContextAssembler):
        self._assemblers.append(assembler)

    def build(self, session_id: str, agent_id: str) -> AgentContext:
        ctx = AgentContext(agent_id=agent_id, session_id=session_id)

        for assembler in sorted(self._assemblers, key=lambda a: a.priority):
            assembler.assemble(ctx)

        return ctx


class ContextAssembler:
    """Context 组装基类"""
    priority: int = 50

    def assemble(self, ctx: AgentContext):
        raise NotImplementedError


class SystemPromptAssembler(ContextAssembler):
    """系统提示词组装"""
    priority = 10

    def __init__(self, system_prompt: str):
        self.system_prompt = system_prompt

    def assemble(self, ctx: AgentContext):
        ctx.system_prompt = self.system_prompt


class BootstrapAssembler(ContextAssembler):
    """Bootstrap 文件组装"""
    priority = 20

    def __init__(self, boot_files: Dict[str, str]):
        self.boot_files = boot_files

    def assemble(self, ctx: AgentContext):
        ctx.bootstrap_files = list(self.boot_files.keys())
        if ctx.system_prompt:
            ctx.system_prompt += "\n\n" + "\n\n".join(self.boot_files.values())
        else:
            ctx.system_prompt = "\n\n".join(self.boot_files.values())


class MemoryContextAssembler(ContextAssembler):
    """记忆上下文组装"""
    priority = 50

    def __init__(self, memories: Dict[str, Any]):
        self.whiteboard = memories.get("whiteboard", {})
        self.hot = memories.get("hot", [])
        self.warm = memories.get("warm", [])
        self.cold = memories.get("cold", [])

    def assemble(self, ctx: AgentContext):
        ctx.memory = MemoryRefs(
            whiteboard=self.whiteboard,
            hot=self.hot,
            warm=self.warm,
            cold=self.cold
        )


class SkillsAssembler(ContextAssembler):
    """技能组装"""
    priority = 30

    def __init__(self, skills: Dict[str, Any]):
        self.skills = skills

    def assemble(self, ctx: AgentContext):
        ctx.skills = self.skills
