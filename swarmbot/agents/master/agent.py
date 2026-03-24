from __future__ import annotations

import importlib
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..base import BaseAgent, AgentConfig, AgentContext
from .loop import MasterLoop
from ...boot.context_loader import load_boot_markdown
from ...config_manager import load_config
from ...llm_client import OpenAICompatibleClient
from ...memory.hot_memory import HotMemory
from ...memory.warm_memory import WarmMemory
from ...memory.cold_memory import ColdMemory
from ...memory.whiteboard import Whiteboard

if TYPE_CHECKING:
    from ...loops.base import BaseInferenceTool


class MasterAgent(BaseAgent):
    """
    MasterAgent - 负责路由、推理工具选择、结果演绎
    
    v2.0 架构:
    - 接收用户输入
    - 判断简单/复杂
    - 选择推理工具
    - 整合结果
    """

    def __init__(self, workspace_path: str, config=None):
        agent_config = AgentConfig(
            agent_id="master",
            role="master",
            max_iterations=2,
            enable_tools=True,
            enable_memory=True
        )
        super().__init__(agent_config)
        
        self.workspace_path = Path(workspace_path)
        self.config = config or load_config()
        
        # 记忆系统
        self.whiteboard = Whiteboard()
        self.hot_memory = HotMemory(self.workspace_path)
        self.warm_memory = WarmMemory(self.workspace_path)
        self.cold_memory = ColdMemory()
        
        # 加载 Boot
        self._load_boot()
        
        # 工具注册表
        self._tools: Dict[str, type] = {}
        self._load_tools()
        
        # MasterLoop
        self.loop = MasterLoop(self, {"max_iterations": 2})
        
        # 会话上下文
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def _load_boot(self):
        """加载 Boot 文件"""
        boot_dir = Path(__file__).parent.parent.parent / "boot" / "master"
        
        self.boot_files = {
            "soul": load_boot_markdown("SOUL.md", "master_agent", max_chars=5000) or "",
            "identity": load_boot_markdown("IDENTITY.md", "master_agent", max_chars=2000) or "",
            "user": load_boot_markdown("USER.md", "master_agent", max_chars=2000) or "",
            "master_agent_boot": load_boot_markdown("masteragentboot.md", "master_agent", max_chars=3000) or "",
        }

    def _load_tools(self):
        """加载推理工具"""
        config_path = Path("~/.swarmbot/boot/inference/inference_tools.md")
        if not config_path.exists():
            config_path = Path(__file__).parent.parent.parent / "boot" / "inference" / "inference_tools.md"
        
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            tool_pattern = r"### \d+\. (\w+).*?\*\*工具 ID\*\*: `(\w+)`.*?\*\*类名\*\*: (\w+).*?\*\*模块路径\*\*: ([\w.]+)"
            matches = re.findall(tool_pattern, content, re.DOTALL)
            
            for name, tool_id, class_name, module_path in matches:
                try:
                    module = importlib.import_module(module_path)
                    tool_class = getattr(module, class_name)
                    self._tools[tool_id] = tool_class
                except Exception as e:
                    pass

    def _get_llm(self) -> OpenAICompatibleClient:
        """获取 LLM 客户端"""
        if not hasattr(self, "_llm"):
            self._llm = OpenAICompatibleClient.from_provider(providers=self.config.providers)
        return self._llm

    def think(self, context: AgentContext) -> str:
        """思考 - 决定回复策略"""
        routing = context.metadata.get("routing", {})
        
        if routing.get("type") == "simple":
            return self._simple_direct(context)
        
        tool_id = routing.get("tool_id", "standard")
        return self._run_inference_tool(tool_id, context)

    def _simple_direct(self, context: AgentContext) -> str:
        """简单直接回复"""
        user_input = context.messages[-1].content if context.messages else ""
        
        prompt = f"""{self.boot_files.get('soul', '')}

用户输入: {user_input}

请给出简洁、自然的回复。"""
        
        try:
            from ...core.agent import CoreAgent, AgentContext as CoreAgentContext
            
            ctx = CoreAgentContext(
                agent_id="master-direct",
                role="master",
                skills={},
            )
            agent = CoreAgent(ctx, self._get_llm(), self.cold_memory, hot_memory=self.hot_memory, enable_tools=False, quiet=True)
            result = agent.step(prompt)
            return result or f"好的：{user_input}"
        except Exception:
            return f"好的：{user_input}"

    def _run_inference_tool(self, tool_id: str, context: AgentContext) -> str:
        """运行推理工具"""
        tool_class = self._tools.get(tool_id)
        if not tool_class:
            return f"工具 {tool_id} 不存在"
        
        user_input = context.messages[-1].content if context.messages else ""
        session_id = context.session_id
        
        try:
            tool = tool_class(self.config, str(self.workspace_path))
            result = tool.run(user_input, session_id=session_id)
            
            if result:
                content = result.content if hasattr(result, 'content') else str(result)
                
                # 演绎结果
                interpreted = self._interpret_result(content, context)
                return interpreted
            return "工具执行返回为空"
        except Exception as e:
            return f"工具执行失败: {e}"

    def _interpret_result(self, raw_result: str, context: AgentContext) -> str:
        """演绎结果"""
        user_input = context.messages[-1].content if context.messages else ""
        
        prompt = f"""你是 Master Agent。请对以下结果进行自然演绎。

原始用户输入: {user_input}
推理结果: {raw_result}

请直接输出最终回复。"""
        
        try:
            from ...core.agent import CoreAgent, AgentContext as CoreAgentContext
            
            ctx = CoreAgentContext(
                agent_id="master-interpret",
                role="master",
                skills={},
            )
            agent = CoreAgent(ctx, self._get_llm(), self.cold_memory, hot_memory=self.hot_memory, enable_tools=False, quiet=True)
            result = agent.step(prompt)
            return result or raw_result
        except Exception:
            return raw_result

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """执行工具"""
        return {"status": "ok"}

    def evaluate(self, output: str, context: AgentContext) -> Dict[str, Any]:
        """评估输出"""
        return {
            "quality": 0.8 if output and len(output) > 10 else 0.5,
            "tool_executed": len(context.tool_calls) > 0,
            "needs_continue": False
        }

    def handle_message(self, user_input: str, session_id: str) -> str:
        """处理消息"""
        # 更新会话
        if session_id not in self._sessions:
            self._sessions[session_id] = {"history": [], "turn_count": 0}
        self._sessions[session_id]["history"].append({"role": "user", "content": user_input})
        self._sessions[session_id]["turn_count"] += 1
        
        # 创建上下文
        context = AgentContext(
            agent_id=self.agent_id,
            session_id=session_id
        )
        context.add_message("user", user_input)
        
        # 执行 Loop
        result = self.loop.run(user_input)
        
        # 记录到记忆
        if result.success:
            self._write_to_memory(user_input, result.content, session_id)
        
        # 记录路由
        routing = context.metadata.get("routing", {})
        self.loop.record_routing({
            "type": routing.get("type", "complex"),
            "tool_id": routing.get("tool_id", "standard"),
            "response_time": result.duration
        })
        
        return result.content

    def _write_to_memory(self, user_input: str, response: str, session_id: str):
        """写入记忆"""
        try:
            self.warm_memory.add_event(session_id, user_input, {"role": "user"})
            self.warm_memory.add_event(session_id, response, {"role": "assistant"})
        except Exception:
            pass

    def read_memory(self, session_id: str, query: str = "") -> Dict[str, Any]:
        """读取记忆"""
        return {
            "hot": self.hot_memory.search(query or session_id, limit=5),
            "warm": self.warm_memory.search(query or session_id, limit=5),
            "cold": self.cold_memory.search(query or session_id, limit=5),
            "whiteboard": dict(self.whiteboard.get_all()),
        }

    def get_system_prompt(self) -> str:
        """获取系统提示词"""
        return self.boot_files.get("soul", "")

    def get_boot_files(self) -> Dict[str, str]:
        """获取 Boot 文件"""
        return self.boot_files
