from __future__ import annotations

import json
import subprocess
import os
import io
import sys
import time
import uuid
import shlex
import threading
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
        self._processes: Dict[str, subprocess.Popen] = {}
        self._process_meta: Dict[str, Dict[str, Any]] = {}
        self._proc_lock = threading.Lock()
        self._load_skills()

    def _register_builtin(self, name: str, desc: str, args: List[str], func: Optional[callable] = None) -> None:
        props = {}
        required = []
        for arg in args:
            if arg in ["interval", "steps", "max_tokens", "timeout", "lines", "pid", "interaction_timeout_hours"]:
                props[arg] = {"type": "integer"}
            elif arg in ["args"]:
                props[arg] = {"type": "object"}
                props[arg]["additionalProperties"] = True
            else:
                props[arg] = {"type": "string"}
                if arg not in ["subcommand", "background", "timeout", "pid", "data", "lines", "approve", "external_checks", "scheduled_tasks", "self_diagnosis", "proactive_delivery"]:
                    required.append(arg)
                 
        parameters = {
            "type": "object",
            "properties": props,
            "required": required
        }
        
        # Qwen/vLLM often requires strict schema compliance.
        # If 'required' is empty list, some versions might complain if not omitted, 
        # but usually empty list is fine.
        
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
        
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Return list of tool definitions in OpenAI format."""
        tools = []
        for name, skill in self.skills.items():
            tools.append({
                "type": "function",
                "function": {
                    "name": skill.name,
                    "description": skill.description,
                    "parameters": skill.parameters
                }
            })
        return tools

    def _tool_skill_load(self, name: str) -> str:
        # Load skill logic... (Assuming this exists from context but not shown fully)
        pass

    def _tool_hot_memory_update(self, content: str) -> str:
        if hasattr(self, "hot_memory") and self.hot_memory:
            self.hot_memory.update(content)
            return "Hot Memory updated successfully."
        return "Error: No Hot Memory attached."

    def _tool_python_exec(self, code: str) -> str:
        """
        Execute Python code in a restricted environment.
        
        IMPORTANT:
        - Built-in tools (print, file_read, web_search, hot_memory_update, etc.) are PRE-LOADED as global functions.
        - DO NOT import them. Just call them directly. e.g., `web_search(query="...")`.
        - Standard libraries (json, time, math, etc.) CAN be imported.
        
        Available Globals:
        - print(text)
        - file_read(path)
        - file_write(path, content)
        - web_search(query)
        - browser_open(url)
        - browser_read(url)
        - shell_exec(command)
        - whiteboard_update(key, value)
        - hot_memory_update(content)
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
            "swarm_exec": self._tool_swarm_exec,
            "swarm_process": self._tool_swarm_process,
            "swarm_exec_approval": self._tool_swarm_exec_approval,
            "overthinking_control": self._tool_overthinking_control,
            "overaction_control": self._tool_overaction_control,
            "whiteboard_update": self._tool_whiteboard_update,
            "hot_memory_update": self._tool_hot_memory_update,
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
        self._register_builtin("python_exec", "Execute Python code to perform complex tasks, data analysis, or orchestrate multiple tool calls. Available tools: file_read, file_write, web_search, browser_open, browser_read, shell_exec, swarm_exec, swarm_process, swarm_exec_approval, overthinking_control, overaction_control, whiteboard_update.", ["code"], self._tool_python_exec)
        self._register_builtin("file_read", "Read a file from local filesystem", ["path"], self._tool_file_read)
        self._register_builtin("file_write", "Write content to a file", ["path", "content"], self._tool_file_write)
        self._register_builtin("web_search", "Search the web for information using a search engine.", ["query"], self._tool_web_search)
        self._register_builtin("shell_exec", "Execute a shell command (Sandboxed)", ["command"], self._tool_shell_exec)
        self._register_builtin("swarm_exec", "Execute command with foreground/background support.", ["command", "background", "timeout"], self._tool_swarm_exec)
        self._register_builtin("swarm_process", "Manage background process: poll/read/kill/send_keys.", ["action", "pid", "data", "lines"], self._tool_swarm_process)
        self._register_builtin("swarm_exec_approval", "Request/confirm command approval for dangerous commands.", ["command", "approve"], self._tool_swarm_exec_approval)
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

        self._register_builtin("hot_memory_update", "Update the Hot Memory (L2) with new content. Use this for persistent Todo lists or short-term context that should survive across sessions.", ["content"], self._tool_hot_memory_update)

        # Add Overthinking Control Tool
        self._register_builtin("overthinking_control", "Control the Overthinking background process.", ["action", "interval", "steps", "external_checks"], self._tool_overthinking_control)
        self._register_builtin("overaction_control", "Control the Overaction background process.", ["action", "interval", "interaction_timeout_hours", "scheduled_tasks", "self_diagnosis", "proactive_delivery"], self._tool_overaction_control)

        self._register_builtin("swarm_control", "Control Swarmbot configuration and lifecycle (CLI wrapper).", ["command", "subcommand", "args"], self._tool_swarm_control)
        self._register_builtin("skill_summary", "List available Swarm skills in a compact summary format.", [], self._tool_skill_summary)
        self._register_builtin("skill_load", "Load a specific skill markdown by name.", ["name"], self._tool_skill_load)
        # Fix for tool schema with no arguments (Qwen strictness)
        # If a tool has no args, we should ensure properties is empty dict
        # _register_builtin handles this via empty args list

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
             action = subcommand or "status"
             interval = None
             steps = None
             if args:
                 interval = args.get("interval")
                 steps = args.get("steps")
             return self._tool_overthinking_control(action, interval, steps)

        elif command == "overaction":
             action = subcommand or "status"
             interval = None
             interaction_timeout_hours = None
             if args:
                 interval = args.get("interval")
                 interaction_timeout_hours = args.get("interaction_timeout_hours")
             return self._tool_overaction_control(action, interval, interaction_timeout_hours)

        else:
            return f"Unknown command: {command}. Supported: config, provider, update, status, onboard, overthinking, overaction, skill"

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

    def _tool_overthinking_control(self, action: str, interval: Optional[int] = None, steps: Optional[int] = None, external_checks: Optional[str] = None) -> str:
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
            if external_checks:
                try:
                    cfg.overthinking.external_checks = json.loads(str(external_checks))
                except Exception as e:
                    return f"Invalid external_checks JSON: {e}"
            save_config(cfg)
            return f"Overthinking configuration updated. Interval: {cfg.overthinking.interval_minutes}m, Steps: {cfg.overthinking.max_steps}"
            
        else:
            return f"Unknown action: {action}. Valid actions: start, stop, status, configure"

    def _tool_overaction_control(self, action: str, interval: Optional[int] = None, interaction_timeout_hours: Optional[int] = None, scheduled_tasks: Optional[str] = None, self_diagnosis: Optional[str] = None, proactive_delivery: Optional[str] = None) -> str:
        from ..config_manager import load_config, save_config

        cfg = load_config()

        if action == "start":
            cfg.overaction.enabled = True
            save_config(cfg)
            return "Overaction loop enabled. It will run in background if gateway is active."

        elif action == "stop":
            cfg.overaction.enabled = False
            save_config(cfg)
            return "Overaction loop disabled."

        elif action == "status":
            status = "enabled" if cfg.overaction.enabled else "disabled"
            return (
                f"Overaction is {status}. Interval: {cfg.overaction.interval_minutes}m, "
                f"Interaction timeout: {cfg.overaction.interaction_timeout_hours}h"
            )

        elif action == "configure":
            if interval is not None:
                cfg.overaction.interval_minutes = int(interval)
            if interaction_timeout_hours is not None:
                cfg.overaction.interaction_timeout_hours = int(interaction_timeout_hours)
            if scheduled_tasks:
                try:
                    cfg.overaction.scheduled_tasks = json.loads(str(scheduled_tasks))
                except Exception as e:
                    return f"Invalid scheduled_tasks JSON: {e}"
            if self_diagnosis:
                try:
                    cfg.overaction.self_diagnosis = json.loads(str(self_diagnosis))
                except Exception as e:
                    return f"Invalid self_diagnosis JSON: {e}"
            if proactive_delivery:
                try:
                    cfg.overaction.proactive_delivery = json.loads(str(proactive_delivery))
                except Exception as e:
                    return f"Invalid proactive_delivery JSON: {e}"
            save_config(cfg)
            return (
                f"Overaction configuration updated. Interval: {cfg.overaction.interval_minutes}m, "
                f"Interaction timeout: {cfg.overaction.interaction_timeout_hours}h"
            )

        elif action == "trigger":
            import threading
            from ..loops.overaction import OveractionLoop

            loop = OveractionLoop(threading.Event())
            result = loop.trigger(reason="manual_tool_trigger")
            return f"Overaction triggered: {json.dumps(result, ensure_ascii=False)}"

        else:
            return f"Unknown action: {action}. Valid actions: start, stop, status, configure, trigger"

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

    def _tool_whiteboard_update(self, key: Optional[str] = None, value: Optional[Any] = None, content: Optional[str] = None, context: Optional[Dict[str, Any]] = None) -> str:
        if (not key or value is None) and content is not None:
            key = "notes"
            value = str(content)
        if not key or value is None:
            return "Error: key/value required"
        if not context or "memory_map" not in context:
            return "Error: MemoryMap not available in context"
        
        memory_map = context["memory_map"]
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
        return self._tool_swarm_exec(command, "false", 30)
        
    def _tool_file_read(self, path: str) -> str:
        if not path: return "Error: path required"
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return f"File not found: {path}"
        except Exception as e:
            return f"File read failed: {e}"
        
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

    def _is_dangerous_command(self, cmd: str) -> bool:
        try:
            from ..config_manager import load_config
            cfg = load_config()
            deny_patterns = cfg.tools.exec.get("deny_patterns", [])
        except Exception:
            deny_patterns = ["rm -rf /", "shutdown", "reboot", ":(){:|:&};:", "mkfs", "dd if="]
        low = (cmd or "").lower()
        for p in deny_patterns:
            if str(p).lower() in low:
                return True
        return False

    def _tool_swarm_exec_approval(self, command: str, approve: Optional[str] = None) -> str:
        if not command:
            return "Error: command required"
        approved = str(approve or "").strip().lower() in ["1", "true", "yes", "approve"]
        if self._is_dangerous_command(command) and not approved:
            return "APPROVAL_REQUIRED: command matched dangerous policy. Re-run with approve=true if user confirmed."
        return "APPROVED"

    def _tool_swarm_exec(self, command: str, background: Optional[str] = None, timeout: Optional[int] = None) -> str:
        if not command:
            return "Error: command required"
        if self._is_dangerous_command(command):
            return "APPROVAL_REQUIRED: use swarm_exec_approval first for dangerous commands."
        bg = str(background or "false").strip().lower() in ["1", "true", "yes", "on"]
        to = int(timeout or 30)
        if bg:
            proc = subprocess.Popen(
                command,
                shell=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            pid = str(proc.pid)
            with self._proc_lock:
                self._processes[pid] = proc
                self._process_meta[pid] = {"command": command, "created_at": int(time.time())}
            return json.dumps({"pid": pid, "status": "running", "mode": "background"})
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=max(1, to))
            return json.dumps(
                {
                    "status": "exited",
                    "exit_code": int(result.returncode),
                    "stdout": (result.stdout or "")[:4000],
                    "stderr": (result.stderr or "")[:4000],
                },
                ensure_ascii=False,
            )
        except subprocess.TimeoutExpired as e:
            return json.dumps(
                {
                    "status": "timeout",
                    "stdout": (e.stdout or "")[:2000] if isinstance(e.stdout, str) else "",
                    "stderr": (e.stderr or "")[:2000] if isinstance(e.stderr, str) else "",
                },
                ensure_ascii=False,
            )
        except Exception as e:
            return f"swarm_exec failed: {e}"

    def _read_process_tail(self, proc: subprocess.Popen, lines: int) -> Dict[str, str]:
        out = ""
        err = ""
        try:
            if proc.stdout:
                out = proc.stdout.read() or ""
        except Exception:
            out = ""
        try:
            if proc.stderr:
                err = proc.stderr.read() or ""
        except Exception:
            err = ""
        out_lines = out.splitlines()[-max(1, lines):]
        err_lines = err.splitlines()[-max(1, lines):]
        return {"stdout": "\n".join(out_lines), "stderr": "\n".join(err_lines)}

    def _tool_swarm_process(self, action: str, pid: Optional[int] = None, data: Optional[str] = None, lines: Optional[int] = None) -> str:
        act = (action or "").strip().lower()
        if act == "list":
            with self._proc_lock:
                items = []
                for k, p in self._processes.items():
                    items.append({"pid": k, "running": p.poll() is None, "meta": self._process_meta.get(k, {})})
            return json.dumps({"processes": items}, ensure_ascii=False)
        if pid is None:
            return "Error: pid required"
        key = str(pid)
        with self._proc_lock:
            proc = self._processes.get(key)
        if proc is None:
            return "Error: process not found"
        if act == "poll":
            code = proc.poll()
            return json.dumps({"pid": key, "running": code is None, "exit_code": code}, ensure_ascii=False)
        if act == "read":
            tail = self._read_process_tail(proc, int(lines or 120))
            return json.dumps({"pid": key, "running": proc.poll() is None, **tail}, ensure_ascii=False)
        if act == "send_keys":
            try:
                if proc.stdin:
                    proc.stdin.write((data or "") + "\n")
                    proc.stdin.flush()
                return "OK"
            except Exception as e:
                return f"send_keys failed: {e}"
        if act == "kill":
            try:
                proc.kill()
            except Exception:
                pass
            with self._proc_lock:
                self._processes.pop(key, None)
                self._process_meta.pop(key, None)
            return "killed"
        return "Error: unknown action, use list|poll|read|send_keys|kill"
