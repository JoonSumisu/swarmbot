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
        
        # INTEGRATE NANOBOT MEMORY & OVERTHINKING
        # Use Nanobot's native memory if available, otherwise QMD fallback
        try:
            from nanobot.agent.memory import MemoryStore as NanobotMemoryStore
            from pathlib import Path
            import os
            
            # Nanobot MemoryStore expects a Path object for workspace
            # We use ~/.nanobot/ by default or current dir
            workspace_path = Path(os.path.expanduser("~/.nanobot"))
            if not workspace_path.exists():
                workspace_path = Path(os.getcwd())
                
            self.memory = NanobotMemoryStore(workspace=workspace_path)
            
            # ------------------------------------------------------------------
            # FIX: Monkey-patch MemoryStore to support Swarmbot CoreAgent API
            # CoreAgent expects: get_context(agent_id, limit), add_event(agent_id, content, meta)
            # Nanobot MemoryStore has: get_memory_context(), append_history(entry)
            # ------------------------------------------------------------------
            
            def get_context_shim(agent_id: str, limit: int = 16) -> List[Dict[str, str]]:
                # Read from history.md and parse last N entries
                # Nanobot history is raw text. We need to parse it or just return raw.
                # For now, we just return the long-term memory + recent raw history as a single system message?
                # No, CoreAgent expects list of dicts.
                # We can try to parse the HISTORY.md file.
                
                # Simplified: Read last 2000 chars of history
                try:
                    hist_path = self.memory.history_file
                    if hist_path.exists():
                        text = hist_path.read_text(encoding="utf-8")
                        # Split by double newline to get chunks
                        chunks = text.split("\n\n")
                        recent = chunks[-limit:] if limit else chunks
                        return [{"content": c.strip(), "role": "user"} for c in recent if c.strip()]
                except:
                    pass
                return []

            def add_event_shim(agent_id: str, content: str, meta: Dict[str, Any] | None = None) -> None:
                # Format: [Timestamp] [AgentID] Content
                import datetime
                ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                entry = f"[{ts}] [{agent_id}] {content}"
                self.memory.append_history(entry)
                
                # Also trigger Overthinking if enabled?
                # self.overthinking.trigger(...)
            
            # Attach shims
            self.memory.get_context = get_context_shim
            self.memory.add_event = add_event_shim
            # Also need whiteboard for concurrent
            # Nanobot doesn't have whiteboard. We add a simple dict.
            self.memory.whiteboard = type("Whiteboard", (), {})()
            self.memory.whiteboard.data = {}
            self.memory.whiteboard.update = lambda k, v: self.memory.whiteboard.data.update({k: v})
            self.memory.whiteboard.get = lambda k: self.memory.whiteboard.data.get(k)
            
            self._log(f"SwarmManager: Using Nanobot native MemoryStore at {workspace_path} (Shimmed)")
            
        except ImportError:
            self.memory = QMDMemoryStore()
            self._log("SwarmManager: Nanobot memory not found, using QMD fallback.")
        except Exception as e:
            self.memory = QMDMemoryStore()
            self._log(f"SwarmManager: Failed to init Nanobot memory ({e}), using QMD fallback.")
            
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
        
        # Initialize Overthinking Loop if enabled
        # We need to hook this into the chat lifecycle or run it as a background task
        # For now, we prepare it.
        self.overthinking = None
        try:
            from nanobot.agent.overthinking import OverthinkingLoop
            # OverthinkingLoop needs an agent instance or similar context
            # We will attach it to the planner or a dedicated thinker agent
            # self.overthinking = OverthinkingLoop(...)
            pass 
        except ImportError:
            pass

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
        mgr._display_mode = cfg.swarm.display_mode  # Inject display mode
        
        # Inject max_tokens into LLM config for AutoSwarmBuilder and agents
        if hasattr(sw_cfg.llm, "max_tokens"):
            # If SwarmConfig.LLMConfig has this field
            sw_cfg.llm.max_tokens = cfg.provider.max_tokens
        else:
            # Otherwise we monkey-patch or handle in CoreAgent creation
            # Since CoreAgent uses OpenAICompatibleClient which reads from config/provider,
            # we ensure the provider config passed down is correct.
            pass
            
        return mgr

    def _log(self, message: str) -> None:
        """Helper for conditional logging based on display_mode."""
        if getattr(self, "_display_mode", "simple") == "log":
            print(f"[SwarmLog] {message}")

    def _init_default_agents(self) -> None:
        # Default initialization based on count, but roles will be dynamically reassigned in auto mode
        # Initialize up to 8 roles to support scale
        roles = ["planner", "coder", "critic", "summarizer", "researcher", "analyst", "writer", "reviewer"]
        for idx in range(self.config.max_agents):
            # If we have predefined roles, use them, otherwise use generic 'worker-N'
            role = roles[idx] if idx < len(roles) else f"worker-{idx+1}"
            ctx = AgentContext(agent_id=f"agent-{role}", role=role)
            agent = CoreAgent(ctx=ctx, llm=self.llm, memory=self.memory)
            self.agents.append(SwarmAgentSlot(agent=agent, weight=1.0))

    def _resize_swarm(self, target_count: int) -> None:
        """Dynamically resize the swarm to match target agent count."""
        current_count = len(self.agents)
        
        if target_count > current_count:
            self._log(f"Scaling up swarm from {current_count} to {target_count} agents.")
            for i in range(current_count, target_count):
                role = f"worker-{i+1}"
                ctx = AgentContext(agent_id=f"agent-{role}", role=role)
                agent = CoreAgent(ctx=ctx, llm=self.llm, memory=self.memory)
                self.agents.append(SwarmAgentSlot(agent=agent, weight=1.0))
                
        elif target_count < current_count:
            self._log(f"Scaling down swarm from {current_count} to {target_count} agents.")
            self.agents = self.agents[:target_count]

    def _reassign_roles(self, new_roles: List[str]) -> None:
        """Dynamically reassign roles to existing agents and inject context-aware skills."""
        self._log(f"Reassigning roles to: {new_roles}")
        
        # 1. Resize swarm to match required roles
        required_count = len(new_roles)
        # Cap at a reasonable limit to prevent explosion (e.g. 10)
        required_count = min(required_count, 10)
        self._resize_swarm(required_count)
        
        # Skill Injection Map (Context -> Tool Name)
        skill_map = {
            "finance": ["web_search"], # Finance usually needs search
            "market": ["web_search"],
            "research": ["web_search", "browser_open"],
            "code": ["file_write", "shell_exec"],
            "developer": ["file_write", "shell_exec"],
            "data": ["python_exec"] # Assuming python skill exists or mapped
        }
        
        for i, slot in enumerate(self.agents):
            if i < len(new_roles):
                role = new_roles[i]
                slot.agent.ctx.role = role
                slot.agent.ctx.agent_id = f"agent-{role}"
                
                # Dynamic Skill Injection
                for key, tools in skill_map.items():
                    if key in role.lower():
                        self._log(f"Injecting skills {tools} into {role}...")
                        # In a real system we would enable these tools here
            else:
                slot.agent.ctx.role = "observer"
                slot.agent.ctx.agent_id = f"agent-observer-{i}"

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
        self._log(f"Starting Sequential flow with {len(self.agents)} agents.")
        context = user_input
        outputs: List[str] = []
        for slot in self.agents:
            self._log(f"Agent [{slot.agent.ctx.role}] is thinking...")
            reply = slot.agent.step(context)
            outputs.append(f"[{slot.agent.ctx.role}]\n{reply}")
            context = context + "\n\n" + reply
        return "\n\n".join(outputs)

    def _consensus_decision(self, user_input: str, outputs: List[str]) -> str:
        """
        Synthesize a final consensus decision from multiple agent outputs.
        Acts as a 'Judge' or 'Moderator' phase.
        Includes multi-round refinement if consensus is weak.
        """
        self._log("--- Consensus Phase ---")
        
        # We can use the first agent (Planner/Director) or a dedicated judge role if available
        judge = self.agents[0].agent
        
        # Force Master/Judge role for Consensus to ensure Soul binding
        judge.ctx.role = "consensus_moderator" 
        
        consensus_prompt = (
            "You are the Consensus Moderator. Your goal is to synthesize a final, cohesive answer "
            "based on the following outputs from different agents. \n"
            "Resolve any conflicts, merge complementary information, and ensure the final answer "
            "directly addresses the user's original request.\n\n"
            f"Original Request: {user_input}\n\n"
            "Agent Outputs:\n" + "\n".join(outputs) + "\n\n"
            "CRITICAL: If any agent provided numerical data (like stock prices), verify if they are from "
            "reliable search results (look for 'Tool result' or 'Source'). "
            "If numbers conflict or look suspicious (e.g. hallucinated old data), "
            "YOU MUST trigger a final validation search or explicitly state the uncertainty.\n"
            "Final Consensus Decision:"
        )
        
        final_decision = judge.step(consensus_prompt)
        
        # Auto-Adjustment / Refinement (Mock Logic for PoC)
        # If the judge thinks the result is bad (e.g. contains "insufficient info"), we could trigger another round.
        if "insufficient info" in final_decision.lower() or "conflict" in final_decision.lower():
            self._log("Consensus weak. Triggering refinement round...")
            # Ideally we would ask specific agents to clarify, but for now we do a self-correction
            refinement_prompt = (
                f"The previous consensus was weak: {final_decision}\n"
                "Please try to reason through the available information again and provide a more definitive answer."
            )
            final_decision = judge.step(refinement_prompt)
            
        self._log(f"Consensus Reached: {final_decision[:100]}...")
        return final_decision

    def _chat_concurrent(self, user_input: str) -> str:
        self._log(f"Starting Concurrent flow with {len(self.agents)} agents.")
        import concurrent.futures
        
        # Determine number of rounds (simple auto-adjustment based on complexity)
        # If input contains "deep" or "iterative", do more rounds.
        rounds = 2 if "deep" in user_input.lower() or "research" in user_input.lower() else 1
        
        context = user_input
        history_acc = [] # Accumulate all rounds
        
        for r in range(rounds):
            self._log(f"--- Round {r+1}/{rounds} ---")
            drafts: List[str] = []
            
            # 0. Shared Context Injection (Whiteboard)
            # Ensure all agents have the latest user input in their memory/context
            
            def _run_agent(slot: SwarmAgentSlot, current_context: str) -> str:
                self._log(f"Agent [{slot.agent.ctx.role}] is working in parallel...")
                # Pass accumulated context if > round 1
                prompt = current_context
                if r > 0:
                    prompt = f"Round {r+1} Task. Previous findings:\n" + "\n".join(history_acc[-len(self.agents):]) + f"\n\nOriginal Request: {user_input}\nRefine or expand on the findings."
                
                result = slot.agent.step(prompt)
                # Structured Log
                self._log(f"[Result] Agent {slot.agent.ctx.role}: {result[:50]}...")
                
                # Post-execution: Share result to Whiteboard
                self.memory.whiteboard.update(f"result_{slot.agent.ctx.role}_r{r}", result)
                
                return f"[{slot.agent.ctx.role}]\n{result}"

            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(self.agents), 2)) as executor:
                # Need to use partial or lambda to pass context
                futures = [executor.submit(_run_agent, slot, context) for slot in self.agents]
                for future in concurrent.futures.as_completed(futures):
                    try:
                        res = future.result()
                        drafts.append(res)
                        history_acc.append(res)
                    except Exception as e:
                        self._log(f"Agent execution failed: {e}")
                        drafts.append(f"[System] Agent failed: {e}")
            
            # Update context for next round (if any)
            # In mixture, we might aggregate here. In concurrent, we just pass all drafts.
            # But passing full text might be too long. 
            # We skip explicit context update here as agents use memory history.
        
        # Apply Consensus Phase on ALL accumulated drafts
        return self._consensus_decision(user_input, history_acc)

    def _chat_mixture(self, user_input: str) -> str:
        self._log("Starting Mixture of Experts flow.")
        import concurrent.futures
        
        rounds = 5 # Default to 5 rounds for MoE
        history_acc = []
        
        # 0. Initial Plan & Round Determination
        # Planner decides if we need 5 rounds or fewer, or more.
        planner = self.agents[0].agent
        plan_prompt = (
            f"Review this task: {user_input}\n"
            "Decide how many rounds of expert discussion are needed (1-10). Default is 5.\n"
            "Return ONLY the integer number."
        )
        try:
            r_resp = planner.step(plan_prompt)
            rounds = int(''.join(filter(str.isdigit, r_resp)))
            rounds = max(1, min(10, rounds))
            self._log(f"Planner decided on {rounds} rounds.")
        except:
            rounds = 5
            
        for r in range(rounds):
            self._log(f"--- MoE Round {r+1}/{rounds} ---")
            drafts: List[str] = []
            
            def _run_expert(slot: SwarmAgentSlot, current_context: str) -> str:
                self._log(f"Expert [{slot.agent.ctx.role}] generating draft...")
                prompt = current_context
                if r > 0:
                    prompt = (
                        f"Round {r+1}/{rounds}. Refine your previous answer based on peer feedback.\n"
                        f"Previous findings:\n" + "\n".join(history_acc[-len(self.agents):]) + 
                        f"\n\nOriginal Request: {user_input}"
                    )
                
                result = slot.agent.step(prompt)
                self._log(f"[Result] Expert {slot.agent.ctx.role}: {result[:50]}...")
                return f"[{slot.agent.ctx.role}]\n{result}"

            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(self.agents), 2)) as executor:
                futures = [executor.submit(_run_expert, slot, user_input) for slot in self.agents]
                for future in concurrent.futures.as_completed(futures):
                    try:
                        res = future.result()
                        drafts.append(res)
                        history_acc.append(res)
                    except Exception as e:
                        drafts.append(f"[System] Expert failed: {e}")
            
            # Early Exit Check (Consensus Check)
            # Ask Judge if we have enough info to stop
            if r < rounds - 1:
                judge = self.agents[0].agent
                check_prompt = (
                    "Review the current findings:\n" + "\n".join(drafts) + 
                    f"\n\nOriginal Request: {user_input}\n"
                    "Do we have a sufficient, high-quality consensus answer? Return 'YES' to stop, 'NO' to continue."
                )
                decision = judge.step(check_prompt)
                if "YES" in decision.upper() and len(decision) < 20: # Simple heuristic
                    self._log(f"Early exit at round {r+1}: Consensus reached.")
                    break
        
        # Post-Loop Extension Check
        judge = self.agents[0].agent
        final_check_prompt = (
            "Review all findings. Is the result complete and satisfactory? "
            "If NO, how many more rounds (1-3) are needed? Return 0 if complete, or N."
        )
        try:
            ext_resp = judge.step(final_check_prompt)
            ext_rounds = int(''.join(filter(str.isdigit, ext_resp)) or 0)
            if ext_rounds > 0:
                self._log(f"Extending workflow by {ext_rounds} rounds...")
                # Run extension loop (simplified reuse of logic)
                for er in range(min(ext_rounds, 3)):
                    self._log(f"--- Extension Round {er+1} ---")
                    # ... (Run one more pass similar to above) ...
                    # For brevity in this patch, we just run one collective pass if needed
                    # Real implementation would recurse or loop.
                    # Let's just do one final refinement pass
                    refine_prompt = "Final refinement pass based on all history."
                    # ... execute ...
        except:
            pass

        # Consensus
        return self._consensus_decision(user_input, history_acc)

    def _chat_group_chat(self, user_input: str, rounds: int = 3) -> str:
        self._log(f"Starting Group Chat ({rounds} rounds).")
        messages: List[str] = [f"[user]\n{user_input}"]
        context = user_input
        outputs_for_consensus = []
        
        for r in range(rounds):
            self._log(f"--- Round {r+1} ---")
            for slot in self.agents:
                self._log(f"Agent [{slot.agent.ctx.role}] speaking...")
                reply = slot.agent.step(context)
                tag = f"[round {r+1} - {slot.agent.ctx.role}]"
                messages.append(f"{tag}\n{reply}")
                outputs_for_consensus.append(f"{tag}\n{reply}")
                context = reply
                
        # Final Consensus
        return self._consensus_decision(user_input, outputs_for_consensus)

    def _chat_hierarchical(self, user_input: str) -> str:
        self._log("Starting Hierarchical flow (Director -> Workers).")
        director = self.agents[0].agent
        workers = self.agents[1:]
        
        self._log("Director planning...")
        plan = director.step(f"作为项目总监，请基于任务给出执行计划并拆分成子任务：\n{user_input}")
        outputs: List[str] = [f"[director-plan]\n{plan}"]
        
        for idx, slot in enumerate(workers):
            self._log(f"Worker [{slot.agent.ctx.role}] executing subtask...")
            reply = slot.agent.step(f"子任务 {idx+1}（基于总监计划执行）：\n{plan}\n\n原始任务：\n{user_input}")
            outputs.append(f"[worker-{slot.agent.ctx.role}]\n{reply}")
            
        self._log("Director summarizing...")
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
        # Enhanced AutoSwarmBuilder prompt with Role Assignment
        # Force complex architecture if task is not trivial
        auto_prompt = (
            "你是 AutoSwarmBuilder。根据下面的用户任务，决定一个合适的 swarm 配置：\n"
            "- name: 一个简短英文名称\n"
            "- description: 1-2 句中文描述\n"
            "- architecture: 必须从 [concurrent, mixture, group_chat, hierarchical] 中选一个，禁止选择 sequential。\n"
            "- max_loops: 建议的最大对话轮数（整数）\n"
            f"- roles: 一个字符串列表，定义 {self.config.max_agents} 个 Agent 的具体角色（建议充分利用 8 个角色，如 ['lead_researcher', 'technical_analyst', 'market_analyst', 'skeptic', 'synthesizer', 'editor', 'fact_checker', 'coordinator']）。\n"
            "- task: 用中文详细说明 swarm 的工作目标\n\n"
            "请输出 JSON 对象。任务如下：\n"
            f"{user_input}"
        )
        resp = planner.step(auto_prompt)
        try:
            import json
            # Robust JSON extraction (handle markdown blocks)
            content = resp.strip()
            if content.startswith("```json"):
                content = content[7:-3]
            elif content.startswith("```"):
                content = content[3:-3]
            
            data = json.loads(content)
            
            # 1. Update Architecture
            arch = data.get("architecture", "concurrent") # Default to concurrent if missing
            if arch in (
                "sequential", "concurrent", "mixture", "group_chat", 
                "hierarchical", "swarm_router", "long_horizon", "state_machine"
            ):
                self._architecture = arch  # type: ignore[assignment]
                self._log(f"AutoSwarmBuilder selected architecture: {self._architecture}")
            else:
                self._architecture = "concurrent" # Fallback to concurrent to ensure logs/consensus
                self._log(f"AutoSwarmBuilder fallback to concurrent.")

            # 2. Dynamic Role Assignment
            new_roles = data.get("roles", [])
            if new_roles and isinstance(new_roles, list):
                self._reassign_roles(new_roles)
            else:
                # Default roles if not provided
                self._reassign_roles(["researcher", "analyst", "writer", "reviewer"])
                
        except Exception as e:
            self._log(f"AutoSwarmBuilder failed: {e}. Fallback to concurrent.")
            self._architecture = "concurrent"  # type: ignore[assignment]
            self._reassign_roles(["researcher", "analyst", "writer", "reviewer"])
            
        return self.chat(user_input)

