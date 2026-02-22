# Swarmbot

[中文](README.md) | [English](README_EN.md)

Swarmbot is a local-first **Multi-Agent Swarm System**.

Swarmbot includes a **vendored nanobot implementation (no pip dependency)** for gateway/channels, and deeply integrates **[swarms](https://github.com/kyegomez/swarms)** orchestration plus **QMD (tri-layer memory)** to empower OpenAI-compatible endpoints (local or private).

Development notes: [development.md](file:///root/swarmbot/docs/development.md).

> **Core Philosophy**: Extending nanobot's single-agent execution power into collective Swarm intelligence, utilizing Horizon Middleware for long-horizon task planning.

---

## 🌟 Core Architecture

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

# Install dependencies (Python only)
chmod +x scripts/install_deps.sh
./scripts/install_deps.sh

# Initialize
swarmbot onboard
```

### 2. Configure Model (Provider)
Swarmbot requires manual configuration for OpenAI-compatible APIs (e.g., Kimi, DeepSeek, Localhost):

```bash
swarmbot provider add \
  --base-url http://127.0.0.1:8000/v1 \
  --api-key YOUR_API_KEY \
  --model your-model-name \
  --max-tokens 8192
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

### 0. Config Locations
*   **Config file**: `~/.swarmbot/config.json`
*   **Swarmbot workspace**: `~/.swarmbot/workspace`
*   **Boot config**: `~/.swarmbot/boot/` (contains `SOUL.md`, `TOOLS.md`, etc.)

### 1. `swarmbot onboard`
*   Initializes config and workspace.
*   Creates `~/.swarmbot/config.json` and `~/.swarmbot/workspace`.
*   Tries to run `nanobot onboard` if nanobot is installed.

### 2. `swarmbot run`
*   Starts an interactive chat loop and routes every user message to SwarmManager.
*   Default architecture is `concurrent` (more stable for smaller/local models).

### 3. `swarmbot config`
*   View/update swarm settings (writes into `~/.swarmbot/config.json`).
*   Common flags:
    *   `--agent-count <int>`
    *   `--architecture <name>` (`concurrent`/`sequential`/`mixture`/`hierarchical`/`state_machine`/`auto`…)
    *   `--max-turns <int>` (`0` means unlimited)
    *   `--auto-builder <true|false>`

```bash
swarmbot config --architecture concurrent --agent-count 4
swarmbot config --architecture auto --auto-builder true
```

### 4. `swarmbot provider`
*   Configure the OpenAI-compatible provider.
*   Subcommands:
    *   `provider add`
    *   `provider delete`

### 5. `swarmbot status`
*   Prints current Provider/Swarm/Overthinking config.

### 6. `swarmbot gateway`
*   Starts the gateway and routes inbound channel messages into SwarmManager.
*   Reads all configs from `~/.swarmbot/config.json` (provider + channels).

### 7. `swarmbot tool / channels / cron / agent / skill`
*   Manages the vendored nanobot tool/channel capabilities (gradually migrating to Swarmbot-native implementations).

### 9. `swarmbot overthinking`
*   Manages idle-time background consolidation.
*   Subcommands:
    *   `overthinking setup`
    *   `overthinking start` (foreground, for debugging)

---

## 🗂️ Repository Structure & Modules

### Top-level
*   `swarmbot/`: Python package (core logic)
*   `tests/`: integration/unit tests (including leaderboard_eval)
*   `scripts/`: installation/dependency helpers

### Package modules (`swarmbot/`)
*   [cli.py](swarmbot/cli.py): CLI entrypoint and subcommands
*   [config_manager.py](swarmbot/config_manager.py): config read/write and defaults (`~/.swarmbot/config.json`)
*   [config.py](swarmbot/config.py): internal SwarmConfig/LLMConfig structs
*   [llm_client.py](swarmbot/llm_client.py): OpenAI-compatible client wrapper
*   [gateway_wrapper.py](swarmbot/gateway_wrapper.py): intercept nanobot gateway message loop and route to SwarmManager

### Swarm orchestration
*   [swarm/manager.py](swarmbot/swarm/manager.py): SwarmManager (architectures, concurrency, consensus, whiteboard injection/cleanup)
*   [swarm/agent_adapter.py](swarmbot/swarm/agent_adapter.py): adapter/bridge layer (if needed)

### Core agent
*   [core/agent.py](swarmbot/core/agent.py): CoreAgent (message building, tool-call loop, memory writes)

### Memory
*   [memory/qmd.py](swarmbot/memory/qmd.py): tri-layer memory (Whiteboard/LocalMD/QMD search)
*   [memory/base.py](swarmbot/memory/base.py): memory store interface

### Tools
*   [tools/adapter.py](swarmbot/tools/adapter.py): tool adapter (file_read/file_write/web_search/shell_exec…)
*   [tools/browser/local_browser.py](swarmbot/tools/browser/local_browser.py): local headless browser helpers

### Overthinking (idle-time)
*   [loops/overthinking.py](swarmbot/loops/overthinking.py): consolidate LocalMD → QMD, plus compression/expansion steps

### Middleware & state machine
*   [middleware/long_horizon.py](swarmbot/middleware/long_horizon.py): long-horizon planning experiments
*   [statemachine/engine.py](swarmbot/statemachine/engine.py): state machine engine (review loops, etc.)

## ✅ Tests
*   Unit tests: `python -m unittest discover -s tests -p "test*.py" -v`
*   Eval script: `tests/integration/leaderboard_eval.py` (run with your own model/server; do not hardcode private endpoints/keys)

### Evaluation Adjustments
To reduce false negatives and better reflect real usage:
*   Persona anti-patterns were tightened (avoid matching generic “User/Assistant”)
*   Some tasks use bilingual/synonym matching (table/表格, rumor/leak/传闻/爆料)
*   Coding scoring avoids relying on a single keyword (e.g., “backtrack”), focusing on usable code output

---

## 🧩 Feishu
Swarmbot reads **provider + channels** from `~/.swarmbot/config.json`. Configure Feishu under `channels.feishu`, then start:

```bash
swarmbot gateway
```

Example (replace with your own values):

```json
{
  "provider": {
    "name": "custom",
    "base_url": "http://127.0.0.1:8000/v1",
    "api_key": "YOUR_API_KEY",
    "model": "your-model-name",
    "max_tokens": 8192,
    "temperature": 0.6
  },
  "channels": {
    "feishu": {
      "enabled": true,
      "appId": "YOUR_APP_ID",
      "appSecret": "YOUR_APP_SECRET",
      "allowFrom": []
    }
  }
}
```

---

## Future Plans

Future plans will focus on Swarm tuning and Overthinking capabilities. I believe Overthinking could bring interesting changes. Ideally, it requires high VRAM GPUs (3090+ or Mac Pro) for long-duration thinking sessions. Unfortunately, I don't have such hardware yet. I hope someone can help test if this direction is viable.

---

## License
MIT

---

**Acknowledgement**: 
*   This project is built upon the excellent work of [nanobot](https://github.com/HKUDS/nanobot), [swarms](https://github.com/kyegomez/swarms), and [qmd](https://github.com/tobi/qmd).
*   All code generated by **Trae & Tomoko**.
