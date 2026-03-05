import os
import sys
import json
import logging
from litellm import completion

logging.basicConfig(level=logging.INFO)

API_BASE = "http://100.110.110.250:8889/v1"
API_KEY = "EMPTY"
MODEL = "openai/qwen3.5-27b"

def test_empty_tools_list():
    print(f"\n=== TEST 6: Empty Tools List (tools=[]) ===")
    
    messages = [{"role": "user", "content": "Hello"}]
    
    # Empty list
    tools = []
    
    try:
        print("Sending request with tools=[] and tool_choice='auto'...")
        resp = completion(
            model=MODEL,
            messages=messages,
            api_base=API_BASE,
            api_key=API_KEY,
            tools=tools,           # Empty list
            tool_choice="auto",    # This might be invalid with empty tools
            max_tokens=100
        )
        print("✅ Success!")
    except Exception as e:
        print(f"❌ Failed as expected: {e}")

if __name__ == "__main__":
    test_empty_tools_list()
