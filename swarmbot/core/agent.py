from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..llm_client import OpenAICompatibleClient
from ..memory.base import MemoryStore
from ..tools.adapter import ToolAdapter
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
    ) -> None:
        self.ctx = ctx
        self.llm = llm
        self.memory = memory
        self._tool_adapter = ToolAdapter()

    def _build_messages(self, user_input: str) -> List[Dict[str, Any]]:
        history = self.memory.get_context(self.ctx.agent_id, limit=8, query=user_input)
        messages: List[Dict[str, Any]] = []
        
        # 1. System Prompt (Role / Soul)
        import datetime
        import time
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        timezone = time.strftime("%z")
        weekday = datetime.datetime.now().strftime("%A")
        
        # Soul Loading Logic
        # Only the 'Master' agent (Planner/Judge) or if specifically configured should load the full Soul.
        # Sub-agents should have a functional persona.
        
        is_overthinking = self.ctx.agent_id == "overthinker"
        is_master = self.ctx.role in ["planner", "judge", "master", "consensus_moderator"] or is_overthinking
        soul_content = ""
        
        if is_master:
            try:
                import os
                soul_paths = []
                if is_overthinking:
                    soul_paths.append(os.path.expanduser("~/.swarmbot/boot/OVERTHINKING.md"))
                soul_paths.extend(
                    [
                        os.path.expanduser("~/.swarmbot/boot/SOUL.md"),
                        "soul.md",
                    ]
                )
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
            f"Current Context:\n"
            f"- Time: {current_time} ({timezone})\n"
            f"- Weekday: {weekday}\n"
            "Act as a seamless part of the swarm. "
        )
        
        if is_master:
            role_desc += "You are the primary interface to the user. Speak with the voice defined in your Soul."
        else:
            role_desc += "Do not introduce yourself or deviate from your specific task. Output only what is required for the collective."

        if self.ctx.skills:
            role_desc += f" You possess the following skills: {', '.join(self.ctx.skills.keys())}. "
        
        system_instructions = (
            "【记忆与白板】\n"
            "Whiteboard 用于存放当前任务的结构化状态，重点关注 task_specification、execution_plan、current_state、loop_counter、"
            "completed_subtasks、pending_subtasks、intermediate_results、content_registry 和 checkpoint_data。"
            "你可以在需要时向用户索取检索关键词，并通过 'whiteboard_update' 只写入与当前问题紧密相关的关键信息。"
            "写入时使用结构化格式，例如 {\"content\": 内容, \"source\": 来源, \"fact_checked\": true/false}。"
            "未核实的信息必须标记为 fact_checked=false，如果某条内容值得长期保存，可追加到 qmd_candidates 并赋予 confidence_score 和 verification_status。\n\n"
            "如果任务较复杂、上下文较长，你可以通过调用 'context_policy_update' 主动设置 max_whiteboard_chars、max_history_items、max_history_chars_per_item、max_qmd_chars、max_qmd_docs 等参数，以平衡上下文信息密度与模型可用 token。\n\n"
            "【工具与 Skill 使用】\n"
            "调用工具前先查看 Whiteboard 的 current_task_context 和已有结果：若已存在 fact_checked=true 的可靠结论，应优先复用；"
            "若只有 fact_checked=false 的假设，需要通过工具补充或复核后再做判断。"
            "使用技能时，优先调用 'skill_summary' 获取列表，仅在确实需要时再用 'skill_load' 加载单个技能详情，避免一次性加载全部技能。\n\n"
            "【系统能力与运维】\n"
            "系统能力（daemon、heartbeat、cron、skills 等）通过 system_capabilities 提供，你可以结合 'file_read'、'file_write' 和 'shell_exec' 分析或调整状态，"
            "但涉及任务调度、心跳、定时任务变更时，应在回答中明确提示风险并要求用户确认。\n\n"
            "【输出与检索规范】\n"
            "输出语言必须与用户输入保持一致。回答涉及最新事件或动态数据时，应优先使用 'web_search' 或相关工具，并在确认信息后再给出结论。"
        )
        
        system_content = f"{role_desc}\n{system_instructions}"
        if len(system_content) > 6000:
            system_content = system_content[:6000] + "\n...[system instructions truncated]\n"
        messages.append({"role": "system", "content": system_content})

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
        # Filter tools based on self.ctx.skills
        # Only expose tools that are in the skills list
        all_tools = self._tool_adapter.get_tool_definitions()
        
        tools = []
        if self.ctx.skills:
            for tool in all_tools:
                tool_name = tool["function"]["name"]
                if tool_name in self.ctx.skills:
                    tools.append(tool)
        else:
            # Default behavior: if no skills defined, expose none (or all? Safer to expose none for specialized agents)
            # But for backward compatibility, if skills is empty dict (default), maybe we expose none?
            # Or expose base tools?
            # Let's assume empty skills means NO tools allowed unless specified.
            # Except maybe for 'master' role which might get all?
            if self.ctx.role in ["planner", "master"]:
                 tools = all_tools
            else:
                 tools = []
        
        # Chain of Thought Logging
        print(f"[CoT] Agent {self.ctx.role} starting thought process...")
        
        try:
            completion_kwargs: Dict[str, Any] = {"messages": messages}
            if tools:
                completion_kwargs["tools"] = tools

            content = ""
            max_tool_rounds = 3
            for round_idx in range(max_tool_rounds):
                resp = self.llm.completion(**completion_kwargs)
                choice = resp.choices[0]
                message = choice.message
                content = message.content or ""
                tool_calls = message.tool_calls

                if round_idx == 0 and content:
                    print(f"[CoT] {self.ctx.role} thought: {content[:200]}...")

                if not tool_calls:
                    if round_idx > 0:
                        print(f"[CoT] {self.ctx.role} final thought: {content[:200]}...")
                    break

                messages.append(message)
                for tool_call in tool_calls:
                    func_name = tool_call.function.name
                    func_args_str = tool_call.function.arguments
                    print(f"[CoT] {self.ctx.role} calls tool: {func_name}({func_args_str[:50]}...)")

                    try:
                        func_args = json.loads(func_args_str)
                    except json.JSONDecodeError:
                        func_args = {}

                    tool_context = {}
                    if hasattr(self.memory, "whiteboard"):
                        tool_context["memory_map"] = self.memory.whiteboard
                        
                    result = self._tool_adapter.execute(func_name, func_args, context=tool_context)
                    print(f"[CoT] Tool result: {str(result)[:100]}...")

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": func_name,
                            "content": str(result),
                        }
                    )

                completion_kwargs["messages"] = messages
            else:
                if content:
                    print(f"[CoT] {self.ctx.role} final thought: {content[:200]}...")

        except Exception as e:
            content = f"Error during execution: {str(e)}"
            # Log error
            print(f"[Agent {self.ctx.role}] Error: {e}")
            
        self.memory.add_event(self.ctx.agent_id, user_input, {"kind": "user"})
        self.memory.add_event(self.ctx.agent_id, content, {"kind": "assistant"})
        return content
