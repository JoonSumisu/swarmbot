from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

from ..boot.context_loader import load_boot_markdown
from ..core.agent import CoreAgent, AgentContext
from ..llm_client import OpenAICompatibleClient
from ..memory.whiteboard import Whiteboard
from ..memory.hot_memory import HotMemory
from ..memory.warm_memory import WarmMemory
from ..memory.cold_memory import ColdMemory
from ..swarm.manager import SwarmManager
from .base import BaseInferenceTool, InferenceResult
from .skill_registry import SkillRegistry


class SwarmsInferenceTool(BaseInferenceTool):
    """
    多Worker协作推理工具 - 使用Swarm框架进行多角色分析
    """

    def _initialize(self):
        self.whiteboard = Whiteboard()
        self.hot_memory = HotMemory(self.workspace_path)
        self.warm_memory = WarmMemory(self.workspace_path)
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
            
            # 4. 整合结果
            response = self._integrate_results(user_input, swarm_result)
            
            # 5. 写入记忆
            self._step_organization(session_id, user_input, response)
            
            print(f"[SwarmsInferenceTool] Done")
            
            return InferenceResult(success=True, content=response)
            
        except Exception as e:
            print(f"[SwarmsInferenceTool] Error: {e}")
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
            from ..core.agent import CoreAgent, AgentContext
            
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
        
        # 使用 SwarmManager
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

    def _integrate_results(self, user_input: str, swarm_result: Dict) -> str:
        """整合 Swarm 结果"""
        prompt = f"""你是 Master Agent。多个Worker已经完成了分析，请整合结果。

用户输入: {user_input}
Swarm结果: {json.dumps(swarm_result, ensure_ascii=False)}
Persona (Soul): {self.soul[:1000]}

请直接输出整合后的最终回答。"""

        try:
            from ..core.agent import CoreAgent, AgentContext
            
            ctx = AgentContext(
                agent_id=f"integrate-{time.time_ns()}",
                role="master",
                skills={}
            )
            worker = CoreAgent(ctx, self.llm, self.cold_memory, enable_tools=False)
            result = worker.step(prompt)
            return result or str(swarm_result.get("result", ""))
        except Exception as e:
            print(f"[SwarmsInferenceTool] Integration error: {e}")
            return str(swarm_result.get("result", ""))

    def _step_organization(self, session_id: str, user_input: str, response: str):
        """写入记忆"""
        try:
            self.warm_memory.add_event(session_id, user_input, {"role": "user", "type": "swarms"})
            self.warm_memory.add_event(session_id, response, {"role": "assistant", "type": "swarms"})
        except Exception as e:
            print(f"[SwarmsInferenceTool] Organization error: {e}")

    def _extract_json(self, text: str) -> Dict[str, Any]:
        import re
        try:
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                return json.loads(match.group())
        except:
            pass
        return {}
