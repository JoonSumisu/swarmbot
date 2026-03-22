from __future__ import annotations

import concurrent.futures
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
from ..memory.evidence_store import EvidenceStore
from .base import BaseInferenceTool, InferenceResult
from .skill_registry import SkillRegistry


class StandardInferenceTool(BaseInferenceTool):
    """
    标准 8 步推理工具 (无人在回路)
    """

    def _initialize(self):
        self.whiteboard = Whiteboard()
        self.hot_memory = HotMemory(self.workspace_path)
        self.warm_memory = WarmMemory(self.workspace_path)
        self.cold_memory = ColdMemory()
        self.evidence_store = EvidenceStore()
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
            
            print(f"[StandardInferenceTool] Start: {user_input[:50]}...")
            
            # 2. Analysis
            analysis = self._step_analysis(user_input)
            self.completed_stages.add("ANALYSIS")
            
            # 3. Collection
            collection = self._step_collection(user_input)
            self.completed_stages.add("COLLECTION")
            
            # 4. Planning
            plan = self._step_planning(user_input, analysis, collection)
            self.completed_stages.add("PLANNING")
            
            # 5. Execution
            execution = self._step_execution(plan)
            self.completed_stages.add("EXECUTION")
            
            # 6. Evaluation
            evaluation = self._step_evaluation(execution)
            self.completed_stages.add("EVALUATION")
            
            # 7. Translation
            response = self._step_translation(user_input, execution, evaluation)
            self.completed_stages.add("TRANSLATION")
            
            # 8. Organization
            self._step_organization(session_id, user_input, response)
            self.completed_stages.add("ORGANIZATION")
            
            print(f"[StandardInferenceTool] Done")
            
            return InferenceResult(success=True, content=response)
            
        except Exception as e:
            print(f"[StandardInferenceTool] Error: {e}")
            return InferenceResult(success=False, error=str(e))

    def _create_worker(self, role: str, enable_tools: bool = True, allowed_tools: List[str] = None) -> CoreAgent:
        skills = self.skill_registry.get_skills_for_task(role, task_desc="", required_skills=None)
        if allowed_tools:
            allowed = set(allowed_tools) | {"whiteboard_update", "hot_memory_update"}
            skills = {k: v for k, v in skills.items() if k in allowed}
        
        ctx = AgentContext(
            agent_id=f"worker-{role}-{time.time_ns()}",
            role=role,
            skills=skills
        )
        return CoreAgent(ctx, self.llm, self.cold_memory, hot_memory=self.hot_memory, enable_tools=enable_tools)

    def _step_analysis(self, user_input: str) -> Dict[str, Any]:
        prompt = f"""你是分析 Agent。请分析用户输入的意图和需求。

用户输入: {user_input}
SWARMBOT: {self.swarmboot[:2000]}

请分析并输出 JSON:
{{
    "intent": "用户意图",
    "domain": "领域",
    "complexity": "low/medium/high",
    "needs_tools": true/false,
    "key_points": ["要点1", "要点2"]
}}"""

        try:
            worker = self._create_worker("analyst", enable_tools=False)
            result = worker.step(prompt)
            analysis = self._extract_json(result)
            self.whiteboard.update("problem_analysis", analysis)
            return analysis
        except Exception as e:
            print(f"[StandardInferenceTool] Analysis error: {e}")
            return {"intent": user_input, "domain": "general", "complexity": "medium"}

    def _step_collection(self, user_input: str) -> Dict[str, Any]:
        prompt = f"""你是收集 Agent。请收集相关的上下文信息。

用户输入: {user_input}
分析结果: {json.dumps(self.whiteboard.get("problem_analysis"), ensure_ascii=False)}

请搜索相关信息，包括：
- Hot Memory 中的近期上下文
- Warm Memory 中的历史记录
- 如需要可以调用 web_search 工具

输出 JSON:
{{
    "context": "收集到的上下文",
    "sources": ["来源1", "来源2"],
    "gaps": "需要补充的信息"
}}"""

        try:
            worker = self._create_worker("collector", enable_tools=True, allowed_tools=["web_search", "browser_open", "browser_read", "file_read"])
            result = worker.step(prompt)
            collection = self._extract_json(result)
            self.whiteboard.update("information_gathering", collection)
            return collection
        except Exception as e:
            print(f"[StandardInferenceTool] Collection error: {e}")
            return {"context": "", "sources": [], "gaps": ""}

    def _step_planning(self, user_input: str, analysis: Dict, collection: Dict) -> Dict[str, Any]:
        prompt = f"""你是规划 Agent。请生成行动计划。

用户输入: {user_input}
分析: {json.dumps(analysis, ensure_ascii=False)}
上下文: {json.dumps(collection, ensure_ascii=False)}

请生成 JSON 格式的计划:
{{
    "objective": "目标",
    "tasks": [
        {{"id": 1, "desc": "任务描述", "tools": ["工具1"], "priority": "high/medium/low"}}
    ],
    "estimated_steps": 3
}}"""

        try:
            worker = self._create_worker("planner", enable_tools=False)
            result = worker.step(prompt)
            plan = self._extract_json(result)
            self.whiteboard.update("action_plan", plan)
            return plan
        except Exception as e:
            print(f"[StandardInferenceTool] Planning error: {e}")
            return {"objective": user_input, "tasks": [], "estimated_steps": 1}

    def _step_execution(self, plan: Dict) -> Dict[str, Any]:
        tasks = plan.get("tasks", [])
        if not tasks:
            return {"results": [], "completed": 0}
        
        results = []
        for task in tasks:
            task_result = self._execute_task(task)
            results.append(task_result)
        
        completed = sum(1 for r in results if r.get("success"))
        return {"results": results, "completed": completed, "total": len(tasks)}

    def _execute_task(self, task: Dict) -> Dict[str, Any]:
        task_desc = task.get("desc", "")
        tools = task.get("tools", [])
        
        prompt = f"""请执行任务：{task_desc}

使用工具: {tools}"""

        try:
            worker = self._create_worker("worker", enable_tools=bool(tools), allowed_tools=tools)
            result = worker.step(prompt)
            return {"success": True, "result": result, "task_id": task.get("id")}
        except Exception as e:
            return {"success": False, "error": str(e), "task_id": task.get("id")}

    def _step_evaluation(self, execution: Dict) -> Dict[str, Any]:
        results = execution.get("results", [])
        completed = execution.get("completed", 0)
        total = execution.get("total", 0)
        
        passed = completed >= total * 0.7
        
        return {
            "passed": passed,
            "completed": completed,
            "total": total,
            "quality": "good" if passed else "needs_improvement"
        }

    def _step_translation(self, user_input: str, execution: Dict, evaluation: Dict) -> str:
        prompt = f"""你是 Master Agent。请基于执行结果生成最终回答。

用户输入: {user_input}
执行结果: {json.dumps(execution, ensure_ascii=False)}
评估结果: {json.dumps(evaluation, ensure_ascii=False)}
Persona (Soul): {self.soul[:1000]}

请直接输出最终回答。"""

        try:
            worker = self._create_worker("master", enable_tools=False)
            result = worker.step(prompt)
            return result or "任务已完成。"
        except Exception as e:
            print(f"[StandardInferenceTool] Translation error: {e}")
            return "任务已完成。"

    def _step_organization(self, session_id: str, user_input: str, response: str):
        try:
            self.warm_memory.add_event(session_id, user_input, {"role": "user", "type": "standard"})
            self.warm_memory.add_event(session_id, response, {"role": "assistant", "type": "standard"})
        except Exception as e:
            print(f"[StandardInferenceTool] Organization error: {e}")

    def _extract_json(self, text: str) -> Dict[str, Any]:
        import re
        try:
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                return json.loads(match.group())
        except:
            pass
        return {}
