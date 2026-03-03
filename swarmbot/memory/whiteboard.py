from typing import Any, Dict, List, Optional
import json
import time

class Whiteboard:
    """
    L1 Whiteboard: Temporary workspace for the current inference loop.
    Cleared after each loop (single dialogue lifecycle).
    
    Structure:
    - input_prompt: Original user input
    - problem_analysis: {type, domain, intent, complexity}
    - information_gathering: {context, memory_refs, search_results}
    - action_plan: {tasks: [{id, desc, worker, tool}], status}
    - inference_conclusions: {task_results: [], final_conclusion}
    - evaluation_report: {reviews: [], passed, retry_count}
    - final_response: Translated output for user
    """
    def __init__(self):
        self._data = {}
        self.clear()

    def clear(self):
        self._data = {
            "metadata": {
                "session_id": "", 
                "loop_id": "",
                "start_time": time.time()
            },
            "input_prompt": "",
            "problem_analysis": {},
            "information_gathering": {},
            "action_plan": {},
            "inference_conclusions": [],
            "evaluation_report": {"retry_count": 0},
            "final_response": ""
        }

    def update(self, section: str, data: Any):
        if section not in self._data:
            self._data[section] = data
        elif isinstance(self._data[section], dict) and isinstance(data, dict):
            self._data[section].update(data)
        elif isinstance(self._data[section], list) and isinstance(data, list):
            self._data[section].extend(data)
        else:
            self._data[section] = data

    def get(self, section: str) -> Any:
        return self._data.get(section)

    def get_full_snapshot(self) -> str:
        return json.dumps(self._data, ensure_ascii=False, indent=2)
