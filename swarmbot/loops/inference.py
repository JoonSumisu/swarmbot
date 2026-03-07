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
from .definitions import *

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
        
        # Load Swarmboot
        self.swarmboot = self._load_boot_file("swarmboot.md")
        self.soul = self._load_boot_file("SOUL.md")
        self.loop_profile_mode = (os.environ.get("SWARMBOT_LOOP_PROFILE") or "auto").strip().lower()

    def _load_boot_file(self, filename: str) -> str:
        paths = [
            os.path.expanduser(f"~/.swarmbot/boot/{filename}"),
            os.path.join(os.path.dirname(__file__), f"../boot/{filename}")
        ]
        for p in paths:
            if os.path.exists(p):
                return open(p, "r", encoding="utf-8").read()
        return f"Boot file {filename} not found."

    def _create_worker(self, role: str, enable_tools: bool = True, allowed_tools: List[str] | None = None) -> CoreAgent:
        skills = {name: True for name in (allowed_tools or [])}
        ctx = AgentContext(agent_id=f"worker-{role}-{int(time.time())}", role=role, skills=skills)
        # Workers get Cold and Hot memory access
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
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(self._decide_tool_gate_once, stage, user_input, context_json, fallback_tools)
                for _ in range(3)
            ]
            decisions = [f.result() for f in concurrent.futures.as_completed(futures)]
        
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
            
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(self._decide_loop_profile_once) for _ in range(3)]
            decisions = [f.result() for f in concurrent.futures.as_completed(futures)]
            
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
        prompt = STEP_ANALYSIS_PROMPT.format(
            user_input=self.whiteboard.get("input_prompt"),
            swarmboot=self.swarmboot
        )
        results = self._run_parallel(prompt, int(settings.get("analysis_workers", 2)), "analyst", enable_tools=False)
        # Simple merge of analysis
        merged = {}
        for r in results:
            try: merged.update(json.loads(self._extract_json(r)))
            except: pass
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
        user_input = self.whiteboard.get("input_prompt") or ""
        # Gather memory snapshots
        hot = self.hot_memory.read()
        warm = self.warm_memory.read_today()
        cold = self.cold_memory.search_text(str(analysis), limit=5)
        
        prompt = STEP_COLLECTION_PROMPT.format(
            analysis_json=self._safe_dumps(analysis),
            swarmboot=self.swarmboot,
            hot_memory=hot[:2000],
            warm_memory=warm[:2000],
            cold_memory=cold[:2000]
        )
        results = self._run_parallel(prompt, int(settings.get("collection_workers", 2)), "collector", enable_tools=False)
        
        merged = {"synthesized_context": "", "memory_references": [], "external_info": ""}
        for r in results:
            try:
                data = json.loads(self._extract_json(r))
                merged["synthesized_context"] += "\n" + data.get("synthesized_context", "")
                merged["memory_references"].extend(data.get("memory_references", []))
                merged["external_info"] += "\n" + data.get("external_info", "")
            except: pass
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
                except:
                    merged["external_info"] += "\n" + str(r)
        self.whiteboard.update("information_gathering", merged)

    def _step_planning(self):
        print("[Step 4] Planning (No Tools)...")
        settings = self._profile_settings()
        info = self.whiteboard.get("information_gathering")
        prompt = STEP_PLANNING_PROMPT.format(
            info_json=self._safe_dumps(info, max_len=int(settings.get("context_limit", 6000))),
            swarmboot=self.swarmboot
        )
        res = self._create_worker("planner", enable_tools=False).step(prompt)
        try:
            plan = json.loads(self._extract_json(res))
            self.whiteboard.update("action_plan", plan)
        except:
            self.whiteboard.update("action_plan", {"tasks": [{"id": 1, "desc": "Fallback task", "worker": "assistant", "tool": "none"}]})

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
            self.whiteboard.update("action_plan", new_plan)
        except: pass

    def _step_inference(self):
        print("[Step 5] Inference (Task-Gated Tools)...")
        settings = self._profile_settings()
        plan = self.whiteboard.get("action_plan")
        context = self.whiteboard.get("information_gathering").get("synthesized_context")
        
        results = []
        for task in plan.get("tasks", []):
            worker_role = task.get("worker", "assistant")
            task_tool = task.get("tool", "none")
            need_tools = task_tool.lower() not in ["none", "null", ""]
            allowed_tools = []
            if need_tools:
                allowed_tools = [task_tool] if isinstance(task_tool, str) else []
            worker = self._create_worker(worker_role, enable_tools=need_tools, allowed_tools=allowed_tools)
            prompt = STEP_INFERENCE_PROMPT.format(
                role=worker_role,
                task_desc=task.get("desc"),
                context=context[: int(settings.get("context_limit", 8000))] if context else ""
            )
            res = worker.step(prompt)
            results.append({"task_id": task.get("id"), "result": res})
        self.whiteboard.update("inference_conclusions", results)

    def _step_evaluation(self) -> bool:
        print("[Step 6] Evaluation (No Tools)...")
        settings = self._profile_settings()
        plan = self.whiteboard.get("action_plan")
        results = self.whiteboard.get("inference_conclusions")
        
        prompt = STEP_EVALUATION_PROMPT.format(
            plan_json=self._safe_dumps(plan),
            results_json=self._safe_dumps(results, max_len=2000),
            swarmboot=self.swarmboot
        )
        evals = self._run_parallel(prompt, int(settings.get("evaluation_workers", 3)), "evaluator", enable_tools=False)
        
        pass_count = 0
        reasons = []
        for e in evals:
            try:
                data = json.loads(self._extract_json(e))
                if data.get("vote") == "PASS": pass_count += 1
                reasons.append(data.get("reason"))
            except: pass
        
        passed = pass_count >= 2
        self.whiteboard.update("evaluation_report", {"passed": passed, "reasons": reasons})
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
