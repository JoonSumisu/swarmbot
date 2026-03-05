import os
import sys
import json
import logging
from litellm import completion

logging.basicConfig(level=logging.INFO)

API_BASE = "http://100.110.110.250:8889/v1"
API_KEY = "EMPTY"
MODEL = "openai/qwen3.5-27b" # Force openai prefix to match Swarmbot behavior

# --- PROMPTS FROM DEFINITIONS.PY ---
# (Simplified versions to mimic structure but shorter for test)
STEP_ANALYSIS_PROMPT = """
You are an Analysis Worker. Load 'swarmboot.md' logic.
Your goal is to analyze the user's input using strict logical and physical constraints.

Input Prompt:
{user_input}

Output JSON:
{{
  "type": "...",
  "constraints": ["..."]
}}
"""

def test_complex_prompt_no_tools():
    print(f"\n=== TEST 3: Complex System Prompt (No Tools) ===")
    
    # 1. Prepare Messages similar to Swarmbot
    user_input = "我想洗车，洗车店距离我家 50 米，你建议我开车去还是走路去？"
    
    # Swarmbot constructs messages like:
    # [System Message (Role/Soul), History..., User Input]
    # But for a specific STEP, it might wrap it differently?
    # Let's check CoreAgent._build_messages:
    # 1. System Prompt (Role / Soul)
    # 2. History
    # 3. User Input
    
    # But loops/inference.py calls agent.step(prompt) where prompt is formatted from template.
    # So CoreAgent receives the FORMATTED prompt as user input?
    # No, CoreAgent.step(prompt) builds messages.
    # If using formatted prompt as input, the "System Prompt" in CoreAgent is generic unless overridden.
    
    # Let's assume generic Agent usage in Swarmbot:
    # It usually has a default System Prompt.
    # And the prompt passed to step() is treated as User message.
    
    formatted_prompt = STEP_ANALYSIS_PROMPT.format(user_input=user_input)
    
    messages = [
        {"role": "system", "content": "You are a helpful AI assistant."},
        {"role": "user", "content": formatted_prompt}
    ]
    
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

def test_complex_prompt_with_tools():
    print(f"\n=== TEST 4: Complex System Prompt + Tools (Schema Check) ===")
    
    user_input = "我想洗车，洗车店距离我家 50 米，你建议我开车去还是走路去？"
    formatted_prompt = STEP_ANALYSIS_PROMPT.format(user_input=user_input)
    
    messages = [
        {"role": "system", "content": "You are a helpful AI assistant."},
        {"role": "user", "content": formatted_prompt}
    ]
    
    # Complex Tool Schema (mimicking Swarmbot)
    tools = [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"}
                    },
                    "required": ["query"],
                    "additionalProperties": True # Testing the new addition
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "python_exec",
                "description": "Execute Python code.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"}
                    },
                    "required": ["code"],
                    "additionalProperties": True 
                }
            }
        }
    ]
    
    try:
        resp = completion(
            model=MODEL,
            messages=messages,
            api_base=API_BASE,
            api_key=API_KEY,
            tools=tools,
            tool_choice="auto",
            max_tokens=500
        )
        print("✅ Success!")
        print(resp.choices[0].message)
    except Exception as e:
        print(f"❌ Failed: {e}")

if __name__ == "__main__":
    test_complex_prompt_no_tools()
    test_complex_prompt_with_tools()
