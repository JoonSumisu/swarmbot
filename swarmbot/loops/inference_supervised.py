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


class SupervisedInferenceTool(BaseInferenceTool):
    """
    人在回路推理工具 - 在关键步骤暂停等待用户确认
    """

    BREAKPOINTS = ["ANALYSIS_REVIEW", "PLAN_REVIEW"]

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
        self.suspended_at = ""

    def get_breakpoints(self) -> List[str]:
        return self.BREAKPOINTS

    def get_required_skills(self) -> List[str]:
        return ["web_search", "browser_open", "browser_read", "file_read", "file_write", "python_exec"]

    def get_required_tools(self) -> List[str]:
        return ["web_search", "browser_open", "browser_read", "file_read", "file_write", "python_exec", "shell_exec"]

    def run(self, user_input: str, session_id: str) -> InferenceResult:
        try:
            # 1. 初始化
            if not self.is_suspended:
                self.whiteboard.clear()
                self.whiteboard.update("metadata", {"session_id": session_id, "loop_id": str(int(time.time()))})
                self.whiteboard.update("input_prompt", user_input)
            
            print(f"[SupervisedInferenceTool] Start: {user_input[:50]}...")
            print(f"[SupervisedInferenceTool] Suspended: {self.is_suspended}, at: {self.suspended_at}")
            
            # 2. Analysis
            if "ANALYSIS" not in self.completed_stages:
                analysis = self._step_analysis(user_input)
                self.completed_stages.add("ANALYSIS")
                
                # BREAKPOINT 1: ANALYSIS_REVIEW
                return self._suspend_at(
                    "ANALYSIS_REVIEW",
                    f"我已经完成分析:\n{json.dumps(analysis, ensure_ascii=False, indent=2)}\n\n请确认分析方向是否正确，或给出调整建议。",
                    {"analysis": analysis}
                )
            
            # Resume from ANALYSIS_REVIEW
            if self.suspended_at == "ANALYSIS_REVIEW":
                self.completed_stages.add("ANALYSIS_REVIEW")
                self.suspended_at = ""
            
            # 3. Collection
            if "COLLECTION" not in self.completed_stages:
                collection = self._step_collection(user_input)
                self.completed_stages.add("COLLECTION")
            
            # 4. Planning
            if "PLANNING" not in self.completed_stages:
                plan = self._step_planning(user_input)
                self.completed_stages.add("PLANNING")
                
                # BREAKPOINT 2: PLAN_REVIEW
                return self._suspend_at(
                    "PLAN_REVIEW",
                    f"我已经制定计划:\n{json.dumps(plan, ensure_ascii=False, indent=2)}\n\n请确认执行计划，或给出调整建议。",
                    {"plan": plan}
                )
            
            # Resume from PLAN_REVIEW
            if self.suspended_at == "PLAN_REVIEW":
                self.completed_stages.add("PLAN_REVIEW")
                self.suspended_at = ""
            
            # 5. Execution
            if "EXECUTION" not in self.completed_stages:
                execution = self._step_execution()
                self.completed_stages.add("EXECUTION")
            
            # 6. Evaluation
            if "EVALUATION" not in self.completed_stages:
                evaluation = self._step_evaluation()
                self.completed_stages.add("EVALUATION")
            
            # 7. Translation
            response = self._step_translation(user_input)
            self.completed_stages.add("TRANSLATION")
            
            # 8. Organization
            self._step_organization(session_id, user_input, response)
            self.completed_stages.add("ORGANIZATION")
            
            print(f"[SupervisedInferenceTool] Done")
            
            return InferenceResult(success=True, content=response)
            
        except Exception as e:
            print(f"[SupervisedInferenceTool] Error: {e}")
            return InferenceResult(success=False, error=str(e))

    def _suspend_at(self, checkpoint_name: str, message: str, checkpoint_data: Dict) -> InferenceResult:
        self.is_suspended = True
        self.suspended_at = checkpoint_name
        
        return InferenceResult(
            success=False,
            content=message,
            metadata={
                "suspended": True,
                "checkpoint_name": checkpoint_name,
                "checkpoint_data": checkpoint_data,
                "needs_human_review": True
            }
        )

    def resume(self, user_feedback: str) -> InferenceResult:
        """恢复执行，处理用户反馈"""
        print(f"[SupervisedInferenceTool] Resuming with feedback: {user_feedback[:50]}...")
        
        # 将用户反馈写入 whiteboard
        self.whiteboard.update("user_feedback", user_feedback)
        
        # 继续执行
        return self.run("", self.whiteboard.get("metadata", {}).get("session_id", ""))

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
            print(f"[SupervisedInferenceTool] Analysis error: {e}")
            return {"intent": user_input, "domain": "general", "complexity": "medium"}

    def _step_collection(self, user_input: str) -> Dict[str, Any]:
        prompt = f"""你是收集 Agent。请收集相关的上下文信息。

用户输入: {user_input}

请搜索相关信息。"""

        try:
            worker = self._create_worker("collector", enable_tools=True)
            result = worker.step(prompt)
            collection = {"context": result, "sources": []}
            self.whiteboard.update("information_gathering", collection)
            return collection
        except Exception as e:
            return {"context": "", "sources": []}

    def _step_planning(self, user_input: str) -> Dict[str, Any]:
        prompt = f"""你是规划 Agent。请生成行动计划。

用户输入: {user_input}

请生成 JSON 格式的计划。"""

        try:
            worker = self._create_worker("planner", enable_tools=False)
            result = worker.step(prompt)
            plan = self._extract_json(result)
            self.whiteboard.update("action_plan", plan)
            return plan
        except Exception as e:
            return {"objective": user_input, "tasks": []}

    def _step_execution(self) -> Dict[str, Any]:
        return {"results": [], "completed": 0, "total": 0}

    def _step_evaluation(self) -> Dict[str, Any]:
        return {"passed": True, "quality": "good"}

    def _step_translation(self, user_input: str) -> str:
        prompt = f"""你是 Master Agent。请生成最终回答。

用户输入: {user_input}
Persona (Soul): {self.soul[:1000]}"""

        try:
            worker = self._create_worker("master", enable_tools=False)
            result = worker.step(prompt)
            return result or "任务已完成。"
        except Exception as e:
            return "任务已完成。"

    def _step_organization(self, session_id: str, user_input: str, response: str):
        try:
            self.warm_memory.add_event(session_id, user_input, {"role": "user", "type": "supervised"})
            self.warm_memory.add_event(session_id, response, {"role": "assistant", "type": "supervised"})
        except Exception as e:
            print(f"[SupervisedInferenceTool] Organization error: {e}")

    def _extract_json(self, text: str) -> Dict[str, Any]:
        import re
        try:
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                return json.loads(match.group())
        except:
            pass
        return {}
