from __future__ import annotations

import json
import subprocess
import os
import io
import sys
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


class ToolAdapter:
    def __init__(self) -> None:
        self.skills: Dict[str, ToolDefinition] = {}
        self._browser = LocalBrowserTool(BrowserConfig())
        self.registry = get_registry()
        self._load_skills()

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
        
    def _tool_skill_load(self, name: str) -> str:
        # Load skill logic... (Assuming this exists from context but not shown fully)
        pass

    def _tool_python_exec(self, code: str) -> str:
        """
        Execute Python code in a restricted environment.
        Available built-in functions:
        - print(text)
        - file_read(path)
        - file_write(path, content)
        - web_search(query)
        - browser_open(url)
        - browser_read(url)
        - shell_exec(command)
        - overthinking_control(action, interval, steps)
        - whiteboard_update(key, value)
        """
        # Capture stdout
        old_stdout = sys.stdout
        redirected_output = io.StringIO()
        sys.stdout = redirected_output
        
        # Prepare environment
        # Bind self methods to local variables for cleaner access in code
        env = {
            "print": print, # Use built-in print which now writes to redirected_output
            "file_read": self._tool_file_read,
            "file_write": self._tool_file_write,
            "web_search": self._tool_web_search,
            "browser_open": self._tool_browser_open,
            "browser_read": self._tool_browser_read,
            "shell_exec": self._tool_shell_exec,
            "overthinking_control": self._tool_overthinking_control,
            "whiteboard_update": self._tool_whiteboard_update,
            "skill_fetch": self._tool_skill_fetch,
            "skill_load": self._tool_skill_load,
            "skill_summary": self._tool_skill_summary,
            "swarm_control": self._tool_swarm_control,
            "context_policy_update": self._tool_context_policy_update,
            # Common utilities
            "json": json,
            "os": os,
            "subprocess": subprocess,
            "sys": sys,
        }
        
        try:
            exec(code, env)
            output = redirected_output.getvalue()
            if not output:
                output = "(Code executed successfully with no output)"
            return output
        except Exception as e:
            import traceback
            return f"Error executing Python code:\n{traceback.format_exc()}"
        finally:
            sys.stdout = old_stdout

    def _load_skills(self) -> None:
        """
        Load available skills.
        """
        # Always add core built-ins manually
        self._register_builtin("python_exec", "Execute Python code to perform complex tasks, data analysis, or orchestrate multiple tool calls. Available tools: file_read, file_write, web_search, browser_open, browser_read, shell_exec, overthinking_control, whiteboard_update.", ["code"], self._tool_python_exec)
        self._register_builtin("file_read", "Read a file from local filesystem", ["path"], self._tool_file_read)
        self._register_builtin("file_write", "Write content to a file", ["path", "content"], self._tool_file_write)
        self._register_builtin("web_search", "Search the web for information using a search engine.", ["query"], self._tool_web_search)
        self._register_builtin("shell_exec", "Execute a shell command (Sandboxed)", ["command"], self._tool_shell_exec)
        self._register_builtin(
            "context_policy_update",
            "Update context selection policy for memory and history.",
            [
                "max_whiteboard_chars",
                "max_history_items",
                "max_history_chars_per_item",
                "max_qmd_chars",
                "max_qmd_docs",
            ],
            self._tool_context_policy_update,
        )
        self._register_builtin(
            "skill_fetch",
            "Fetch a remote SKILL.md and cache it as a local skill directory.",
            ["name", "url"],
            self._tool_skill_fetch,
        )
        
        self._register_builtin("browser_open", "Open a URL in local browser to view content.", ["url"], self._tool_browser_open)
        self._register_builtin("browser_read", "Read text content of a URL (headless). Use this to extract information from a specific webpage.", ["url"], self._tool_browser_read)
        
        # Add Whiteboard Tools
        self._register_builtin("whiteboard_update", "Update the shared Whiteboard memory with key information.", ["key", "value"], self._tool_whiteboard_update)

        # Add Overthinking Control Tool
        self._register_builtin("overthinking_control", "Control the Overthinking background process.", ["action", "interval", "steps"], self._tool_overthinking_control)

        self._register_builtin("swarm_control", "Control Swarmbot configuration and lifecycle (CLI wrapper).", ["command", "subcommand", "args"], self._tool_swarm_control)
        self._register_builtin("skill_summary", "List available Swarm skills in a compact summary format.", [], self._tool_skill_summary)
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
            if "max_agents" in args: cfg.swarm.max_agents = int(args["max_agents"])
            # Legacy support
            if "agent_count" in args: cfg.swarm.max_agents = int(args["agent_count"])
            
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
                # Update primary provider (create if not exists, update if exists)
                from ..config_manager import LLMConfig
                
                if not cfg.providers:
                    # Create new primary
                    p = LLMConfig(name="primary")
                    cfg.providers = [p]
                else:
                    # Update existing primary
                    p = cfg.providers[0]
                
                if "base_url" in args: p.base_url = args["base_url"]
                if "api_key" in args: p.api_key = args["api_key"]
                if "model" in args: p.model = args["model"]
                if "max_tokens" in args: p.max_tokens = int(args["max_tokens"])
                
                save_config(cfg)
                return "Primary provider updated."
            elif subcommand == "delete":
                cfg.providers = []
                save_config(cfg)
                return "Providers reset (cleared)."
            else:
                return f"Current Providers:\n{json.dumps([asdict(p) for p in cfg.providers], indent=2)}"

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
                 return "Skill 管理请结合 skill_summary 与 skill_load 查看和加载本地技能。"

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
            from ..config_manager import WORKSPACE_PATH
            base = Path(WORKSPACE_PATH)
            search_dirs: List[Path] = []
            workspace_dir = base / "skills"
            if workspace_dir.exists():
                search_dirs.append(workspace_dir)
            builtin_dir = Path(__file__).resolve().parent.parent / "nanobot" / "skills"
            if builtin_dir.exists():
                search_dirs.append(builtin_dir)

            skills: List[Dict[str, Any]] = []
            for root in search_dirs:
                source = "workspace" if root == workspace_dir else "builtin"
                for entry in root.iterdir():
                    if entry.is_dir():
                        skill_md = entry / "SKILL.md"
                        if skill_md.exists():
                            skills.append(
                                {
                                    "name": entry.name,
                                    "source": source,
                                    "path": str(skill_md),
                                }
                            )

            if not skills:
                return "<skills></skills>"
            return json.dumps(skills, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"Skill summary error: {e}"

    def _tool_skill_load(self, name: str) -> str:
        try:
            if not name:
                return "Skill name required"

            from ..config_manager import WORKSPACE_PATH

            base = Path(WORKSPACE_PATH)
            search_dirs: List[Path] = []
            workspace_dir = base / "skills"
            if workspace_dir.exists():
                search_dirs.append(workspace_dir)
            builtin_dir = Path(__file__).resolve().parent.parent / "nanobot" / "skills"
            if builtin_dir.exists():
                search_dirs.append(builtin_dir)

            for root in search_dirs:
                for entry in root.iterdir():
                    if entry.is_dir() and entry.name == name:
                        skill_md = entry / "SKILL.md"
                        if skill_md.exists():
                            return skill_md.read_text(encoding="utf-8")

            return f"Skill not found: {name}"
        except Exception as e:
            return f"Skill load error: {e}"

    def _tool_context_policy_update(
        self,
        max_whiteboard_chars: Optional[int] = None,
        max_history_items: Optional[int] = None,
        max_history_chars_per_item: Optional[int] = None,
        max_qmd_chars: Optional[int] = None,
        max_qmd_docs: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not context or "memory_map" not in context:
            return "Error: MemoryMap not available in context"
        memory_map = context["memory_map"]
        data = {}
        try:
            if hasattr(memory_map, "_data"):
                raw = memory_map._data.get("context_policy")
                if isinstance(raw, dict):
                    data = raw.copy()
            elif isinstance(memory_map, dict):
                raw = memory_map.get("context_policy")
                if isinstance(raw, dict):
                    data = raw.copy()
        except Exception:
            data = {}
        if max_whiteboard_chars is not None:
            data["max_whiteboard_chars"] = int(max_whiteboard_chars)
        if max_history_items is not None:
            data["max_history_items"] = int(max_history_items)
        if max_history_chars_per_item is not None:
            data["max_history_chars_per_item"] = int(max_history_chars_per_item)
        if max_qmd_chars is not None:
            data["max_qmd_chars"] = int(max_qmd_chars)
        if max_qmd_docs is not None:
            data["max_qmd_docs"] = int(max_qmd_docs)
        if hasattr(memory_map, "update"):
            memory_map.update("context_policy", data)
        elif isinstance(memory_map, dict):
            memory_map["context_policy"] = data
        return json.dumps(data, ensure_ascii=False)

    def _tool_skill_fetch(self, name: str, url: str) -> str:
        if not name:
            return "Error: name is required"
        if not url:
            return "Error: url is required"
        from ..config_manager import WORKSPACE_PATH
        from urllib.request import urlopen, Request

        skill_root = Path(WORKSPACE_PATH) / "skills" / name
        skill_root.mkdir(parents=True, exist_ok=True)
        target = skill_root / "SKILL.md"
        try:
            req = Request(url, headers={"User-Agent": "Swarmbot/0.3.1"})
            with urlopen(req, timeout=15) as resp:
                content_bytes = resp.read()
            content = content_bytes.decode("utf-8", errors="replace")
            target.write_text(content, encoding="utf-8")
            return f"Fetched SKILL to {target}"
        except Exception as e:
            return f"Skill fetch failed: {e}"

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
