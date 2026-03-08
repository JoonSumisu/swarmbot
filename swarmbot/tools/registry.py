from typing import Dict, List, Any, Callable, Optional, Union
import logging
from .policy import ToolPolicy

logger = logging.getLogger(__name__)

import inspect

class ToolRegistry:
    """
    Central registry for all tools available to the Swarmbot.
    Handles tool registration, discovery, and execution with policy checks.
    """
    def __init__(self, policy_config: Optional[Dict[str, Any]] = None):
        self._tools: Dict[str, Callable] = {}
        self._schemas: Dict[str, Dict[str, Any]] = {}
        self.policy = ToolPolicy(policy_config)

    def register(self, name: str, func: Callable, schema: Dict[str, Any]):
        """
        Register a new tool with its function and schema.
        """
        if name in self._tools:
            # Downgrade to debug as re-registration is common in multi-agent setup
            logger.debug(f"Overwriting existing tool: {name}")
        else:
            logger.info(f"Registered tool: {name}")
            
        self._tools[name] = func
        self._schemas[name] = schema

    def get_tool(self, name: str) -> Optional[Callable]:
        return self._tools.get(name)

    def get_schema(self, name: str) -> Optional[Dict[str, Any]]:
        return self._schemas.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        """
        Return a list of all registered tool schemas.
        """
        return list(self._schemas.values())

    def execute(self, name: str, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Any:
        """
        Execute a tool with policy check.
        """
        if name not in self._tools:
            raise ValueError(f"Tool not found: {name}")

        # Check policy
        if not self.policy.check_permission(name, args):
            raise PermissionError(f"Tool execution denied by policy: {name} with args {args}")

        func = self._tools[name]
        try:
            sig = inspect.signature(func)
            params = sig.parameters
            accepts_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
            final_args: Dict[str, Any] = {}
            if isinstance(args, dict):
                for k, v in args.items():
                    if not isinstance(k, str):
                        continue
                    key = k.strip()
                    if not key:
                        continue
                    if accepts_var_kw or key in params:
                        final_args[key] = v
            if "context" in params:
                final_args["context"] = context
            return func(**final_args)
        except Exception as e:
            logger.error(f"Error executing tool {name}: {e}")
            raise

# Global registry instance
_registry = ToolRegistry()

def get_registry() -> ToolRegistry:
    return _registry
