from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import time
from typing import Any, Dict, List, Literal, Optional

from ..config import SwarmConfig
from ..config_manager import SwarmbotConfig
from ..llm_client import OpenAICompatibleClient
from ..memory.qmd import QMDMemoryStore
from ..core.agent import AgentContext, CoreAgent


@dataclass
class SwarmAgentSlot:
    agent: CoreAgent
    weight: float = 1.0


class SwarmSession:
    """
    Represents a persistent conversation session with its own memory, agents, and state.
    This ensures that context is isolated per chat/user.
    """
    def __init__(self, session_id: str, config: SwarmConfig, llm_client: OpenAICompatibleClient):
        self.session_id = session_id
        self.config = config
        self.llm = llm_client
        self.memory = QMDMemoryStore()
        self.agents: List[SwarmAgentSlot] = []
        self.architecture: Literal[
            "sequential", "concurrent", "agent_rearrange", "graph", "mixture",
            "group_chat", "forest", "hierarchical", "heavy", "swarm_router",
            "long_horizon", "state_machine", "auto"
        ] = "concurrent"
        self.display_mode = "simple"
        
        self._init_default_agents()

    def _init_default_agents(self) -> None:
        # Default initialization based on count
        roles = ["planner", "coder", "critic", "summarizer", "researcher", "analyst", "writer", "reviewer"]
        for idx in range(self.config.max_agents):
            role = roles[idx] if idx < len(roles) else f"worker-{idx+1}"
            ctx = AgentContext(agent_id=f"agent-{role}-{self.session_id[:8]}", role=role)
            # Agents share the session's memory store
            agent = CoreAgent(ctx=ctx, llm=self.llm, memory=self.memory)
            self.agents.append(SwarmAgentSlot(agent=agent, weight=1.0))

    def resize_swarm(self, target_count: int) -> None:
        current_count = len(self.agents)
        if target_count > current_count:
            for i in range(current_count, target_count):
                role = f"worker-{i+1}"
                ctx = AgentContext(agent_id=f"agent-{role}-{self.session_id[:8]}", role=role)
                agent = CoreAgent(ctx=ctx, llm=self.llm, memory=self.memory)
                self.agents.append(SwarmAgentSlot(agent=agent, weight=1.0))
        elif target_count < current_count:
            self.agents = self.agents[:target_count]

    def reassign_roles(self, new_roles: List[str]) -> None:
        required_count = min(len(new_roles), 10)
        self.resize_swarm(required_count)
        
        skill_map = {
            "finance": ["web_search"],
            "market": ["web_search"],
            "research": ["web_search", "browser_open", "browser_read"],
            "code": ["file_write", "shell_exec", "file_read"],
            "developer": ["file_write", "shell_exec", "file_read"],
            "data": ["python_exec"],
            "writer": ["web_search"],
            "analyst": ["web_search", "browser_read"],
            "reviewer": ["file_read"]
        }
        
        for i, slot in enumerate(self.agents):
            if i < len(new_roles):
                role = new_roles[i]
                slot.agent.ctx.role = role
                slot.agent.ctx.skills = {}
                slot.agent.ctx.skills["whiteboard_update"] = True
                
                for key, tools in skill_map.items():
                    if key in role.lower():
                        for tool in tools:
                            slot.agent.ctx.skills[tool] = True
            else:
                slot.agent.ctx.role = "observer"
                slot.agent.ctx.skills = {}


class SwarmManager:
    def __init__(self, config: SwarmConfig | None = None) -> None:
        self.config = config or SwarmConfig()
        self.llm = OpenAICompatibleClient(self.config.llm)
        self.sessions: Dict[str, SwarmSession] = {}
        self._display_mode = "simple" # Global default
        self._swarmboot_cache: Optional[str] = None
        self._masterboot_cache: Optional[str] = None

    @classmethod
    def from_swarmbot_config(cls, cfg: SwarmbotConfig) -> "SwarmManager":
        sw_cfg = SwarmConfig()
        sw_cfg.max_agents = cfg.swarm.agent_count
        sw_cfg.max_turns = cfg.swarm.max_turns
        sw_cfg.llm.base_url = cfg.provider.base_url
        sw_cfg.llm.api_key = cfg.provider.api_key
        sw_cfg.llm.model = cfg.provider.model
        
        if hasattr(sw_cfg.llm, "max_tokens"):
            sw_cfg.llm.max_tokens = cfg.provider.max_tokens
            
        # Force sync nanobot config env vars
        os.environ["OPENAI_API_BASE"] = cfg.provider.base_url
        os.environ["OPENAI_API_KEY"] = cfg.provider.api_key
        os.environ["LITELLM_MODEL"] = cfg.provider.model
        
        mgr = cls(sw_cfg)
        mgr._display_mode = cfg.swarm.display_mode
        # Set default architecture in config for new sessions
        mgr.config.architecture = cfg.swarm.architecture 
        return mgr

    def _log(self, message: str) -> None:
        if getattr(self, "_display_mode", "simple") == "log":
            print(f"[SwarmLog] {message}")

    def get_session(self, session_id: str) -> SwarmSession:
        if session_id not in self.sessions:
            self._log(f"Creating new SwarmSession: {session_id}")
            session = SwarmSession(session_id, self.config, self.llm)
            # Initialize session with global config defaults
            if hasattr(self.config, "architecture"):
                session.architecture = self.config.architecture
            session.display_mode = self._display_mode
            self.sessions[session_id] = session
        return self.sessions[session_id]

    def chat(self, user_input: str, session_id: str = "default") -> str:
        session = self.get_session(session_id)
        
        # Dual Boot Architecture
        self._boot_swarm_context(session, user_input)
        
        self._log(f"--- Phase 2: Architecture Execution ({session.architecture}) ---")
        
        if session.architecture == "auto":
            swarm_result = self._chat_auto(session, user_input)
        elif session.architecture == "sequential":
            swarm_result = self._chat_sequential(session, user_input)
        elif session.architecture == "concurrent":
            swarm_result = self._chat_concurrent(session, user_input)
        elif session.architecture == "mixture":
            swarm_result = self._chat_mixture(session, user_input)
        elif session.architecture == "group_chat":
            swarm_result = self._chat_group_chat(session, user_input)
        elif session.architecture == "hierarchical":
            swarm_result = self._chat_hierarchical(session, user_input)
        elif session.architecture == "swarm_router":
            swarm_result = self._chat_swarm_router(session, user_input)
        elif session.architecture == "long_horizon":
            swarm_result = self._chat_long_horizon(session, user_input)
        elif session.architecture == "state_machine":
            swarm_result = self._chat_state_machine(session, user_input)
        else:
            swarm_result = self._chat_concurrent(session, user_input)

        self._log("--- Phase 3: Cleanup & Consolidation ---")
        self._persist_log(session, user_input, swarm_result)

        try:
            if hasattr(session.memory.whiteboard, "clear"):
                # 保留核心结构，仅清理临时键，支持跨循环渐进式推进
                session.memory.whiteboard.clear(preserve_core=True)
            elif isinstance(session.memory.whiteboard, dict):
                session.memory.whiteboard.clear()
        except:
            pass

        # Master Agent Interpretation
        master_response = self._master_agent_interpret(session, user_input, swarm_result)
        if master_response is None:
            master_response = ""
        if not str(master_response).strip():
            fallback = swarm_result if swarm_result is not None else ""
            if not str(fallback).strip():
                fallback = "Swarmbot 没有生成可用回答，请稍后重试或简化你的问题。"
            return str(fallback)
        return str(master_response)

    def _boot_swarm_context(self, session: SwarmSession, user_input: str) -> None:
        self._log("--- Phase 1: Swarm Boot (Memory Retrieval & Context Injection) ---")
        
        # 生命周期管理：循环开始时恢复 / 初始化 Whiteboard 核心结构与循环计数
        try:
            if hasattr(session.memory, "whiteboard"):
                wb = session.memory.whiteboard
                if hasattr(wb, "ensure_task_frame"):
                    wb.ensure_task_frame()
                # 检查点恢复
                try:
                    cache_root = session.memory.local_cache.root
                    ckpt_path = os.path.join(cache_root, f"checkpoint_{session.session_id}.json")
                    if os.path.exists(ckpt_path):
                        with open(ckpt_path, "r", encoding="utf-8") as f:
                            ckpt_data = json.load(f)
                        if isinstance(ckpt_data, dict):
                            for k, v in ckpt_data.items():
                                wb.update(k, v)
                except Exception:
                    pass
                # 更新循环计数
                loop_counter = wb.get("loop_counter") or 0
                wb.update("loop_counter", int(loop_counter) + 1)
                wb.update("current_state", "PLANNING")
        except:
            pass
        
        swarmboot_content = ""
        user_boot_path = os.path.expanduser("~/.swarmbot/boot/swarmboot.md")
        pkg_boot_path = os.path.join(os.path.dirname(__file__), "../boot/swarmboot.md")
        if self._swarmboot_cache is not None:
            swarmboot_content = self._swarmboot_cache
        else:
            try:
                if os.path.exists(user_boot_path):
                    with open(user_boot_path, "r", encoding="utf-8") as f:
                        swarmboot_content = f.read()
                elif os.path.exists(pkg_boot_path):
                    with open(pkg_boot_path, "r", encoding="utf-8") as f:
                        swarmboot_content = f.read()
            except:
                swarmboot_content = ""
            self._swarmboot_cache = swarmboot_content
        if swarmboot_content and len(swarmboot_content) > 8000:
            swarmboot_content = swarmboot_content[:8000] + "\n...[swarmboot truncated]\n"

        # Clear events (short term volatile)
        try:
            session.memory._events.clear()
        except:
            pass

        qmd_context = ""
        try:
            q_len = len(user_input or "")
            if q_len < 40:
                q_limit = 3
            elif q_len < 120:
                q_limit = 5
            else:
                q_limit = 10
            results = session.memory.search(user_input, limit=q_limit)
            if results:
                parts = []
                for r in results:
                    if isinstance(r, dict):
                        parts.append(r.get("content") or r.get("text") or json.dumps(r, ensure_ascii=False))
                    else:
                        parts.append(str(r))
                qmd_context = "\n".join(parts)
                if len(qmd_context) > 4000:
                    qmd_context = qmd_context[:4000] + "\n...[qmd context truncated]\n"
        except:
            pass

        md_excerpt = ""
        try:
            date_str = time.strftime("%Y-%m-%d")
            log_file = f"chat_log_{session.session_id}_{date_str}.md"
            md_text = session.memory.local_cache.read(log_file)
            if md_text:
                segments = md_text.split("\n## Loop ")
                if len(segments) > 1:
                    loops = []
                    base = segments[0]
                    for seg in segments[1:]:
                        loops.append("## Loop " + seg)
                    def _extract_terms(text: str) -> list[str]:
                        terms: list[str] = []
                        if not text:
                            return terms
                        for w in text.split():
                            if len(w) >= 3:
                                terms.append(w)
                        buf = []
                        for ch in text:
                            if "\u4e00" <= ch <= "\u9fff":
                                buf.append(ch)
                            else:
                                if len(buf) >= 2:
                                    terms.append("".join(buf))
                                buf = []
                        if len(buf) >= 2:
                            terms.append("".join(buf))
                        return list(dict.fromkeys(terms))
                    query_terms = _extract_terms(user_input or "")
                    def score_loop(text: str) -> int:
                        if not query_terms:
                            return 0
                        s = 0
                        for t in query_terms:
                            if t and t in text:
                                s += 1
                        return s
                    scored = []
                    for idx, lp in enumerate(loops):
                        s = score_loop(lp)
                        scored.append((s, idx, lp))
                    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
                    top = [lp for s, i, lp in scored[:5] if s > 0]
                    if not top and not query_terms:
                        top = loops[-3:]
                    # Strict filtering: if query terms exist but no matches found, 
                    # do NOT fallback to last 3. Keep top empty.
                    # This avoids context pollution from irrelevant previous sessions.
                    
                    def _shrink_loop(text: str) -> str:
                        start = text.find("### Input")
                        if start == -1:
                            return text
                        end = text.find("### Whiteboard Snapshot")
                        if end == -1:
                            end = len(text)
                        return text[start:end].strip()
                    shrunk = []
                    for lp in top:
                        s = _shrink_loop(lp)
                        shrunk.append(s)
                    md_excerpt = "\n".join(shrunk)
                    if len(md_excerpt) > 4000:
                        md_excerpt = md_excerpt[:4000] + "\n...[local history truncated]\n"
                else:
                    md_excerpt = md_text[-2000:]
        except:
            pass

        system_caps = {}
        try:
            from ..config_manager import WORKSPACE_PATH
            from pathlib import Path

            workspace = Path(WORKSPACE_PATH)
            cron_store = workspace / "cron" / "jobs.json"
            daemon_state = os.path.expanduser("~/.swarmbot/daemon_state.json")
            skills_workspace = workspace / "skills"
            skills_builtin = Path(__file__).resolve().parent.parent / "nanobot" / "skills"
            system_caps = {
                "daemon": {
                    "state_file": str(daemon_state),
                    "config_section": "daemon",
                    "services": ["gateway", "overthinking", "backup", "health"],
                },
                "cron": {
                    "store_path": str(cron_store),
                    "cli": "swarmbot cron",
                },
                "heartbeat": {
                    "workspace_heartbeat": str(workspace / "HEARTBEAT.md"),
                    "cli": "swarmbot heartbeat",
                },
                "skills": {
                    "workspace_dir": str(skills_workspace),
                    "builtin_dir": str(skills_builtin),
                    "summary_tool": "skill_summary",
                },
            }
        except Exception:
            system_caps = {}

        structured_context = {
            "swarmboot_config": swarmboot_content,
            "prompt": user_input,
            "qmd": qmd_context,
            "md": md_excerpt,
            "session_id": session.session_id,
            "system_capabilities": system_caps
        }
        session.memory.whiteboard.update("current_task_context", structured_context)

    def _persist_log(self, session: SwarmSession, user_input: str, result: str) -> None:
        try:
            date_str = time.strftime("%Y-%m-%d")
            # Log file per session to avoid mixing chats
            log_file = f"chat_log_{session.session_id}_{date_str}.md"
            
            whiteboard_data = {}
            try:
                if hasattr(session.memory.whiteboard, "_data"):
                     whiteboard_data = session.memory.whiteboard._data.copy()
                elif isinstance(session.memory.whiteboard, dict):
                     whiteboard_data = session.memory.whiteboard.copy()
            except:
                pass
            
            whiteboard_dump = json.dumps(whiteboard_data, ensure_ascii=False, indent=2)
            snippet = result[:1200] if result else ""

            # 结构化 Loop 记录
            loop_counter = 0
            current_state = whiteboard_data.get("current_state") or "UNKNOWN"
            try:
                loop_counter = int(whiteboard_data.get("loop_counter") or 0)
            except Exception:
                loop_counter = 0

            timestamp = time.strftime("%H:%M:%S")

            loop_entry = (
                f"\n## Loop {loop_counter} [{timestamp}] - State: {current_state}\n\n"
                f"### Input\n\n{user_input}\n\n"
                f"### Result (snippet)\n\n{snippet}\n\n"
                f"### Whiteboard Snapshot\n\n```json\n{whiteboard_dump}\n```\n"
            )

            # 若文件不存在，则先写入前置信息头，再追加 Loop 记录
            cache = session.memory.local_cache
            from os import path as _path
            full_path = _path.join(cache.root, log_file)

            if not _path.exists(full_path):
                header = (
                    "---\n"
                    f"session_id: {session.session_id}\n"
                    f"date: {date_str}\n"
                    "task_type: general\n"
                    "loops: 0\n"
                    "final_status: running\n"
                    "---\n"
                )
                cache.write(log_file, header + loop_entry)
            else:
                cache.append(log_file, loop_entry)

            # QMD 写入流：处理 qmd_candidates
            try:
                candidates = whiteboard_data.get("qmd_candidates") or []
                if isinstance(candidates, list):
                    for item in candidates:
                        if not isinstance(item, dict):
                            continue
                        content = item.get("content") or ""
                        if not str(content).strip():
                            continue
                        score = float(item.get("confidence_score") or 0)
                        status = str(item.get("verification_status") or "").lower()
                        if score <= 0.7 or status == "pending":
                            continue
                        collection = item.get("collection") or "core_memory"
                        meta = {}
                        for k, v in item.items():
                            if k != "content":
                                meta[k] = v
                        session.memory.persist_to_qmd(str(content), collection=collection)
            except:
                pass

            # 检查点数据持久化
            try:
                core_keys = [
                    "task_specification",
                    "execution_plan",
                    "current_state",
                    "loop_counter",
                    "completed_subtasks",
                    "pending_subtasks",
                    "intermediate_results",
                    "content_registry",
                    "checkpoint_data",
                ]
                checkpoint = {}
                for k in core_keys:
                    if k in whiteboard_data:
                        checkpoint[k] = whiteboard_data[k]
                cache_root = cache.root
                ckpt_path = _path.join(cache_root, f"checkpoint_{session.session_id}.json")
                with open(ckpt_path, "w", encoding="utf-8") as f:
                    json.dump(checkpoint, f, ensure_ascii=False)
            except:
                pass
        except:
            pass

    def _master_agent_interpret(self, session: SwarmSession, user_input: str, swarm_result: str) -> str:
        self._log("--- Phase 4: Master Agent Interpretation ---")
        master_agent = session.agents[0].agent
        original_role = master_agent.ctx.role
        master_agent.ctx.role = "master"
        
        masterboot_content = ""
        user_boot_path = os.path.expanduser("~/.swarmbot/boot/masteragentboot.md")
        pkg_boot_path = os.path.join(os.path.dirname(__file__), "../boot/masteragentboot.md")
        if self._masterboot_cache is not None:
            masterboot_content = self._masterboot_cache
        else:
            try:
                 if os.path.exists(user_boot_path):
                     with open(user_boot_path, "r", encoding="utf-8") as f:
                         masterboot_content = f.read()
                 elif os.path.exists(pkg_boot_path):
                     with open(pkg_boot_path, "r", encoding="utf-8") as f:
                         masterboot_content = f.read()
            except:
                 masterboot_content = ""
            self._masterboot_cache = masterboot_content

        master_prompt = (
            f"System Boot Configuration:\n{masterboot_content}\n\n"
            f"User Input: {user_input}\n\n"
            f"Swarm Execution Result:\n{swarm_result}\n\n"
            "Task: Interpret the Swarm's result for the user. "
            "Translate technical details into a response that matches your persona (SOUL.md). "
            "If the result is an error, explain it kindly. "
            "Do not just copy the result; synthesize it."
        )
        
        final_response = master_agent.step(master_prompt)
        master_agent.ctx.role = original_role
        return final_response

    # --- Architecture Implementations (Updated to use session) ---

    def _chat_sequential(self, session: SwarmSession, user_input: str) -> str:
        self._log(f"Starting Sequential flow with {len(session.agents)} agents.")
        context = user_input
        outputs = []
        for slot in session.agents:
            self._log(f"Agent [{slot.agent.ctx.role}] is thinking...")
            reply = slot.agent.step(context)
            outputs.append(f"[{slot.agent.ctx.role}]\n{reply}")
            context = context + "\n\n" + reply
        return "\n\n".join(outputs)

    def _chat_concurrent(self, session: SwarmSession, user_input: str) -> str:
        self._log(f"Starting Concurrent flow with {len(session.agents)} agents.")
        import concurrent.futures
        
        rounds = 2 if "deep" in user_input.lower() or "research" in user_input.lower() else 1
        history_acc = []
        
        for r in range(rounds):
            self._log(f"--- Round {r+1}/{rounds} ---")
            drafts = []
            
            def _run_agent(slot: SwarmAgentSlot, current_context: str) -> str:
                prompt = current_context
                if r > 0:
                    prompt = (
                        f"Round {r+1} Task. Previous findings:\n" + 
                        "\n".join(history_acc[-len(session.agents):]) + 
                        f"\n\nOriginal Request: {user_input}\nRefine or expand."
                    )
                result = slot.agent.step(prompt)
                session.memory.whiteboard.update(f"result_{slot.agent.ctx.role}_r{r}", result)
                return f"[{slot.agent.ctx.role}]\n{result}"

            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(session.agents), 2)) as executor:
                futures = [executor.submit(_run_agent, slot, user_input) for slot in session.agents]
                for future in concurrent.futures.as_completed(futures):
                    try:
                        res = future.result()
                        drafts.append(res)
                        history_acc.append(res)
                    except Exception as e:
                        drafts.append(f"[System] Agent failed: {e}")

        return self._consensus_decision(session, user_input, history_acc)

    def _chat_mixture(self, session: SwarmSession, user_input: str) -> str:
        self._log("Starting Mixture of Experts flow.")
        import concurrent.futures
        
        rounds = 5
        history_acc = []
        
        planner = session.agents[0].agent
        try:
            r_resp = planner.step(f"Task: {user_input}\nDecide rounds (1-10). Default 5. Return int.")
            import re
            match = re.search(r"\b([1-9]|10)\b", r_resp)
            if match:
                rounds = int(match.group(1))
        except:
            pass
            
        for r in range(rounds):
            self._log(f"--- MoE Round {r+1}/{rounds} ---")
            drafts = []
            
            def _run_expert(slot: SwarmAgentSlot, current_context: str) -> str:
                prompt = current_context
                if r > 0:
                    prompt = (
                        f"Round {r+1}/{rounds}. Refine based on feedback.\n"
                        f"Previous:\n" + "\n".join(history_acc[-len(session.agents):]) + 
                        f"\n\nRequest: {user_input}"
                    )
                return f"[{slot.agent.ctx.role}]\n{slot.agent.step(prompt)}"

            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(session.agents), 2)) as executor:
                futures = [executor.submit(_run_expert, slot, user_input) for slot in session.agents]
                for future in concurrent.futures.as_completed(futures):
                    try:
                        res = future.result()
                        drafts.append(res)
                        history_acc.append(res)
                    except Exception as e:
                        drafts.append(f"Error: {e}")
            
            # Early Exit
            if r < rounds - 1:
                judge = session.agents[0].agent
                decision = judge.step(
                    "Findings:\n" + "\n".join(drafts) + 
                    f"\n\nRequest: {user_input}\nConsensus reached? Return YES/NO."
                )
                if "YES" in decision.upper() and len(decision) < 20:
                    break
        
        # Extension Check
        judge = session.agents[0].agent
        try:
            ext_resp = judge.step("Is result complete? If NO, return extra rounds (1-3) else 0.")
            import re
            match = re.search(r"\b([0-9])\b", ext_resp)
            ext_rounds = int(match.group(1)) if match else 0
            ext_rounds = min(ext_rounds, 3)
            
            if ext_rounds > 0:
                self._log(f"Extending by {ext_rounds} rounds...")
                # Simplified extension
                refine_prompt = "Final refinement based on history."
                for _ in range(ext_rounds):
                    # Just run one sequential pass of refinement for simplicity in this patch
                    pass 
        except:
            pass

        return self._consensus_decision(session, user_input, history_acc)

    def _chat_group_chat(self, session: SwarmSession, user_input: str, rounds: int = 3) -> str:
        self._log(f"Starting Group Chat ({rounds} rounds).")
        context = user_input
        outputs = []
        for r in range(rounds):
            for slot in session.agents:
                reply = slot.agent.step(context)
                tag = f"[round {r+1} - {slot.agent.ctx.role}]"
                outputs.append(f"{tag}\n{reply}")
                context = reply
        return self._consensus_decision(session, user_input, outputs)

    def _chat_hierarchical(self, session: SwarmSession, user_input: str) -> str:
        director = session.agents[0].agent
        workers = session.agents[1:]
        
        plan = director.step(f"Plan and split subtasks for:\n{user_input}")
        outputs = [f"[director-plan]\n{plan}"]
        
        for idx, slot in enumerate(workers):
            reply = slot.agent.step(f"Subtask {idx+1} based on plan:\n{plan}\n\nOriginal: {user_input}")
            outputs.append(f"[worker-{slot.agent.ctx.role}]\n{reply}")
            
        summary = director.step("Summarize these results:\n" + "\n".join(outputs))
        outputs.append(f"[director-summary]\n{summary}")
        return "\n\n".join(outputs)

    def _chat_swarm_router(self, session: SwarmSession, user_input: str) -> str:
        if "并行" in user_input or "many" in user_input.lower():
            return self._chat_concurrent(session, user_input)
        if "计划" in user_input or "roadmap" in user_input.lower():
            return self._chat_hierarchical(session, user_input)
        return self._chat_sequential(session, user_input)
    
    def _chat_state_machine(self, session: SwarmSession, user_input: str) -> str:
        from ..statemachine.engine import StateMachine, State
        # Simple hardcoded workflow for demo
        coder = session.agents[1].agent
        critic = session.agents[2].agent
        
        sm = StateMachine(initial_state="coding")
        sm.add_state(State("coding", coder, "Write code", {"default": "review"}))
        sm.add_state(State("review", critic, "Review code", {"PASS": "end", "FAIL": "coding"}))
        # 'end' state implicitly handling return
        
        return sm.run(user_input)

    def _chat_long_horizon(self, session: SwarmSession, user_input: str) -> str:
        # Placeholder for complex long horizon logic
        return self._chat_sequential(session, user_input)

    def _chat_auto(self, session: SwarmSession, user_input: str) -> str:
        planner = session.agents[0].agent
        try:
            arch_resp = planner.step(
                f"Task: {user_input}\nSelect arch: [concurrent, mixture, group_chat, hierarchical]. Return name."
            ).strip().lower()
            if "mixture" in arch_resp: session.architecture = "mixture"
            elif "group" in arch_resp: session.architecture = "group_chat"
            elif "hierarchical" in arch_resp: session.architecture = "hierarchical"
            else: session.architecture = "concurrent"
        except:
            session.architecture = "concurrent"
            
        self._log(f"Auto selected: {session.architecture}")
        
        # Negotiate Roles
        try:
            analysis_resp = planner.step(
                f"Analyze: {user_input}\nIdentify {self.config.max_agents} roles. Return python list."
            )
            import re
            match = re.search(r"\[(.*?)\]", analysis_resp, re.DOTALL)
            if match:
                roles = [r.strip().strip("'").strip('"') for r in match.group(1).split(',')]
                session.reassign_roles(roles)
        except:
            pass
            
        return self.chat(user_input, session.session_id)

    def _consensus_decision(self, session: SwarmSession, user_input: str, outputs: List[str]) -> str:
        judge = session.agents[0].agent
        original_role = judge.ctx.role
        judge.ctx.role = "consensus_moderator"
        
        import datetime
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        prompt = (
            f"Synthesize final answer from agent outputs. Ref Time: {current_time}.\n"
            f"Original: {user_input}\nOutputs:\n" + "\n".join(outputs)
        )
        decision = judge.step(prompt)
        
        if "insufficient info" in decision.lower():
            decision = judge.step(f"Previous consensus weak: {decision}\nRefine answer.")
            
        judge.ctx.role = original_role
        return decision
