# Swarmbot Architecture (v0.5)

## Overview
Swarmbot is a multi-agent collective intelligence system designed for complex problem solving and long-term memory retention. It operates on a 3-Loop Architecture supported by a 4-Layer Memory System.

## 🧠 4-Layer Memory System

| Layer | Name | Persistence | Description | Storage |
|:---:|:---:|:---:|:---|:---|
| **L1** | **Whiteboard** | Session (Volatile) | Structured workspace for the current dialogue. Stores prompt analysis, plans, execution results, and evaluations. Cleared after each loop. | Memory Object |
| **L2** | **Hot Memory** | Short-term (1-7 days) | Context for recent past, present focus, future plans, and **Todo List**. Edited by agents and self-optimization loops. | `hot_memory.md` |
| **L3** | **Warm Memory** | Sequential Log | Time-series record of all completed inference loops (Input + Conclusion + Facts). Read-only for most agents. | `memory/YYYY-MM-DD.md` |
| **L4** | **Cold Memory** | Long-term (Permanent) | Semantic knowledge base (Facts, Experiences, Theories) derived from Warm Memory via Overthinking. | QMD (Vector DB) |

---

## 🔄 3-Loop Architecture

### 1. Inference Loop (The "Fast" Loop)
Triggered by user input (Feishu/CLI).
**Steps:**
1.  **Ingress**: Receive message.
2.  **Analysis**: 2 Workers analyze intent & requirements -> Whiteboard.
3.  **Collection**: 3 Workers gather context (L2/L3/L4 + Web) -> Whiteboard.
4.  **Planning**: Planner creates execution plan -> Whiteboard.
5.  **Inference**: Workers execute tools/tasks -> Whiteboard.
6.  **Evaluation**: 3 Evaluators vote on results (Pass/Fail). Retry up to 3 times.
7.  **Translation**: Master Agent formats final response.
8.  **Organization**: Master Agent updates L2/L3 memories.

### 2. Overthinking Loop (The "Background" Loop)
Runs periodically (e.g., every 30 mins).
**Functions:**
*   **Read-only** access to Hot & Warm memory.
*   **Compression**: Extracts high-value insights from daily logs (Warm) and moves them to QMD (Cold).
*   **Archiving**: Identifies completed patterns.

### 3. Overaction Loop (The "Evolution" Loop)
Runs after Overthinking (e.g., every 60 mins).
**Functions:**
*   **Refinement**: Reads QMD, performs web searches to verify/expand knowledge.
*   **Cleanup**: Deletes old Warm Memory files that have been processed.
*   **Self-Optimization**:
    *   Updates `swarmboot.md` (System Prompts).
    *   Updates `hot_memory.md` (Context).
    *   Adds "Self-Improvement" tasks to Todo List.

---

## 📂 File Structure
```
swarmbot/
├── boot/               # System prompts (SOUL.md, swarmboot.md)
├── core/               # Agent & LLM primitives
├── loops/              # The 3 Loops
│   ├── inference.py
│   ├── overthinking.py
│   ├── overaction.py
│   └── definitions.py  # Prompt templates
├── memory/             # Memory classes
│   ├── whiteboard.py
│   ├── hot_memory.py
│   ├── warm_memory.py
│   └── cold_memory.py  # QMD wrapper
├── swarm/              # Legacy manager (being phased out/integrated)
└── gateway/            # Server & Message Bus
```
