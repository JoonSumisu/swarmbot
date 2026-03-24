from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..base import AgentConfig, AgentContext
from .base import BaseWorkerAgent, WorkerLoop

if TYPE_CHECKING:
    from ...config_manager import SwarmbotConfig


class StandardWorkerAgent(BaseWorkerAgent):
    """
    Standard Worker - 标准 8 步推理
    
    特点:
    - 固定 8 步推理流程
    - 无人在回路
    - 适合常规复杂任务
    """

    STEPS = [
        "理解问题",
        "分解任务",
        "收集信息",
        "制定计划",
        "执行计划",
        "检查结果",
        "优化改进",
        "输出结论"
    ]

    def __init__(self, config: "SwarmbotConfig" = None, workspace_path: str = ""):
        worker_config = AgentConfig(
            agent_id="worker-standard",
            role="worker",
            max_iterations=3,
            enable_tools=True
        )
        super().__init__(worker_config, "standard")
        
        self.config = config
        self.workspace_path = workspace_path
        self.loop = StandardWorkerLoop(self, {"max_iterations": 3})
        
        # 当前步骤
        self.current_step = 0
        self.step_results: List[Dict[str, Any]] = []

    def execute_task(self, user_input: str, context: AgentContext) -> Dict[str, Any]:
        """执行标准推理任务"""
        self.reset_steps()
        self.step_results = []
        
        for i, step_name in enumerate(self.STEPS):
            self.step_count = i + 1
            step_result = self._execute_single_step(user_input, step_name, context)
            self.step_results.append(step_result)
            
            # 记录到 loop
            self.loop.record_execution({
                "step": i + 1,
                "name": step_name,
                "duration": step_result.get("duration", 0),
                "quality": step_result.get("quality", 0.5),
                "accurate": step_result.get("accurate", True)
            })
            
            # 检查是否需要提前结束
            if step_result.get("early_exit"):
                break
        
        # 组合最终结果
        return self._compose_result()

    def _execute_single_step(self, user_input: str, step_name: str, context: AgentContext) -> Dict[str, Any]:
        """执行单个步骤"""
        start_time = time.time()
        
        # 构建步骤提示
        prompt = f"""任务: {user_input}
当前步骤: {step_name}
步骤 {self.step_count}/8"""
        
        try:
            from ...core.agent import CoreAgent, AgentContext as CoreCtx
            llm = self._get_llm()
            
            ctx = CoreCtx(
                agent_id=f"standard-step-{self.step_count}",
                role="worker",
                skills={},
            )
            agent = CoreAgent(ctx, llm, None, enable_tools=False, quiet=True)
            result = agent.step(prompt)
            
            return {
                "step": self.step_count,
                "name": step_name,
                "content": result,
                "duration": time.time() - start_time,
                "quality": 0.8 if result else 0.5,
                "accurate": True,
                "early_exit": False
            }
        except Exception as e:
            return {
                "step": self.step_count,
                "name": step_name,
                "content": f"Error: {e}",
                "duration": time.time() - start_time,
                "quality": 0.3,
                "accurate": False,
                "early_exit": False
            }

    def _compose_result(self) -> Dict[str, Any]:
        """组合最终结果"""
        contents = [s.get("content", "") for s in self.step_results]
        
        # 最终总结
        summary = f"""【标准推理完成】

{'='*50}
任务执行摘要:
- 总步骤: {len(self.step_results)}/8
- 总耗时: {sum(s.get('duration', 0) for s in self.step_results):.2f}秒
- 平均质量: {sum(s.get('quality', 0) for s in self.step_results) / max(1, len(self.step_results)):.2f}
{'='*50}

"""
        
        for i, result in enumerate(self.step_results):
            summary += f"\n【步骤 {i+1}: {result.get('name', '')}】\n{result.get('content', '')}\n"
        
        return {
            "content": summary,
            "step_count": len(self.step_results),
            "quality": sum(s.get('quality', 0) for s in self.step_results) / max(1, len(self.step_results)),
            "duration": sum(s.get('duration', 0) for s in self.step_results)
        }

    def _get_llm(self):
        """获取 LLM"""
        from ...llm_client import OpenAICompatibleClient
        return OpenAICompatibleClient.from_provider(providers=self.config.providers if self.config else [])


class StandardWorkerLoop(WorkerLoop):
    """Standard Worker 专用 Loop"""
    
    pass


class SupervisedWorkerAgent(BaseWorkerAgent):
    """
    Supervised Worker - 人在回路推理
    
    特点:
    - 在关键步骤暂停等待用户确认
    - 支持分析方向确认
    - 支持执行计划确认
    """

    CHECKPOINT_STEPS = ["理解问题", "制定计划", "执行计划"]

    def __init__(self, config: "SwarmbotConfig" = None, workspace_path: str = ""):
        worker_config = AgentConfig(
            agent_id="worker-supervised",
            role="worker",
            max_iterations=3,
            enable_tools=True
        )
        super().__init__(worker_config, "supervised")
        
        self.config = config
        self.workspace_path = workspace_path
        self.loop = SupervisedWorkerLoop(self, {"max_iterations": 3})
        
        # 检查点状态
        self.checkpoints: List[Dict[str, Any]] = []
        self.pending_confirmation: Optional[Dict[str, Any]] = None

    def execute_task(self, user_input: str, context: AgentContext) -> Dict[str, Any]:
        """执行人在回路任务"""
        self.reset_steps()
        self.checkpoints = []
        
        for i, step_name in enumerate(self.STEPS):
            self.step_count = i + 1
            
            # 检查是否为检查点
            is_checkpoint = step_name in self.CHECKPOINT_STEPS
            
            if is_checkpoint:
                # 生成检查点内容
                checkpoint_content = self._generate_checkpoint(user_input, step_name, context)
                
                # 保存待确认状态
                self.pending_confirmation = {
                    "step": i + 1,
                    "name": step_name,
                    "content": checkpoint_content,
                    "user_confirmed": None
                }
                
                # 记录检查点
                self.checkpoints.append(self.pending_confirmation.copy())
                
                # 返回暂停信息
                return {
                    "content": checkpoint_content,
                    "requires_confirmation": True,
                    "checkpoint": self.pending_confirmation,
                    "step": i + 1,
                    "total_steps": len(self.STEPS)
                }
            else:
                # 执行普通步骤
                step_result = self._execute_single_step(user_input, step_name, context)
                self.loop.record_execution({
                    "step": i + 1,
                    "name": step_name,
                    "duration": step_result.get("duration", 0),
                    "quality": step_result.get("quality", 0.5)
                })
        
        return self._compose_result()

    def _generate_checkpoint(self, user_input: str, step_name: str, context: AgentContext) -> str:
        """生成检查点内容"""
        prompt = f"""请分析以下任务，并给出【{step_name}】的详细方案。

任务: {user_input}

请输出:
1. 当前分析/计划的核心内容
2. 需要用户确认的关键点
3. 继续执行的建议"""
        
        try:
            from ...core.agent import CoreAgent, AgentContext as CoreCtx
            llm = self._get_llm()
            
            ctx = CoreCtx(
                agent_id=f"supervised-checkpoint-{self.step_count}",
                role="worker",
                skills={},
            )
            agent = CoreAgent(ctx, llm, None, enable_tools=False, quiet=True)
            result = agent.step(prompt)
            return result or "请确认是否继续执行"
        except Exception as e:
            return f"检查点生成失败: {e}"

    def confirm_continuation(self, user_feedback: str) -> Dict[str, Any]:
        """处理用户确认"""
        if self.pending_confirmation:
            self.pending_confirmation["user_confirmed"] = True
            self.pending_confirmation["feedback"] = user_feedback
        return self.execute_task("", None)

    def _execute_single_step(self, user_input: str, step_name: str, context: AgentContext) -> Dict[str, Any]:
        """执行单个步骤"""
        start_time = time.time()
        
        try:
            from ...core.agent import CoreAgent, AgentContext as CoreCtx
            llm = self._get_llm()
            
            ctx = CoreCtx(
                agent_id=f"supervised-step-{self.step_count}",
                role="worker",
                skills={},
            )
            agent = CoreAgent(ctx, llm, None, enable_tools=False, quiet=True)
            result = agent.step(f"任务: {user_input}\n步骤: {step_name}")
            
            return {
                "content": result,
                "duration": time.time() - start_time,
                "quality": 0.8 if result else 0.5
            }
        except Exception as e:
            return {
                "content": f"Error: {e}",
                "duration": time.time() - start_time,
                "quality": 0.3
            }

    def _compose_result(self) -> Dict[str, Any]:
        """组合最终结果"""
        checkpoint_summary = "\n".join(
            f"✓ [{c.get('step')}] {c.get('name')}: 已确认"
            for c in self.checkpoints
            if c.get("user_confirmed")
        )
        
        return {
            "content": f"【人在回路推理完成】\n\n已确认检查点:\n{checkpoint_summary}",
            "checkpoints": len(self.checkpoints),
            "quality": 0.85
        }

    def _get_llm(self):
        from ...llm_client import OpenAICompatibleClient
        return OpenAICompatibleClient.from_provider(providers=self.config.providers if self.config else [])


class SupervisedWorkerLoop(WorkerLoop):
    """Supervised Worker 专用 Loop"""

    def evaluate(self) -> Dict[str, Any]:
        return {
            "checkpoint_accuracy": len([c for c in self.execution_history if c.get("confirmed")]) / max(1, len(self.execution_history)),
            "confirmation_rate": sum(1 for e in self.execution_history if e.get("user_confirmed")) / max(1, len(self.execution_history)),
            "quality_score": self.get_quality_score()
        }


class SwarmsWorkerAgent(BaseWorkerAgent):
    """
    Swarms Worker - 多 Worker 协作
    
    特点:
    - 多个 Worker 并行/串行执行
    - 支持树形/管道/网格架构
    - 协调结果整合
    """

    def __init__(self, config: "SwarmbotConfig" = None, workspace_path: str = ""):
        worker_config = AgentConfig(
            agent_id="worker-swarms",
            role="worker",
            max_iterations=3,
            enable_tools=True
        )
        super().__init__(worker_config, "swarms")
        
        self.config = config
        self.workspace_path = workspace_path
        self.loop = SwarmsWorkerLoop(self, {"max_iterations": 3})
        
        # 子 Worker
        self.sub_workers: List[BaseWorkerAgent] = []

    def execute_task(self, user_input: str, context: AgentContext) -> Dict[str, Any]:
        """执行多 Worker 协作任务"""
        self.reset_steps()
        
        # 任务分解
        sub_tasks = self._decompose_task(user_input)
        
        # 创建子 Worker
        results = []
        for i, task in enumerate(sub_tasks):
            self.step_count = i + 1
            
            worker = StandardWorkerAgent(self.config, self.workspace_path)
            result = worker.execute_task(task, context)
            results.append({
                "task": task,
                "result": result,
                "worker_id": f"swarms-{i}"
            })
            
            self.loop.record_execution({
                "task": task,
                "duration": result.get("duration", 0),
                "quality": result.get("quality", 0.5)
            })
        
        # 整合结果
        return self._integrate_results(results)

    def _decompose_task(self, user_input: str) -> List[str]:
        """分解任务"""
        prompt = f"""请将以下任务分解为多个可并行执行的子任务。

任务: {user_input}

请输出 2-4 个子任务，每个一行。"""
        
        try:
            from ...core.agent import CoreAgent, AgentContext as CoreCtx
            llm = self._get_llm()
            
            ctx = CoreCtx(
                agent_id="swarms-decompose",
                role="worker",
                skills={},
            )
            agent = CoreAgent(ctx, llm, None, enable_tools=False, quiet=True)
            result = agent.step(prompt)
            
            # 解析子任务
            tasks = [line.strip() for line in result.split("\n") if line.strip() and not line.strip().startswith("#")]
            return tasks[:4]  # 最多 4 个
        except:
            return [user_input]  # 默认返回原任务

    def _integrate_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """整合子 Worker 结果"""
        summaries = []
        total_duration = 0
        total_quality = 0
        
        for r in results:
            summaries.append(f"【{r['worker_id']}】{r['result'].get('content', '')[:200]}...")
            total_duration += r['result'].get('duration', 0)
            total_quality += r['result'].get('quality', 0)
        
        integration = f"""【多 Worker 协作完成】

{'='*50}
协作摘要:
- Worker 数量: {len(results)}
- 总耗时: {total_duration:.2f}秒
- 平均质量: {total_quality / max(1, len(results)):.2f}
{'='*50}

"""
        
        for summary in summaries:
            integration += summary + "\n\n"
        
        return {
            "content": integration,
            "worker_count": len(results),
            "quality": total_quality / max(1, len(results)),
            "duration": total_duration
        }

    def _get_llm(self):
        from ...llm_client import OpenAICompatibleClient
        return OpenAICompatibleClient.from_provider(providers=self.config.providers if self.config else [])


class SwarmsWorkerLoop(WorkerLoop):
    """Swarms Worker 专用 Loop"""

    def evaluate(self) -> Dict[str, Any]:
        return {
            "worker_utilization": len([e for e in self.execution_history if e.get("task")]) / max(1, len(self.execution_history)),
            "quality_score": self.get_quality_score(),
            "execution_time": self.get_execution_time()
        }
