import concurrent.futures
import json
import time
import os
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

    def _load_boot_file(self, filename: str) -> str:
        paths = [
            os.path.expanduser(f"~/.swarmbot/boot/{filename}"),
            os.path.join(os.path.dirname(__file__), f"../boot/{filename}")
        ]
        for p in paths:
            if os.path.exists(p):
                return open(p, "r", encoding="utf-8").read()
        return f"Boot file {filename} not found."

    def _create_worker(self, role: str, enable_tools: bool = True) -> CoreAgent:
        ctx = AgentContext(agent_id=f"worker-{role}-{int(time.time())}", role=role)
        # Workers get Cold and Hot memory access
        return CoreAgent(ctx, self.llm, self.cold_memory, hot_memory=self.hot_memory, enable_tools=enable_tools)

    def run(self, user_input: str, session_id: str) -> str:
        self.whiteboard.clear()
        self.whiteboard.update("metadata", {"session_id": session_id, "loop_id": str(int(time.time()))})
        self.whiteboard.update("input_prompt", user_input)
        
        print(f"[InferenceLoop] Start: {user_input[:50]}...")

        # Step 2: Problem Analysis (No Tools)
        self._step_analysis()
        
        # Step 3: Information Collection (Tools Enabled - User Requirement)
        self._step_collection()
        
        # Step 4: Action Planning (No Tools - JSON Gen)
        self._step_planning()
        
        # Step 5 & 6: Inference & Evaluation (Max 3 Loops with Re-planning)
        max_eval_loops = 3
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
        self.whiteboard.update("final_response", final_response)
        
        # Step 8: Organization & Persistence (No Tools)
        self._step_organization()
        
        return final_response

    def _run_parallel(self, prompt: str, count: int, role: str, enable_tools: bool = True) -> List[str]:
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=count) as executor:
            futures = [executor.submit(self._create_worker(role, enable_tools).step, prompt) for _ in range(count)]
            for f in concurrent.futures.as_completed(futures):
                try: results.append(f.result())
                except Exception as e: print(f"Worker {role} error: {e}")
        return results

    def _step_analysis(self):
        print("[Step 2] Analysis (No Tools)...")
        prompt = STEP_ANALYSIS_PROMPT.format(
            user_input=self.whiteboard.get("input_prompt"),
            swarmboot=self.swarmboot
        )
        # Optimized: enable_tools=False
        results = self._run_parallel(prompt, 2, "analyst", enable_tools=False)
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
        print("[Step 3] Collection (Tools Enabled)...")
        analysis = self.whiteboard.get("problem_analysis")
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
        # Tools Enabled per requirement
        results = self._run_parallel(prompt, 3, "collector", enable_tools=True)
        
        merged = {"synthesized_context": "", "memory_references": [], "external_info": ""}
        for r in results:
            try:
                data = json.loads(self._extract_json(r))
                merged["synthesized_context"] += "\n" + data.get("synthesized_context", "")
                merged["memory_references"].extend(data.get("memory_references", []))
                merged["external_info"] += "\n" + data.get("external_info", "")
            except: pass
        self.whiteboard.update("information_gathering", merged)

    def _step_planning(self):
        print("[Step 4] Planning (No Tools)...")
        info = self.whiteboard.get("information_gathering")
        prompt = STEP_PLANNING_PROMPT.format(
            info_json=self._safe_dumps(info, max_len=6000),
            swarmboot=self.swarmboot
        )
        # Optimized: enable_tools=False
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
        print("[Step 5] Inference (Tools Enabled)...")
        plan = self.whiteboard.get("action_plan")
        context = self.whiteboard.get("information_gathering").get("synthesized_context")
        
        results = []
        for task in plan.get("tasks", []):
            worker_role = task.get("worker", "assistant")
            # Decide if this specific task needs tools based on description or tool field
            # Ideally we check task['tool'] != 'none'
            # But user said "decide... then load".
            # For simplicity, we enable tools if the plan suggests a tool.
            task_tool = task.get("tool", "none")
            need_tools = task_tool.lower() not in ["none", "null", ""]
            
            worker = self._create_worker(worker_role, enable_tools=need_tools)
            prompt = STEP_INFERENCE_PROMPT.format(
                role=worker_role,
                task_desc=task.get("desc"),
                context=context[:8000] if context else ""  # Truncate context
            )
            res = worker.step(prompt)
            results.append({"task_id": task.get("id"), "result": res})
        self.whiteboard.update("inference_conclusions", results)

    def _step_evaluation(self) -> bool:
        print("[Step 6] Evaluation (No Tools)...")
        plan = self.whiteboard.get("action_plan")
        results = self.whiteboard.get("inference_conclusions")
        
        prompt = STEP_EVALUATION_PROMPT.format(
            plan_json=self._safe_dumps(plan),
            results_json=self._safe_dumps(results, max_len=2000),  # Aggressively truncate individual results
            swarmboot=self.swarmboot
        )
        # Optimized: enable_tools=False
        evals = self._run_parallel(prompt, 3, "evaluator", enable_tools=False)
        
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
        print("[Step 7] Translation (Tools Enabled)...")
        conclusions = self.whiteboard.get("inference_conclusions")
        prompt = STEP_TRANSLATION_PROMPT.format(
            user_input=self.whiteboard.get("input_prompt"),
            conclusions_json=json.dumps(conclusions),
            soul_content=self.soul
        )
        # Tools Enabled per requirement
        return self._create_worker("master", enable_tools=True).step(prompt)

    def _step_organization(self):
        print("[Step 8] Organization (No Tools)...")
        prompt = STEP_ORGANIZATION_PROMPT.format(
            response=self.whiteboard.get("final_response"),
            conclusions_json=json.dumps(self.whiteboard.get("inference_conclusions"))
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
