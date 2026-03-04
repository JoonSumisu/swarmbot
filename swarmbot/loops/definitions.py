# Swarmbot Loop Prompts (v0.6 Logic Enhanced)

# ------------------------------------------------------------------
# INFERENCE LOOP PROMPTS
# ------------------------------------------------------------------

STEP_ANALYSIS_PROMPT = """
You are an Analysis Worker. Load 'swarmboot.md' logic.
Your goal is to analyze the user's input using strict logical and physical constraints.

Input Prompt:
{user_input}

Task:
1. **Goal Identification**: What is the ultimate state change desired? (e.g., "Car becomes clean").
2. **Object/Location State Analysis**:
   - Where is the subject (User)? Where is the object (Car)?
   - Where does the action need to take place?
   - **CRITICAL**: If the action requires the object to be at a specific location, how does it get there?
3. **Modal/Physical Constraints**:
   - Necessity (□): What *must* happen for the goal to be achieved? (e.g., "Car must move to wash").
   - Possibility (◇): What implies a failure? (e.g., "Walking leaves car behind").

Output JSON:
{{
  "type": "...",
  "domain": "...",
  "intent": "...",
  "physical_states": {{
    "current_location": "...",
    "target_location": "...",
    "object_to_move": "..."
  }},
  "constraints": ["..."],
  "requirements": ["..."]
}}
"""

STEP_COLLECTION_PROMPT = """
You are a Collection Worker. Load 'swarmboot.md' logic.
Your goal is to gather context and verify physical assumptions.

Analysis:
{analysis_json}

Task:
1. **Epistemic Check**: Do we know the location of the car? Do we know if "walking" transports the car?
2. **Constraint Verification**: confirm if the proposed action (e.g., walking) violates the necessary physical constraint (moving the car).
3. **Synthesize**: Combine facts to support or refute the user's options.

Output JSON:
{{
  "synthesized_context": "...",
  "verification_of_constraints": "...",
  "external_info": "..."
}}
"""

STEP_PLANNING_PROMPT = """
You are a Planning Worker. Load 'swarmboot.md' logic.
Your goal is to create a concrete execution plan.

Whiteboard Info:
{info_json}

Task:
1. **Strategy Selection**: Choose the path that satisfies ALL physical constraints.
   - If Option A (Walk) violates Constraint X (Car must move), discard it or flag it as impossible.
   - If Option B (Drive) satisfies constraints, prioritize it despite costs.
2. **Task Generation**: Create specific reasoning tasks to explain *why* an option is chosen.
   - Do NOT create generic "analysis" tasks. Create specific checks like "Verify if walking transports vehicle".

Output JSON:
{{
  "strategy_rationale": "...",
  "tasks": [
    {{"id": 1, "desc": "Check if walking moves the car to the destination", "worker": "reasoner", "tool": "none"}},
    {{"id": 2, "desc": "Compare total time including vehicle transport", "worker": "analyst", "tool": "none"}}
  ]
}}
"""

STEP_INFERENCE_PROMPT = """
You are an Inference Worker. Role: {role}.
Your goal is to execute the subtask using Proof Theory and rigorous reasoning.

Subtask: {task_desc}
Context: {context}

Task:
1. **Derivation**: Treat the subtask as a theorem to be proved or a goal to be derived.
2. **Execution**: Use tools to perform the necessary steps.
3. **Sanity Check**: Verify the result against real-world physics and logic.

Output your conclusion or result.
"""

STEP_EVALUATION_PROMPT = """
You are an Evaluation Worker. Load 'swarmboot.md' logic.
Your goal is to evaluate results using Model Checking and Logic Verification.

Plan: {plan_json}
Results: {results_json}

Task:
1. **Model Checking**: Treat the Plan as the "Specification" and the Results as the "System Model". Does Model |= Specification?
2. **Logical Consistency**: Check for contradictions.
3. **Factuality**: Verify against known truths.
4. Vote PASS only if logical and factual integrity is maintained.

Output JSON ONLY:
{{
  "vote": "PASS",
  "reason": "..."
}}
OR
{{
  "vote": "FAIL",
  "reason": "Logical error: ..."
}}
"""

STEP_TRANSLATION_PROMPT = """
You are the Master Agent.
Translate the logical conclusions into a natural, user-friendly response.

Original Input: {user_input}
Final Conclusions: {conclusions_json}
Persona (Soul): {soul_content}

Task:
Synthesize the rigorous logical analysis into a clear, empathetic, and helpful response.
Maintain the persona but ensure the underlying logic is sound.
"""

STEP_ORGANIZATION_PROMPT = """
You are the Master Agent.
Organize results using Cybernetics (Feedback Loop).

Final Response: {response}
Conclusions: {conclusions_json}

Task:
1. **Feedback Generation**: Identify what went well and what failed (Error Signal).
2. **Memory Extraction**: Extract key facts for Warm Memory.
3. **Actionable Updates**: Identify updates for Hot Memory (Todo).

Output JSON:
{{
  "hot_memory_update": "...",
  "warm_memory_facts": ["...", "..."],
  "feedback_signal": "..."
}}
"""

# ------------------------------------------------------------------
# OVERTHINKING LOOP PROMPTS
# ------------------------------------------------------------------

OVERTHINKING_PROMPT = """
You are the Overthinker.
Your goal is to compress and archive memory using Abstraction and Pattern Recognition.

Hot Memory:
{hot_content}

Warm Memory (Today):
{warm_content}

Task:
1. **Pattern Recognition**: Identify recurring themes or logical structures across the memories.
2. **Abstraction**: Compress specific details into general Rules or Theories.
3. **Archive**: Select high-value Knowledge for Cold Memory (QMD).

Output JSON ONLY. Do not include thinking process or markdown text outside the JSON block.

Output JSON:
{{
  "entries": [
    {{"content": "...", "type": "experience/theory/fact"}}
  ]
}}
"""

# ------------------------------------------------------------------
# OVERACTION LOOP PROMPTS
# ------------------------------------------------------------------

OVERACTION_REFINE_PROMPT = """
You are the Overactor (Evolution Agent).
Your goal is to refine knowledge using Dialectic Reasoning (Thesis-Antithesis-Synthesis).

Recent QMD Entries:
{recent_qmd}

Task:
1. **Critique**: Challenge the existing entries. Are they complete? Are they accurate?
2. **Supplement**: Use 'web_search' to find supporting or contradicting evidence.
3. **Synthesis**: Rewrite the entries to be more robust and comprehensive.

Output your actions or refined entries.
"""

OVERACTION_OPT_PROMPT = """
You are the Overactor (System Optimizer).
Your goal is to optimize the system using Cybernetics (Self-Regulation).

Task:
1. **System Diagnosis**: Analyze recent performance.
2. **Control Action**: Suggest updates to 'swarmboot.md' (Rules) or 'hot_memory.md' (Context) to improve stability or efficiency.

Output JSON:
{{
  "todo": "...",
  "boot_update": "..."
}}
"""
