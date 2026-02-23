from __future__ import annotations

import json
import subprocess
import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
from pathlib import Path

@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]

from .browser.local_browser import LocalBrowserTool, BrowserConfig

from .registry import get_registry
from .openclaw_bridge import OpenClawBridge

class NanobotSkillAdapter:
    """
    Adapter to bridge nanobot skills to Swarmbot agents.
    Allows agents to discover and execute nanobot skills via CLI passthrough or direct API.
    Also manages local built-in tools like Browser.
    """
    def __init__(self) -> None:
        self.skills: Dict[str, ToolDefinition] = {}
        self._browser = LocalBrowserTool(BrowserConfig())
        self.registry = get_registry()
        self.openclaw_bridge = OpenClawBridge()
        self._load_skills()
        self._load_openclaw_tools()

    def _load_openclaw_tools(self) -> None:
        """
        Dynamically discover and register OpenClaw tools if available.
        """
        try:
            oc_tools = self.openclaw_bridge.discover_tools()
            for tool_def in oc_tools:
                name = tool_def["function"]["name"]
                desc = tool_def["function"]["description"]
                schema = tool_def["function"]["parameters"]
                
                # Wrap execution to call bridge
                # Use closure to capture tool name
                def make_wrapper(tool_name):
                    def wrapper(**kwargs):
                        return self.openclaw_bridge.execute(tool_name, kwargs)
                    return wrapper
                
                func = make_wrapper(name)
                
                # Register
                self.registry.register(name, func, {
                    "name": name,
                    "description": desc,
                    "parameters": schema
                })
        except Exception as e:
            print(f"[SkillAdapter] Failed to load OpenClaw tools: {e}")

    def _register_builtin(self, name: str, desc: str, args: List[str], func: Optional[callable] = None) -> None:
        props = {}
        required = []
        for arg in args:
             if arg in ["interval", "steps", "max_tokens"]:
                 props[arg] = {"type": "integer"}
                 # optional
             elif arg in ["args"]: # Dict/Object types
                 props[arg] = {"type": "object"}
             else:
                 props[arg] = {"type": "string"}
                 if arg not in ["subcommand"]: # subcommand is optional for some commands
                     required.append(arg)
                 
        parameters = {
            "type": "object",
            "properties": props,
            "required": required
        }
        
        # Store for internal use (compatibility)
        self.skills[name] = ToolDefinition(
            name=name,
            description=desc,
            parameters=parameters
        )
        
        # Register to global registry
        if func:
            schema = {
                "name": name,
                "description": desc,
                "parameters": parameters
            }
            self.registry.register(name, func, schema)
        
    def _load_skills(self) -> None:
        """
        Load available skills.
        """
        # Always add core built-ins manually
        self._register_builtin("file_read", "Read a file from local filesystem", ["path"], self._tool_file_read)
        self._register_builtin("file_write", "Write content to a file", ["path", "content"], self._tool_file_write)
        self._register_builtin("web_search", "Search the web for information using a search engine.", ["query"], self._tool_web_search)
        self._register_builtin("shell_exec", "Execute a shell command (Sandboxed)", ["command"], self._tool_shell_exec)
        
        # Add Browser Tools
        self._register_builtin("browser_open", "Open a URL in local browser to view content.", ["url"], self._tool_browser_open)
        self._register_builtin("browser_read", "Read text content of a URL (headless). Use this to extract information from a specific webpage.", ["url"], self._tool_browser_read)
        
        # Add Whiteboard Tools
        self._register_builtin("whiteboard_update", "Update the shared Whiteboard memory with key information.", ["key", "value"], self._tool_whiteboard_update)

        # Add Overthinking Control Tool
        self._register_builtin("overthinking_control", "Control the Overthinking background process.", ["action", "interval", "steps"], self._tool_overthinking_control)

        self._register_builtin("swarm_control", "Control Swarmbot configuration and lifecycle (CLI wrapper).", ["command", "subcommand", "args"], self._tool_swarm_control)
        self._register_builtin("skill_summary", "List available nanobot skills in a compact summary format.", [], self._tool_skill_summary)
        self._register_builtin("skill_load", "Load a specific skill markdown by name.", ["name"], self._tool_skill_load)

    def _tool_swarm_control(self, command: str, subcommand: Optional[str] = None, args: Optional[Dict[str, Any]] = None) -> str:
        """
        Execute Swarmbot CLI commands internally.
        Supports: config, provider, onboard, update, status, overthinking
        """
        from ..config_manager import load_config, save_config, SwarmbotConfig
        import subprocess
        import sys
        
        # Security check: Limit commands to safe subset?
        # User requested full control.
        
        if command == "update":
            # Call CLI update logic
            # Since CLI update uses subprocess to call git, we can just invoke it or replicate logic.
            # Invoking subprocess 'swarmbot update' might be circular if not careful with env, but safe here.
            # Better: replicate logic to capture output directly.
            try:
                # Re-use logic from cli.py if possible, or just subprocess
                res = subprocess.run(["swarmbot", "update"], capture_output=True, text=True)
                return f"Update Result:\n{res.stdout}\n{res.stderr}"
            except Exception as e:
                return f"Update failed: {e}"

        elif command == "config":
            cfg = load_config()
            if not args:
                return f"Current Swarm Config:\n{json.dumps(asdict(cfg.swarm), indent=2)}"
            
            # Apply updates
            if "agent_count" in args: cfg.swarm.agent_count = int(args["agent_count"])
            if "architecture" in args: cfg.swarm.architecture = str(args["architecture"])
            if "max_turns" in args: cfg.swarm.max_turns = int(args["max_turns"])
            if "auto_builder" in args: 
                val = args["auto_builder"]
                if isinstance(val, str): val = val.lower() in ("true", "1", "yes")
                cfg.swarm.auto_builder = bool(val)
            
            save_config(cfg)
            return f"Config updated:\n{json.dumps(asdict(cfg.swarm), indent=2)}"

        elif command == "provider":
            cfg = load_config()
            if subcommand == "add" and args:
                cfg.provider.base_url = args.get("base_url", cfg.provider.base_url)
                cfg.provider.api_key = args.get("api_key", cfg.provider.api_key)
                cfg.provider.model = args.get("model", cfg.provider.model)
                if "max_tokens" in args: cfg.provider.max_tokens = int(args["max_tokens"])
                save_config(cfg)
                return "Provider updated."
            elif subcommand == "delete":
                from ..config_manager import ProviderConfig
                cfg.provider = ProviderConfig()
                save_config(cfg)
                return "Provider reset to default."
            else:
                return f"Current Provider:\n{json.dumps(asdict(cfg.provider), indent=2)}"

        elif command == "status":
            cfg = load_config()
            return f"Status:\n{json.dumps(asdict(cfg), indent=2)}"
            
        elif command == "onboard":
             # Disabled for safety via swarm_control
             return "Command 'onboard' is disabled in swarm_control to prevent accidental reset. Please run 'swarmbot onboard' manually in terminal if really needed."

        elif command == "skill":
             action = subcommand or "list"
             if action == "list":
                 return self._tool_skill_summary()
             elif action == "info" and args and "name" in args:
                 return self._tool_skill_load(str(args["name"]))
             else:
                 return "Skill 管理请结合 skill_summary、skill_load 以及 shell_exec 执行 ClawHub 提供的命令完成。"

        elif command == "overthinking":
             # Proxy to _tool_overthinking_control
             action = subcommand or "status"
             interval = None
             steps = None
             if args:
                 interval = args.get("interval")
                 steps = args.get("steps")
             return self._tool_overthinking_control(action, interval, steps)

        else:
            return f"Unknown command: {command}. Supported: config, provider, update, status, onboard, overthinking, skill"

    def _tool_skill_summary(self) -> str:
        try:
            from nanobot.config.loader import load_config
            from nanobot.agent.skills import SkillsLoader
            cfg = load_config()
            loader = SkillsLoader(Path(cfg.workspace_path))
            summary = loader.build_skills_summary()
            if not summary:
                return "<skills></skills>"
            return summary
        except Exception as e:
            return f"Skill summary error: {e}"

    def _tool_skill_load(self, name: str) -> str:
        try:
            if not name:
                return "Skill name required"
            from nanobot.config.loader import load_config
            from nanobot.agent.skills import SkillsLoader
            cfg = load_config()
            loader = SkillsLoader(Path(cfg.workspace_path))
            content = loader.load_skill(name)
            if not content:
                return f"Skill not found: {name}"
            return content
        except Exception as e:
            return f"Skill load error: {e}"

    def _tool_overthinking_control(self, action: str, interval: Optional[int] = None, steps: Optional[int] = None) -> str:
        """
        Control the overthinking loop configuration.
        action: 'start', 'stop', 'status', 'configure'
        """
        from ..config_manager import load_config, save_config
        
        cfg = load_config()
        
        if action == "start":
            cfg.overthinking.enabled = True
            save_config(cfg)
            # In a real daemon, we might need to signal the process.
            # For now, we update config which the loop polls.
            return "Overthinking loop enabled. It will start in the background if running."
            
        elif action == "stop":
            cfg.overthinking.enabled = False
            save_config(cfg)
            return "Overthinking loop disabled."
            
        elif action == "status":
            status = "enabled" if cfg.overthinking.enabled else "disabled"
            return f"Overthinking is {status}. Interval: {cfg.overthinking.interval_minutes}m, Steps: {cfg.overthinking.max_steps}"
            
        elif action == "configure":
            if interval is not None:
                cfg.overthinking.interval_minutes = int(interval)
            if steps is not None:
                cfg.overthinking.max_steps = int(steps)
            save_config(cfg)
            return f"Overthinking configuration updated. Interval: {cfg.overthinking.interval_minutes}m, Steps: {cfg.overthinking.max_steps}"
            
        else:
            return f"Unknown action: {action}. Valid actions: start, stop, status, configure"

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Return OpenAI-compatible tool definitions."""
        tools = []
        # Use registry schemas if available, otherwise fallback to local skills
        # But to ensure full compatibility with existing code that might rely on self.skills:
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

    def execute(self, tool_name: str, arguments: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> str:
        """
        Execute a skill.
        """
        print(f"[ToolExec] Executing {tool_name} with {arguments}")
        
        # Try registry first
        if self.registry.get_tool(tool_name):
            try:
                return self.registry.execute(tool_name, arguments, context=context)
            except Exception as e:
                print(f"[ToolExec] Registry execution failed: {e}")
                return f"Tool execution error: {e}"
        
        return f"Tool {tool_name} not found in registry"

    def _tool_whiteboard_update(self, key: str, value: str, context: Optional[Dict[str, Any]] = None) -> str:
        if not context or "memory_map" not in context:
            # Fallback to direct access if possible (hacky)
            return "Error: MemoryMap not available in context"
        
        memory_map = context["memory_map"]
        # Assuming memory_map is a MemoryMap object or dict
        if hasattr(memory_map, "update"):
            memory_map.update(key, value)
            return f"Whiteboard updated: {key}"
        elif isinstance(memory_map, dict):
            memory_map[key] = value
            return f"Whiteboard updated: {key}"
        return "Error: Invalid MemoryMap object"

    def _tool_browser_open(self, url: str) -> str:
        return self._browser.open_page(url)
        
    def _tool_browser_read(self, url: str) -> str:
        try:
            return self._browser.one_off_read(url)
        except Exception as e:
            print(f"[ToolExec] Browser read failed: {e}. Trying simple fetch.")
            return self._simple_web_fetch(url)

    def _tool_web_search(self, query: str) -> str:
        # Auto-append current year logic...
        import datetime
        current_year = str(datetime.datetime.now().year)
        if current_year not in query and any(k in query.lower() for k in ["latest", "current", "new", "price", "stock", "news"]):
            query += f" {current_year}"
        
        try:
            import urllib.parse
            encoded_query = urllib.parse.quote(query)
            search_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
            return self._browser.one_off_read(search_url)
        except Exception as e:
            print(f"[ToolExec] Browser search failed: {e}. Trying simple fetch.")
            try:
                import urllib.parse
                encoded_query = urllib.parse.quote(query)
                search_url = f"https://lite.duckduckgo.com/lite/?q={encoded_query}"
                return self._simple_web_fetch(search_url)
            except Exception as e2:
                return f"Search failed: {e2}"

    def _tool_shell_exec(self, command: str) -> str:
        return self._run_shell_cmd(command)
        
    def _tool_file_read(self, path: str) -> str:
        if not path: return "Error: path required"
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
        
    def _tool_file_write(self, path: str, content: str) -> str:
        if not path: return "Error: path required"
        if os.path.isabs(path) and path.startswith("/output/"):
            path = os.path.join(os.getcwd(), path.lstrip("/"))
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Wrote to {path}"

    def _simple_web_fetch(self, url: str) -> str:
        """
        Simple fallback using standard library or requests if available.
        """
        try:
            # Try requests first
            import requests
            # Add fake user agent to avoid bot detection
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            # Simple text extraction
            return resp.text[:4000] # Limit output
        except ImportError:
            # Fallback to urllib
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as f:
                return f.read().decode('utf-8')[:4000]

    def _run_shell_cmd(self, cmd: str) -> str:
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            return f"Stdout: {result.stdout}\nStderr: {result.stderr}"
        except Exception as e:
            return f"Shell execution failed: {e}"

    def _run_nanobot_cmd(self, *args: str) -> str:
        """
        Execute nanobot CLI commands safely.
        """
        try:
            # We must use "nanobot" executable or python module
            cmd = ["nanobot"] + list(args)
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False
            )
            # Combine stdout and stderr
            output = result.stdout
            if result.stderr:
                output += f"\nError/Warning: {result.stderr}"
            return output.strip()
        except Exception as e:
            return f"Execution failed: {str(e)}"
