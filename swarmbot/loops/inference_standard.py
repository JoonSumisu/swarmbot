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
from ..memory.memory_manager import MemoryManager
from .base import BaseInferenceTool, InferenceResult
from .skill_registry import SkillRegistry


class StandardInferenceTool(BaseInferenceTool):
    """
    标准 7 步推理工具 (无人在回路)
    结果通过 Hub 发送，由 MasterAgent 翻译回复
    """

    def _initialize(self):
        self.whiteboard = Whiteboard()
        self.memory_manager = MemoryManager.get_instance()
        self.skill_registry = SkillRegistry()

        self.inference_boot = load_boot_markdown("inference/inference_boot.md", "inference_loop", max_chars=3000) or ""
        self.swarmboot = load_boot_markdown("swarmboot.md", "inference_loop", max_chars=6000) or ""
        self.soul = load_boot_markdown("SOUL.md", "inference_loop", max_chars=3000) or ""

        self.llm = OpenAICompatibleClient.from_provider(providers=self.config.providers)

        self.completed_stages: set = set()
        self.is_suspended = False

    def get_breakpoints(self) -> List[str]:
        return []

    def get_required_skills(self) -> List[str]:
        return ["web_search", "file_read", "file_write", "python_exec"]

    def get_required_tools(self) -> List[str]:
        return ["web_search", "file_read", "file_write", "python_exec"]

    def run(self, user_input: str, session_id: str) -> InferenceResult:
        try:
            self.whiteboard.clear()
            self.whiteboard.update("metadata", {"session_id": session_id, "loop_id": str(int(time.time()))})
            self.whiteboard.update("input_prompt", user_input)

            print(f"[StandardInferenceTool] Start: {user_input[:50]}...")

            # 获取记忆上下文
            context = self.memory_manager.get_recent_context(session_id, max_turns=5)
            facts = self.memory_manager.get_important_facts_text(session_id, limit=3)

            # 1. Analysis（合并分析+收集，减少步数）
            analysis = self._step_analysis(user_input, context, facts)
            self.completed_stages.add("ANALYSIS")

            # 2. Planning
            plan = self._step_planning(user_input, analysis)
            self.completed_stages.add("PLANNING")

            # 3. Execution
            execution = self._step_execution(plan)
            self.completed_stages.add("EXECUTION")

            # 4. Evaluation
            evaluation = self._step_evaluation(execution)
            self.completed_stages.add("EVALUATION")

            # 5. 发送结果到 Hub
            result_content = json.dumps({
                "analysis": analysis,
                "plan": plan,
                "execution": execution,
                "evaluation": evaluation,
            }, ensure_ascii=False)

            success = evaluation.get("passed", False)

            if self.hub:
                self.hub.send_task_result(
                    result=result_content,
                    session_id=session_id,
                    success=success,
                )
                print(f"[StandardInferenceTool] Result sent to Hub")

            self.whiteboard.clear()
            print(f"[StandardInferenceTool] Done")

            return InferenceResult(success=success, content=result_content)

        except Exception as e:
            print(f"[StandardInferenceTool] Error: {e}")
            if self.hub:
                self.hub.send_task_result(
                    result=str(e),
                    session_id=session_id,
                    success=False,
                    error=str(e),
                )
            return InferenceResult(success=False, error=str(e))

    def _create_worker(self, role: str, enable_tools: bool = True, allowed_tools: List[str] = None) -> CoreAgent:
        skills = self.skill_registry.get_skills_for_task(role, task_desc="", required_skills=None)
        if allowed_tools:
            allowed = set(allowed_tools) | {"whiteboard_update"}
            skills = {k: v for k, v in skills.items() if k in allowed}

        ctx = AgentContext(
            agent_id=f"worker-{role}-{time.time_ns()}",
            role=role,
            skills=skills
        )
        return CoreAgent(ctx, self.llm, self.memory_manager, enable_tools=enable_tools)

    def _step_analysis(self, user_input: str, context: str, facts: str) -> Dict[str, Any]:
        prompt = f"""分析用户意图并输出 JSON。

用户输入: {user_input}
最近对话: {context[:500] if context else '无'}
重要事实: {facts[:300] if facts else '无'}

输出:
{{"intent": "意图", "domain": "领域", "complexity": "low/medium/high", "needs_tools": true/false, "key_points": ["要点"]}}"""

        try:
            worker = self._create_worker("analyst", enable_tools=False)
            result = worker.step(prompt)
            analysis = self._extract_json(result)
            self.whiteboard.update("problem_analysis", analysis)
            return analysis
        except Exception as e:
            print(f"[StandardInferenceTool] Analysis error: {e}")
            return {"intent": user_input, "domain": "general", "complexity": "medium"}

    def _step_planning(self, user_input: str, analysis: Dict) -> Dict[str, Any]:
        prompt = f"""生成行动计划。

用户输入: {user_input}
分析: {json.dumps(analysis, ensure_ascii=False)}

输出 JSON:
{{"objective": "目标", "tasks": [{{"id": 1, "desc": "任务描述", "tools": [], "priority": "high/medium/low"}}], "estimated_steps": 1}}"""

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
        for task in tasks[:3]:  # 最多执行 3 个任务
            task_result = self._execute_task(task)
            results.append(task_result)

        completed = sum(1 for r in results if r.get("success"))
        return {"results": results, "completed": completed, "total": len(results)}

    def _execute_task(self, task: Dict) -> Dict[str, Any]:
        task_desc = task.get("desc", "")
        tools = task.get("tools", [])

        try:
            worker = self._create_worker("worker", enable_tools=bool(tools), allowed_tools=tools)
            result = worker.step(task_desc)
            return {"success": True, "result": result, "task_id": task.get("id")}
        except Exception as e:
            return {"success": False, "error": str(e), "task_id": task.get("id")}

    def _step_evaluation(self, execution: Dict) -> Dict[str, Any]:
        results = execution.get("results", [])
        completed = execution.get("completed", 0)
        total = execution.get("total", 0)

        passed = completed >= total * 0.7 if total > 0 else True

        return {
            "passed": passed,
            "completed": completed,
            "total": total,
            "quality": "good" if passed else "needs_improvement"
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
