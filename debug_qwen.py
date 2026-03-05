import os
import sys
import json
import logging
from litellm import completion

# Configure logging
logging.basicConfig(level=logging.INFO)

API_BASE = "http://100.110.110.250:8889/v1"
API_KEY = "EMPTY"  # Usually empty for local vLLM/Ollama
MODEL = "qwen3.5-27b"

def test_simple_chat():
    print(f"\n=== TEST 1: Simple Chat (No Tools) ===")
    messages = [{"role": "user", "content": "Hello, who are you?"}]
    try:
        resp = completion(
            model=f"openai/{MODEL}",
            messages=messages,
            api_base=API_BASE,
            api_key=API_KEY,
            max_tokens=100
        )
        print("✅ Success!")
        print(resp.choices[0].message.content)
    except Exception as e:
        print(f"❌ Failed: {e}")

def test_chat_with_tools():
    print(f"\n=== TEST 2: Chat with Tools (Schema Check) ===")
    messages = [{"role": "user", "content": "What is the weather in Beijing?"}]
    
    # Minimal Tool Schema
    tools = [{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"}
                },
                "required": ["location"]
            }
        }
    }]
    
    try:
        resp = completion(
            model=f"openai/{MODEL}",
            messages=messages,
            api_base=API_BASE,
            api_key=API_KEY,
            tools=tools,
            tool_choice="auto",
            max_tokens=100
        )
        print("✅ Success!")
        print(resp.choices[0].message)
    except Exception as e:
        print(f"❌ Failed: {e}")

if __name__ == "__main__":
    test_simple_chat()
    test_chat_with_tools()
