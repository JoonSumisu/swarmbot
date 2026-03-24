from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

from ..boot.context_loader import load_boot_markdown
from ..core.agent import CoreAgent, AgentContext
from ..llm_client import OpenAICompatibleClient
from ..memory.whiteboard import Whiteboard
from ..memory.cold_memory import ColdMemory
from ..swarm.manager import SwarmManager
from .base import BaseInferenceTool, InferenceResult
from .skill_registry import SkillRegistry


class SwarmsInferenceTool(BaseInferenceTool):
    """
    多Worker协作推理工具 - 使用Swarm框架进行多角色分析
    结果通过 Hub 发送，由 MasterAgent 翻译回复
    """

    def _initialize(self):
        self.whiteboard = Whiteboard()
        self.cold_memory = ColdMemory()
        self.skill_registry = SkillRegistry()

        self.swarmboot = load_boot_markdown("swarmboot.md", "inference_loop", max_chars=12000) or ""
        self.soul = load_boot_markdown("SOUL.md", "inference_loop", max_chars=5000) or ""

        self.llm = OpenAICompatibleClient.from_provider(providers=self.config.providers)

        self.completed_stages: set = set()
        self.is_suspended = False

    def get_breakpoints(self) -> List[str]:
        return []

    def get_required_skills(self) -> List[str]:
        return ["web_search", "browser_open", "browser_read", "file_read", "file_write", "python_exec"]

    def get_required_tools(self) -> List[str]:
        return ["web_search", "browser_open", "browser_read", "file_read", "file_write", "python_exec", "shell_exec"]

    def run(self, user_input: str, session_id: str) -> InferenceResult:
        try:
            # 1. 初始化
            self.whiteboard.clear()
            self.whiteboard.update("metadata", {"session_id": session_id, "loop_id": str(int(time.time()))})
            self.whiteboard.update("input_prompt", user_input)

            print(f"[SwarmsInferenceTool] Start: {user_input[:50]}...")

            # 2. 决策 Swarm 策略
            strategy = self._decide_swarm_strategy(user_input)
            self.whiteboard.update("swarm_strategy", strategy)

            # 3. 执行 Swarm
            swarm_result = self._execute_swarm(user_input, strategy)

            # 4. 发送结果到 Hub
            result_content = json.dumps({
                "strategy": strategy,
                "swarm_result": swarm_result,
                "success": swarm_result.get("success", False),
            }, ensure_ascii=False)

            success = swarm_result.get("success", False)

            if self.hub:
                self.hub.send_task_result(
                    result=result_content,
                    session_id=session_id,
                    success=success,
                )
                print(f"[SwarmsInferenceTool] Result sent to Hub")

            self.whiteboard.clear()

            print(f"[SwarmsInferenceTool] Done")

            return InferenceResult(success=success, content=result_content)

        except Exception as e:
            print(f"[SwarmsInferenceTool] Error: {e}")
            if self.hub:
                self.hub.send_task_result(
                    result=str(e),
                    session_id=session_id,
                    success=False,
                    error=str(e),
                )
            return InferenceResult(success=False, error=str(e))

    def _decide_swarm_strategy(self, user_input: str) -> Dict[str, Any]:
        """决策使用哪种Swarm架构"""
        prompt = f"""你是Swarm策略决策器。
请决定使用哪种架构和Agent数量。

用户输入: {user_input}

可选架构:
- concurrent: 并发执行
- mixture: 混合专家
- group_chat: 组聊天
- hierarchical: 层级
- sequential: 串行

输出JSON:
{{
    "architecture": "concurrent",
    "agent_count": 3,
    "roles": ["analyst", "collector", "evaluator"],
    "reason": "原因"
}}"""

        try:
            ctx = AgentContext(
                agent_id=f"strategy-{time.time_ns()}",
                role="planner",
                skills={}
            )
            worker = CoreAgent(ctx, self.llm, self.cold_memory, enable_tools=False)
            result = worker.step(prompt)
            strategy = self._extract_json(result)
            return strategy or {"architecture": "concurrent", "agent_count": 3, "roles": ["analyst", "collector", "evaluator"]}
        except Exception as e:
            print(f"[SwarmsInferenceTool] Strategy error: {e}")
            return {"architecture": "concurrent", "agent_count": 3, "roles": ["analyst", "collector", "evaluator"]}

    def _execute_swarm(self, user_input: str, strategy: Dict) -> Dict[str, Any]:
        """执行 Swarm 多Worker协作"""
        architecture = strategy.get("architecture", "concurrent")
        agent_count = strategy.get("agent_count", 3)

        try:
            manager = SwarmManager.from_swarmbot_config(self.config)
            session = manager.get_session(f"swarm-{int(time.time())}")
            session.architecture = architecture
            session.resize_swarm(max(1, agent_count))

            result = manager.chat(user_input=user_input, session_id=session.session_id)

            return {
                "architecture": architecture,
                "agent_count": agent_count,
                "result": result,
                "success": True
            }
        except Exception as e:
            print(f"[SwarmsInferenceTool] Swarm execution error: {e}")
            return {
                "architecture": architecture,
                "agent_count": agent_count,
                "result": f"Swarm执行失败: {str(e)}",
                "success": False
            }

    def _extract_json(self, text: str) -> Dict[str, Any]:
        import re
        try:
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                return json.loads(match.group())
        except:
            pass
        return {}
