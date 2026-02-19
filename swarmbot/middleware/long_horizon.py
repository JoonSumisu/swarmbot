from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..core.agent import CoreAgent
from ..llm_client import OpenAICompatibleClient


@dataclass
class Skill:
    name: str
    description: str
    usage: str


class WorkMapMemory:
    """
    工作地图记忆：存储已知的 Skill 能力，并支持根据任务描述检索最佳 Skill。
    也可以模拟“在线寻找 Skill”的能力（通过 LLM 脑补或搜索工具）。
    """
    def __init__(self, llm: OpenAICompatibleClient) -> None:
        self.llm = llm
        self.skills: List[Skill] = []
        self._load_local_skills()

    def _load_local_skills(self) -> None:
        """从 nanobot 加载本地技能"""
        try:
            # 假设 nanobot skill list 输出某种格式，这里简化处理
            # 实际需解析 nanobot 输出
            result = subprocess.run(
                ["nanobot", "skill", "list", "--json"],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0 and result.stdout.strip():
                try:
                    data = json.loads(result.stdout)
                    for item in data:
                        self.skills.append(Skill(
                            name=item.get("name", "unknown"),
                            description=item.get("description", ""),
                            usage=item.get("usage", "")
                        ))
                except json.JSONDecodeError:
                    pass
        except FileNotFoundError:
            pass

        # 添加内置基础能力
        self.skills.append(Skill("llm_reasoning", "通用推理能力", "直接使用 LLM 进行回答"))
        self.skills.append(Skill("qmd_search", "本地知识库搜索", "搜索本地文档和记忆"))

    def find_best_skill(self, task_description: str) -> Skill:
        """
        使用 LLM 从 WorkMap 中选择最合适的 Skill，或者决定寻找新 Skill
        """
        skill_desc = "\n".join([f"- {s.name}: {s.description}" for s in self.skills])
        prompt = (
            f"已有技能列表：\n{skill_desc}\n\n"
            f"当前任务：{task_description}\n"
            "请选择最合适的技能名称。如果现有技能都不合适，请返回 'search_online'。\n"
            "只返回技能名称，不要其他内容。"
        )
        resp = self.llm.completion([{"role": "user", "content": prompt}])
        choice = resp["choices"][0]["message"]["content"].strip()
        
        for s in self.skills:
            if s.name == choice:
                return s
        
        if "search_online" in choice:
            return Skill("online_search", "在线搜索技能", "尝试在网络上寻找解决方案")
        
        return self.skills[0]  # default to llm_reasoning or first skill


@dataclass
class SubTask:
    id: str
    description: str
    dependencies: List[str] = field(default_factory=list)
    status: str = "pending"
    result: str = ""


class HierarchicalTaskGraph:
    """
    长程任务图：将复杂任务分解为 DAG（有向无环图），并调度执行。
    """
    def __init__(self, llm: OpenAICompatibleClient, work_map: WorkMapMemory) -> None:
        self.llm = llm
        self.work_map = work_map
        self.tasks: Dict[str, SubTask] = {}

    def plan(self, user_goal: str) -> None:
        """使用 LLM 生成任务图"""
        prompt = (
            f"目标：{user_goal}\n"
            "请将该目标分解为 3-5 个步骤的依赖任务图。\n"
            "返回 JSON 格式：\n"
            "[\n"
            "  {\"id\": \"step1\", \"description\": \"...\", \"dependencies\": []},\n"
            "  {\"id\": \"step2\", \"description\": \"...\", \"dependencies\": [\"step1\"]}\n"
            "]"
        )
        resp = self.llm.completion([{"role": "user", "content": prompt}])
        content = resp["choices"][0]["message"]["content"]
        # 简单提取 JSON
        try:
            start = content.find("[")
            end = content.rfind("]") + 1
            json_str = content[start:end]
            data = json.loads(json_str)
            for item in data:
                self.tasks[item["id"]] = SubTask(
                    id=item["id"],
                    description=item["description"],
                    dependencies=item.get("dependencies", [])
                )
        except Exception as e:
            print(f"Plan parsing failed: {e}")
            # Fallback: single task
            self.tasks["root"] = SubTask("root", user_goal)

    def execute(self, agent: CoreAgent) -> str:
        """执行任务图"""
        completed = set()
        results = []
        
        # 简单拓扑排序执行（或循环检查依赖）
        # 增加最大循环次数防止死锁
        max_cycles = len(self.tasks) * 2
        cycles = 0
        
        while len(completed) < len(self.tasks) and cycles < max_cycles:
            cycles += 1
            progress = False
            for task_id, task in self.tasks.items():
                if task_id in completed:
                    continue
                
                # Check deps
                if all(dep in completed for dep in task.dependencies):
                    # Execute task
                    skill = self.work_map.find_best_skill(task.description)
                    
                    # 构造包含 WorkMap 技能建议的 Prompt
                    context_deps = "\n".join([f"前置任务 {dep} 结果: {self.tasks[dep].result}" for dep in task.dependencies])
                    full_prompt = (
                        f"[Long Horizon Execution]\n"
                        f"当前子任务 ID：{task_id}\n"
                        f"任务描述：{task.description}\n"
                        f"建议技能：{skill.name} ({skill.description})\n"
                        f"前置依赖结果：\n{context_deps}\n\n"
                        "请执行该任务。如果需要使用工具，请生成相应的 Tool Call。"
                    )
                    
                    # 调用 Agent 执行（Agent 内部会自动处理 Tool Call）
                    result = agent.step(full_prompt)
                    
                    task.result = result
                    task.status = "completed"
                    completed.add(task_id)
                    results.append(f"## Task [{task_id}] - {skill.name}\n{result}")
                    progress = True
            
            if not progress:
                break  # Deadlock or cyclic dependency
                
        return "\n\n".join(results)
