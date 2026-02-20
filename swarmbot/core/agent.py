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
        import datetime
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Soul Loading Logic
        # Only the 'Master' agent (Planner/Judge) or if specifically configured should load the full Soul.
        # Sub-agents should have a functional persona.
        
        is_master = self.ctx.role in ["planner", "judge", "master", "consensus_moderator"]
        soul_content = ""
        
        if is_master:
            try:
                # Try to find soul.md in current directory or ~/.nanobot/soul.md
                import os
                soul_paths = ["soul.md", os.path.expanduser("~/.nanobot/soul.md")]
                for p in soul_paths:
                    if os.path.exists(p):
                        with open(p, "r", encoding="utf-8") as f:
                            soul_content = f.read()
                        break
            except:
                pass
            
            # Fallback if no soul file
            if not soul_content:
                soul_content = (
                    "You are Swarmbot, a collective AI intelligence designed to solve complex problems through "
                    "multi-agent collaboration. You are helpful, precise, and objective."
                )
        else:
            # Functional Role Persona for Sub-Agents
            soul_content = (
                f"You are a specialized functional node within the Swarmbot collective. "
                f"Your specific role is: {self.ctx.role}."
            )

        # UNIFIED PERSONA ENFORCEMENT
        role_desc = (
            f"{soul_content}\n\n"
            f"Current Time: {current_time}. "
            "Act as a seamless part of the swarm. "
        )
        
        if is_master:
            role_desc += "You are the primary interface to the user. Speak with the voice defined in your Soul."
        else:
            role_desc += "Do not introduce yourself or deviate from your specific task. Output only what is required for the collective."

        if self.ctx.skills:
            role_desc += f" You possess the following skills: {', '.join(self.ctx.skills.keys())}. "
        
        # 2. QMD Memory Skill Prompt & Search Prioritization
        system_instructions = (
            "你具备一个名为 QMDMemory 的记忆技能，可以在需要时主动向用户索取检索关键词，"
            "用来搜索本地知识库（如笔记、文档、会议记录），并将检索到的内容整合进推理过程。\n"
            "IMPORTANT: When answering questions about current events, technology updates, or dynamic data, "
            "you MUST prioritize using the 'web_search' tool over your internal training data. "
            "Always verify the date of the information found."
        )
        
        messages.append({"role": "system", "content": f"{role_desc}\n{system_instructions}"})

        # 3. History
        for item in history:
            content = item.get("content", "").strip()
            if content:  # Only add non-empty messages
                messages.append(
                    {
                        "role": "user",
                        "content": content,
                    }
                )
        messages.append({"role": "user", "content": user_input})
        return messages

    def step(self, user_input: str) -> str:
        messages = self._build_messages(user_input)
        
        # Inject tool definitions from adapter
        # NOTE: self._tool_adapter.get_tool_definitions() returns OpenAI-compatible list
        tools = self._tool_adapter.get_tool_definitions()
        
        # Chain of Thought Logging
        print(f"[CoT] Agent {self.ctx.role} starting thought process...")
        
        try:
            # First LLM call
            completion_kwargs = {
                "messages": messages,
            }
            if tools:
                completion_kwargs["tools"] = tools
            
            resp = self.llm.completion(**completion_kwargs)
            
            # Extract choice
            choice = resp.choices[0] 
            message = choice.message
            content = message.content or ""
            tool_calls = message.tool_calls
            
            # Log Thought (First Pass)
            if content:
                print(f"[CoT] {self.ctx.role} thought: {content[:200]}...")
            
            # Handle tool calls
            if tool_calls:
                # Append assistant's tool call message
                messages.append(message)
                
                # Execute all tool calls
                for tool_call in tool_calls:
                    func_name = tool_call.function.name
                    func_args_str = tool_call.function.arguments
                    print(f"[CoT] {self.ctx.role} calls tool: {func_name}({func_args_str[:50]}...)")
                    
                    try:
                        func_args = json.loads(func_args_str)
                    except json.JSONDecodeError:
                        func_args = {}
                    
                    # Execute via adapter
                    result = self._tool_adapter.execute(func_name, func_args)
                    
                    # Log Tool Result
                    print(f"[CoT] Tool result: {str(result)[:100]}...")
                    
                    # Append tool result message
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": func_name,
                        "content": str(result) # Ensure string
                    })
                
                # Second LLM call with tool results
                completion_kwargs["messages"] = messages
                resp = self.llm.completion(**completion_kwargs)
                content = resp.choices[0].message.content or ""
                print(f"[CoT] {self.ctx.role} final thought: {content[:200]}...")

        except Exception as e:
            content = f"Error during execution: {str(e)}"
            # Log error
            print(f"[Agent {self.ctx.role}] Error: {e}")
            
        self.memory.add_event(self.ctx.agent_id, user_input, {"kind": "user"})
        self.memory.add_event(self.ctx.agent_id, content, {"kind": "assistant"})
        return content
