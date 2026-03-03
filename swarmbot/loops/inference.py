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

    def _create_worker(self, role: str) -> CoreAgent:
        ctx = AgentContext(agent_id=f"worker-{role}-{int(time.time())}", role=role)
        # Workers get Cold and Hot memory access
        return CoreAgent(ctx, self.llm, self.cold_memory, hot_memory=self.hot_memory)

    def run(self, user_input: str, session_id: str) -> str:
        self.whiteboard.clear()
        self.whiteboard.update("metadata", {"session_id": session_id, "loop_id": str(int(time.time()))})
        self.whiteboard.update("input_prompt", user_input)
        
        print(f"[InferenceLoop] Start: {user_input[:50]}...")

        # Step 2: Problem Analysis (2 Workers)
        self._step_analysis()
        
        # Step 3: Information Collection (3 Workers)
        self._step_collection()
        
        # Step 4: Action Planning
        self._step_planning()
        
        # Step 5 & 6: Inference & Evaluation (Max 3 Loops)
        max_eval_loops = 3
        for i in range(max_eval_loops):
            self.whiteboard.update("evaluation_report", {"retry_count": i})
            self._step_inference()
            if self._step_evaluation():
                break
            print(f"[InferenceLoop] Evaluation failed, retrying {i+1}/{max_eval_loops}")

        # Step 7: Output Translation
        final_response = self._step_translation()
        self.whiteboard.update("final_response", final_response)
        
        # Step 8: Organization & Persistence
        self._step_organization()
        
        return final_response

    def _run_parallel(self, prompt: str, count: int, role: str) -> List[str]:
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=count) as executor:
            futures = [executor.submit(self._create_worker(role).step, prompt) for _ in range(count)]
            for f in concurrent.futures.as_completed(futures):
                try: results.append(f.result())
                except Exception as e: print(f"Worker {role} error: {e}")
        return results

    def _step_analysis(self):
        print("[Step 2] Analysis...")
        prompt = STEP_ANALYSIS_PROMPT.format(user_input=self.whiteboard.get("input_prompt"))
        results = self._run_parallel(prompt, 2, "analyst")
        # Simple merge of analysis
        merged = {}
        for r in results:
            try: merged.update(json.loads(self._extract_json(r)))
            except: pass
        self.whiteboard.update("problem_analysis", merged)

    def _step_collection(self):
        print("[Step 3] Collection...")
        analysis = self.whiteboard.get("problem_analysis")
        # Gather memory snapshots
        hot = self.hot_memory.read()
        warm = self.warm_memory.read_today()
        cold = self.cold_memory.search_text(str(analysis), limit=5)
        
        prompt = STEP_COLLECTION_PROMPT.format(
            analysis_json=json.dumps(analysis),
            hot_memory=hot[:2000],
            warm_memory=warm[:2000],
            cold_memory=cold[:2000]
        )
        results = self._run_parallel(prompt, 3, "collector")
        
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
        print("[Step 4] Planning...")
        info = self.whiteboard.get("information_gathering")
        prompt = STEP_PLANNING_PROMPT.format(info_json=json.dumps(info))
        res = self._create_worker("planner").step(prompt)
        try:
            plan = json.loads(self._extract_json(res))
            self.whiteboard.update("action_plan", plan)
        except:
            self.whiteboard.update("action_plan", {"tasks": [{"id": 1, "desc": "Fallback task", "worker": "assistant", "tool": "none"}]})

    def _step_inference(self):
        print("[Step 5] Inference...")
        plan = self.whiteboard.get("action_plan")
        context = self.whiteboard.get("information_gathering").get("synthesized_context")
        
        results = []
        for task in plan.get("tasks", []):
            worker = self._create_worker(task.get("worker", "assistant"))
            prompt = STEP_INFERENCE_PROMPT.format(
                role=task.get("worker"),
                task_desc=task.get("desc"),
                context=context
            )
            res = worker.step(prompt)
            results.append({"task_id": task.get("id"), "result": res})
        self.whiteboard.update("inference_conclusions", results)

    def _step_evaluation(self) -> bool:
        print("[Step 6] Evaluation...")
        plan = self.whiteboard.get("action_plan")
        results = self.whiteboard.get("inference_conclusions")
        
        prompt = STEP_EVALUATION_PROMPT.format(
            plan_json=json.dumps(plan),
            results_json=json.dumps(results)
        )
        evals = self._run_parallel(prompt, 3, "evaluator")
        
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
        print("[Step 7] Translation...")
        conclusions = self.whiteboard.get("inference_conclusions")
        prompt = STEP_TRANSLATION_PROMPT.format(
            user_input=self.whiteboard.get("input_prompt"),
            conclusions_json=json.dumps(conclusions),
            soul_content=self.soul
        )
        return self._create_worker("master").step(prompt)

    def _step_organization(self):
        print("[Step 8] Organization...")
        prompt = STEP_ORGANIZATION_PROMPT.format(
            response=self.whiteboard.get("final_response"),
            conclusions_json=json.dumps(self.whiteboard.get("inference_conclusions"))
        )
        res = self._create_worker("master").step(prompt)
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
