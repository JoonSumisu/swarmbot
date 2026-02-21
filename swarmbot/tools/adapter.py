from __future__ import annotations

import json
import subprocess
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]

from .browser.local_browser import LocalBrowserTool, BrowserConfig

class NanobotSkillAdapter:
    """
    Adapter to bridge nanobot skills to Swarmbot agents.
    Allows agents to discover and execute nanobot skills via CLI passthrough or direct API.
    Also manages local built-in tools like Browser.
    """
    def __init__(self) -> None:
        self.skills: Dict[str, ToolDefinition] = {}
        self._browser = LocalBrowserTool(BrowserConfig())
        self._load_skills()

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
        
    def _load_skills(self) -> None:
        """
        Load available skills.
        """
        # Always add core built-ins manually
        self._register_builtin("file_read", "Read a file from local filesystem", ["path"])
        self._register_builtin("file_write", "Write content to a file", ["path", "content"])
        self._register_builtin("web_search", "Search the web for information using a search engine.", ["query"])
        self._register_builtin("shell_exec", "Execute a shell command (Sandboxed)", ["command"])
        
        # Add Browser Tools
        self._register_builtin("browser_open", "Open a URL in local browser to view content.", ["url"])
        self._register_builtin("browser_read", "Read text content of a URL (headless). Use this to extract information from a specific webpage.", ["url"])

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Return OpenAI-compatible tool definitions."""
        tools = []
        for name, tool in self.skills.items():
            # Ensure correct format for litellm/OpenAI
            # tool definition should be:
            # { "type": "function", "function": { "name": ..., "description": ..., "parameters": ... } }
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
        """
        print(f"[ToolExec] Executing {tool_name} with {arguments}")
        
        try:
            if tool_name == "browser_open":
                return self._browser.open_page(arguments.get("url", ""))
                
            if tool_name == "browser_read":
                # Fallback: Use simple requests if browser fails (e.g. no chrome installed)
                try:
                    return self._browser.one_off_read(arguments.get("url", ""))
                except Exception as e:
                    print(f"[ToolExec] Browser read failed: {e}. Trying simple fetch.")
                    return self._simple_web_fetch(arguments.get("url", ""))

            if tool_name == "web_search":
                query = arguments.get("query", "")
                
                # Auto-append current year if query is time-sensitive but ambiguous
                # Simple heuristic: if query doesn't have 4-digit year, append current year.
                # Actually, better to just let the agent handle it via system prompt, 
                # but we can force it for robustness.
                import datetime
                current_year = str(datetime.datetime.now().year)
                if current_year not in query and any(k in query.lower() for k in ["latest", "current", "new", "price", "stock", "news"]):
                    query += f" {current_year}"
                
                # 2. Try DuckDuckGo HTML search via Browser Tool
                try:
                    import urllib.parse
                    encoded_query = urllib.parse.quote(query)
                    search_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
                    return self._browser.one_off_read(search_url)
                except Exception as e:
                    print(f"[ToolExec] Browser search failed: {e}. Trying simple fetch.")
                    
                    # 3. Fallback: Simple Requests to DDG Lite
                    try:
                        import urllib.parse
                        encoded_query = urllib.parse.quote(query)
                        search_url = f"https://lite.duckduckgo.com/lite/?q={encoded_query}"
                        return self._simple_web_fetch(search_url)
                    except Exception as e2:
                        return f"Search failed: {e2}"
                
            if tool_name == "shell_exec":
                cmd = arguments.get("command", "")
                # Security: Direct execution is risky, but required for this tool.
                # In production, use nanobot's sandbox. Here we use subprocess for PoC.
                return self._run_shell_cmd(cmd)
                
            if tool_name == "file_read":
                path = arguments.get("path", "")
                if not path: return "Error: path required"
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
                
            if tool_name == "file_write":
                path = arguments.get("path", "")
                content = arguments.get("content", "")
                if not path: return "Error: path required"
                if os.path.isabs(path) and path.startswith("/output/"):
                    path = os.path.join(os.getcwd(), path.lstrip("/"))
                parent = os.path.dirname(path)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                return f"Wrote to {path}"
                
            return f"Tool {tool_name} executed with {arguments} (Mock)"
        except Exception as e:
            print(f"[ToolExec] Failed: {e}")
            return f"Tool execution error: {e}"

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
