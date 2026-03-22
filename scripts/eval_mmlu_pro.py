
import re
import time
import json
from datasets import load_dataset
from swarmbot.config_manager import load_config
from swarmbot.core.agent import CoreAgent, AgentContext
from swarmbot.memory.cold_memory import ColdMemory
from swarmbot.llm_client import OpenAICompatibleClient

# --- MMLU-Pro Parsing ---
def format_mmlu_pro_prompt(sample, include_cot=False):
    question = sample['question']
    options = sample['options']
    
    prompt = f"Question: {question}\n\nOptions:\n"
    for i, opt in enumerate(options):
        # MMLU-Pro uses letters A, B, C... up to J (10 options usually)
        letter = chr(65 + i)
        prompt += f"{letter}. {opt}\n"
        
    prompt += "\nAnswer with the option letter directly, e.g. 'The answer is (A)'."
    return prompt
    
def extract_answer(text):
    if not text: return None
    # Try to find "The answer is (X)" or just "Answer: X"
    match = re.search(r"answer is \(?([A-J])\)?", text, re.IGNORECASE)
    if match: return match.group(1).upper()
    
    match = re.search(r"Option ([A-J])", text, re.IGNORECASE)
    if match: return match.group(1).upper()
    
    # Last standalone letter logic
    # Clean text
    text = text.strip()
    # If text is just a letter
    if len(text) == 1 and text.upper() in "ABCDEFGHIJ":
        return text.upper()
        
    # Try to find last letter in parens (A)
    match = re.search(r"\(([A-J])\)\s*$", text)
    if match: return match.group(1).upper()
    
    return None

# --- Evaluation Logic ---

def run_mmlu_pro_comparison(start_idx=0, num_samples=30):
    print("Initializing...")
    cfg = load_config()
    # Ensure model is set correctly
    cfg.providers[0].model = 'agentcpm-explore'
    
    try:
        llm = OpenAICompatibleClient.from_provider(providers=cfg.providers)
        print(f"Model: {cfg.providers[0].model}")
    except Exception as e:
        print(f"LLM Init Failed: {e}")
        return

    print("Loading MMLU-Pro (validation split)...")
    try:
        ds = load_dataset("TIGER-Lab/MMLU-Pro", split="validation", trust_remote_code=True)
    except Exception as e:
        print(f"Dataset Load Failed: {e}")
        return

    print(f"Dataset size: {len(ds)}. Testing samples {start_idx} to {start_idx+num_samples}.")
    
    results = []
    
    for i in range(start_idx, min(start_idx + num_samples, len(ds))):
        sample = ds[i]
        # Swarmbot expects prompt
        # Pure expects prompt
        prompt = format_mmlu_pro_prompt(sample)
        ground_truth = sample['answer'] # Letter A-J
        category = sample.get('category', 'unknown')
        
        # --- Pure AgentCPM ---
        start_t = time.time()
        pure_ans = "-"
        
        try:
            # Simple CoT prompt
            messages = [{"role": "user", "content": prompt + "\nLet's think step by step."}]
            resp = llm.completion(messages=messages)
            pure_raw = resp.choices[0].message.content
            pure_ans = extract_answer(pure_raw)
        except Exception as e:
            print(f"Pure Error on {i}: {e}")
            
        pure_time = time.time() - start_t
        
        # --- Swarmbot ---
        start_t = time.time()
        swarm_ans = "-"
        
        try:
            # Initialize Swarmbot
            ctx = AgentContext(
                agent_id=f"eval-mmlu-{i}",
                role="reasoner", 
                skills={} 
            )
            agent = CoreAgent(ctx, llm, ColdMemory(), enable_tools=True)
            
            # Run
            swarm_raw = agent.step(prompt)
            swarm_ans = extract_answer(swarm_raw)
            
        except Exception as e:
            print(f"Swarmbot Error on {i}: {e}")
            
        swarm_time = time.time() - start_t
        
        # --- Result ---
        # Compare
        is_pure_correct = (pure_ans == ground_truth)
        is_swarm_correct = (swarm_ans == ground_truth)
        
        results.append({
            "id": i,
            "category": category,
            "truth": ground_truth,
            "pure": pure_ans,
            "swarm": swarm_ans,
            "pure_ok": is_pure_correct,
            "swarm_ok": is_swarm_correct,
            "pure_t": f"{pure_time:.1f}s",
            "swarm_t": f"{swarm_time:.1f}s"
        })
        
        print(f"Sample {i} ({category}): Truth={ground_truth} | Pure={pure_ans}({is_pure_correct}) | Swarm={swarm_ans}({is_swarm_correct})")

    # --- Report ---
    print("\n" + "="*100)
    print(f"MMLU-Pro COMPARISON REPORT: Pure AgentCPM vs Swarmbot")
    print("="*100)
    print(f"{'ID':<4} | {'Category':<15} | {'Truth':<5} | {'Pure':<5} | {'Swarm':<5} | {'PureOK':<6} | {'SwarmOK':<6} | {'Time(P/S)':<12}")
    print("-" * 100)
    
    p_ok = 0
    s_ok = 0
    
    for r in results:
        if r['pure_ok']: p_ok += 1
        if r['swarm_ok']: s_ok += 1
        
        print(f"{r['id']:<4} | {r['category'][:15]:<15} | {r['truth']:<5} | {str(r['pure']):<5} | {str(r['swarm']):<5} | {str(r['pure_ok']):<6} | {str(r['swarm_ok']):<6} | {r['pure_t']}/{r['swarm_t']}")
        
    print("-" * 100)
    print(f"Total: {len(results)}")
    print(f"Pure Accuracy: {p_ok/len(results)*100:.1f}% ({p_ok}/{len(results)})")
    print(f"Swarm Accuracy: {s_ok/len(results)*100:.1f}% ({s_ok}/{len(results)})")
    print("="*100)

if __name__ == "__main__":
    run_mmlu_pro_comparison(start_idx=10, num_samples=30)
