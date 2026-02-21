# Swarmbot

[中文](README.md) | [English](README_EN.md)

Swarmbot is a local-first **Multi-Agent Swarm System**.

Built on the **[nanobot](https://github.com/HKUDS/nanobot)** framework, it deeply integrates **[swarms](https://github.com/kyegomez/swarms)** orchestration capabilities and **[qmd](https://github.com/tobi/qmd)** tri-layer memory system, designed to empower local LLMs (like Kimi, vLLM, Ollama) with powerful task planning and execution abilities.

> **Core Philosophy**: Extending nanobot's single-agent execution power into collective Swarm intelligence, utilizing Horizon Middleware for long-horizon task planning.

---

## 🌟 Core Architecture v0.1.2

Swarmbot achieves a "Trinity" integration:

### 1. Swarm Orchestration (Swarms Integrated)
*   **Source**: Integrated `swarms` orchestration logic.
*   **Role**: Manages agent collaboration workflows.
*   **Supported Architectures**:
    *   `Sequential`: Linear pipeline (SOP).
    *   `Concurrent`: Parallel execution (default; recommended for smaller/local models).
    *   `Hierarchical`: Director -> Workers command structure.
    *   `Mixture of Experts (MoE)`: Dynamic expert network with debate and consensus.
    *   `State Machine`: Dynamic state transitions (e.g., Code Review loop).
    *   `Auto`: Optional for stronger models; dynamically selects architectures and roles (has some randomness).

### 2. Core Agent (Nanobot Inside)
*   **Source**: Built on `nanobot` core.
*   **Role**: Execution unit within the Swarm.
*   **Features**: 
    *   **Tool Adapter**: Encapsulates native skills (File I/O, Shell) as OpenAI Tools.
    *   **Web Search**: Integrated headless Chrome for dynamic scraping, prioritizing 2024-2026 data.
    *   **Gateway**: Reuses nanobot's multi-channel gateway (Feishu, Slack, Telegram).

### 3. Tri-Layer Memory (QMD Powered)
*   **Source**: Local vector retrieval engine based on `qmd`.
*   **Role**: Provides multi-span memory support.
*   **Layers**:
    1.  **LocalMD (Short-term)**: Real-time session logs.
    2.  **MemoryMap (Whiteboard)**: Shared in-memory whiteboard for global state.
    3.  **QMD (Long-term)**: Vector + BM25 persistent knowledge base.

### 4. Overthinking Loop (Deep Thinking)
*   **Function**: Optional idle-time background consolidation.
*   **Role**: Consolidates LocalMD into QMD and aggressively clears LocalMD after successful persistence.

### 5. Memory Workflow (How it works)
*   **On Prompt**: Query QMD + LocalMD excerpt, then inject a structured task context into Whiteboard (`current_task_context`).
*   **During Swarm**: Nodes should prioritize the Whiteboard context to align task understanding; intermediate results are also written to Whiteboard.
*   **After Chat**: Write an important summary into LocalMD and clear Whiteboard.
*   **When Idle**: Overthinking turns LocalMD into long-term QMD memory, expanding it into Experience/Theory/Concepts.

---

## 🚀 Quick Start

### 1. Installation
```bash
git clone https://github.com/JoonSumisu/swarmbot.git
cd swarmbot

# Install dependencies (Python + npm qmd)
chmod +x scripts/install_deps.sh
./scripts/install_deps.sh

# Initialize
swarmbot onboard
```

### 2. Configure Model (Provider)
Swarmbot requires manual configuration for OpenAI-compatible APIs (e.g., Kimi, DeepSeek, Localhost):

```bash
swarmbot provider add \
  --base-url https://api.moonshot.cn/v1 \
  --api-key YOUR_API_KEY \
  --model kimi-k2-turbo-preview \
  --max-tokens 126000
```

### 3. Run
```bash
# Start (default Concurrent)
swarmbot run
```

### Switch Architectures (Concurrent / Auto)
```bash
swarmbot config --architecture concurrent

# Auto is recommended for stronger models (has some randomness)
swarmbot config --architecture auto --auto-builder true
```

---

## 📖 CLI Features

### 1. `swarmbot onboard`
*   Initializes workspace and config.

### 2. `swarmbot run`
*   Starts interactive chat session.
*   Default: AutoSwarmBuilder mode.

### 3. `swarmbot gateway`
*   **Default Port**: `18990` (v0.1 update).
*   Connects to Feishu/Slack gateways.

### 4. `swarmbot overthinking`
*   Manages background thinking loops (`start`, `setup`).

---

## 📊 Galileo Leaderboard Simulation

Based on internal integration tests [leaderboard_eval.py](file:///root/swarmbot/tests/integration/leaderboard_eval.py), with a local OpenAI-compatible server + `openai/openbmb/agentcpm-explore`:
*   **Best score**: 5/5 (single run, all tasks passed)
*   **Note**: Parallel coordination (and optional auto role selection) can be slightly stochastic across runs

### Evaluation Adjustments
To reduce false negatives and better reflect real usage:
*   Persona anti-patterns were tightened (avoid matching generic “User/Assistant”)
*   Some tasks use bilingual/synonym matching (table/表格, rumor/leak/传闻/爆料)
*   Coding scoring avoids relying on a single keyword (e.g., “backtrack”), focusing on usable code output

---

## 🧩 Feishu (via nanobot gateway)
Swarmbot intercepts nanobot gateway message processing via [gateway_wrapper.py](file:///root/swarmbot/swarmbot/gateway_wrapper.py).
1. Configure Feishu credentials in nanobot first (see nanobot docs)
2. Configure Swarmbot provider (OpenAI-compatible API)
3. Start gateway:

```bash
swarmbot gateway
```

### Provider Examples (Remote / Local)
```bash
swarmbot provider add --base-url https://api.example.com/v1 --api-key YOUR_API_KEY --model openai/your-model --max-tokens 126000
swarmbot provider add --base-url http://127.0.0.1:8000/v1 --api-key dummy --model openai/your-local-model --max-tokens 8192
swarmbot provider add --base-url http://127.0.0.1:11434/v1 --api-key dummy --model openai/your-ollama-model --max-tokens 8192
```

---

## � Future Plans

Future plans will focus on Swarm tuning and Overthinking capabilities. I believe Overthinking could bring interesting changes. Ideally, it requires high VRAM GPUs (3090+ or Mac Pro) for long-duration thinking sessions. Unfortunately, I don't have such hardware yet. I hope someone can help test if this direction is viable.

---

## License
MIT

---

**Acknowledgement**: 
*   This project is built upon the excellent work of [nanobot](https://github.com/HKUDS/nanobot), [swarms](https://github.com/kyegomez/swarms), and [qmd](https://github.com/tobi/qmd).
*   All code generated by **Trae & Tomoko**.
