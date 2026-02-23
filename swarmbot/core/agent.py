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
                        os.path.expanduser("~/.nanobot/soul.md"),
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
        
        # 2. QMD Memory Skill Prompt & Search Prioritization
        system_instructions = (
            "你具备一个名为 QMDMemory 的记忆技能，可以在需要时主动向用户索取检索关键词，"
            "用来搜索本地知识库（如笔记、文档、会议记录），并将检索到的内容整合进推理过程。\n"
            "【关键】：你还可以使用 'whiteboard_update' 工具将你的推理过程中的关键结论、事实或计划写入共享白板 (MemoryMap)，"
            "这对于多 Agent 协作至关重要，请确保及时更新白板。\n"
            "系统中存在一个名为 Swarmbot Daemon 的守护进程，用于管理 gateway、Overthinking、备份和健康检查。"
            "其状态保存在 ~/.swarmbot/daemon_state.json 中，你可以通过 'file_read' 工具查看当前 LLM 与 Channel 健康状态，"
            "并通过 'swarm_control' / 'overthinking_control' 等工具协助用户调整配置（例如启停 overthinking 或修改 provider）。\n"
            "Heartbeat 相关任务定义在工作区的 HEARTBEAT.md 中，你应该将其视为“后台任务清单”："
            "需要修改 Heartbeat 行为时，优先通过 'file_read' / 'file_write' 更新 HEARTBEAT.md 的内容，并在必要时建议用户运行 "
            "'swarmbot heartbeat status' 或 'swarmbot heartbeat trigger'（可以通过 'shell_exec' 调用）。\n"
            "定时任务由 'swarmbot cron' 管理，你可以通过 'shell_exec' 调用相关命令查看或建议创建 Cron 任务，但在修改定时任务前，应确保用户有明确授权和需求。\n"
            "你可以通过 'skill_summary' 查看当前可用的工具技能集合，并用 'skill_load' 加载具体技能说明；"
            "如需安装新的 ClawHub 技能，可以结合 'shell_exec' 执行相应命令（例如搜索/安装），然后再次使用 'skill_summary' 确认技能是否可用。\n"
            "输出语言必须与用户输入保持一致（用户用中文就用中文，用户用英文就用英文）。\n"
            "如果你看到 Whiteboard/WorkMap 中的 current_task_context，请以其为最高优先级理解任务，并参考其中的 system_capabilities 字段了解 Daemon/Cron/Heartbeat/Skills 的结构化信息。\n"
            "IMPORTANT: When answering questions about current events, technology updates, or dynamic data, "
            "you MUST prioritize using the 'web_search' tool over your internal training data. "
            "Always verify the date of the information found。\n\n"
            "【工具调用限制】:\n"
            "请务必先检查 Whiteboard (current_task_context 或其他字段) 中是否已经存在其他 Agent 提供的相关信息。\n"
            "如果 Whiteboard 中已经有了所需的天气、搜索结果或代码，**请不要重复调用相同的工具**去获取相同的信息。\n"
            "直接使用白板中的信息进行推理和回答。"
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
