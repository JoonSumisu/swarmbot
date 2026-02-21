from typing import Dict, List, Any, Optional
import os
import re

class ToolPolicy:
    """
    Defines permissions and constraints for tool execution.
    """
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.update_config(config)

    def update_config(self, config: Dict[str, Any]):
        self.config = config or {}
        self.fs_allow_read = self.config.get("fs", {}).get("allow_read", [])
        self.fs_allow_write = self.config.get("fs", {}).get("allow_write", [])
        self.shell_allow_commands = self.config.get("shell", {}).get("allow_commands", [])
        self.shell_deny_commands = self.config.get("shell", {}).get("deny_commands", []) # Unrestricted by default

    def check_permission(self, tool_name: str, args: Dict[str, Any]) -> bool:
        """
        Check if the tool execution is allowed based on the policy.
        """
        if tool_name == "file_read":
            return self._check_fs_read(args.get("path"))
        elif tool_name == "file_write":
            return self._check_fs_write(args.get("path"))
        elif tool_name == "shell_exec":
            return self._check_shell_exec(args.get("command"))
        # Default allow for other tools (like web_search)
        return True

    def _check_fs_read(self, path: str) -> bool:
        if not path:
            return False
        abs_path = os.path.abspath(path)
        # If allow list is empty, default to allow all (or strict? let's default to loose for now but warn)
        if not self.fs_allow_read:
            return True
        return any(abs_path.startswith(os.path.abspath(p)) for p in self.fs_allow_read)

    def _check_fs_write(self, path: str) -> bool:
        if not path:
            return False
        
        # Normalize path
        abs_path = os.path.abspath(path)
        
        # If allow list is empty, deny
        if not self.fs_allow_write:
            return False
            
        # Check against allow list
        # We need to handle relative paths carefully.
        # If allow list contains ".", it means current directory.
        for p in self.fs_allow_write:
            allowed_abs = os.path.abspath(p)
            # Check if target path starts with allowed path
            if abs_path.startswith(allowed_abs):
                return True
                
        return False

    def _check_shell_exec(self, command: str) -> bool:
        if not command:
            return False
        
        # If no allow/deny lists are configured, allow everything (Unrestricted Mode)
        if not self.shell_allow_commands and not self.shell_deny_commands:
            return True
            
        cmd_base = command.split()[0]
        if cmd_base in self.shell_deny_commands:
            return False
        if self.shell_allow_commands and cmd_base not in self.shell_allow_commands:
            return False
        return True
