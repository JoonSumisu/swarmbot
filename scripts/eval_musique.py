
import random
import time
import json
from datasets import load_dataset
from swarmbot.config_manager import load_config
from swarmbot.core.agent import CoreAgent, AgentContext
from swarmbot.memory.cold_memory import ColdMemory
from swarmbot.llm_client import OpenAICompatibleClient

# --- MuSiQue Parsing ---
def format_musique_prompt(sample, include_paragraphs=True):
    # MuSiQue is a multi-hop QA dataset.
    # It provides a list of paragraphs, some of which are supporting.
    # For a fair "Agent" test, we can:
    # 1. Provide all paragraphs in context (RAG-style input).
    # 2. Or assume open-book (search) if paragraphs are not provided.
    # The dataset provides 'paragraphs' key.
    # Let's provide the paragraphs as context to simulate the RAG retrieval result,
    # and ask the model to answer the question.
    
    question = sample['question']
    paragraphs = sample['paragraphs']
    
    context_str = ""
    if include_paragraphs:
        for i, p in enumerate(paragraphs):
            title = p.get('title', '')
            text = p.get('paragraph_text', '')
            context_str += f"Document {i+1} (Title: {title}):\n{text}\n\n"
            
    prompt = f"Background Information:\n{context_str}\nQuestion: {question}\n\nAnswer the question based on the background information. If the answer cannot be found, say 'unanswerable'."
    return prompt

def evaluate_answer(prediction, ground_truth, aliases=[]):
    # Simple inclusion check
    if not prediction: return False
    pred_norm = prediction.lower().strip()
    gt_norm = ground_truth.lower().strip()
    
    if gt_norm in pred_norm: return True
    for alias in aliases:
        if alias.lower().strip() in pred_norm: return True
        
    return False

# --- Evaluation Logic ---

def run_musique_comparison(num_samples=15):
    print("Initializing...")
    cfg = load_config()
    # Update to Qwen-Coder model as requested
    cfg.providers[0].model = 'qwen3-coder-next'
    cfg.providers[0].max_tokens = 64000
    
    try:
        llm = OpenAICompatibleClient.from_provider(providers=cfg.providers)
        print(f"Model: {cfg.providers[0].model}")
    except Exception as e:
        print(f"LLM Init Failed: {e}")
        return

    print("Loading MuSiQue (validation split)...")
    try:
        ds = load_dataset("bdsaglam/musique", split="validation", trust_remote_code=True)
    except Exception as e:
        print(f"Dataset Load Failed: {e}")
        return

    print(f"Dataset size: {len(ds)}. Randomly selecting {num_samples} samples.")
    
    # Random sampling
    import random
    indices = random.sample(range(len(ds)), num_samples)
    results = []
    
    for i, idx in enumerate(indices):
        sample = ds[idx]
        # Format MuSiQue prompt
        # MuSiQue provides paragraphs as context.
        # We simulate RAG by feeding these paragraphs.
        
        question = sample['question']
        paragraphs = sample['paragraphs']
        
        context_str = ""
        for pi, p in enumerate(paragraphs):
            title = p.get('title', '')
            text = p.get('paragraph_text', '')
            context_str += f"Document {pi+1} (Title: {title}):\n{text}\n\n"
            
        prompt = f"Background Information:\n{context_str}\nQuestion: {question}\n\nAnswer the question based on the background information. If the answer cannot be found, say 'unanswerable'."
        
        ground_truth = sample['answer']
        aliases = sample.get('answer_aliases', [])
        
        # --- Pure AgentCPM ---
        start_t = time.time()
        pure_ans = "-"
        
        try:
            # Simple prompt
            messages = [{"role": "user", "content": prompt + "\nAnswer concisely."}]
            resp = llm.completion(messages=messages)
            pure_ans = resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"Pure Error on {idx}: {e}")
            
        pure_time = time.time() - start_t
        
        # --- Swarmbot ---
        start_t = time.time()
        swarm_ans = "-"
        
        try:
            # Initialize Swarmbot
            ctx = AgentContext(
                agent_id=f"eval-musique-{idx}",
                role="reasoner", 
                skills={} 
            )
            agent = CoreAgent(ctx, llm, ColdMemory(), enable_tools=True)
            
            swarm_ans = agent.step(prompt)
            
        except Exception as e:
            print(f"Swarmbot Error on {idx}: {e}")
            
        swarm_time = time.time() - start_t
        
        # --- Result ---
        # Evaluate Answer
        def evaluate_answer(prediction, ground_truth, aliases=[]):
            if not prediction: return False
            pred_norm = prediction.lower().strip()
            gt_norm = ground_truth.lower().strip()
            
            # Direct match or inclusion
            if gt_norm in pred_norm: return True
            for alias in aliases:
                if alias.lower().strip() in pred_norm: return True
            return False

        is_pure_correct = evaluate_answer(pure_ans, ground_truth, aliases)
        is_swarm_correct = evaluate_answer(swarm_ans, ground_truth, aliases)
        
        results.append({
            "id": idx,
            "truth": ground_truth,
            "pure": pure_ans,
            "swarm": swarm_ans,
            "pure_ok": is_pure_correct,
            "swarm_ok": is_swarm_correct,
            "pure_t": f"{pure_time:.1f}s",
            "swarm_t": f"{swarm_time:.1f}s"
        })
        
        print(f"Sample {i+1}/{num_samples} (ID {idx}): Truth='{ground_truth}' | PureOK={is_pure_correct} | SwarmOK={is_swarm_correct}")

    # --- Report ---
    print("\n" + "="*100)
    print(f"MuSiQue COMPARISON REPORT: Pure Qwen-Coder vs Swarmbot (Random 30)")
    print("="*100)
    print(f"{'ID':<6} | {'Truth':<20} | {'PureOK':<6} | {'SwarmOK':<6} | {'Time(P/S)':<12}")
    print("-" * 100)
    
    p_ok = 0
    s_ok = 0
    
    for r in results:
        if r['pure_ok']: p_ok += 1
        if r['swarm_ok']: s_ok += 1
        
        truth_disp = r['truth'][:20] + "..." if len(r['truth']) > 20 else r['truth']
        print(f"{r['id']:<6} | {truth_disp:<20} | {str(r['pure_ok']):<6} | {str(r['swarm_ok']):<6} | {r['pure_t']}/{r['swarm_t']}")
        
    print("-" * 100)
    print(f"Total: {len(results)}")
    print(f"Pure Accuracy: {p_ok/len(results)*100:.1f}% ({p_ok}/{len(results)})")
    print(f"Swarm Accuracy: {s_ok/len(results)*100:.1f}% ({s_ok}/{len(results)})")
    print("="*100)

if __name__ == "__main__":
    run_musique_comparison(num_samples=15)
