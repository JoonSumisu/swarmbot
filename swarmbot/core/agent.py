from __future__ import annotations

import json
import os
import re
import time
import datetime
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..llm_client import OpenAICompatibleClient
from ..tools.adapter import ToolAdapter
from .agent_config import CoreAgentConfig
from .assessment import Assessment
from .boot_loader import BootLoader


@dataclass
class AgentContext:
    """Agent 上下文"""
    agent_id: str
    role: str = "assistant"
    skills: Dict[str, Any] = field(default_factory=dict)
    session_id: Optional[str] = None


@dataclass
class AgentResult:
    """Agent 执行结果"""
    content: str
    assessment: Optional[Assessment] = None
    iterations: int = 0
    should_delegate: bool = False
    delegate_reason: str = ""
    delegate_tool: str = ""
    delegate_target: str = ""  # inference/autonomous/None
    tool_calls_made: List[str] = field(default_factory=list)
    tokens_used: int = 0
    execution_time: float = 0.0


class CoreAgent:
    """CoreAgent - 通用 Agent 核心
    
    参考 autoresearch 的任务驱动循环
    参考 OpenClaw 的 agent lifecycle 管理
    
    所有任务都通过 run() 进入循环，自评估决定是否继续。
    简单任务迭代少，复杂任务迭代多，超复杂任务委托给推理工具。
    """
    
    def __init__(
        self,
        ctx: AgentContext,
        llm: OpenAICompatibleClient,
        memory: Any,
        config: CoreAgentConfig = None,
        hot_memory: Any = None,
        session_memory: Any = None,
        enable_tools: bool = True,
        quiet: bool = False,
    ) -> None:
        self.ctx = ctx
        self.llm = llm
        self.memory = memory
        self.hot_memory = hot_memory
        self.session_memory = session_memory
        
        # 兼容旧接口
        if config is None:
            self.config = CoreAgentConfig(
                agent_id=ctx.agent_id,
                role=ctx.role,
                enable_tools=enable_tools,
                verbose=not quiet,
            )
        else:
            self.config = config
            # 确保 enable_tools 设置一致
            if not quiet:
                config.enable_tools = enable_tools
        
        self._tool_adapter = ToolAdapter()
        self._boot_loader = BootLoader()
        
        # 状态追踪
        self._previous_assessment: Optional[Assessment] = None
        
    # =========================================================================
    # 核心方法：run() - autoresearch 风格的任务驱动循环
    # =========================================================================
    
    def run(self, user_input: str) -> AgentResult:
        """主循环 - autoresearch 风格
        
        所有任务都走这个循环，区别只在迭代次数。
        简单任务 1-2 次，中度任务多次，复杂任务发现需要委托。
        """
        start_time = time.time()
        iteration = 0
        tools_used: List[str] = []
        total_tokens = 0
        previous_assessment: Optional[Assessment] = None
        
        self._log(f"[CoreAgent] Starting run for: {user_input[:50]}...")
        
        # 构建初始 context
        context = self._build_initial_context(user_input)
        
        # 主循环
        final_content = ""
        while True:
            iteration += 1
            
            # 安全上限检查
            if iteration > self.config.max_iterations:
                self._log(f"[CoreAgent] Reached max iterations ({self.config.max_iterations})")
                break
            
            self._log(f"[CoreAgent] === Iteration {iteration} ===")
            
            # 1. LLM 推理
            self._log(f"[CoreAgent] Calling LLM...")
            response, content, tool_calls = self._inference(context)
            total_tokens += response.usage.total_tokens if response.usage else 0
            final_content = content
            
            self._log(f"[CoreAgent] LLM response: {content[:100]}...")
            self._log(f"[CoreAgent] Tool calls: {len(tool_calls) if tool_calls else 0}")
            
            # 2. 执行工具
            if tool_calls:
                tool_results, tool_names = self._execute_tools(tool_calls)
                context["messages"].extend(tool_results)
                tools_used.extend(tool_names)
                self._log(f"[CoreAgent] Executed tools: {tool_names}")
            
            # 3. 自评估（核心！）
            self._log(f"[CoreAgent] Running self-assessment...")
            assessment = self._self_assess(
                task=user_input,
                output=content,
                context=context,
                iteration=iteration,
                previous_assessment=previous_assessment,
            )
            
            # 记录评估日志
            if self.config.log_assessment:
                self._log_assessment(assessment, iteration)
            
            previous_assessment = assessment
            self._previous_assessment = assessment
            
            # 4. 根据决策执行
            if assessment.decision == "stop":
                self._log(f"[CoreAgent] Decision: STOP - {assessment.decision_reason}")
                break
            
            elif assessment.decision == "delegate":
                self._log(f"[CoreAgent] Decision: DELEGATE - {assessment.delegate_reason}")
                return AgentResult(
                    content=content,
                    assessment=assessment,
                    iterations=iteration,
                    should_delegate=True,
                    delegate_reason=assessment.delegate_reason,
                    delegate_tool=assessment.delegate_tool,
                    delegate_target=assessment.delegate_target,
                    tool_calls_made=tools_used,
                    tokens_used=total_tokens,
                    execution_time=time.time() - start_time,
                )
            
            elif assessment.decision == "escalate":
                self._log(f"[CoreAgent] Decision: ESCALATE - {assessment.decision_reason}")
                break
            
            # decision == "continue"
            self._log(f"[CoreAgent] Decision: CONTINUE - {assessment.decision_reason}")
            
            # 5. 处理资源需求
            if assessment.skill_needed:
                self._log(f"[CoreAgent] Loading skills: {assessment.skill_needed}")
                self._load_skills(assessment.skill_needed)
            
            if assessment.memory_needed and assessment.memory_query:
                self._log(f"[CoreAgent] Fetching more memory: {assessment.memory_query}")
                memory_content = self._fetch_memory(assessment.memory_query)
                context["messages"].append({
                    "role": "system",
                    "content": f"相关记忆：{memory_content}"
                })
            
            # 6. 构建继续 prompt
            continuation = self._build_continuation_prompt(assessment)
            context["messages"].append({"role": "user", "content": continuation})
        
        return AgentResult(
            content=final_content,
            assessment=assessment if 'assessment' in locals() else None,
            iterations=iteration,
            should_delegate=False,
            tool_calls_made=tools_used,
            tokens_used=total_tokens,
            execution_time=time.time() - start_time,
        )
    
    # =========================================================================
    # 兼容旧接口：step()
    # =========================================================================
    
    def step(self, user_input: str) -> str:
        """旧接口兼容 - 内部调用 run()"""
        result = self.run(user_input)
        return result.content
    
    # =========================================================================
    # 自评估 - 核心逻辑
    # =========================================================================
    
    def _self_assess(
        self,
        task: str,
        output: str,
        context: Dict,
        iteration: int,
        previous_assessment: Optional[Assessment] = None,
    ) -> Assessment:
        """自评估 - 每次迭代都执行"""
        
        # 构建评估 prompt
        prompt = self._build_assessment_prompt(
            task=task,
            output=output,
            context=context,
            iteration=iteration,
            previous_assessment=previous_assessment,
        )
        
        try:
            # 使用较低温度进行评估，限制输出长度
            resp = self.llm.completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.assessment_temperature,
                max_tokens=1000,  # 限制评估输出长度
            )
            
            assessment_text = self._extract_content(resp.choices[0].message)
            self._log(f"[CoreAgent] Assessment response: {assessment_text[:200]}...")
            
            # 解析评估结果
            assessment = self._parse_assessment(assessment_text)
            
            # 填充迭代信息
            assessment.previous_iteration = iteration
            if previous_assessment:
                assessment.previous_completion = previous_assessment.completion_percentage
                assessment.improvement_made = (
                    assessment.completion_percentage > previous_assessment.completion_percentage
                )
            
            # 根据评估结果决定决策
            assessment = self._make_decision(assessment, iteration)
            
            return assessment
            
        except Exception as e:
            self._log(f"[CoreAgent] Assessment error: {e}")
            # 评估失败，继续执行
            return Assessment(
                complete=False,
                decision="continue",
                decision_reason=f"评估失败，继续执行: {e}",
            )
    
    def _make_decision(self, assessment: Assessment, iteration: int) -> Assessment:
        """根据评估结果决定决策"""
        
        # 1. 完成度检查
        if assessment.complete and assessment.confidence >= 0.8:
            assessment.decision = "stop"
            assessment.decision_reason = "任务完成，置信度足够"
            return assessment
        
        # 2. 委托检查（需要推理循环）
        if assessment.should_delegate:
            assessment.decision = "delegate"
            assessment.decision_reason = assessment.delegate_reason or "需要委托给推理工具"
            assessment.delegate_target = "inference"
            return assessment
        
        # 3. 复杂任务检查（需要更多迭代或专业工具）
        if assessment.completion_percentage < 30 and iteration >= 2:
            # 2次迭代后完成度仍低于30%，可能需要推理循环
            assessment.decision = "delegate"
            assessment.decision_reason = "任务复杂，需要推理循环"
            assessment.delegate_target = "inference"
            assessment.should_delegate = True
            return assessment
        
        # 4. 角色定位检查
        if not assessment.fits_persona or not assessment.in_scope:
            if assessment.confidence < 0.5:
                assessment.decision = "delegate"
                assessment.decision_reason = "超出角色范围或不符合定位"
                assessment.delegate_target = "inference"
                assessment.should_delegate = True
                return assessment
        
        # 5. 质量检查
        if assessment.quality in ["poor"] and iteration >= 3:
            # 连续 3 次迭代质量差，考虑委托
            if assessment.should_optimize:
                assessment.decision = "delegate"
                assessment.decision_reason = "多次迭代质量仍差，需要更专业工具"
                assessment.delegate_target = "inference"
                assessment.should_delegate = True
                return assessment
        
        # 6. 继续优化
        if assessment.should_optimize:
            assessment.decision = "continue"
            assessment.decision_reason = f"需要继续优化: {', '.join(assessment.optimization_areas)}"
            return assessment
        
        # 7. 默认：如果达到高完成度但未标记完成
        if assessment.completion_percentage >= 90 and assessment.quality_score >= 0.7:
            assessment.decision = "stop"
            assessment.decision_reason = "完成度和质量已达标准"
            assessment.complete = True
            return assessment
        
        # 8. 继续
        assessment.decision = "continue"
        assessment.decision_reason = "继续执行"
        return assessment
    
    # =========================================================================
    # 构建方法
    # =========================================================================
    
    def _build_initial_context(self, user_input: str) -> Dict[str, Any]:
        """构建初始 context"""
        messages: List[Dict[str, Any]] = []
        
        # 1. System Prompt
        system_content = self._build_system_prompt()
        messages.append({"role": "system", "content": system_content})
        
        # 2. 历史上下文
        if self.memory:
            history = self.memory.get_context(self.ctx.agent_id, limit=self.config.context_limit, query=user_input)
            for item in history:
                content = item.get("content", "").strip()
                if content:
                    messages.append({"role": "user", "content": content})
        
        # 3. 用户输入
        messages.append({"role": "user", "content": user_input})
        
        # 4. 工具定义
        tools = self._get_tools()
        
        return {
            "messages": messages,
            "tools": tools,
            "tools_used": [],
        }
    
    def _build_system_prompt(self) -> str:
        """构建系统 prompt - 参考 OpenClaw 的 system prompt 结构"""
        # 获取当前时间
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        timezone = time.strftime("%z")
        weekday = datetime.datetime.now().strftime("%A")
        
        # 加载 boot 内容
        boot_content = self._boot_loader.load_boot(
            boot_mode=self.config.boot_mode,
            custom_files=self.config.custom_boot_files if self.config.custom_boot_files else None,
        )
        
        # 角色描述
        is_master = self.config.role in ["planner", "judge", "master", "consensus_moderator"]
        
        role_desc = (
            f"Current Context:\n"
            f"- Time: {current_time} ({timezone})\n"
            f"- Weekday: {weekday}\n"
            f"- Role: {self.config.role}\n"
            f"- Agent ID: {self.config.agent_id}\n"
        )
        
        if is_master:
            role_desc += "You are the primary interface to the user. Speak with the voice defined in your Soul.\n"
        else:
            role_desc += f"You are a specialized functional node. Your role is: {self.config.role}.\n"
        
        # 技能列表
        skills_text = ""
        if self.ctx.skills:
            skills_list = list(self.ctx.skills.keys())
            skills_text = f"\nAvailable Skills: {skills_list}\n"
        
        # 组装系统 prompt
        system_parts = [
            f"### Role & Context\n{role_desc}",
            f"### Boot Configuration\n{boot_content}",
            skills_text,
            "### 自评估说明\n"
            "在每次回答后，系统会自动评估你的回复质量、角色符合度、是否需要继续优化等。\n"
            "你需要根据角色定位，判断任务是否完成、是否需要更多资源、是否需要委托给更专业的工具。",
        ]
        
        system_content = "\n\n".join(p for p in system_parts if p)
        
        # 限制长度
        if len(system_content) > 8000:
            system_content = system_content[:8000] + "\n...[system prompt truncated]\n"
        
        return system_content
    
    def _build_assessment_prompt(
        self,
        task: str,
        output: str,
        context: Dict,
        iteration: int,
        previous_assessment: Optional[Assessment] = None,
    ) -> str:
        """构建自评估 prompt - 完整版本"""
        
        # 获取 boot 摘要
        boot_summary = self._boot_loader.get_boot_summary(
            boot_mode=self.config.boot_mode,
        )
        
        # 获取可用资源
        available_skills = list(self.ctx.skills.keys()) if self.ctx.skills else []
        available_tools = [t["function"]["name"] for t in self._get_tools()] if self.config.enable_tools else []
        
        # 之前状态
        prev_info = ""
        if previous_assessment:
            prev_info = f"""
## 之前迭代状态
- 迭代次数: {previous_assessment.previous_iteration}
- 完成度: {previous_assessment.completion_percentage}%
- 质量分数: {previous_assessment.quality_score}
- 决策: {previous_assessment.decision}
- 已使用的工具: {context.get('tools_used', [])}
"""
        
        return f"""你是 {self.config.role} 角色。请对当前输出进行全面评估。

## 角色定位
{boot_summary}

## 任务信息
原始任务: {task}
当前输出: {output[:1000]}
当前迭代: {iteration}

{prev_info}

## 可用资源
可用 Skills: {available_skills}
可用 Tools: {available_tools}

## 评估要求

请从以下维度进行全面评估：

### 1. 任务完成度
- complete: 任务是否完全完成？(true/false)
- completion_percentage: 完成百分比 (0-100)
- confidence: 你的置信度 (0.0-1.0)

### 2. 角色定位评估
- fits_persona: 回复是否符合你的角色定位和语气？(true/false)
- in_scope: 任务是否在你的能力范围内？(true/false)

### 3. 质量评估
- quality: 输出质量 - good/acceptable/needs_improvement/poor
- quality_score: 质量分数 (0.0-1.0)
- issues: 发现的问题列表

### 4. 优化建议
- should_optimize: 是否需要继续优化？(true/false)
- optimization_areas: 需要优化的方面列表
- next_action: 具体的下一步建议

### 5. 资源需求评估
- skill_needed: 需要引入的 skill 列表（从可用 skills 中选择）
- memory_needed: 是否需要读取更多记忆？(true/false)
- tool_needed: 需要使用的工具列表（从可用 tools 中选择）

### 6. 委托评估
- should_delegate: 是否需要委托给更专业的推理工具？(true/false)
- delegate_reason: 委托原因
- delegate_tool: 建议的推理工具 (standard/supervised/swarms/subswarm)

### 7. 最终决策
- decision: continue/stop/delegate
- decision_reason: 决策原因

请输出 JSON：
{{"complete": bool, "completion_percentage": float, "confidence": float, 
  "fits_persona": bool, "in_scope": bool, "quality": "good|acceptable|needs_improvement|poor", 
  "quality_score": float, "issues": [], "should_optimize": bool, "optimization_areas": [],
  "next_action": str, "skill_needed": [], "memory_needed": bool, "tool_needed": [],
  "should_delegate": bool, "delegate_reason": str, "delegate_tool": str,
  "decision": "continue|stop|delegate", "decision_reason": str}}
"""
    
    def _build_continuation_prompt(self, assessment: Assessment) -> str:
        """构建继续执行的 prompt"""
        parts = [f"系统自评估：任务完成度 {assessment.completion_percentage}%"]
        
        if assessment.quality in ["needs_improvement", "poor"]:
            parts.append(f"质量需要改进：{assessment.quality}")
        
        if assessment.issues:
            parts.append(f"存在问题：{', '.join(assessment.issues)}")
        
        if assessment.next_action:
            parts.append(f"建议下一步：{assessment.next_action}")
        
        if assessment.optimization_areas:
            parts.append(f"需要优化的方面：{', '.join(assessment.optimization_areas)}")
        
        return "\n".join(parts) + "\n\n请继续优化你的回答。"
    
    # =========================================================================
    # 推理和工具执行
    # =========================================================================
    
    def _inference(self, context: Dict) -> Tuple[Any, str, List]:
        """LLM 推理"""
        messages = context["messages"]
        tools = context.get("tools")
        
        completion_kwargs: Dict[str, Any] = {"messages": messages}
        if tools and self.config.enable_tools:
            completion_kwargs["tools"] = tools
        
        resp = self.llm.completion(**completion_kwargs)
        message = resp.choices[0].message
        content = self._extract_content(message)
        tool_calls = message.tool_calls or []
        
        # 添加 assistant 消息到 context
        if content or tool_calls:
            context["messages"].append(self._message_to_dict(message))
        
        return resp, content, tool_calls
    
    def _execute_tools(self, tool_calls: List) -> Tuple[List[Dict[str, Any]], List[str]]:
        """并行执行工具"""
        tool_results = []
        tool_names = []
        
        if not tool_calls:
            return tool_results, tool_names
        
        def execute_single_tool(tc):
            func_name = tc.function.name
            tool_names.append(func_name)
            
            # Tool name sanitization
            if self._tool_adapter.registry.get_tool(func_name) is None:
                matched = re.match(r"[A-Za-z0-9_]+", func_name or "")
                if matched:
                    candidate = matched.group(0)
                    if self._tool_adapter.registry.get_tool(candidate) is not None:
                        func_name = candidate
            
            if self.config.allowed_tools and func_name not in self.config.allowed_tools:
                return {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": func_name,
                    "content": f"Tool '{func_name}' is not allowed for this agent.",
                }
            
            func_args_str = tc.function.arguments
            self._log(f"[CoreAgent] Calling tool: {func_name}({func_args_str[:50]}...)")
            
            try:
                func_args = json.loads(func_args_str)
            except json.JSONDecodeError:
                func_args = {}
            
            tool_context = {}
            if hasattr(self.memory, "whiteboard"):
                tool_context["memory_map"] = self.memory.whiteboard
            
            result = self._tool_adapter.execute(func_name, func_args, context=tool_context)
            self._log(f"[CoreAgent] Tool result: {str(result)[:100]}...")
            
            return {
                "role": "tool",
                "tool_call_id": tc.id,
                "name": func_name,
                "content": str(result),
            }
        
        if self.config.enable_parallel_tools:
            max_workers = min(len(tool_calls), self.config.max_parallel_tools)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(execute_single_tool, tc) for tc in tool_calls]
                for future in futures:
                    try:
                        msg = future.result()
                        tool_results.append(msg)
                    except Exception as e:
                        self._log(f"[CoreAgent] Tool Execution Error: {e}")
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": "unknown",
                            "name": "unknown",
                            "content": f"Error: {str(e)}"
                        })
        else:
            for tc in tool_calls:
                try:
                    msg = execute_single_tool(tc)
                    tool_results.append(msg)
                except Exception as e:
                    self._log(f"[CoreAgent] Tool Execution Error: {e}")
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.function.name,
                        "content": f"Error: {str(e)}"
                    })
        
        return tool_results, tool_names
    
    # =========================================================================
    # 辅助方法
    # =========================================================================
    
    def _get_tools(self) -> List[Dict[str, Any]]:
        """获取可用工具定义"""
        if not self.config.enable_tools:
            return []
        
        all_tools = self._tool_adapter.get_tool_definitions()
        
        if self.config.allowed_tools:
            tools = [t for t in all_tools if t["function"]["name"] in self.config.allowed_tools]
        elif self.ctx.skills:
            tools = [t for t in all_tools if t["function"]["name"] in self.ctx.skills]
        else:
            tools = []
        
        return tools
    
    def _load_skills(self, skill_names: List[str]):
        """动态加载技能"""
        for skill_name in skill_names:
            if skill_name not in self.ctx.skills:
                self.ctx.skills[skill_name] = {"loaded": True}
                self._log(f"[CoreAgent] Loaded skill: {skill_name}")
    
    def _fetch_memory(self, query: str) -> str:
        """获取相关记忆"""
        if self.memory:
            context = self.memory.get_context(self.ctx.agent_id, limit=3, query=query)
            return "\n".join([item.get("content", "") for item in context if item.get("content")])
        return ""
    
    def _extract_content(self, message) -> str:
        """从消息中提取内容（处理 reasoning 模型）"""
        content = message.content or ""
        if content.strip():
            return content
        
        # 处理 reasoning 模型（内容在 reasoning_content 中）
        reasoning = getattr(message, "reasoning_content", None) or ""
        if reasoning:
            return reasoning
        
        return ""
    
    def _message_to_dict(self, message: Any) -> Dict[str, Any]:
        """将 message 对象转换为字典"""
        role = getattr(message, "role", "assistant")
        content = getattr(message, "content", "") or ""
        tool_calls = getattr(message, "tool_calls", None)
        
        normalized_tool_calls = []
        if tool_calls:
            for tc in tool_calls:
                function = getattr(tc, "function", None)
                normalized_tool_calls.append({
                    "id": getattr(tc, "id", ""),
                    "type": "function",
                    "function": {
                        "name": getattr(function, "name", ""),
                        "arguments": getattr(function, "arguments", "{}"),
                    },
                })
        
        result = {"role": role, "content": content}
        if normalized_tool_calls:
            result["tool_calls"] = normalized_tool_calls
        return result
    
    def _parse_assessment(self, text: str) -> Assessment:
        """解析评估结果 - 支持多种格式"""
        try:
            # 1. 尝试提取 JSON
            match = re.search(r'\{[\s\S]*?\}', text)
            if match:
                data = json.loads(match.group())
                return Assessment.from_dict(data)
            
            # 2. 尝试从 markdown 表格中提取信息
            data = self._extract_from_markdown(text)
            if data:
                return Assessment.from_dict(data)
            
            # 3. 尝试从文本中提取关键信息
            data = self._extract_from_text(text)
            if data:
                return Assessment.from_dict(data)
                
        except Exception as e:
            self._log(f"[CoreAgent] Failed to parse assessment: {e}")
        
        # 解析失败，返回默认
        return Assessment(
            complete=False,
            decision="continue",
            decision_reason="评估解析失败，继续执行",
        )
    
    def _extract_from_markdown(self, text: str) -> Optional[Dict[str, Any]]:
        """从 markdown 表格中提取评估信息"""
        try:
            data = {}
            
            # 提取任务完成度
            if "true" in text.lower() and "complete" in text.lower():
                data["complete"] = True
            elif "false" in text.lower() and "complete" in text.lower():
                data["complete"] = False
            
            # 提取完成百分比
            match = re.search(r'completion_percentage.*?(\d+)%', text, re.IGNORECASE)
            if match:
                data["completion_percentage"] = float(match.group(1))
            
            # 提取置信度
            match = re.search(r'confidence.*?(\d+\.?\d*)', text, re.IGNORECASE)
            if match:
                data["confidence"] = float(match.group(1))
            
            # 提取质量
            if "good" in text.lower():
                data["quality"] = "good"
                data["quality_score"] = 0.85
            elif "acceptable" in text.lower():
                data["quality"] = "acceptable"
                data["quality_score"] = 0.72
            elif "needs_improvement" in text.lower():
                data["quality"] = "needs_improvement"
                data["quality_score"] = 0.5
            
            # 角色符合
            if "fits_persona" in text.lower() and "true" in text.lower():
                data["fits_persona"] = True
            
            if "in_scope" in text.lower() and "true" in text.lower():
                data["in_scope"] = True
            
            # 决策
            if "stop" in text.lower() and "decision" in text.lower():
                data["decision"] = "stop"
            elif "continue" in text.lower() and "decision" in text.lower():
                data["decision"] = "continue"
            
            return data if data else None
        except:
            return None
    
    def _extract_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """从文本中提取关键信息"""
        try:
            data = {}
            
            # 简单的关键词匹配
            if "完成" in text or "complete" in text.lower():
                data["complete"] = True
                data["completion_percentage"] = 100.0
            
            if "继续" in text or "continue" in text.lower():
                data["decision"] = "continue"
            elif "停止" in text or "stop" in text.lower():
                data["decision"] = "stop"
            
            return data if data else None
        except:
            return None
    
    def _log(self, message: str):
        """基础日志"""
        if self.config.verbose:
            print(message)
        
        if self.config.log_to_file:
            try:
                log_file = self.config.get_log_file()
                os.makedirs(os.path.dirname(log_file), exist_ok=True)
                with open(log_file, "a", encoding="utf-8") as f:
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"[{timestamp}] {message}\n")
            except Exception:
                pass
    
    def _log_assessment(self, assessment: Assessment, iteration: int):
        """评估日志 - 详细版本"""
        print(f"""
[{self.config.agent_id}] === Assessment (Iteration {iteration}) ===
完成度: {assessment.completion_percentage}% (confidence: {assessment.confidence:.2f})
角色符合: {'✓' if assessment.fits_persona else '✗'} | 能力范围: {'✓' if assessment.in_scope else '✗'} | 得分: {assessment.persona_alignment_score:.2f}
质量: {assessment.quality} ({assessment.quality_score:.2f})
决策: {assessment.decision.upper()} - {assessment.decision_reason}
需要优化: {'是' if assessment.should_optimize else '否'} {assessment.optimization_areas if assessment.should_optimize else ''}
需要委托: {'是' if assessment.should_delegate else '否'} {f'→ {assessment.delegate_tool} ({assessment.delegate_reason})' if assessment.should_delegate else ''}
需要资源: skills={assessment.skill_needed}, memory={assessment.memory_needed}, tools={assessment.tool_needed}
问题: {assessment.issues if assessment.issues else '无'}
下一步: {assessment.next_action if assessment.next_action else '无'}
改进: {'是' if assessment.improvement_made else '否'} (之前: {assessment.previous_completion}% → 现在: {assessment.completion_percentage}%)
""")

    # =========================================================================
    # 工具支持方法
    # =========================================================================
    
    def _should_enable_skill_tools(self, user_input: str) -> bool:
        """判断是否启用 skill 工具"""
        text = (user_input or "").lower()
        keys = ["skill", "技能", "skill_summary", "skill_load", "加载技能", "可用技能"]
        return any(k in text for k in keys)
