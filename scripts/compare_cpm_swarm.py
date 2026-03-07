
import json
import time
import io
from typing import List, Dict, Any
from contextlib import redirect_stdout
from modelscope.msdatasets import MsDataset
from swarmbot.config_manager import load_config
from swarmbot.core.agent import CoreAgent, AgentContext
from swarmbot.memory.cold_memory import ColdMemory
from swarmbot.llm_client import OpenAICompatibleClient

# --- Mock Adapter for Dynamic Tools ---
class MockToolAdapter:
    def __init__(self, tools: List[Dict]):
        self.tools = tools
        self.registry = self # Mock registry to support get_tool check
    
    def get_tool_definitions(self) -> List[Dict]:
        return self.tools
    
    def get_tool(self, name: str):
        # Return a dummy function so agent thinks tool exists
        return lambda **kwargs: f"Mock execution of {name}"


# --- Evaluation Logic ---

def run_comparison(num_samples=20):
    # 1. Setup
    print("Initializing...")
    cfg = load_config()
    # Ensure using agentcpm-explore as requested
    cfg.providers[0].model = 'agentcpm-explore' 
    
    try:
        llm = OpenAICompatibleClient.from_provider(providers=cfg.providers)
        model_name = cfg.providers[0].model
        print(f"Model: {model_name}")
    except Exception as e:
        print(f"LLM Init Failed: {e}")
        return

    # 2. Load Data
    print("Loading dataset...")
    try:
        ds = MsDataset.load('evalscope/GeneralFunctionCall-Test', split='test')
    except Exception as e:
        print(f"Dataset Load Failed: {e}")
        return

    print(f"Dataset size: {len(ds)}. Testing first {num_samples} samples.")
    
    results = []
    
    # 3. Iterate
    for i in range(num_samples):
        sample = ds[i]
        
        # Parse tools
        tools_json = sample.get('tools', '[]')
        try:
            tools = json.loads(tools_json) if isinstance(tools_json, str) else tools_json
        except:
            tools = []
            
        # Parse messages
        messages = sample.get('messages', [])
        if isinstance(messages, str):
            messages = json.loads(messages)
            
        should_call = sample.get('should_call_tool', False)
        
        # Extract inputs
        if not messages:
            continue
            
        # Standardize history and last input
        # Benchmark format: [System, User, Assistant, ..., User]
        # We assume last message is User for the query
        if messages[-1]['role'] != 'user':
            # Skip if not ending in user query
            continue
            
        query = messages[-1]['content']
        history = messages[:-1]
        
        # --- Run Pure CPM ---
        start_t = time.time()
        pure_call = False
        pure_tool_name = None
        
        try:
            # Direct LLM call
            # We pass full history + tools
            # Note: Swarmbot Agent usually adds its own system prompt. 
            # Pure CPM should just use the benchmark's messages (which include system prompt).
            
            # OpenAI API format for tools
            formatted_tools = []
            for t in tools:
                if 'function' in t:
                    formatted_tools.append(t)
                else:
                    # If format is different, wrap it (EvalScope usually follows OpenAI format)
                    formatted_tools.append({"type": "function", "function": t})
            
            resp = llm.completion(
                messages=messages,
                tools=formatted_tools if formatted_tools else None
            )
            msg = resp.choices[0].message
            if msg.tool_calls:
                pure_call = True
                pure_tool_name = msg.tool_calls[0].function.name
        except Exception as e:
            print(f"Pure CPM Error on {i}: {e}")
            
        pure_time = time.time() - start_t
        
        # --- Run Swarmbot + CPM ---
        start_t = time.time()
        swarm_call = False
        swarm_tool_name = None
        
        try:
            # Setup Agent
            # Swarmbot adds its own system prompt. 
            # We inject benchmark history into the agent's memory or message build process.
            # And we MUST provide the tools via MockAdapter.
            
            tool_names = [t['function']['name'] for t in formatted_tools]
            
            # Create Context with skills enabled (to pass gate)
            ctx = AgentContext(
                agent_id=f"eval-{i}",
                role="assistant",
                skills={name: True for name in tool_names}
            )
            agent = CoreAgent(ctx, llm, ColdMemory(), enable_tools=True)
            agent._tool_adapter = MockToolAdapter(formatted_tools)
            
            # Mock _build_messages to inject history
            # Swarmbot's default _build_messages only looks at self.history (which is empty here)
            # We want to inject `history` (from benchmark) *after* system prompt.
            original_build = agent._build_messages
            
            def mock_build(input_str):
                base = original_build(input_str) # [System, User(input)]
                # Insert benchmark history in between
                # Note: benchmark history might contain System prompts too. 
                # If so, we might have double system prompts. 
                # Some LLMs handle it, some don't. 
                # Let's trust the model handles it or filter out benchmark system prompt if needed.
                # Usually benchmark system prompt defines the persona/tools.
                # Swarmbot system prompt defines the Agent behavior.
                # We want to test "Swarmbot Agent", so Swarmbot system prompt is essential.
                return [base[0]] + history + [base[-1]]
                
            agent._build_messages = mock_build
            
            # Capture output to detect tool usage
            # CoreAgent prints "[CoT] ... calls tool: ..."
            buf = io.StringIO()
            with redirect_stdout(buf):
                agent.step(query)
            
            logs = buf.getvalue()
            for line in logs.split('\n'):
                if "calls tool:" in line:
                    swarm_call = True
                    # Extract name: "... calls tool: search(...)"
                    parts = line.split("calls tool:", 1)[1].strip().split('(')
                    if parts:
                        swarm_tool_name = parts[0].strip()
                    break
                    
        except Exception as e:
            print(f"Swarmbot Error on {i}: {e}")
            
        swarm_time = time.time() - start_t
        
        # --- Evaluate ---
        
        def check_status(should, called, tool_name, allowed_tools):
            if should:
                if not called: return "MISSING"
                # Check if tool is allowed
                # (Simple check, benchmark might have specific expected tool)
                # For now, if it calls *any* allowed tool, we count as pass for "Call Decision"
                # Ideally check name match if ground truth provides it.
                # EvalScope dataset `tools` list defines available tools.
                # `should_call_tool` just says boolean.
                # We assume if it called one of the available tools, it's correct-ish.
                return "PASS" 
            else:
                if called: return "FALSE_POS"
                return "PASS"

        pure_status = check_status(should_call, pure_call, pure_tool_name, tool_names)
        swarm_status = check_status(should_call, swarm_call, swarm_tool_name, tool_names)
        
        results.append({
            "id": i,
            "query": query[:30].replace('\n', ' '),
            "should": should_call,
            "pure_res": pure_status,
            "swarm_res": swarm_status,
            "pure_tool": pure_tool_name or "-",
            "swarm_tool": swarm_tool_name or "-",
            "pure_t": f"{pure_time:.2f}s",
            "swarm_t": f"{swarm_time:.2f}s"
        })
        
        print(f"Sample {i}: Pure={pure_status} Swarm={swarm_status}")

    # 4. Report
    print("\n" + "="*100)
    print(f"COMPARISON REPORT: Pure {model_name} vs Swarmbot")
    print("="*100)
    print(f"{'ID':<4} | {'Query':<30} | {'Expect':<6} | {'Pure':<10} | {'Swarm':<10} | {'PureTool':<10} | {'SwarmTool':<10}")
    print("-" * 100)
    
    pure_pass = 0
    swarm_pass = 0
    
    for r in results:
        if r['pure_res'] == 'PASS': pure_pass += 1
        if r['swarm_res'] == 'PASS': swarm_pass += 1
        
        print(f"{r['id']:<4} | {r['query']:<30} | {str(r['should']):<6} | {r['pure_res']:<10} | {r['swarm_res']:<10} | {r['pure_tool']:<10} | {r['swarm_tool']:<10}")
        
    print("-" * 100)
    print(f"Total Samples: {len(results)}")
    print(f"Pure CPM Accuracy: {pure_pass/len(results)*100:.1f}% ({pure_pass}/{len(results)})")
    print(f"Swarmbot Accuracy: {swarm_pass/len(results)*100:.1f}% ({swarm_pass}/{len(results)})")
    print("="*100)

if __name__ == "__main__":
    run_comparison()
