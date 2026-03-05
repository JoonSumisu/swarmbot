import os
import sys
import json
import logging
from litellm import completion

logging.basicConfig(level=logging.INFO)

API_BASE = "http://100.110.110.250:8889/v1"
API_KEY = "EMPTY"
MODEL = "openai/qwen3.5-27b"

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

def test_full_core_agent_prompt():
    print(f"\n=== TEST 5: Full CoreAgent Prompt Construction ===")
    
    # Simulate CoreAgent._build_messages logic
    
    # 1. System Content (truncated simulation)
    role_desc = "You are Swarmbot... You possess the following skills: ..."
    system_instructions = "【记忆与白板分层】\n..." * 50 # Make it long
    system_content = f"{role_desc}\n{system_instructions}"
    if len(system_content) > 6000:
        system_content = system_content[:6000]
        
    messages = [{"role": "system", "content": system_content}]
    
    # 2. History (Simulate some context)
    # Swarmbot history items are dicts, usually just content?
    # CoreAgent: item.get("content", "").strip()
    # It constructs: {"role": "user", "content": content}
    # WAIT! CoreAgent puts history as 'user' role ALWAYS?
    # Yes: messages.append({"role": "user", "content": content})
    # If history contains previous assistant replies, they are marked as 'user'?
    # That might be the issue for Qwen!
    
    history_content = "Previous analysis result: {...json...}"
    messages.append({"role": "user", "content": history_content})
    
    # 3. User Input (The Step Prompt)
    user_input = STEP_PLANNING_PROMPT.format(info_json='{"some": "data"}')
    messages.append({"role": "user", "content": user_input})
    
    # 4. Debug: Check role sequence
    print("Message Roles:", [m["role"] for m in messages])
    # Expected: System, User, User
    # Qwen might dislike consecutive Users without Assistant in between?
    # Or maybe it's fine.
    
    try:
        resp = completion(
            model=MODEL,
            messages=messages,
            api_base=API_BASE,
            api_key=API_KEY,
            max_tokens=500
        )
        print("✅ Success!")
        print(resp.choices[0].message.content[:100] + "...")
    except Exception as e:
        print(f"❌ Failed: {e}")

if __name__ == "__main__":
    test_full_core_agent_prompt()
