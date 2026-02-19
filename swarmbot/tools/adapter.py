from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]

class NanobotSkillAdapter:
    """
    Adapter to bridge nanobot skills to Swarmbot agents.
    Allows agents to discover and execute nanobot skills via CLI passthrough or direct API.
    """
    def __init__(self) -> None:
        self.skills: Dict[str, ToolDefinition] = {}
        self._load_skills()

    def _load_skills(self) -> None:
        """
        Load available skills from nanobot.
        Currently uses CLI 'nanobot skill list --json' to discover.
        """
        try:
            # Try to get skills in JSON format from nanobot
            # Assuming nanobot skill list supports --json or similar structured output
            # If not, we might need to parse text or rely on known built-ins
            result = subprocess.run(
                ["nanobot", "skill", "list", "--json"],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0 and result.stdout.strip():
                try:
                    data = json.loads(result.stdout)
                    for item in data:
                        # Map nanobot skill structure to ToolDefinition
                        name = item.get("name", "unknown")
                        desc = item.get("description", "")
                        # Simplistic parameter schema inference
                        params = {
                            "type": "object",
                            "properties": {
                                "args": {"type": "string", "description": "Arguments for the skill"}
                            },
                            "required": ["args"]
                        }
                        self.skills[name] = ToolDefinition(name, desc, params)
                except json.JSONDecodeError:
                    # Fallback if not JSON
                    pass
        except FileNotFoundError:
            pass

        # Always add core built-ins manually if discovery fails or to ensure presence
        self._register_builtin("file_read", "Read a file from local filesystem", ["path"])
        self._register_builtin("file_write", "Write content to a file", ["path", "content"])
        self._register_builtin("web_search", "Search the web via nanobot provider", ["query"])
        self._register_builtin("shell_exec", "Execute a shell command (Sandboxed)", ["command"])

    def _register_builtin(self, name: str, desc: str, args: List[str]) -> None:
        props = {arg: {"type": "string"} for arg in args}
        self.skills[name] = ToolDefinition(
            name=name,
            description=desc,
            parameters={
                "type": "object",
                "properties": props,
                "required": args
            }
        )

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Return OpenAI-compatible tool definitions."""
        tools = []
        for name, tool in self.skills.items():
            tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool.description,
                    "parameters": tool.parameters
                }
            })
        return tools

    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        Execute a skill.
        For built-ins, we map to nanobot CLI commands or direct python logic.
        """
        # For this PoC, we map known tools to nanobot CLI calls
        # In a deep integration, we would import nanobot.skills...
        
        if tool_name == "web_search":
            query = arguments.get("query", "")
            # nanobot tool run web_search "query"
            return self._run_nanobot_cmd("tool", "run", "web_search", query)
            
        if tool_name == "shell_exec":
            cmd = arguments.get("command", "")
            return self._run_nanobot_cmd("tool", "run", "shell", cmd)
            
        if tool_name == "file_read":
            path = arguments.get("path", "")
            # Assuming nanobot has fs skills exposed
            return self._run_nanobot_cmd("tool", "run", "fs_read", path)
            
        return f"Tool {tool_name} executed with {arguments} (Mock)"

    def _run_nanobot_cmd(self, *args: str) -> str:
        try:
            cmd = ["nanobot"] + list(args)
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return f"Error: {result.stderr.strip()}"
        except Exception as e:
            return f"Execution failed: {str(e)}"
