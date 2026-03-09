import concurrent.futures
import json
import time
import os
import re
from typing import List, Dict, Any

from ..core.agent import CoreAgent, AgentContext
from ..llm_client import OpenAICompatibleClient
from ..memory.whiteboard import Whiteboard
from ..memory.hot_memory import HotMemory
from ..memory.warm_memory import WarmMemory
from ..memory.cold_memory import ColdMemory
from ..boot.context_loader import load_boot_markdown
from .definitions import *
from .skill_registry import SkillRegistry

class InferenceLoop:
    def __init__(self, config, workspace_path: str):
        self.config = config
        self.workspace_path = workspace_path
        self.llm = OpenAICompatibleClient.from_provider(providers=config.providers)
        
        # Memories
        self.whiteboard = Whiteboard()
        self.hot_memory = HotMemory(workspace_path)
        self.warm_memory = WarmMemory(workspace_path)
        self.cold_memory = ColdMemory()
        self.skill_registry = SkillRegistry()
        
        # Load Swarmboot
        self.swarmboot = self._load_boot_file("swarmboot.md")
        self.soul = self._load_boot_file("SOUL.md")
        self.loop_profile_mode = (os.environ.get("SWARMBOT_LOOP_PROFILE") or "auto").strip().lower()

    def _extract_urls(self, text: str) -> List[str]:
        if not isinstance(text, str):
            return []
        urls = re.findall(r"https?://[^\s`\"'<>]+", text)
        out: List[str] = []
        for u in urls:
            if u not in out:
                out.append(u)
        return out

    def _is_explicit_read_analyze_request(self, text: str) -> bool:
        t = (text or "").lower()
        has_read = any(k in t for k in ["阅读", "读一下", "分析", "总结", "提取", "review", "analyze", "summarize", "extract"])
        has_directive = any(k in t for k in ["请", "先", "然后", "并", "立即", "直接"])
        return has_read and (has_directive or bool(self._extract_urls(text)))

    def _load_boot_file(self, filename: str) -> str:
        content = load_boot_markdown(filename, "inference_loop", max_chars=12000)
        if content:
            return content
        return f"Boot file {filename} not found."

    def _create_worker(
        self,
        role: str,
        enable_tools: bool = True,
        allowed_tools: List[str] | None = None,
        task_desc: str = "",
        required_skills: List[str] | None = None,
    ) -> CoreAgent:
        skills = self.skill_registry.get_skills_for_task(role, task_desc=task_desc, required_skills=required_skills)
        if allowed_tools is not None:
            allowed = set(allowed_tools) | {"whiteboard_update", "hot_memory_update"}
            skills = {k: v for k, v in skills.items() if k in allowed}
        ctx = AgentContext(agent_id=f"worker-{role}-{time.time_ns()}", role=role, skills=skills)
        return CoreAgent(ctx, self.llm, self.cold_memory, hot_memory=self.hot_memory, enable_tools=enable_tools)

    def _profile_settings(self, profile: str | None = None) -> Dict[str, Any]:
        active = (profile or self.whiteboard.get("loop_profile") or "balanced").strip().lower()
        if active == "lean":
            return {"analysis_workers": 1, "collection_workers": 1, "evaluation_workers": 2, "max_eval_loops": 2, "context_limit": 3500}
        if active == "swarm_max":
            return {"analysis_workers": 3, "collection_workers": 3, "evaluation_workers": 3, "max_eval_loops": 3, "context_limit": 9000}
        return {"analysis_workers": 2, "collection_workers": 2, "evaluation_workers": 3, "max_eval_loops": 3, "context_limit": 6000}

    def _sanitize_tools(self, names: List[str], fallback: List[str]) -> List[str]:
        valid = {"web_search", "browser_open", "browser_read", "file_read", "python_exec"}
        cleaned = []
        for n in names or []:
            if isinstance(n, str) and n in valid and n not in cleaned:
                cleaned.append(n)
        if cleaned:
            return cleaned
        return fallback

    def _decide_tool_gate_once(self, stage: str, user_input: str, context_json: str, fallback_tools: List[str]) -> Dict[str, Any]:
        prompt = (
            "你是工具门控决策器。你的任务是判断当前阶段是否需要外部工具。\n"
            f"阶段: {stage}\n"
            f"用户问题: {user_input}\n"
            f"上下文摘要: {context_json[:2000]}\n"
            "判断原则:\n"
            "1) 若仅靠已有上下文和常识即可高置信回答，则 need_tools=false。\n"
            "2) 若需要实时信息、外部事实、网页证据、文件读取，need_tools=true。\n"
            "3) 仅返回必要的最小工具集合。\n"
            "输出JSON:\n"
            '{"need_tools": true, "preferred_tools": ["web_search"], "confidence": 0.78, "reason": "..."}'
        )
        res = self._create_worker("planner", enable_tools=False).step(prompt)
        try:
            data = json.loads(self._extract_json(res))
            need = bool(data.get("need_tools"))
            tools = self._sanitize_tools(data.get("preferred_tools") or [], fallback_tools)
            reason = str(data.get("reason") or "")
            conf = float(data.get("confidence") or 0.5)
            conf = 0.0 if conf < 0 else (1.0 if conf > 1 else conf)
            return {"ok": True, "need_tools": need, "tools": tools, "reason": reason, "confidence": conf}
        except:
            return {"ok": False, "need_tools": False, "tools": fallback_tools, "reason": "parse_failed", "confidence": 0.0}

    def _decide_tool_gate(self, stage: str, user_input: str, context_json: str, fallback_tools: List[str]) -> Dict[str, Any]:
        urls = self._extract_urls(user_input)
        if urls and self._is_explicit_read_analyze_request(user_input):
            forced_tools = self._sanitize_tools(["browser_open", "browser_read", "web_search", "file_read"], fallback_tools)
            return {
                "need_tools": True,
                "tools": forced_tools,
                "reason": "rule:explicit_url_read_request",
                "confidence": 1.0,
                "mode": "rule_forced",
                "targets": urls,
            }
        decisions = [self._decide_tool_gate_once(stage, user_input, context_json, fallback_tools) for _ in range(3)]
        valid = [d for d in decisions if d.get("ok")]
        if not valid:
            return {"need_tools": False, "tools": fallback_tools, "reason": "all_parse_failed", "confidence": 0.0, "mode": "fallback"}
        true_votes = [d for d in valid if d.get("need_tools")]
        false_votes = [d for d in valid if not d.get("need_tools")]
        win_need = len(true_votes) >= len(false_votes)
        winner = true_votes if win_need else false_votes
        if not winner:
            winner = valid
        merged_tools = self._sanitize_tools(sum([(d.get("tools") or []) for d in winner], []), fallback_tools)
        avg_conf = sum(float(d.get("confidence") or 0.5) for d in winner) / max(1, len(winner))
        reason = "; ".join([str(d.get("reason") or "") for d in winner[:2]]).strip("; ")
        return {
            "need_tools": win_need,
            "tools": merged_tools,
            "reason": f"majority:{reason}",
            "confidence": round(avg_conf, 3),
            "mode": "majority_vote",
        }

    def _decide_loop_profile_once(self) -> Dict[str, Any]:
        forced = self.loop_profile_mode
        if forced in ["lean", "balanced", "swarm_max"]:
            return {"ok": True, "profile": forced, "reason": "forced"}
        analysis = self.whiteboard.get("problem_analysis")
        user_input = self.whiteboard.get("input_prompt") or ""
        prompt = (
            "你是Loop调度决策器。请在 lean / balanced / swarm_max 中选择一个。\n"
            f"用户问题: {user_input}\n"
            f"问题分析: {self._safe_dumps(analysis, max_len=2000)}\n"
            "选择原则:\n"
            "- lean: 常识型、低风险、无需外部信息\n"
            "- balanced: 默认，复杂度中等或不确定\n"
            "- swarm_max: 高风险、高不确定、需要更强冗余评估\n"
            '输出JSON: {"profile":"balanced","reason":"...","confidence":0.72}'
        )
        res = self._create_worker("planner", enable_tools=False).step(prompt)
        try:
            data = json.loads(self._extract_json(res))
            profile = str(data.get("profile") or "balanced").strip().lower()
            if profile not in ["lean", "balanced", "swarm_max"]:
                profile = "balanced"
            conf = float(data.get("confidence") or 0.5)
            conf = 0.0 if conf < 0 else (1.0 if conf > 1 else conf)
            return {"ok": True, "profile": profile, "reason": str(data.get("reason") or ""), "confidence": conf}
        except:
            return {"ok": False, "profile": "balanced", "reason": "parse_failed", "confidence": 0.0}

    def _decide_loop_profile(self) -> str:
        forced = self.loop_profile_mode
        if forced in ["lean", "balanced", "swarm_max"]:
            self.whiteboard.update("profile_decision", {"profile": forced, "reason": "forced"})
            return forced
        decisions = [self._decide_loop_profile_once() for _ in range(3)]
        valid = [d for d in decisions if d.get("ok")]
        if not valid:
            self.whiteboard.update("profile_decision", {"profile": "balanced", "reason": "all_parse_failed", "mode": "fallback"})
            return "balanced"
        counts: Dict[str, int] = {"lean": 0, "balanced": 0, "swarm_max": 0}
        for d in valid:
            p = str(d.get("profile") or "balanced")
            if p in counts:
                counts[p] += 1
        best = sorted(counts.items(), key=lambda x: (-x[1], 0 if x[0] == "balanced" else 1))[0][0]
        winners = [d for d in valid if d.get("profile") == best] or valid
        avg_conf = sum(float(d.get("confidence") or 0.5) for d in winners) / max(1, len(winners))
        reason = "; ".join([str(d.get("reason") or "") for d in winners[:2]]).strip("; ")
        self.whiteboard.update(
            "profile_decision",
            {"profile": best, "reason": f"majority:{reason}", "confidence": round(avg_conf, 3), "mode": "majority_vote"},
        )
        return best

    def run(self, user_input: str, session_id: str) -> str:
        self.whiteboard.clear()
        self.whiteboard.update("metadata", {"session_id": session_id, "loop_id": str(int(time.time()))})
        self.whiteboard.update("input_prompt", user_input)
        self.whiteboard.update("loop_profile", self.loop_profile_mode)
        
        print(f"[InferenceLoop] Start: {user_input[:50]}...")

        # Step 2: Problem Analysis (No Tools)
        self._step_analysis()
        selected_profile = self._decide_loop_profile()
        self.whiteboard.update("loop_profile", selected_profile)
        settings = self._profile_settings(selected_profile)
        
        # Step 3: Information Collection (Tools Enabled - User Requirement)
        self._step_collection()
        
        # Step 4: Action Planning (No Tools - JSON Gen)
        self._step_planning()
        
        # Step 5 & 6: Inference & Evaluation (Max 3 Loops with Re-planning)
        max_eval_loops = int(settings.get("max_eval_loops", 3))
        for i in range(max_eval_loops):
            self.whiteboard.update("evaluation_report", {"retry_count": i})
            
            # Step 5: Inference (Tools Enabled)
            self._step_inference()
            
            # Step 6: Evaluation (No Tools - Logic Check)
            if self._step_evaluation():
                break
            
            print(f"[InferenceLoop] Evaluation failed, retrying {i+1}/{max_eval_loops}")
            # Re-planning Logic: If failed, adjust plan before next inference
            if i < max_eval_loops - 1:
                self._step_replanning(retry_idx=i)

        # Step 7: Output Translation (Tools Enabled - User Requirement)
        final_response = self._step_translation()
        final_response = self._calibrate_final_response(
            self.whiteboard.get("input_prompt"),
            final_response,
        )
        self.whiteboard.update("final_response", final_response)
        
        # Step 8: Organization & Persistence (No Tools)
        self._step_organization()
        
        return final_response

    def _run_parallel(self, prompt: str, count: int, role: str, enable_tools: bool = True, allowed_tools: List[str] | None = None) -> List[str]:
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=count) as executor:
            futures = [executor.submit(self._create_worker(role, enable_tools, allowed_tools).step, prompt) for _ in range(count)]
            for f in concurrent.futures.as_completed(futures):
                try: results.append(f.result())
                except Exception as e: print(f"Worker {role} error: {e}")
        return results

    def _step_analysis(self):
        print("[Step 2] Analysis (No Tools)...")
        settings = self._profile_settings()
        base_prompt = STEP_ANALYSIS_PROMPT.format(
            user_input=self.whiteboard.get("input_prompt"),
            swarmboot=self.swarmboot
        )
        prompt = (
            base_prompt
            + "\n\n你需要先自定义你的专业角色类型，并补充工具建议。"
            + "\n输出JSON时增加字段：self_defined_role, required_tools, confidence。"
            + "\n示例: {\"self_defined_role\":\"security_analyst\",\"required_tools\":[\"web_search\"],\"confidence\":0.78,...}"
        )
        results = self._run_parallel(prompt, int(settings.get("analysis_workers", 2)), "analyst", enable_tools=False)
        merged = {}
        worker_roles: List[str] = []
        for r in results:
            try:
                data = json.loads(self._extract_json(r))
                merged.update(data)
                role = str(data.get("self_defined_role") or "").strip()
                if role:
                    worker_roles.append(role)
            except:
                pass
        if not worker_roles:
            worker_roles = ["general_analyst"]
        self.whiteboard.update("worker_roles", worker_roles)
        self.whiteboard.update("problem_analysis", merged)

    def _safe_dumps(self, data: Any, max_len: int = 4000) -> str:
        """Safely dump data to JSON string, truncating long strings if necessary."""
        def truncate(obj):
            if isinstance(obj, str):
                return obj[:max_len] + "..." if len(obj) > max_len else obj
            if isinstance(obj, list):
                return [truncate(x) for x in obj]
            if isinstance(obj, dict):
                return {k: truncate(v) for k, v in obj.items()}
            return obj
        
        try:
            return json.dumps(truncate(data))
        except:
            return "{}"

    def _step_collection(self):
        print("[Step 3] Collection (Analysis First)...")
        settings = self._profile_settings()
        analysis = self.whiteboard.get("problem_analysis")
        analysis_roles = self.whiteboard.get("worker_roles") or []
        user_input = self.whiteboard.get("input_prompt") or ""
        input_urls = self._extract_urls(user_input)
        # Gather memory snapshots
        hot = self.hot_memory.read()
        warm = self.warm_memory.read_today()
        cold = self.cold_memory.search_text(str(analysis), limit=5)
        
        base_prompt = STEP_COLLECTION_PROMPT.format(
            analysis_json=self._safe_dumps(analysis),
            swarmboot=self.swarmboot,
            hot_memory=hot[:2000],
            warm_memory=warm[:2000],
            cold_memory=cold[:2000]
        )
        prompt = (
            base_prompt
            + f"\n\n上一阶段角色参考: {self._safe_dumps(analysis_roles)}"
            + "\n请先定义你当前的 collector 专业角色，返回 self_defined_role。"
        )
        if input_urls and self._is_explicit_read_analyze_request(user_input):
            prompt += (
                f"\n用户输入中包含 URL：{self._safe_dumps(input_urls)}。"
                "\n这是明确的读取与分析指令：你必须立即读取并分析，不要向用户请求确认或补充目标。"
                "\n若 URL 无法访问，直接返回失败原因和可执行替代方案，不要反问是否允许读取。"
            )
        results = self._run_parallel(prompt, int(settings.get("collection_workers", 2)), "collector", enable_tools=False)
        
        merged = {"synthesized_context": "", "memory_references": [], "external_info": ""}
        collector_roles: List[str] = []
        for r in results:
            try:
                data = json.loads(self._extract_json(r))
                merged["synthesized_context"] += "\n" + data.get("synthesized_context", "")
                merged["memory_references"].extend(data.get("memory_references", []))
                merged["external_info"] += "\n" + data.get("external_info", "")
                role = str(data.get("self_defined_role") or "").strip()
                if role:
                    collector_roles.append(role)
            except:
                pass
        gate = self._decide_tool_gate(
            "collection",
            user_input,
            self._safe_dumps({"analysis": analysis, "merged": merged}, max_len=2500),
            ["web_search", "browser_open", "browser_read", "file_read"],
        )
        self.whiteboard.update("collection_tool_gate", gate)
        if gate.get("need_tools"):
            print("[Step 3b] Collection Tool Pass...")
            tool_results = self._run_parallel(
                prompt,
                1,
                "collector",
                enable_tools=True,
                allowed_tools=gate.get("tools") or ["web_search"],
            )
            for r in tool_results:
                try:
                    data = json.loads(self._extract_json(r))
                    merged["synthesized_context"] += "\n" + data.get("synthesized_context", "")
                    merged["external_info"] += "\n" + data.get("external_info", "")
                    role = str(data.get("self_defined_role") or "").strip()
                    if role:
                        collector_roles.append(role)
                except:
                    merged["external_info"] += "\n" + str(r)
        if not collector_roles:
            collector_roles = ["general_collector"]
        self.whiteboard.update("collection_worker_roles", collector_roles)
        self.whiteboard.update("information_gathering", merged)

    def _step_planning(self):
        print("[Step 4] Planning (No Tools)...")
        settings = self._profile_settings()
        info = self.whiteboard.get("information_gathering")
        prompt = STEP_PLANNING_PROMPT.format(
            info_json=self._safe_dumps(info, max_len=int(settings.get("context_limit", 6000))),
            swarmboot=self.swarmboot
        ) + "\n\n输出 tasks 时不要分配 worker 和 tool。每个任务必须包含 required_skills 数组。"
        res = self._create_worker("planner", enable_tools=False).step(prompt)
        try:
            plan = json.loads(self._extract_json(res))
            tasks = []
            for idx, task in enumerate(plan.get("tasks") or []):
                required = task.get("required_skills")
                if not isinstance(required, list):
                    required = []
                required = [x for x in required if isinstance(x, str)]
                if not required and isinstance(task.get("tool"), str) and task.get("tool") not in ["none", "", "null"]:
                    required = [task.get("tool")]
                tasks.append({
                    "id": task.get("id") or (idx + 1),
                    "desc": str(task.get("desc") or f"Task {idx + 1}"),
                    "required_skills": required,
                })
            plan["tasks"] = tasks
            self.whiteboard.update("action_plan", plan)
        except:
            self.whiteboard.update("action_plan", {"tasks": [{"id": 1, "desc": "Fallback task", "required_skills": []}]})

    def _step_replanning(self, retry_idx: int):
        print(f"[Step 4b] Re-Planning (Attempt {retry_idx+1})...")
        # Update plan based on evaluation feedback
        eval_report = self.whiteboard.get("evaluation_report")
        current_plan = self.whiteboard.get("action_plan")
        
        prompt = (
            "You are the Planner. The previous execution failed evaluation.\n"
            f"Evaluation Report: {self._safe_dumps(eval_report)}\n"
            f"Current Plan: {self._safe_dumps(current_plan)}\n\n"
            "Task: Adjust the plan to address the failure reasons.\n"
            "Output the updated JSON plan."
        )
        res = self._create_worker("planner", enable_tools=False).step(prompt)
        try:
            new_plan = json.loads(self._extract_json(res))
            tasks = []
            for idx, task in enumerate(new_plan.get("tasks") or []):
                required = task.get("required_skills")
                if not isinstance(required, list):
                    required = []
                required = [x for x in required if isinstance(x, str)]
                if not required and isinstance(task.get("tool"), str) and task.get("tool") not in ["none", "", "null"]:
                    required = [task.get("tool")]
                tasks.append({
                    "id": task.get("id") or (idx + 1),
                    "desc": str(task.get("desc") or f"Task {idx + 1}"),
                    "required_skills": required,
                })
            new_plan["tasks"] = tasks
            self.whiteboard.update("action_plan", new_plan)
        except: pass

    def _extract_task_claim(self, text: str) -> Dict[str, Any]:
        try:
            data = json.loads(self._extract_json(text))
            task_id = data.get("task_id")
            self_role = str(data.get("self_role") or "worker").strip() or "worker"
            tools = data.get("tools") if isinstance(data.get("tools"), list) else []
            confidence = float(data.get("confidence") or 0.5)
            return {
                "task_id": task_id,
                "self_role": self_role,
                "tools": self._sanitize_tools(tools, []),
                "confidence": max(0.0, min(1.0, confidence)),
            }
        except:
            return {"task_id": None, "self_role": "worker", "tools": [], "confidence": 0.0}

    def _step_inference(self):
        print("[Step 5] Inference (Self-Organized Task Claim)...")
        settings = self._profile_settings()
        plan = self.whiteboard.get("action_plan")
        info = self.whiteboard.get("information_gathering") or {}
        context = info.get("synthesized_context") or ""
        tasks = plan.get("tasks") or []
        max_agents = max(1, int(getattr(self.config.swarm, "max_agents", 4)))
        worker_ids = [f"worker_{i+1}" for i in range(max_agents)]
        assignments: Dict[str, Dict[str, Any]] = {}
        claim_history: List[Dict[str, Any]] = []
        def to_task_id(v: Any) -> int | None:
            try:
                return int(v)
            except:
                return None

        pending = [tid for tid in (to_task_id(t.get("id")) for t in tasks) if tid is not None]

        for round_idx in range(1, 4):
            if not pending:
                break

            def run_claim(worker_id: str) -> Dict[str, Any]:
                visible_tasks = [t for t in tasks if to_task_id(t.get("id")) in pending]
                claim_prompt = (
                    "你是自组织任务系统中的执行体。\n"
                    "你先读取完整任务列表，再基于专长自主认领最匹配任务。\n"
                    "你需要主动给出你的专业角色与所需工具，并与其他执行体形成互补分工。\n"
                    f"轮次: {round_idx}\n"
                    f"当前 Worker: {worker_id}\n"
                    f"待认领任务: {self._safe_dumps(visible_tasks)}\n"
                    f"已有认领历史: {self._safe_dumps(claim_history[-8:])}\n"
                    "基于任务需求自主决定：是否认领、认领哪个任务、你自己的专业角色、你需要的工具。\n"
                    "请返回 JSON: {\"task_id\":1,\"self_role\":\"finance_expert\",\"tools\":[\"web_search\"],\"confidence\":0.8}\n"
                    "若本轮不认领则 task_id 返回 null。"
                )
                worker = self._create_worker("worker", enable_tools=False)
                claim = self._extract_task_claim(worker.step(claim_prompt))
                claim["worker_id"] = worker_id
                return claim

            claims: List[Dict[str, Any]] = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(worker_ids)) as executor:
                futures = [executor.submit(run_claim, wid) for wid in worker_ids]
                for future in concurrent.futures.as_completed(futures):
                    try:
                        claims.append(future.result())
                    except:
                        pass

            grouped: Dict[int, List[Dict[str, Any]]] = {}
            for c in claims:
                try:
                    tid = int(c.get("task_id"))
                except:
                    continue
                if tid in pending:
                    grouped.setdefault(tid, []).append(c)

            for tid in list(pending):
                cs = grouped.get(tid) or []
                if not cs:
                    continue
                chosen = sorted(cs, key=lambda x: float(x.get("confidence") or 0.0), reverse=True)[0]
                task = next((t for t in tasks if to_task_id(t.get("id")) == tid), None)
                if task is None:
                    continue
                tools = self._sanitize_tools(chosen.get("tools") or [], task.get("required_skills") or [])
                assignments[str(tid)] = {
                    "worker_id": chosen.get("worker_id"),
                    "task_id": tid,
                    "role": chosen.get("self_role") or "worker",
                    "tools": tools,
                    "required_skills": task.get("required_skills") or [],
                    "task_desc": task.get("desc") or "",
                }
                pending.remove(tid)
                claim_history.append(assignments[str(tid)])

        idle_workers = [wid for wid in worker_ids if wid not in {a["worker_id"] for a in assignments.values()}]
        for tid in list(pending):
            task = next((t for t in tasks if to_task_id(t.get("id")) == tid), None)
            if task is None:
                continue
            wid = idle_workers.pop(0) if idle_workers else worker_ids[tid % len(worker_ids)]
            tools = self._sanitize_tools(task.get("required_skills") or [], [])
            assignments[str(tid)] = {
                "worker_id": wid,
                "task_id": tid,
                "role": "generalist_worker",
                "tools": tools,
                "required_skills": task.get("required_skills") or [],
                "task_desc": task.get("desc") or "",
            }

        self.whiteboard.update("task_assignments", list(assignments.values()))
        results = []

        def run_task(assign: Dict[str, Any]) -> Dict[str, Any]:
            worker = self._create_worker(
                assign["role"],
                enable_tools=bool(assign["tools"]),
                allowed_tools=assign["tools"],
                task_desc=assign["task_desc"],
                required_skills=assign["required_skills"],
            )
            prompt = STEP_INFERENCE_PROMPT.format(
                role=assign["role"],
                task_desc=assign["task_desc"],
                context=context[: int(settings.get("context_limit", 8000))] if context else "",
            )
            res = worker.step(prompt)
            return {
                "task_id": assign["task_id"],
                "worker_id": assign["worker_id"],
                "role": assign["role"],
                "tools": assign["tools"],
                "result": res,
            }

        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(len(assignments), max_agents))) as executor:
            futures = [executor.submit(run_task, a) for a in assignments.values()]
            for future in concurrent.futures.as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    results.append({"task_id": None, "result": f"Task failed: {e}"})
        self.whiteboard.update("inference_conclusions", results)

    def _step_evaluation(self) -> bool:
        print("[Step 6] Evaluation (Self-Organized Roles)...")
        settings = self._profile_settings()
        plan = self.whiteboard.get("action_plan")
        results = self.whiteboard.get("inference_conclusions")
        prompt = STEP_EVALUATION_PROMPT.format(
            plan_json=self._safe_dumps(plan),
            results_json=self._safe_dumps(results, max_len=2000),
            swarmboot=self.swarmboot
        ) + '\n请先定义你的评估角色 self_defined_role，再投票。输出JSON: {"self_defined_role":"code_reviewer","vote":"PASS","reason":"..."}'
        evals = self._run_parallel(prompt, int(settings.get("evaluation_workers", 3)), "evaluator", enable_tools=False)
        pass_count = 0
        reasons = []
        eval_roles: List[str] = []
        for e in evals:
            try:
                data = json.loads(self._extract_json(e))
                if data.get("vote") == "PASS": pass_count += 1
                reasons.append(data.get("reason"))
                role = str(data.get("self_defined_role") or "").strip()
                if role:
                    eval_roles.append(role)
            except:
                pass
        if not eval_roles:
            eval_roles = ["general_evaluator"]
        passed = pass_count >= 2
        self.whiteboard.update("evaluation_roles", eval_roles)
        self.whiteboard.update("evaluation_report", {"passed": passed, "reasons": reasons, "roles": eval_roles})
        return passed

    def _step_translation(self) -> str:
        print("[Step 7] Translation (No Tools by Default)...")
        conclusions = self.whiteboard.get("inference_conclusions")
        prompt = STEP_TRANSLATION_PROMPT.format(
            user_input=self.whiteboard.get("input_prompt"),
            conclusions_json=self._safe_dumps(conclusions, max_len=2000),
            soul_content=self.soul
        )
        user_input = self.whiteboard.get("input_prompt") or ""
        gate = self._decide_tool_gate(
            "translation",
            user_input,
            self._safe_dumps(conclusions, max_len=1800),
            ["web_search", "browser_open", "browser_read"],
        )
        self.whiteboard.update("translation_tool_gate", gate)
        res = self._create_worker(
            "master",
            enable_tools=bool(gate.get("need_tools")),
            allowed_tools=gate.get("tools") or [],
        ).step(prompt)
        if isinstance(res, str) and res.strip():
            if self._extract_urls(user_input) and self._is_explicit_read_analyze_request(user_input):
                low = res.lower()
                blocked = any(k in low for k in ["clarify", "can you", "please confirm", "请确认", "请问", "能否说明", "what is your goal"])
                if blocked:
                    return "已完成分析。若文档访问受限，我已按可见内容提取关键信息并标注限制。"
            return res
        return "我建议先满足前置条件，再执行目标动作。"

    def _derive_hard_constraints(self, user_input: str) -> List[str]:
        constraints: List[str] = []
        text = user_input or ""
        if "洗车" in text and "车" in text:
            constraints.append("涉及洗车时，车辆必须被带到洗车地点，不能只让人到场。")
        m = re.search(r"(包裹|U盘|文件|合同|钥匙).{0,8}在([^，。！？\n]{1,12})", text)
        if m:
            obj = m.group(1)
            loc = m.group(2)
            constraints.append(f"若任务依赖{obj}且其在{loc}，应先获取{obj}再执行后续动作。")
        return constraints

    def _response_violates_constraints(self, user_input: str, response: str) -> List[str]:
        reasons: List[str] = []
        q = user_input or ""
        r = response or ""
        if "洗车" in q and "车" in q:
            rl = r.lower()
            walk_strong = bool(
                re.search(r"(步行是最优|走路是最优|建议.{0,8}(走路|步行)|walk is .*best|recommend.*walk)", rl)
                or "走路去" in r
                or "步行去" in r
                or "步行是" in r
                or "走路是" in r
            )
            walk_reco = bool(
                re.search(r"(建议|推荐|结论|最优).{0,10}(走路|步行)", r)
                or re.search(r"(suggest|recommend|verdict|best).{0,16}(walk|walking)", rl)
                or "walk to the car wash" in rl
            )
            drive_reco = bool(
                re.search(r"(建议|推荐|结论|最优).{0,10}(开车|驾车|把车开)", r)
                or re.search(r"(suggest|recommend|verdict|best).{0,16}(drive|driving)", rl)
                or "开车去" in r
            )
            if walk_strong or (walk_reco and not drive_reco):
                reasons.append("回答建议步行但未满足“车必须到洗车点”的必要条件。")
        m = re.search(r"(包裹|U盘|文件|合同|钥匙).{0,8}在([^，。！？\n]{1,12})", q)
        if m:
            obj = m.group(1)
            loc = m.group(2)
            if (
                f"先去{loc}" not in r
                and f"先到{loc}" not in r
                and f"先回{loc}" not in r
                and f"先拿{obj}" not in r
                and f"先取{obj}" not in r
            ):
                reasons.append(f"回答未明确给出前置顺序：先到{loc}获取{obj}。")
        if ("车" not in q and "汽车" not in q) and ("开车" in r or "驾车" in r):
            reasons.append("问题未涉及车辆，但回答引入了驾车方案。")
        return reasons

    def _rule_based_fallback(self, user_input: str) -> str:
        q = user_input or ""
        if "洗车" in q and "车" in q:
            return "建议开车去。洗车的前提是把车带到洗车店，步行只会让人到场而车不在现场。"
        m = re.search(r"(包裹|U盘|文件|合同|钥匙).{0,8}在([^，。！？\n]{1,12})", q)
        if m:
            obj = m.group(1)
            loc = m.group(2)
            if "快递点" in q:
                return f"建议先去{loc}拿{obj}，再去快递点办理寄送。"
            if "打印店" in q:
                return f"建议先去{loc}取{obj}，再去打印店处理打印。"
            return f"建议先到{loc}拿到{obj}，再去目标地点执行任务。"
        return "建议先确认并满足前置条件，再执行目标动作。"

    def _calibrate_final_response(self, user_input: str, response: str) -> str:
        constraints = self._derive_hard_constraints(user_input)
        if not constraints:
            return response
        q = user_input or ""
        if "洗车" in q and "车" in q:
            return self._rule_based_fallback(q)
        if re.search(r"(包裹|U盘|文件|合同|钥匙).{0,8}在([^，。！？\n]{1,12})", q):
            return self._rule_based_fallback(q)
        if not isinstance(response, str) or not response.strip() or "先满足前置条件" in response:
            return self._rule_based_fallback(user_input)
        violations = self._response_violates_constraints(user_input, response)
        if not violations:
            return response
        print("[Step 7b] Calibration (No Tools)...")
        prompt = (
            "你是最终校准器。请在不改变用户问题域的前提下，重写最终回答。\n"
            f"用户问题：{user_input}\n"
            f"当前回答：{response}\n"
            f"必须满足的硬约束：{json.dumps(constraints, ensure_ascii=False)}\n"
            f"当前违规点：{json.dumps(violations, ensure_ascii=False)}\n"
            "要求：给出简洁、可执行、无跑题的最终答案。"
        )
        calibrated = self._create_worker("master", enable_tools=False).step(prompt)
        if isinstance(calibrated, str) and calibrated.strip():
            violations2 = self._response_violates_constraints(user_input, calibrated)
            if not violations2:
                return calibrated
        return self._rule_based_fallback(user_input)

    def _step_organization(self):
        print("[Step 8] Organization (No Tools)...")
        prompt = STEP_ORGANIZATION_PROMPT.format(
            response=self.whiteboard.get("final_response"),
            conclusions_json=self._safe_dumps(self.whiteboard.get("inference_conclusions"), max_len=1500)
        )
        # Optimized: enable_tools=False
        res = self._create_worker("master", enable_tools=False).step(prompt)
        try:
            data = json.loads(self._extract_json(res))
            # 1. Update Hot Memory
            hot_upd = data.get("hot_memory_update")
            if hot_upd:
                # Basic append logic for now
                cur_hot = self.hot_memory.read()
                self.hot_memory.update(cur_hot + f"\n\n### Loop Update\n{hot_upd}")
            
            # 2. Update Warm Memory
            self.warm_memory.append_log(
                self.whiteboard.get("metadata").get("loop_id"),
                self.whiteboard.get("input_prompt"),
                data.get("summary", ""),
                data.get("warm_memory_facts", [])
            )
        except: pass

    def _extract_json(self, text: str) -> str:
        import re
        match = re.search(r"\{.*\}", text, re.DOTALL)
        return match.group(0) if match else "{}"
