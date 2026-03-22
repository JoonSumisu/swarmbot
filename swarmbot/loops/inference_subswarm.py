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
from .base import BaseInferenceTool, InferenceResult
from .skill_registry import SkillRegistry


class SubSwarmInferenceTool(BaseInferenceTool):
    """
    SubSwarm 推理工具 - 解耦 MasterAgent 和推理工具
    异步分发多个子任务，通过 Hub 协调结果
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

    def get_breakpoints(self) -> List[str]:
        return []

    def get_required_skills(self) -> List[str]:
        return ["web_search", "browser_open", "browser_read", "file_read", "file_write", "python_exec"]

    def get_required_tools(self) -> List[str]:
        return ["web_search", "browser_open", "browser_read", "file_read", "file_write", "python_exec", "shell_exec"]

    def run(self, user_input: str, session_id: str) -> InferenceResult:
        try:
            print(f"[SubSwarmInferenceTool] Start: {user_input[:50]}...")
            
            # 1. 分析任务，分解为子任务
            subtasks = self._decompose_tasks(user_input)
            
            if not subtasks:
                return InferenceResult(success=False, error="无法分解任务")
            
            print(f"[SubSwarmInferenceTool] Decomposed into {len(subtasks)} subtasks")
            
            # 2. 执行子任务 (通过 Hub)
            results = self._execute_subtasks(subtasks, session_id)
            
            # 3. 整合结果
            response = self._integrate_results(user_input, results)
            
            # 4. 写入记忆
            self._step_organization(session_id, user_input, response)
            
            print(f"[SubSwarmInferenceTool] Done")
            
            return InferenceResult(success=True, content=response)
            
        except Exception as e:
            print(f"[SubSwarmInferenceTool] Error: {e}")
            return InferenceResult(success=False, error=str(e))

    def _decompose_tasks(self, user_input: str) -> List[Dict[str, Any]]:
        """分解任务为多个子任务"""
        prompt = f"""你是任务分解 Agent。请将用户输入分解为多个独立的子任务。

用户输入: {user_input}

分解要求:
1. 每个子任务应该是独立的，可以并行执行
2. 每个子任务有明确的 topic
3. 子任务之间不应该有强依赖关系
4. 总共不超过 5 个子任务

输出 JSON 数组:
[
    {{"topic": "topic_name", "description": "子任务描述", "priority": 1}},
    {{"topic": "topic_name", "description": "子任务描述", "priority": 0}}
]"""

        try:
            from ..core.agent import CoreAgent, AgentContext
            
            ctx = AgentContext(
                agent_id=f"decomposer-{time.time_ns()}",
                role="planner",
                skills={}
            )
            worker = CoreAgent(ctx, self.llm, self.cold_memory, enable_tools=False)
            result = worker.step(prompt)
            
            tasks = self._extract_json(result)
            
            if isinstance(tasks, list):
                return tasks
            elif isinstance(tasks, dict) and "tasks" in tasks:
                return tasks["tasks"]
            
            return []
        except Exception as e:
            print(f"[SubSwarmInferenceTool] Decompose error: {e}")
            return []

    def _execute_subtasks(self, subtasks: List[Dict[str, Any]], session_id: str) -> List[Dict[str, Any]]:
        """执行子任务"""
        from ..gateway.subswarm_manager import SubSwarmManager, SubSwarmConfig
        from ..gateway.communication_hub import CommunicationHub
        
        hub = CommunicationHub(str(self.workspace_path))
        
        config = SubSwarmConfig(max_concurrent=min(3, len(subtasks)))
        manager = SubSwarmManager(hub, session_id, config)
        
        # 添加任务
        for task in subtasks:
            manager.add_task(
                topic=task.get("topic", "default"),
                description=task.get("description", ""),
                tool_id="standard",
                priority=task.get("priority", 0),
            )
        
        # 执行
        def executor(task_desc: str, task_id: str) -> str:
            return self._execute_single_task(task_desc)
        
        manager.dispatch(executor)
        
        # 等待完成
        results = manager.wait_for_completion(timeout=120)
        
        return [
            {
                "topic": r.topic,
                "content": r.content,
                "success": r.success,
                "error": r.error,
                "execution_time": r.execution_time,
            }
            for r in results
        ]

    def _execute_single_task(self, task_description: str) -> str:
        """执行单个子任务"""
        prompt = f"""请执行以下子任务:

{task_description}

请直接输出执行结果。"""

        try:
            from ..core.agent import CoreAgent, AgentContext
            
            ctx = AgentContext(
                agent_id=f"worker-{time.time_ns()}",
                role="worker",
                skills={}
            )
            worker = CoreAgent(ctx, self.llm, self.cold_memory, hot_memory=self.hot_memory, enable_tools=True)
            result = worker.step(prompt)
            return result
        except Exception as e:
            return f"执行失败: {str(e)}"

    def _integrate_results(self, user_input: str, results: List[Dict[str, Any]]) -> str:
        """整合子任务结果"""
        prompt = f"""你是 Master Agent。多个子任务已经完成，请整合结果。

原始用户输入: {user_input}

子任务结果:
{chr(10).join([f"[{r['topic']}] {r.get('content', r.get('error', ''))[:200]}" for r in results])}

请整合这些结果，给出连贯、有条理的最终回答。"""

        try:
            from ..core.agent import CoreAgent, AgentContext
            
            ctx = AgentContext(
                agent_id=f"integrator-{time.time_ns()}",
                role="master",
                skills={}
            )
            worker = CoreAgent(ctx, self.llm, self.cold_memory, hot_memory=self.hot_memory, enable_tools=False)
            result = worker.step(prompt)
            return result
        except Exception as e:
            print(f"[SubSwarmInferenceTool] Integration error: {e}")
            return "任务完成。"

    def _step_organization(self, session_id: str, user_input: str, response: str):
        """写入记忆"""
        try:
            self.warm_memory.add_event(session_id, user_input, {"role": "user", "type": "subswarm"})
            self.warm_memory.add_event(session_id, response, {"role": "assistant", "type": "subswarm"})
        except Exception as e:
            print(f"[SubSwarmInferenceTool] Organization error: {e}")

    def _extract_json(self, text: str) -> Any:
        import re
        try:
            match = re.search(r'\[[\s\S]*\]|\{[\s\S]*\}', text)
            if match:
                return json.loads(match.group())
        except:
            pass
        return None
