#!/usr/bin/env python3
"""
Swarmbot Memory Simulation Test
Simulates 19-turn user conversation to test memory system
"""
import asyncio
import json
import os
import sys
import time

os.chdir("/root/swarmbot_dev")
sys.path.insert(0, "/root/swarmbot_dev")

from swarmbot.config_manager import load_config, WORKSPACE_PATH
from swarmbot.gateway.orchestrator import GatewayMasterAgent


# Test conversation scenarios
CONVERSATION = [
    # Scenario 1: Basic conversation & memory writing
    ("1.1", "你好，我是张三，我住在北京", "基本信息写入"),
    ("1.2", "我是一名 Python 开发者，在一家 AI 创业公司工作", "职业信息写入"),
    ("1.3", "我最近在研究 RAG（检索增强生成）技术", "技术兴趣写入"),

    # Scenario 2: Memory retrieval
    ("2.1", "你还记得我叫什么名字吗？", "记忆检索-姓名"),
    ("2.2", "我住在哪里？", "记忆检索-地址"),
    ("2.3", "我的职业是什么？", "记忆检索-职业"),

    # Scenario 3: Cold memory search
    ("3.1", "什么是 RAG 技术？", "冷记忆搜索"),
    ("3.2", "搜索一下我之前提到的技术", "冷记忆搜索-技术"),

    # Scenario 4: Auto-compact (after 8 turns)
    ("4.1", "我喜欢用 FastAPI 写后端", "技术栈补充-1"),
    ("4.2", "前端用的是 React", "技术栈补充-2"),
    ("4.3", "数据库用的 PostgreSQL", "技术栈补充-3"),
    ("4.4", "部署用 Docker 和 K8s", "技术栈补充-4"),
    ("4.5", "监控用 Prometheus", "技术栈补充-5"),
    ("4.6", "日志用 ELK Stack", "技术栈补充-6"),
    ("4.7", "CI/CD 用 GitHub Actions", "技术栈补充-7"),

    # Scenario 5: Multi-turn plan & memory organization
    ("5.1", "帮我制定一个学习计划，学习 LLM 微调", "多轮计划-1"),
    ("5.2", "加入 LoRA 微调方法", "多轮计划-2"),
    ("5.3", "加上 QLoRA 和 PEFT", "多轮计划-3"),
    ("5.4", "把计划总结一下", "多轮计划-总结"),
]


def check_memory_files():
    """Check memory files state"""
    results = {}
    
    # Session memory
    session_path = os.path.join(WORKSPACE_PATH, "sessions", "sim-session.md")
    if os.path.exists(session_path):
        with open(session_path, "r") as f:
            results["session"] = f.read()
    else:
        results["session"] = "[NOT FOUND]"
    
    # Hot memory
    hot_path = os.path.join(WORKSPACE_PATH, "hot_memory.md")
    if os.path.exists(hot_path):
        with open(hot_path, "r") as f:
            results["hot"] = f.read()
    else:
        results["hot"] = "[NOT FOUND]"
    
    # Warm memory
    warm_dir = os.path.join(WORKSPACE_PATH, "memory")
    if os.path.exists(warm_dir):
        files = os.listdir(warm_dir)
        results["warm_files"] = files
        if files:
            for f in sorted(files):
                if f.endswith(".md"):
                    with open(os.path.join(warm_dir, f), "r") as rf:
                        results["warm"] = rf.read()
                    break
    else:
        results["warm_files"] = []
        results["warm"] = "[NOT FOUND]"
    
    # Cold memory (SQLite)
    sqlite_path = os.path.join(WORKSPACE_PATH, "memory.sqlite")
    results["cold_exists"] = os.path.exists(sqlite_path)
    
    return results


def run_simulation():
    print("=" * 70)
    print("SWARMBOT MEMORY SIMULATION TEST")
    print("=" * 70)
    print(f"LLM: {load_config().providers[0].base_url}")
    print(f"Model: {load_config().providers[0].model}")
    print("=" * 70)

    # Initialize
    cfg = load_config()
    orchestrator = GatewayMasterAgent(WORKSPACE_PATH, cfg)
    session_id = "sim-session"
    
    print(f"\n[Init] Memory layers loaded:")
    print(f"  - Session Memory: {orchestrator.session_memory}")
    print(f"  - Hot Memory: {orchestrator.hot_memory}")
    print(f"  - Warm Memory: {orchestrator.warm_memory}")
    print(f"  - Cold Memory: {orchestrator.cold_memory}")

    results = []
    start_time = time.time()

    for turn_id, user_input, description in CONVERSATION:
        print(f"\n{'='*70}")
        print(f"[Turn {turn_id}] {description}")
        print(f"User: {user_input}")
        
        turn_start = time.time()
        try:
            response = orchestrator.handle_message(user_input, session_id)
            turn_time = time.time() - turn_start
            
            print(f"Bot ({turn_time:.1f}s): {response[:200]}...")
            
            results.append({
                "turn": turn_id,
                "input": user_input,
                "response": response[:500],
                "time": round(turn_time, 1),
                "ok": True,
            })
        except Exception as e:
            turn_time = time.time() - turn_start
            error_msg = str(e)[:200]
            print(f"ERROR ({turn_time:.1f}s): {error_msg}")
            
            results.append({
                "turn": turn_id,
                "input": user_input,
                "error": error_msg,
                "time": round(turn_time, 1),
                "ok": False,
            })

    total_time = time.time() - start_time

    # Check memory files
    print(f"\n{'='*70}")
    print("MEMORY FILES STATE")
    print(f"{'='*70}")
    
    memory = check_memory_files()
    
    print(f"\n--- Session Memory ---")
    print(memory["session"][:500] if memory["session"] != "[NOT FOUND]" else "[NOT FOUND]")
    
    print(f"\n--- Hot Memory ---")
    print(memory["hot"][:500] if memory["hot"] != "[NOT FOUND]" else "[NOT FOUND]")
    
    print(f"\n--- Warm Memory Files ---")
    print(f"Files: {memory['warm_files']}")
    if "warm" in memory and memory["warm"] != "[NOT FOUND]":
        print(memory["warm"][:500])
    
    print(f"\n--- Cold Memory (SQLite) ---")
    print(f"Exists: {memory['cold_exists']}")

    # Get stats from orchestrator
    print(f"\n--- Stats ---")
    try:
        stats = orchestrator.cold_memory.get_stats()
        print(f"Cold Memory Stats: {stats}")
    except Exception as e:
        print(f"Stats error: {e}")

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    
    ok_count = sum(1 for r in results if r["ok"])
    fail_count = sum(1 for r in results if not r["ok"])
    print(f"Total turns: {len(results)}")
    print(f"OK: {ok_count}, Failed: {fail_count}")
    print(f"Total time: {total_time:.1f}s")
    
    if fail_count > 0:
        print(f"\nFailed turns:")
        for r in results:
            if not r["ok"]:
                print(f"  - Turn {r['turn']}: {r.get('error', 'unknown')}")

    # Save results
    report_path = os.path.join(WORKSPACE_PATH, "memory_test_report.json")
    with open(report_path, "w") as f:
        json.dump({
            "timestamp": time.time(),
            "total_time": round(total_time, 1),
            "turns": results,
            "ok": ok_count,
            "failed": fail_count,
            "memory": {k: v[:200] if isinstance(v, str) else v for k, v in memory.items()},
        }, f, ensure_ascii=False, indent=2)
    print(f"\nReport saved to: {report_path}")

    return ok_count, fail_count


if __name__ == "__main__":
    ok, fail = run_simulation()
    sys.exit(0 if fail == 0 else 1)
