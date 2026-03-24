from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .base_agent import BaseAgent, AgentConfig, RunResult
from .context import AgentContext, ContextBuilder
from .events import EventBus, AgentEvent, EventType, EventPhase

if TYPE_CHECKING:
    from ..llm_client import OpenAICompatibleClient


class Hook:
    """Hook 基类"""
    
    BEFORE_THINK = "before_think"
    AFTER_THINK = "after_think"
    BEFORE_EXECUTE = "before_execute"
    AFTER_EXECUTE = "after_execute"
    BEFORE_COMPACT = "before_compact"
    AFTER_COMPACT = "after_compact"
    ON_ERROR = "on_error"


class AgentLoop:
    """
    Agent Loop 核心
    
    生命周期:
    1. prepare    - 准备上下文
    2. think      - LLM 推理 (Hook: before_think, after_think)
    3. execute    - 执行工具 (Hook: before_execute, after_execute)
    4. evaluate   - 评估结果
    5. compact    - 压缩 (Hook: before_compact, after_compact)
    6. repeat/finish - 循环或结束
    
    参考 OpenClaw Hook 系统设计
    """

    def __init__(self, agent: BaseAgent, config: Dict[str, Any]):
        self.agent = agent
        self.config = config
        self.agent_id = agent.agent_id
        
        # 配置
        agent_config = agent.config if agent.config else AgentConfig(agent_id=agent.agent_id, role="")
        self.max_iterations = config.get("max_iterations", agent_config.max_iterations)
        self.timeout_seconds = config.get("timeout_seconds", agent_config.timeout_seconds)
        self.enable_compact = config.get("enable_compact", True)
        
        # Hooks
        self._hooks: Dict[str, List[callable]] = {}
        
        # 状态
        self.iteration = 0
        self._start_time: Optional[float] = None
        self._context: Optional[AgentContext] = None

    def register_hook(self, hook_name: str, callback: callable):
        """注册 Hook"""
        if hook_name not in self._hooks:
            self._hooks[hook_name] = []
        self._hooks[hook_name].append(callback)

    def _run_hooks(self, hook_name: str, *args, **kwargs) -> List[Any]:
        """运行所有 Hook"""
        results = []
        for callback in self._hooks.get(hook_name, []):
            try:
                result = callback(self, *args, **kwargs)
                results.append(result)
            except Exception:
                pass
        return results

    def _prepare_context(self, input_data: Any, context_builder: Optional[ContextBuilder] = None) -> AgentContext:
        """准备上下文"""
        if context_builder:
            ctx = context_builder.build(
                session_id=self.config.get("session_id", "default"),
                agent_id=self.agent_id
            )
        else:
            ctx = AgentContext(
                agent_id=self.agent_id,
                session_id=self.config.get("session_id", "default"),
            )
        
        # 添加输入消息
        if isinstance(input_data, str):
            ctx.add_message("user", input_data)
        elif isinstance(input_data, dict):
            ctx.add_message("user", input_data.get("content", str(input_data)))
        
        # Hook: before_think (在首次 think 前运行)
        self._run_hooks(Hook.BEFORE_THINK, ctx)
        
        return ctx

    def _think(self, context: AgentContext) -> str:
        """思考阶段"""
        self.agent.emit_lifecycle(EventPhase.THINK)
        
        # 执行 agent think
        output = self.agent.think(context)
        
        # Hook: after_think
        self._run_hooks(Hook.AFTER_THINK, output, context)
        
        return output

    def _execute_tools(self, output: str, context: AgentContext) -> List[Dict[str, Any]]:
        """执行工具阶段"""
        self.agent.emit_lifecycle(EventPhase.EXECUTE)
        
        # 解析工具调用
        tool_calls = self._parse_tool_calls(output)
        
        if not tool_calls:
            return []
        
        results = []
        
        # Hook: before_execute
        self._run_hooks(Hook.BEFORE_EXECUTE, tool_calls, context)
        
        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            arguments = tool_call.get("arguments", {})
            
            try:
                result = self.agent.execute_tool(tool_name, arguments)
                context.add_tool_call(tool_name, arguments, result, success=True)
                results.append({
                    "name": tool_name,
                    "arguments": arguments,
                    "result": result,
                    "success": True
                })
            except Exception as e:
                context.add_tool_call(tool_name, arguments, None, success=False, error=str(e))
                results.append({
                    "name": tool_name,
                    "arguments": arguments,
                    "error": str(e),
                    "success": False
                })
        
        # Hook: after_execute
        self._run_hooks(Hook.AFTER_EXECUTE, results, context)
        
        return results

    def _parse_tool_calls(self, output: str) -> List[Dict[str, Any]]:
        """解析工具调用 - 支持多种格式"""
        import json
        import re
        
        tool_calls = []
        
        # 尝试 JSON 格式: {"tool": "xxx", "args": {...}}
        try:
            # 查找 JSON 对象
            matches = re.findall(r'\{[^{}]*"tool"[^{}]*"args"[^{}]*\}', output, re.DOTALL)
            for match in matches:
                try:
                    obj = json.loads(match)
                    if "tool" in obj or "name" in obj:
                        tool_calls.append({
                            "name": obj.get("tool") or obj.get("name"),
                            "arguments": obj.get("args") or obj.get("arguments", {})
                        })
                except:
                    pass
        except:
            pass
        
        # 尝试 XML 格式: <tool>xxx</tool> 或 <invoke name="xxx">
        try:
            xml_matches = re.findall(r'<invoke\s+name="([^"]+)">(.*?)</invoke>', output, re.DOTALL)
            for name, content in xml_matches:
                args = {}
                arg_matches = re.findall(r'<parameter\s+name="([^"]+)">([^<]+)</parameter>', content)
                for arg_name, arg_value in arg_matches:
                    try:
                        args[arg_name] = json.loads(arg_value.strip())
                    except:
                        args[arg_name] = arg_value.strip()
                tool_calls.append({"name": name, "arguments": args})
        except:
            pass
        
        return tool_calls

    def _evaluate(self, output: str, context: AgentContext) -> Dict[str, Any]:
        """评估阶段"""
        self.agent.emit_lifecycle(EventPhase.EVALUATE)
        
        evaluation = self.agent.evaluate(output, context)
        
        # 发射评估指标
        self.agent.emit_metrics(evaluation)
        
        return evaluation

    def _should_finish(self, evaluation: Dict[str, Any]) -> bool:
        """判断是否结束"""
        # 质量达标
        quality = evaluation.get("quality", 0)
        if quality >= 0.8:
            return True
        
        # 达到最大迭代
        if self.iteration >= self.max_iterations:
            return True
        
        # 工具调用成功但无需继续
        if evaluation.get("tool_executed", False) and not evaluation.get("needs_continue", False):
            return True
        
        return False

    def _compact(self, context: AgentContext):
        """压缩阶段"""
        if not self.enable_compact:
            return
        
        if not self.agent.should_compact(context):
            return
        
        self.agent.emit_lifecycle(EventPhase.COMPACT)
        
        # Hook: before_compact
        self._run_hooks(Hook.BEFORE_COMPACT, context)
        
        self.agent.compact(context)
        
        # Hook: after_compact
        self._run_hooks(Hook.AFTER_COMPACT, context)

    def run(self, input_data: Any, context_builder: Optional[ContextBuilder] = None) -> RunResult:
        """
        执行 Agent Loop
        
        Args:
            input_data: 输入数据 (str 或 dict)
            context_builder: 可选的上下文构建器
            
        Returns:
            RunResult: 运行结果
        """
        self._start_time = time.time()
        self.iteration = 0
        self._context = None
        
        # 发射开始事件
        self.agent.emit_lifecycle(EventPhase.START)
        
        tool_calls_history = []
        error = None
        
        try:
            # 1. 准备上下文
            context = self._prepare_context(input_data, context_builder)
            self._context = context
            
            # Loop
            while self.iteration < self.max_iterations:
                self.iteration += 1
                
                # 2. Think
                output = self._think(context)
                
                # 3. Execute tools
                results = self._execute_tools(output, context)
                if results:
                    tool_calls_history.extend(results)
                    # 添加工具结果到上下文
                    for result in results:
                        if result.get("success"):
                            content = f"[Tool: {result['name']}] {result.get('result', 'OK')}"
                        else:
                            content = f"[Tool Error: {result['name']}] {result.get('error', 'Unknown')}"
                        context.add_message("assistant", content)
                    continue
                
                # 4. Evaluate
                evaluation = self._evaluate(output, context)
                
                # 5. Check finish
                if self._should_finish(evaluation):
                    break
                
                # 添加输出到上下文继续
                context.add_message("assistant", output)
            
            # 6. Compact
            self._compact(context)
            
            # 获取最终输出
            final_output = context.messages[-1].content if context.messages else ""
            
        except Exception as e:
            error = str(e)
            final_output = f"Error: {e}"
            self.agent.emit_lifecycle(EventPhase.ERROR)
            
            # Hook: on_error
            self._run_hooks(Hook.ON_ERROR, error)
        
        # 发射结束事件
        self.agent.emit_lifecycle(EventPhase.END)
        
        duration = time.time() - (self._start_time or time.time())
        
        return RunResult(
            success=error is None,
            content=final_output,
            iterations=self.iteration,
            duration=duration,
            tool_calls=tool_calls_history,
            events=[e.to_dict() for e in self.agent.event_bus.get_events()],
            metrics=self.agent.get_metrics(),
            error=error
        )

    def get_context(self) -> Optional[AgentContext]:
        """获取当前上下文"""
        return self._context

    def get_state(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            "agent_id": self.agent_id,
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "running": self._context is not None,
            "duration": time.time() - (self._start_time or time.time()) if self._start_time else 0
        }
