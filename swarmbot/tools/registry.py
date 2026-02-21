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
            logger.warning(f"Overwriting existing tool: {name}")
        self._tools[name] = func
        self._schemas[name] = schema
        logger.info(f"Registered tool: {name}")

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
            # Check if func accepts context or extra kwargs
            sig = inspect.signature(func)
            if "context" in sig.parameters:
                args["context"] = context
            elif any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
                # If function accepts **kwargs, we can pass context if we want, but let's be careful
                # For now, only pass if explicitly named 'context'
                pass
                
            return func(**args)
        except Exception as e:
            logger.error(f"Error executing tool {name}: {e}")
            raise

# Global registry instance
_registry = ToolRegistry()

def get_registry() -> ToolRegistry:
    return _registry
