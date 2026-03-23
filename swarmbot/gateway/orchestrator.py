from __future__ import annotations

import importlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..boot.context_loader import load_boot_markdown
from ..config_manager import load_config
from ..llm_client import OpenAICompatibleClient
from ..memory.hot_memory import HotMemory
from ..memory.warm_memory import WarmMemory
from ..memory.cold_memory import ColdMemory
from ..memory.whiteboard import Whiteboard
from .communication_hub import CommunicationHub, HubMessage, MessageSender, MessageType
from ..loops.base import BaseInferenceTool, InferenceResult
from ..core.agent import AgentContext, CoreAgent


class GatewayMasterAgent:
    """
    GatewayMasterAgent 是 Gateway 的智能核心。
    负责：路由决策、Hub 通信、结果演绎、人在回路转发。
    """

    def __init__(self, workspace_path: str, config=None):
        self.workspace_path = Path(workspace_path)
        self.config = config or load_config()
        
        # Hub 通信
        self.hub = CommunicationHub(workspace_path)
        
        # 加载 Boot 和记忆
        self._load_boot_and_memory()
        
        # 工具注册表
        self._tools: Dict[str, type[BaseInferenceTool]] = {}
        self._load_tools()
        
        # 会话上下文
        self._sessions: Dict[str, Dict[str, Any]] = {}
        
        # LLM 客户端
        self._llm: Optional[OpenAICompatibleClient] = None

    def _load_boot_and_memory(self):
        """加载 MasterAgent 专用 boot 文件"""
        boot_dir = Path(__file__).parent.parent / "boot" / "master"
        
        self.boot_files = {
            "soul": load_boot_markdown("SOUL.md", "master_agent", max_chars=5000) or "",
            "identity": load_boot_markdown("IDENTITY.md", "master_agent", max_chars=2000) or "",
            "user": load_boot_markdown("USER.md", "master_agent", max_chars=2000) or "",
            "master_agent_boot": load_boot_markdown("masteragentboot.md", "master_agent", max_chars=3000) or "",
            "boot_index": load_boot_markdown("../BOOT_INDEX.md", "master_agent", max_chars=3000) or "",
        }
        
        # 记忆系统
        self.whiteboard = Whiteboard()
        self.hot_memory = HotMemory(self.workspace_path)
        self.warm_memory = WarmMemory(self.workspace_path)
        self.cold_memory = ColdMemory()

    def _load_tools(self):
        """从 inference_tools.md 加载工具配置并动态导入"""
        config_path = Path(os.path.expanduser("~/.swarmbot/boot/inference/inference_tools.md"))
        if not config_path.exists():
            config_path = Path(__file__).parent.parent / "boot" / "inference" / "inference_tools.md"
        
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            tool_pattern = r"### (\d+)\. (\w+).*?\*\*工具 ID\*\*: `(\w+)`.*?\*\*类名\*\*: `(\w+)`.*?\*\*模块路径\*\*: `([\w.]+)`"
            matches = re.findall(tool_pattern, content, re.DOTALL)
            
            for _, name, tool_id, class_name, module_path in matches:
                try:
                    module = importlib.import_module(module_path)
                    tool_class = getattr(module, class_name)
                    self._tools[tool_id] = tool_class
                except Exception as e:
                    print(f"[GatewayMasterAgent] Failed to load tool {tool_id}: {e}")

    def _get_llm(self) -> OpenAICompatibleClient:
        if self._llm is None:
            self._llm = OpenAICompatibleClient.from_provider(providers=self.config.providers)
        return self._llm

    def _think_then_decide(self, user_input: str) -> str:
        """
        LLM 浅思考路由决策 - 判断走 simple_direct 还是推理工具
        """
        prompt = f"""You are a dialog classifier. Classify the user input into SIMPLE or COMPLEX.

User input: {user_input}

Classification rules:
- SIMPLE: greetings (你好，hi), thanks (谢谢), farewells (再见，拜拜), confirmations (好的), short self-intro requests (介绍一下你自己，你是谁), short identity Q&A, small talk (最近怎么样), VERY SHORT questions that don't need tools
- COMPLEX: concept explanations (什么是...), how-to questions (如何...), analysis requests (分析), coding tasks (写代码，创建，解释代码), problem solving (怎么办，如何解决), LONG/DETAILED identity requests, deployment (部署), tasks requiring research or tools

First, think briefly about the classification. Then output your final answer in this format:
CLASSIFICATION: [SIMPLE] or CLASSIFICATION: [COMPLEX]"""

        try:
            llm = self._get_llm()
            response = llm.completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1000,
            )
            
            decision = response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            decision_lower = decision.lower()
            
            # 多策略解析
            class_match = re.search(r'CLASSIFICATION:\s*\[(SIMPLE|COMPLEX)\]', decision, re.IGNORECASE)
            if class_match:
                return class_match.group(1).lower()
            
            bracket_match = re.search(r'\[(simple|complex)\]', decision_lower)
            if bracket_match:
                return bracket_match.group(1)
            
            words = re.findall(r'\b(simple|complex)\b', decision_lower)
            if words:
                return words[-1]
            
            return "complex"
        except Exception as e:
            print(f"[GatewayMasterAgent] LLM decision failed: {e}, defaulting to complex")
            return "complex"

    def _select_tool(self, user_input: str) -> str:
        """选择合适的推理工具"""
        prompt = f"""Select the appropriate inference tool for this user input.

User input: {user_input}

Available tools:
- standard: Standard 8-step inference, no human-in-the-loop
- supervised: Human-in-the-loop, pauses at key steps for user confirmation
- swarms: Multi-worker collaboration using Swarms framework

Selection rules:
- Use "supervised" for high-risk tasks (money, legal, security), tasks needing user to confirm analysis direction or execution plan
- Use "swarms" for multi-role analysis, parallel processing, group chat scenarios
- Use "standard" for regular complex tasks

Output format:
TOOL: [standard/supervised/swarms]
REASON: brief reason"""

        try:
            llm = self._get_llm()
            response = llm.completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=500,
            )
            
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            
            tool_match = re.search(r'TOOL:\s*\[?(\w+)\]?', content, re.IGNORECASE)
            if tool_match:
                tool_id = tool_match.group(1).lower()
                if tool_id in self._tools:
                    return tool_id
            
            return "standard"
        except Exception as e:
            print(f"[GatewayMasterAgent] Tool selection failed: {e}")
            return "standard"

    def _simple_direct(self, user_input: str, session_id: str) -> str:
        """
        简单直接回复 - 无需复杂推理工具
        """
        try:
            prompt = self._build_prompt(user_input, session_id)
            ctx = AgentContext(
                agent_id="master",
                role="master",
                skills={},
            )
            agent = CoreAgent(ctx, self._get_llm(), self.cold_memory, hot_memory=self.hot_memory, enable_tools=False, quiet=True)
            result = agent.step(prompt)
            return result or "好的，我明白了。"
        except Exception as e:
            return f"好的，这是我的回答：{user_input}"

    def _interpret_result(self, raw_result: str, user_input: str) -> str:
        """MasterAgent 演绎推理工具的结果"""
        prompt = f"""你是 Master Agent。推理工具已经完成了任务，请对结果进行演绎加工，使回答更自然、更符合你的 Persona。

原始用户输入: {user_input}
推理工具结果: {raw_result}
Persona (Soul): {self.boot_files.get('soul', '')}

请直接输出加工后的回答，不需要提及推理过程。"""

        try:
            from ..core.agent import CoreAgent, AgentContext
            
            ctx = AgentContext(
                agent_id=f"master-interpret-{time.time_ns()}",
                role="master",
                skills={},
            )
            agent = CoreAgent(ctx, self._get_llm(), self.cold_memory, hot_memory=self.hot_memory, enable_tools=False)
            result = agent.step(prompt)
            return result or raw_result
        except Exception as e:
            print(f"[GatewayMasterAgent] Interpret failed: {e}")
            return raw_result

    def handle_message(self, user_input: str, session_id: str) -> str:
        """
        主入口：处理用户消息
        """
        return self._handle_message_impl(user_input, session_id)

    def handle_user_message_sync(self, message: Any) -> str:
        """
        处理用户消息（同步版本）- 用于 CLI run 模式

        v2.0 架构：
        1. 首先判断是否为简单对话（直接回复）
        2. 否则决策使用哪个推理工具
        3. 调用推理工具执行
        4. 整合输出
        """
        chat_id = getattr(message, 'chat_id', 'cli-session')
        content = getattr(message, 'content', '')

        if not content:
            return "请输入内容"

        return self._handle_message_impl(content, chat_id)

    def _handle_message_impl(self, user_input: str, session_id: str) -> str:
        """
        实际的消息处理逻辑
        """
        # 1. 更新会话上下文
        self._update_session(session_id, user_input)
        
        # 2. 路由决策
        route = self._think_then_decide(user_input)
        
        if route == "simple":
            return self._simple_direct(user_input, session_id)
        
        # 3. 选择推理工具
        tool_id = self._select_tool(user_input)
        
        # 4. 通过 Hub 发送任务
        self.hub.send_task_request(tool_id, user_input, session_id)
        
        # 5. 通过 Hub 接收结果 (阻塞等待)
        result_msg = self.hub.recv(
            recipient=MessageSender.MASTER_AGENT,
            session_id=session_id,
            blocking=True,
            timeout=120,
        )
        
        if result_msg and result_msg.msg_type == MessageType.TASK_RESULT:
            raw_content = result_msg.content
            
            # 检查是否需要人在回路
            if result_msg.metadata.get("needs_human_review"):
                return self._handle_human_in_loop(result_msg, session_id)
            
            # 6. 演绎结果
            interpreted = self._interpret_result(raw_content, user_input)
            
            # 7. 写入 Warm Memory
            self._write_to_memory(user_input, interpreted, session_id)
            
            return interpreted
        
        return "抱歉，处理过程中出现了一些问题，请稍后重试。"

    def _handle_human_in_loop(self, suspend_msg: HubMessage, session_id: str) -> str:
        """处理人在回路暂停"""
        checkpoint_data = suspend_msg.metadata.get("checkpoint_data", {})
        stage = checkpoint_data.get("stage", "unknown")
        message_to_user = f"【需要确认】{suspend_msg.content}\n\n请回复你的决定。"
        
        # 保存暂停状态
        self._sessions[session_id]["suspended"] = True
        self._sessions[session_id]["suspend_data"] = suspend_msg
        
        return message_to_user

    def handle_user_feedback(self, feedback: str, session_id: str) -> str:
        """处理用户在回路的反馈"""
        session = self._sessions.get(session_id, {})
        
        if not session.get("suspended"):
            # 正常对话的用户反馈
            return self.handle_message(feedback, session_id)
        
        # 处理人在回路的反馈
        suspend_msg = session.get("suspend_data")
        if suspend_msg:
            # 发送继续指令到 Hub
            self.hub.send_resume_request(feedback, session_id)
            
            # 接收最终结果
            result_msg = self.hub.recv(
                recipient=MessageSender.MASTER_AGENT,
                session_id=session_id,
                blocking=True,
                timeout=120,
            )
            
            if result_msg:
                interpreted = self._interpret_result(result_msg.content, session.get("last_input", ""))
                self._sessions[session_id]["suspended"] = False
                return interpreted
        
        self._sessions[session_id]["suspended"] = False
        return "已收到你的反馈，继续处理中..."

    def _update_session(self, session_id: str, user_input: str):
        """更新会话上下文"""
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                "history": [],
                "last_input": "",
                "suspended": False,
                "suspend_data": None,
            }
        
        session = self._sessions[session_id]
        session["history"].append({"role": "user", "content": user_input})
        session["last_input"] = user_input
        
        # 限制历史长度
        if len(session["history"]) > 20:
            session["history"] = session["history"][-20:]

    def _write_to_memory(self, user_input: str, response: str, session_id: str):
        """写入记忆"""
        try:
            # 写入 Warm Memory
            self.warm_memory.add_event(
                session_id,
                user_input,
                {"role": "user", "content": user_input, "type": "inference"}
            )
            self.warm_memory.add_event(
                session_id,
                response,
                {"role": "assistant", "content": response, "type": "inference"}
            )
        except Exception as e:
            print(f"[GatewayMasterAgent] Write to memory failed: {e}")

    def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """获取会话上下文"""
        return self._sessions.get(session_id, {})

    def read_memory(self, session_id: str, query: str = "") -> Dict[str, Any]:
        """读取记忆"""
        results = {
            "hot": [],
            "warm": [],
            "cold": [],
            "whiteboard": dict(self.whiteboard.get_all()),
        }
        
        try:
            if self.hot_memory:
                results["hot"] = self.hot_memory.search(query or session_id, limit=5)
        except Exception as e:
            print(f"[GatewayMasterAgent] Read hot memory failed: {e}")
        
        try:
            if self.warm_memory:
                results["warm"] = self.warm_memory.search(query or session_id, limit=5)
        except Exception as e:
            print(f"[GatewayMasterAgent] Read warm memory failed: {e}")
        
        try:
            if self.cold_memory:
                results["cold"] = self.cold_memory.search(query or session_id, limit=5)
        except Exception as e:
            print(f"[GatewayMasterAgent] Read cold memory failed: {e}")
        
        return results

    def check_autonomous_messages(self) -> List[HubMessage]:
        """检查来自 Autonomous 的消息"""
        return self.hub.get_unconsumed_messages(
            recipient=MessageSender.MASTER_AGENT
        )

    def send_to_autonomous(self, content: str, bundle_id: str = "", session_id: str = "") -> str:
        """发送消息给 Autonomous"""
        return self.hub.send_autonomous_request(content, bundle_id, session_id)

    def dispatch_subswarms(self, tasks: List[Dict[str, Any]], session_id: str, max_concurrent: int = 3) -> str:
        """
        分发多个 subswarms 异步执行
        
        tasks: [
            {"topic": "topic1", "description": "任务描述", "priority": 1},
            {"topic": "topic2", "description": "任务描述", "priority": 0},
        ]
        
        返回 swarm_id
        """
        from .subswarm_manager import SubSwarmManager, SubSwarmConfig
        
        config = SubSwarmConfig(max_concurrent=max_concurrent)
        manager = SubSwarmManager(self.hub, session_id, config)
        
        for task in tasks:
            manager.add_task(
                topic=task.get("topic", "default"),
                description=task.get("description", ""),
                tool_id=task.get("tool_id", "standard"),
                priority=task.get("priority", 0),
                metadata=task.get("metadata", {}),
            )
        
        # 保存 manager 到会话
        if session_id not in self._sessions:
            self._sessions[session_id] = {"history": [], "swarm_managers": {}}
        if "swarm_managers" not in self._sessions[session_id]:
            self._sessions[session_id]["swarm_managers"] = {}
        self._sessions[session_id]["swarm_managers"][manager.swarm_id] = manager
        
        # 启动执行
        def executor(task_desc: str, task_id: str) -> str:
            tool = self._select_tool(task_desc)
            if tool in self._tools:
                tool_class = self._tools[tool]
                tool_instance = tool_class(self.config, str(self.workspace_path))
                result = tool_instance.run(task_desc, task_id)
                return result.content if hasattr(result, 'content') else str(result)
            return f"Tool {tool} not found"
        
        manager.dispatch(executor)
        
        return manager.swarm_id

    def wait_and_coordinate_subswarms(self, swarm_id: str, session_id: str, timeout: int = 120) -> Dict[str, Any]:
        """
        等待 subswarms 完成并协调结果
        """
        manager = self._sessions.get(session_id, {}).get("swarm_managers", {}).get(swarm_id)
        
        if not manager:
            return {"error": "Swarm not found"}
        
        # 等待完成
        results = manager.wait_for_completion(timeout=timeout)
        
        # 检查是否有协调请求需要用户决策
        coords = self.hub.get_coordination_requests(swarm_id, session_id)
        requires_decision = any(c.metadata.get("requires_human_decision", False) for c in coords)
        
        # 按 topic 分组结果
        grouped = manager.group_results_by_topic()
        
        return {
            "swarm_id": swarm_id,
            "total_results": len(results),
            "success_count": sum(1 for r in results if r.success),
            "failed_count": sum(1 for r in results if not r.success),
            "grouped_by_topic": {
                topic: [r.content for r in tasks] 
                for topic, tasks in grouped.items()
            },
            "requires_human_decision": requires_decision,
            "coordination_requests": [
                {"content": c.content, "topic": c.topic}
                for c in coords if c.metadata.get("requires_human_decision", False)
            ],
        }

    def coordinate_subswarms_results(self, swarm_id: str, session_id: str) -> str:
        """
        MasterAgent 演绎 subswarms 的结果
        """
        status = self.hub.get_swarm_status(swarm_id, session_id)
        results = self.hub.get_subswarm_results(swarm_id, session_id)
        
        if not results:
            return "所有任务已完成，但无结果返回。"
        
        prompt = f"""你是 Master Agent。多个 SubSwarm 已经完成了各自的任务，请整合结果并给出最终回答。

Swarm 状态: {json.dumps(status, ensure_ascii=False)}
SubSwarm 结果数量: {len(results)}

各 SubSwarm 结果:
{chr(10).join([f"- [{r.topic}]: {r.content[:200]}..." for r in results[:5]])}

请整合这些结果，给出连贯、有条理的最终回答。"""

        try:
            from ..core.agent import CoreAgent, AgentContext
            
            ctx = AgentContext(
                agent_id=f"coordinator-{swarm_id}",
                role="coordinator",
                skills={},
            )
            agent = CoreAgent(ctx, self._get_llm(), self.cold_memory, hot_memory=self.hot_memory, enable_tools=False)
            result = agent.step(prompt)
            return result
        except Exception as e:
            print(f"[GatewayMasterAgent] Coordinate failed: {e}")
            return f"完成，共 {len(results)} 个子任务。"


def create_master_agent(workspace_path: str, config=None) -> GatewayMasterAgent:
    """工厂函数：创建 MasterAgent 实例"""
    return GatewayMasterAgent(workspace_path, config)
