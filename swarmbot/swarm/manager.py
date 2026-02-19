from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Optional

from ..config import SwarmConfig
from ..config_manager import SwarmbotConfig
from ..llm_client import OpenAICompatibleClient
from ..memory.qmd import QMDMemoryStore
from ..core.agent import AgentContext, CoreAgent


@dataclass
class SwarmAgentSlot:
    agent: CoreAgent
    weight: float = 1.0


class SwarmManager:
    def __init__(self, config: SwarmConfig | None = None) -> None:
        self.config = config or SwarmConfig()
        self.llm = OpenAICompatibleClient(self.config.llm)
        self.memory = QMDMemoryStore()
        self.agents: List[SwarmAgentSlot] = []
        self._init_default_agents()
        self._architecture: Literal[
            "sequential",
            "concurrent",
            "agent_rearrange",
            "graph",
            "mixture",
            "group_chat",
            "forest",
            "hierarchical",
            "heavy",
            "swarm_router",
            "long_horizon",
            "state_machine",
            "auto",
        ] = "sequential"

    @classmethod
    def from_swarmbot_config(cls, cfg: SwarmbotConfig) -> "SwarmManager":
        sw_cfg = SwarmConfig()
        sw_cfg.max_agents = cfg.swarm.agent_count
        sw_cfg.max_turns = cfg.swarm.max_turns
        sw_cfg.llm.base_url = cfg.provider.base_url
        sw_cfg.llm.api_key = cfg.provider.api_key
        sw_cfg.llm.model = cfg.provider.model
        mgr = cls(sw_cfg)
        mgr._architecture = cfg.swarm.architecture  # type: ignore[assignment]
        return mgr

    def _init_default_agents(self) -> None:
        roles = ["planner", "coder", "critic", "summarizer"]
        for idx, role in enumerate(roles[: self.config.max_agents]):
            ctx = AgentContext(agent_id=f"agent-{role}", role=role)
            agent = CoreAgent(ctx=ctx, llm=self.llm, memory=self.memory)
            self.agents.append(SwarmAgentSlot(agent=agent, weight=1.0))

    def chat(self, user_input: str) -> str:
        if self._architecture == "auto":
            return self._chat_auto(user_input)
        if self._architecture == "sequential":
            return self._chat_sequential(user_input)
        if self._architecture == "concurrent":
            return self._chat_concurrent(user_input)
        if self._architecture == "mixture":
            return self._chat_mixture(user_input)
        if self._architecture == "group_chat":
            return self._chat_group_chat(user_input)
        if self._architecture == "hierarchical":
            return self._chat_hierarchical(user_input)
        if self._architecture == "swarm_router":
            return self._chat_swarm_router(user_input)
        if self._architecture == "long_horizon":
            return self._chat_long_horizon(user_input)
        if self._architecture == "state_machine":
            return self._chat_state_machine(user_input)
        return self._chat_sequential(user_input)

    def _chat_state_machine(self, user_input: str) -> str:
        from ..statemachine.engine import StateMachine, State
        
        # Example: Review Workflow (Coder -> Critic -> Coder/Summarizer)
        # We reuse the default agents (0:planner, 1:coder, 2:critic, 3:summarizer)
        
        coder = self.agents[1].agent
        critic = self.agents[2].agent
        summarizer = self.agents[3].agent
        
        sm = StateMachine(initial_state="coding")
        
        sm.add_state(State(
            name="coding",
            agent=coder,
            description="Write code based on user request.",
            transitions={"default": "review"}
        ))
        
        sm.add_state(State(
            name="review",
            agent=critic,
            description="Review the code. If good, say 'PASS'. If bad, say 'FAIL'.",
            transitions={"PASS": "summary", "FAIL": "coding"}
        ))
        
        sm.add_state(State(
            name="summary",
            agent=summarizer,
            description="Summarize the final approved code.",
            transitions={} # End state
        ))
        
        return sm.run(user_input)

    def _chat_long_horizon(self, user_input: str) -> str:
        from ..middleware.long_horizon import HierarchicalTaskGraph, WorkMapMemory

        work_map = WorkMapMemory(self.llm)
        planner = HierarchicalTaskGraph(self.llm, work_map)
        
        # 1. Plan
        planner.plan(user_input)
        
        # 2. Execute
        # 使用第一个 agent 作为执行者，配合 WorkMap 和 SkillExecutor 逻辑
        return planner.execute(self.agents[0].agent)

    def _chat_sequential(self, user_input: str) -> str:
        context = user_input
        outputs: List[str] = []
        for slot in self.agents:
            reply = slot.agent.step(context)
            outputs.append(f"[{slot.agent.ctx.role}]\n{reply}")
            context = context + "\n\n" + reply
        return "\n\n".join(outputs)

    def _chat_concurrent(self, user_input: str) -> str:
        drafts: List[str] = []
        for slot in self.agents:
            reply = slot.agent.step(user_input)
            drafts.append(f"[{slot.agent.ctx.role}]\n{reply}")
        return "\n\n".join(drafts)

    def _chat_mixture(self, user_input: str) -> str:
        drafts: List[str] = []
        for slot in self.agents:
            reply = slot.agent.step(user_input)
            drafts.append(f"[{slot.agent.ctx.role}]\n{reply}")
        mix_prompt = (
            "你是一个集成器，下面是不同专家 agent 的回答，请综合它们给出一个最优结论：\n\n"
            + "\n\n".join(drafts)
        )
        agg = self.agents[0].agent.step(mix_prompt)
        drafts.append(f"[mixture]\n{agg}")
        return "\n\n".join(drafts)

    def _chat_group_chat(self, user_input: str, rounds: int = 3) -> str:
        messages: List[str] = [f"[user]\n{user_input}"]
        context = user_input
        for r in range(rounds):
            for slot in self.agents:
                reply = slot.agent.step(context)
                tag = f"[round {r+1} - {slot.agent.ctx.role}]"
                messages.append(f"{tag}\n{reply}")
                context = reply
        return "\n\n".join(messages)

    def _chat_hierarchical(self, user_input: str) -> str:
        director = self.agents[0].agent
        workers = self.agents[1:]
        plan = director.step(f"作为项目总监，请基于任务给出执行计划并拆分成子任务：\n{user_input}")
        outputs: List[str] = [f"[director-plan]\n{plan}"]
        for idx, slot in enumerate(workers):
            reply = slot.agent.step(f"子任务 {idx+1}（基于总监计划执行）：\n{plan}\n\n原始任务：\n{user_input}")
            outputs.append(f"[worker-{slot.agent.ctx.role}]\n{reply}")
        summary = director.step(
            "请汇总以下 worker 结果，给出统一的最终输出：\n\n" + "\n\n".join(outputs)
        )
        outputs.append(f"[director-summary]\n{summary}")
        return "\n\n".join(outputs)

    def _chat_swarm_router(self, user_input: str) -> str:
        if "并行" in user_input or "批量" in user_input or "many" in user_input.lower():
            return self._chat_concurrent(user_input)
        if "计划" in user_input or "项目" in user_input or "roadmap" in user_input.lower():
            return self._chat_hierarchical(user_input)
        return self._chat_sequential(user_input)

    def _chat_auto(self, user_input: str) -> str:
        planner = self.agents[0].agent
        auto_prompt = (
            "你是 AutoSwarmBuilder。根据下面的用户任务，决定一个合适的 swarm 配置：\n"
            "- name: 一个简短英文名称\n"
            "- description: 1-2 句中文描述\n"
            "- architecture: 从 [sequential, concurrent, mixture, group_chat, hierarchical, swarm_router] 中选一个\n"
            "- max_loops: 建议的最大对话轮数（整数）\n"
            "- task: 用中文详细说明 swarm 的工作目标\n"
            "请输出 JSON 对象。任务如下：\n\n"
            f"{user_input}"
        )
        resp = planner.step(auto_prompt)
        try:
            import json

            data = json.loads(resp)
            arch = data.get("architecture", "sequential")
            if arch in (
                "sequential",
                "concurrent",
                "mixture",
                "group_chat",
                "hierarchical",
                "swarm_router",
            ):
                self._architecture = arch  # type: ignore[assignment]
        except Exception:
            self._architecture = "sequential"  # type: ignore[assignment]
        return self.chat(user_input)

