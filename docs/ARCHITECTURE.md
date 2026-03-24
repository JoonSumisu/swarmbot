# Swarmbot Architecture (v2.2.0)

## Overview
Swarmbot is a multi-agent collective intelligence system designed for complex problem solving and long-term memory retention. It operates on a 3-Loop Architecture supported by a 5-Layer Memory System (L1 + L1.5 + L2 + L3 + L4).

## 🧠 5-Layer Memory System (v2.2.0)

| Layer | Name | Capacity | Lifecycle | Description | Storage |
|:---:|:---:|:---:|:---:|:---|:---|
| **L1** | **Whiteboard** | Unlimited | Cleared after loop | Structured workspace for the current inference. Stores analysis, plans, execution results. | Memory Object |
| **L1.5** | **SessionMemory** | 8-turn sliding window | Session end / 7-day TTL | Session-level context. Auto-compact triggers at >8 turns, extracting key info to Hot. | `sessions/{chat_id}.md` |
| **L2** | **HotMemory** | Max 20 entries | Persistent (auto-cleanup) | Important info, Todo, plans. Oldest entries removed when exceeding 20. | `hot_memory.md` |
| **L3** | **WarmMemory** | Unlimited | Daily archive | Time-series log of all completed inference loops. Cleaned by Autonomous (>30 days). | `memory/YYYY-MM-DD.md` |
| **L4** | **ColdMemory** | Unlimited | Permanent | Semantic knowledge base (Facts, Experiences, Theories) derived from Hot/Warm via Autonomous. | QMD (Vector DB) |

### Memory Flow

```
User Input
    │
    ▼
MasterAgent (simple_direct / inference)
    ├── Read: Session + Hot + Cold
    └── Write: Session + Warm

Session > 8 turns → Auto Compact
    ├── Keep recent 8 turns
    └── MasterAgent extracts → Write to Hot (max 20)

Autonomous memory_foundation (periodic/30min)
    ├── Read: Hot + Warm
    ├── Compress → Write to Cold (QMD)
    └── Cleanup: Warm files (>30 days)
```

---

## 🔄 3-Loop Architecture

### 1. Inference Loop (The "Fast" Loop)
Triggered by user input (CLI/Feishu/Gateway).
**Steps:**
1.  **Routing**: GatewayMasterAgent decides simple_direct vs inference_tool
2.  **Analysis**: 2 Workers analyze intent & requirements -> Whiteboard.
3.  **Collection**: 3 Workers gather context (Session/Hot/Cold + Web) -> Whiteboard.
4.  **Planning**: Planner creates execution plan -> Whiteboard.
5.  **Inference**: Workers execute tools/tasks -> Whiteboard.
6.  **Evaluation**: 3 Evaluators vote on results (Pass/Fail). Retry up to 3 times.
7.  **Translation**: Master Agent formats final response.
8.  **Organization**: Write to Session + Warm (NOT directly to Hot - done via compact).

**Runtime Guards**
- Gateway handles each inbound request with an isolated `InferenceLoop` instance to avoid cross-session whiteboard contamination.
- Outbound delivery is dispatched asynchronously and retried on transient dispatch failures.
- If inference fails, gateway still emits a fallback outbound response instead of silently dropping the user request.

### 2. Overthinking Loop (The "Background" Loop)
Now integrated into Autonomous Engine as `memory_foundation` Bundle.
**Functions:**
*   **Read** Hot & Warm memory.
*   **Compress**: Extract high-value insights from Hot/Warm and move to QMD (Cold).
*   **Cleanup**: Delete Warm Memory files older than 30 days.

### 3. Overaction Loop (The "Evolution" Loop)
Runs after Overthinking (e.g., every 60 mins).
**Functions:**
*   **Refinement**: Reads QMD, performs web searches to verify/expand knowledge.
*   **Self-Optimization**:
    *   Updates `swarmboot.md` (System Prompts).
    *   Updates `hot_memory.md` (Context).
    *   Adds "Self-Improvement" tasks to Todo List.

---

## 🔎 Observability Checklist

- **Ingress:** Feishu receive log exists (`[Feishu] Received message ...`).
- **Inference:** loop enters Step 2~8 and records CoT/tool-call traces.
- **Egress:** outbound message published and dispatched to channel subscriber.
- **Channel Delivery:** Feishu send success log appears; if card send fails, text fallback path is attempted.
- **MemoryMap (EvoMap):** `context_policy_update` / `whiteboard_update` can mutate whiteboard keys during runtime.
- **Session Compact:** >8 turns triggers auto-compact, verify Hot entries increase.
- **Hot Capacity:** Verify old entries removed when exceeding 20.

---

## 📂 File Structure (v2.2.0)
```
swarmbot/
├── boot/               # System prompts (SOUL.md, swarmboot.md)
├── core/               # Agent & LLM primitives
├── loops/              # Inference tools
│   ├── base.py        # BaseInferenceTool
│   ├── inference_standard.py
│   ├── inference_supervised.py
│   ├── inference_swarms.py
│   ├── inference_subswarm.py
│   ├── overthinking.py  # Integrated into Autonomous
│   └── definitions.py   # Prompt templates
├── memory/             # Memory classes
│   ├── whiteboard.py    # L1
│   ├── session_memory.py # L1.5 (NEW in v2.2.0)
│   ├── hot_memory.py    # L2 (capacity limit: 20)
│   ├── warm_memory.py   # L3 (auto cleanup >30 days)
│   └── cold_memory.py   # L4 (QMD)
├── gateway/            # Server & Message Bus
│   ├── orchestrator.py # GatewayMasterAgent
│   └── communication_hub.py
├── autonomous/         # Autonomous Engine
│   └── engine.py       # BundleGovernor + memory_foundation
└── skill_pool.py       # Skill固化池
```
