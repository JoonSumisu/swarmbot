from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class InferenceContext:
    user_input: str
    session_id: str
    tool_id: str
    created_at: int = field(default_factory=lambda: int(time.time()))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SuspendResult:
    accepted: bool = True
    reason: str = ""
    checkpoint_name: str = ""
    checkpoint_data: Dict[str, Any] = field(default_factory=dict)
    message_to_user: str = ""


@dataclass
class InferenceResult:
    success: bool = True
    content: str = ""
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseInferenceTool(ABC):
    def __init__(self, config, workspace_path: str):
        self.config = config
        self.workspace_path = workspace_path
        self._initialize()

    def _initialize(self):
        pass

    @abstractmethod
    def run(self, user_input: str, session_id: str) -> InferenceResult:
        pass

    def get_breakpoints(self) -> List[str]:
        return []

    def get_required_skills(self) -> List[str]:
        return []

    def get_required_tools(self) -> List[str]:
        return []

    def suspend(
        self, reason: str, checkpoint_name: str, checkpoint_data: Dict[str, Any]
    ) -> SuspendResult:
        return SuspendResult(
            accepted=True,
            reason=reason,
            checkpoint_name=checkpoint_name,
            checkpoint_data=checkpoint_data,
            message_to_user=f"需要确认: {reason}",
        )

    def resume(self, user_feedback: str) -> InferenceResult:
        return InferenceResult(success=False, error="Resume not implemented")


class SimpleDirectTool(BaseInferenceTool):
    def run(self, user_input: str, session_id: str) -> InferenceResult:
        from ..llm_client import OpenAICompatibleClient
        from ..boot.context_loader import load_boot_markdown

        llm = OpenAICompatibleClient.from_provider(providers=self.config.providers)
        soul = load_boot_markdown("SOUL.md", "master_agent", max_chars=5000) or ""
        master_agent_boot = load_boot_markdown(
            "masteragentboot.md", "master_agent", max_chars=3000
        ) or ""

        prompt = (
            f"你是 Master Agent。请直接给用户自然、友好、可执行的回答。\n"
            f"优先使用正常对话语气，不要工程化术语。\n"
            f"用户输入: {user_input}\n"
            f"Persona (Soul): {soul}\n"
            f"系统配置: {master_agent_boot}"
        )

        try:
            from ..core.agent import CoreAgent, AgentContext

            ctx = AgentContext(
                agent_id=f"master-{session_id}-{time.time_ns()}",
                role="master",
                skills={},
            )
            agent = CoreAgent(ctx, llm, None, enable_tools=False)
            result = agent.step(prompt)
            return InferenceResult(success=True, content=result)
        except Exception as e:
            return InferenceResult(success=False, error=str(e))

    def get_required_skills(self) -> List[str]:
        return []

    def get_required_tools(self) -> List[str]:
        return []
