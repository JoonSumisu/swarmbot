import subprocess
import json
import os
import sys
from typing import Dict, Any, List, Optional

class OpenClawBridge:
    """
    Bridge to OpenClaw (Node.js) tools.
    Requires 'openclaw' CLI or 'node' to be available in the environment.
    """
    def __init__(self, runner_script_path: Optional[str] = None):
        self.available = False
        self._check_environment()
        self.runner_script = runner_script_path or os.path.join(os.path.dirname(__file__), "openclaw_runner.js")

    def _check_environment(self):
        # Check for node
        try:
            subprocess.run(["node", "--version"], check=True, capture_output=True)
            self.available = True
        except (FileNotFoundError, subprocess.CalledProcessError):
            self.available = False
            print("[OpenClawBridge] Node.js not found. OpenClaw tools will be unavailable.")

    def discover_tools(self) -> List[Dict[str, Any]]:
        """
        Discover available OpenClaw tools via CLI or Runner.
        Returns a list of tool definitions (OpenAI format).
        """
        if not self.available:
            return []

        # Strategy 1: Try 'openclaw skills list --json'
        try:
            res = subprocess.run(
                ["openclaw", "skills", "list", "--json"], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            if res.returncode == 0:
                skills = json.loads(res.stdout)
                return self._convert_skills_to_tools(skills)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        # Strategy 2: Use custom runner script to inspect installed packages/skills
        # This is a fallback if CLI is not installed globally but source is present
        # For now, return empty if CLI fails
        return []

    def _convert_skills_to_tools(self, skills_data: Any) -> List[Dict[str, Any]]:
        # Convert OpenClaw skill format to OpenAI tool definition
        tools = []
        # Assumption on skills_data structure (list of objects with name, description, schema)
        if isinstance(skills_data, list):
            for skill in skills_data:
                tools.append({
                    "type": "function",
                    "function": {
                        "name": skill.get("name"),
                        "description": skill.get("description", ""),
                        "parameters": skill.get("schema", {})
                    }
                })
        return tools

    def execute(self, tool_name: str, args: Dict[str, Any]) -> str:
        """
        Execute an OpenClaw tool.
        """
        if not self.available:
            return "Error: OpenClaw environment (Node.js) not available."

        # Use the runner script to execute the tool
        # We pass tool name and args (as JSON string)
        try:
            cmd = ["node", self.runner_script, tool_name, json.dumps(args)]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if res.returncode != 0:
                return f"OpenClaw execution failed: {res.stderr}"
            
            return res.stdout.strip()
        except Exception as e:
            return f"Bridge execution error: {str(e)}"
