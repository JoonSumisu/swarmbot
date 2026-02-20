# Swarmbot

[中文](README.md) | [English](README_EN.md)

Swarmbot is a **Multi-Agent Swarm System** designed for local environments.

It is built upon the **[nanobot](https://github.com/HKUDS/nanobot)** framework, deeply integrating the multi-agent orchestration capabilities of **[swarms](https://github.com/kyegomez/swarms)** and the tri-layer memory system of **[qmd](https://github.com/tobi/qmd)**. Its goal is to provide powerful task planning and execution capabilities for local models (e.g., Kimi, vLLM, Ollama).

> **Core Philosophy**: Extending nanobot's single-agent execution power into collective Swarm intelligence, and enabling long-horizon task planning via Horizon Middleware.

---

## 🌟 Core Architecture

Swarmbot is not just a stack of components, but a deep fusion of three key elements:

### 1. Core Agent (Nanobot Inside)
*   **Origin**: Built on `nanobot` core code.
*   **Role**: The execution unit within the Swarm.
*   **Features**:
    *   **Tool Adapter**: All nanobot native skills (file ops, shell execution, Feishu/Slack messaging) are wrapped as OpenAI-format Tools, automatically callable by Planner/Coder agents in the Swarm.
    *   **Gateway**: Reuses nanobot's powerful multi-channel gateway, supporting Feishu, Slack, Telegram, etc.

### 2. Swarm Orchestration (Swarms Integrated)
*   **Origin**: Integrates `swarms` framework's orchestration logic.
*   **Role**: Manages collaboration flows between agents.
*   **Supported Architectures**:
    *   `Sequential`: Linear pipeline (SOPs).
    *   `Concurrent`: Parallel execution (Batch tasks).
    *   `Hierarchical`: Director -> Workers.
    *   `State Machine`: Dynamic state transitions (Code Review loops).
    *   **AutoSwarmBuilder**: Built-in intelligence to automatically select the best architecture based on user tasks.

### 3. Tri-Layer Memory (QMD Powered)
*   **Origin**: Based on `qmd` local vector search engine.
*   **Role**: Provides memory support across different time spans.
*   **The Three Layers**:
    1.  **LocalMD (Short-term)**: Local Markdown logs caching daily sessions as working memory.
    2.  **MemoryMap (Whiteboard)**: In-memory shared whiteboard storing global task state and decision snapshots for synchronization.
    3.  **QMD (Long-term)**: Persistent knowledge base with Vector + BM25 search for semantic retrieval of documents and notes.

### 4. Long Horizon Middleware
For complex long-term tasks (e.g., "Develop a complete Snake game"), Swarmbot introduces middleware:
*   **Hierarchical Task Graph**: Decomposes user goals into a Directed Acyclic Graph (DAG) of dependent tasks.
*   **WorkMap Memory**: Maintains a "Skill Map" to automatically match the best local Skill for each sub-task.
*   **Skill Executor**: Schedules Agents to execute specific sub-tasks, handling dependencies and context passing.

---

## 🚀 Quick Start

### 1. Installation
```bash
# Clone repository
git clone https://github.com/JoonSumisu/swarmbot.git
cd swarmbot

# Run independent environment install script (Python deps + npm qmd)
chmod +x scripts/install_deps.sh
./scripts/install_deps.sh

# Initialize config
swarmbot onboard
```

### 2. Configure Model (Provider)
Swarmbot does not include any API Keys by default. Please manually configure an OpenAI-compatible interface (e.g., Kimi, DeepSeek, Localhost):

```bash
swarmbot provider add \
  --base-url https://api.moonshot.cn/v1 \
  --api-key YOUR_API_KEY \
  --model kimi-k2-turbo-preview \
  --max-tokens 126000
```

### 3. Run Chat
```bash
# Start in Auto mode (Recommended)
swarmbot run
```

---

## 📖 CLI Reference

Swarmbot provides a complete CLI to manage your Agent Swarm.

### 1. `swarmbot onboard`
*   **Function**: Initialize workspace.
*   **Usage**: Creates `~/.swarmbot` config, initializes nanobot core, prepares workspace directory.
*   **When**: After fresh install.

### 2. `swarmbot run`
*   **Function**: Start local chat session.
*   **Usage**: Enter interactive terminal to chat directly with the Swarm.
*   **Default**: Starts AutoSwarmBuilder to decide architecture based on input.

### 3. `swarmbot config`
*   **Function**: Adjust Swarm working mode.
*   **Options**:
    *   `--agent-count <int>`: Set number of agents (Default 4).
    *   `--architecture <str>`: Force specific architecture.
        *   `auto`: Automatic selection (Default).
        *   `long_horizon`: Enable Long Horizon middleware.
        *   `state_machine`: Enable Dynamic State Machine.
        *   `sequential`: Force linear execution.
        *   `concurrent`: Force parallel execution.
        *   `hierarchical`: Force hierarchical execution.
    *   `--max-turns <int>`: Set max conversation turns.
*   **Example**:
    ```bash
    # Switch to Long Horizon mode
    swarmbot config --architecture long_horizon
    ```

### 4. `swarmbot gateway`
*   **Function**: Start multi-channel gateway.
*   **Usage**: Passthrough to `nanobot gateway`.
*   **Value**: Lets Swarmbot take over messages from Feishu/Slack, replying via Swarm intelligence.

### 5. `swarmbot provider`
*   **Function**: Manage model provider.
*   **Subcommands**:
    *   `add`: Add/Update model config (base_url, api_key, model, max_tokens).
    *   `delete`: Remove current config, reset to default.
*   **Note**: Swarmbot uses a Single Provider design to ensure consistency across all agents.

### 6. `swarmbot skill` / `tool` / `heartbeat` ...
*   **Function**: Native command passthrough.
*   **Usage**: Directly calls corresponding nanobot commands to manage local skills, tools, and heartbeat.

### 7. `swarmbot overthinking`
*   **Function**: Manage the background Overthinking Loop.
*   **Subcommands**:
    *   `setup --enabled true --interval 30 --steps 10`: Configure parameters (default 30 mins, 10 steps).
    *   `start`: Start the loop manually.
*   **Mechanism**: Automatically consolidates short-term memory, refines QMD knowledge base, expands thoughts, and performs web searches to enrich memory during idle times.

---

## 📚 Advanced: Long Horizon Workflow

When `long_horizon` architecture is selected (manually or via AutoSwarmBuilder), the system enters **Long-Range Planning Mode**:

1.  **Plan**: 
    `HierarchicalTaskGraph` calls LLM to decompose user input into a dependent task chain.
    > User: "Analyze these three financial reports and generate a summary."
    > Plan: [Read Report A -> Read Report B -> Read Report C] -> [Data Comparison] -> [Generate Report]

2.  **Skill Match**: 
    `WorkMapMemory` scans local skill library, finding `file_read` suitable for reading tasks and `python_exec` for analysis.

3.  **Execute**: 
    `SwarmManager` schedules Agents sequentially. When executing "Read Report", the Agent automatically calls `file_read` tool; when executing "Analysis", it receives data from previous tasks as Context.

4.  **Loop**: 
    Until all tasks are `completed`.

---

## License
MIT

---

**Acknowledgement**: 
*   This project is built upon the excellent work of [nanobot](https://github.com/HKUDS/nanobot), [swarms](https://github.com/kyegomez/swarms), and [qmd](https://github.com/tobi/qmd).
*   All code generated by **Trae & Tomoko**.
