from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..llm_client import OpenAICompatibleClient
from ..memory.base import MemoryStore
from ..config_manager import load_config
from ..tools.adapter import NanobotSkillAdapter
import json


@dataclass
class AgentContext:
    agent_id: str
    role: str = "assistant"
    skills: Dict[str, Any] = field(default_factory=dict)


class CoreAgent:
    def __init__(
        self,
        ctx: AgentContext,
        llm: OpenAICompatibleClient,
        memory: MemoryStore,
        use_nanobot: bool = True,
    ) -> None:
        self.ctx = ctx
        self.llm = llm
        self.memory = memory
        self._use_nanobot = use_nanobot
        self._nanobot_agent = None
        self._tool_adapter = NanobotSkillAdapter()  # Initialize adapter
        
        if self._use_nanobot:
            try:
                import nanobot  # type: ignore

                self._nanobot_agent = nanobot
            except Exception:
                self._use_nanobot = False

    def _build_messages(self, user_input: str) -> List[Dict[str, Any]]:
        history = self.memory.get_context(self.ctx.agent_id, limit=16)
        messages: List[Dict[str, Any]] = []
        
        # 1. System Prompt (Role / Soul)
        role_desc = f"Your name is {self.ctx.agent_id}. Your role is {self.ctx.role}. "
        if self.ctx.skills:
            role_desc += f"You possess the following skills: {', '.join(self.ctx.skills.keys())}. "
        
        # 2. QMD Memory Skill Prompt
        memory_skill = (
            "你具备一个名为 QMDMemory 的记忆技能，可以在需要时主动向用户索取检索关键词，"
            "用来搜索本地知识库（如笔记、文档、会议记录），并将检索到的内容整合进推理过程。"
        )
        
        messages.append({"role": "system", "content": f"{role_desc}\n{memory_skill}"})

        # 3. History
        for item in history:
            messages.append(
                {
                    "role": "user",
                    "content": item["content"],
                }
            )
        messages.append({"role": "user", "content": user_input})
        return messages

    def step(self, user_input: str) -> str:
        messages = self._build_messages(user_input)
        cfg = load_config()
        
        # Inject tool definitions from adapter
        tools = self._tool_adapter.get_tool_definitions()
        
        # First LLM call
        resp_json = self.llm.completion(
            messages,
            temperature=cfg.provider.temperature,
            max_tokens=cfg.provider.max_tokens,
            tools=tools if tools else None,  # Support tool calling
        )
        
        try:
            choice = resp_json["choices"][0]
            message = choice["message"]
            content = message.get("content", "") or ""
            tool_calls = message.get("tool_calls", [])
            
            # Handle tool calls
            if tool_calls:
                # Append assistant's tool call message
                messages.append(message)
                
                for tool_call in tool_calls:
                    func_name = tool_call["function"]["name"]
                    func_args = json.loads(tool_call["function"]["arguments"])
                    
                    # Execute via adapter
                    result = self._tool_adapter.execute(func_name, func_args)
                    
                    # Append tool result message
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": func_name,
                        "content": result
                    })
                
                # Second LLM call with tool results
                resp_json = self.llm.completion(
                    messages,
                    temperature=cfg.provider.temperature,
                    max_tokens=cfg.provider.max_tokens,
                )
                content = resp_json["choices"][0]["message"]["content"]

        except Exception as e:
            content = f"Error during execution: {str(e)}"
            # Fallback logic if needed
            
        self.memory.add_event(self.ctx.agent_id, user_input, {"kind": "user"})
        self.memory.add_event(self.ctx.agent_id, content, {"kind": "assistant"})
        return content
