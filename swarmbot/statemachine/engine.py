from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..core.agent import CoreAgent


@dataclass
class State:
    name: str
    agent: CoreAgent
    description: str
    transitions: Dict[str, str] = field(default_factory=dict)  # condition -> next_state_name
    on_enter: Optional[Callable[[Dict[str, Any]], str]] = None


class StateMachine:
    """
    A dynamic state machine for agent orchestration.
    Allows agents to decide the next state based on output analysis.
    """

    def __init__(self, initial_state: str, context: Dict[str, Any] | None = None) -> None:
        self.states: Dict[str, State] = {}
        self.current_state: str = initial_state
        self.context: Dict[str, Any] = context or {}
        self.history: List[str] = []

    def add_state(self, state: State) -> None:
        self.states[state.name] = state

    def run(self, user_input: str, max_steps: int = 10) -> str:
        step = 0
        final_output = ""
        
        while step < max_steps:
            current_node = self.states.get(self.current_state)
            if not current_node:
                return f"Error: State {self.current_state} not found."

            # Execute Agent Step
            # Inject context into prompt
            context_str = json.dumps(self.context, ensure_ascii=False)
            prompt = (
                f"Current State: {current_node.name}\n"
                f"Task Description: {current_node.description}\n"
                f"Global Context: {context_str}\n"
                f"User Input: {user_input}\n\n"
                "Please execute the task. "
                "If you need to transition, end your response with 'NEXT: <condition>'."
            )
            
            response = current_node.agent.step(prompt)
            self.history.append(f"[{current_node.name}] {response}")
            final_output = response

            # Check transitions
            transition_found = False
            
            # Simple keyword based transition logic (can be upgraded to LLM router)
            # Format expected in response: "NEXT: condition" or implicit logic
            # Here we use a simpler approach: Ask LLM to decide next step if multiple transitions exist
            
            if current_node.transitions:
                if len(current_node.transitions) == 1 and "default" in current_node.transitions:
                     self.current_state = current_node.transitions["default"]
                     transition_found = True
                else:
                    # Dynamic Routing
                    router_prompt = (
                        f"Based on the last response:\n'{response}'\n"
                        f"Which condition is met? Options: {list(current_node.transitions.keys())}\n"
                        "Return only the condition name."
                    )
                    # We reuse the current agent for routing decision to save resources, 
                    # or could use a dedicated router agent.
                    decision = current_node.agent.step(router_prompt).strip()
                    
                    if decision in current_node.transitions:
                        self.current_state = current_node.transitions[decision]
                        transition_found = True
                    # FIX: Don't auto-fallback to default if explicit check failed but transition exists
                    # However, if the agent returned something else, we MIGHT want fallback
                    elif "default" in current_node.transitions:
                        self.current_state = current_node.transitions["default"]
                        transition_found = True
            
            if not transition_found:
                # End state
                # FIX: Ensure we don't loop forever if no transition found but step limit not reached
                # Actually break is correct here.
                break
                
            step += 1
            
        return "\n\n".join(self.history)
