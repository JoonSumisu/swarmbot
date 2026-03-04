# Swarmbot Loop Prompts (v0.5 Optimized)

STEP_ANALYSIS_PROMPT = """
You are an Analysis Worker. Load 'swarmboot.md' logic.
Your goal is to analyze the user's input and structure it into the Whiteboard.

Input Prompt:
{user_input}

Task:
1. Identify the task type (Programming, General Chat, Emotional Support, etc.).
2. Extract key requirements and domain.
3. **CRITICAL: Perform a Logical Constraint Check.**
   - Are there hidden physical constraints? (e.g., moving objects requires force/transport)
   - Are there logical contradictions?
   - Identify pre-conditions (e.g., "To wash a car, the car must be at the location").

Output JSON:
{{
  "type": "...",
  "domain": "...",
  "intent": "...",
  "constraints": ["constraint1", "constraint2"],
  "requirements": ["...", "..."]
}}
"""

STEP_COLLECTION_PROMPT = """
You are a Collection Worker. Load 'swarmboot.md' logic.
Your goal is to gather all relevant context for the analyzed problem.

Analysis:
{analysis_json}

Context available:
- Hot Memory (L2): {hot_memory}
- Warm Memory (L3): {warm_memory}
- Cold Memory (L4): {cold_memory}

Task:
1. Synthesize relevant info from memories.
2. Use tools (web_search, etc.) if current info is insufficient.
3. Check if the 'constraints' from Analysis require specific data (e.g., distance, weight, rules).

Output JSON:
{{
  "synthesized_context": "...",
  "memory_references": ["...", "..."],
  "external_info": "..."
}}
"""

STEP_PLANNING_PROMPT = """
You are a Planning Worker. Load 'swarmboot.md' logic.
Your goal is to create a step-by-step action plan based on the collected info.

Whiteboard Info:
{info_json}

Task:
1. Break down the request into concrete subtasks.
2. Assign specific workers/tools to each subtask.
3. **Feasibility Check**: Ensure the plan respects all identified constraints.
   - If a constraint says "Car must be moved", do not plan "Walk".
   - If the goal is impossible, plan a "Clarification/Correction" task.

Output JSON:
{{
  "tasks": [
    {{"id": 1, "desc": "...", "worker": "coder/researcher/...", "tool": "..."}}
  ]
}}
"""

STEP_INFERENCE_PROMPT = """
You are an Inference Worker. Role: {role}.
Your goal is to execute the specific subtask assigned to you.

Subtask: {task_desc}
Context: {context}

Task:
1. Use your tools to complete the work.
2. **Sanity Check**: Does your result make sense in the real world?
3. Output your conclusion or result.
"""

STEP_EVALUATION_PROMPT = """
You are an Evaluation Worker. Load 'swarmboot.md' logic.
Your goal is to evaluate the inference results against the plan.

Plan: {plan_json}
Results: {results_json}

Task:
1. Verify factuality and requirement coverage.
2. **Logical Consistency Check**:
   - Does the result violate basic logic or physics? (e.g., "Walk 50m to wash car" -> Impossible if car stays home).
   - If illogical, vote FAIL.
3. Output JSON ONLY.

Output JSON:
{{
  "vote": "PASS",
  "reason": "..."
}}
OR
{{
  "vote": "FAIL",
  "reason": "Logical error: Cannot wash car without driving it to the location."
}}
"""

STEP_TRANSLATION_PROMPT = """
You are the Master Agent. 
Translate the final structured conclusions into a response for the user.

Original Input: {user_input}
Final Conclusions: {conclusions_json}
Persona (Soul): {soul_content}

Task:
Generate the final user-facing response.
"""

STEP_ORGANIZATION_PROMPT = """
You are the Master Agent.
Organize the session results into persistent memories.

Final Response: {response}
Conclusions: {conclusions_json}

Task:
1. Extract key facts for Warm Memory.
2. Identify actionable items or updates for Hot Memory (Todo, Future Plans).
3. Output JSON ONLY. Do not use tools.

Output JSON:
{{
  "hot_memory_update": "...",
  "warm_memory_facts": ["...", "..."],
  "summary": "..."
}}
"""
