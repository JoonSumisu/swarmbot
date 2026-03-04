# Swarmbot

Swarmbot (v0.5.0) is a multi-agent collective intelligence system designed for local/private LLMs. It integrates a 4-layer memory system and a 3-loop self-evolution architecture.

> Core idea: “All-in-One” — gateway, memory, toolchain, and multi-agent orchestration in one lightweight process.

---

## 🧠 v0.6 Logic Enhanced

To address common logical pitfalls in traditional Agents (e.g., "Walking 50m is faster than driving, so walk to the car wash"), v0.6 introduces multiple logical frameworks:

1.  **Modal Logic**:
    *   Distinguishes **Necessity (□)** from **Possibility (◇)**.
    *   Enforces pre-condition checks (e.g., "Car wash requires vehicle presence").
2.  **Deontic Logic**:
    *   Analyzes **Obligations**, **Prohibitions**, and **Permissions**.
3.  **Epistemic Logic**:
    *   Separates **Knowledge** (Facts) from **Beliefs** (Assumptions) to reduce hallucinations.
4.  **Cybernetics**:
    *   Implements Feedback Loops for self-correction and optimization.

These constraints are deeply integrated into the System Prompts, ensuring Swarmbot prioritizes "Physical/Logical Consistency" over mere "Efficiency".

---

## 🚀 Quick Start

### 1. Install (cross-platform, venv-safe)

On macOS (Homebrew Python) or distro-managed Python, pip may show:

```
This environment is externally managed
```

Always install into a virtual environment. This repo includes bootstrap scripts to create `.venv/` and install Swarmbot without touching system Python.

```bash
git clone https://github.com/JoonSumisu/swarmbot.git
cd swarmbot
python3 scripts/bootstrap.py
```

Optional:
```bash
bash scripts/bootstrap.sh
# Windows PowerShell:
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
```

After installation:
```bash
./.venv/bin/swarmbot --help
./.venv/bin/swarmbot daemon start
# or activate venv to run `swarmbot` directly:
source ./.venv/bin/activate
```

### 2. First Run (Onboarding)

`swarmbot daemon start` automatically initializes:
- Config: `~/.swarmbot/config.json`
- Workspace: `~/.swarmbot/workspace/`
- Boot templates: `~/.swarmbot/boot/*.md`

You can also run:
```bash
./.venv/bin/swarmbot onboard
```

### 3. Configure Provider (required)

```bash
./.venv/bin/swarmbot provider add \
  --base-url "http://127.0.0.1:8000/v1" \
  --api-key "sk-xxxx" \
  --model "qwen3-coder-30b-instruct" \
  --max-tokens 8192
```

### 4. Configure Feishu (optional)

```bash
./.venv/bin/swarmbot channels add feishu \
  app_id=cli_xxx \
  app_secret=xxx \
  encrypt_key=xxx \
  verification_token=xxx
```

### 5. Start Gateway

```bash
./.venv/bin/swarmbot gateway
```

### 6. Local Chat (without IM)

```bash
./.venv/bin/swarmbot run
```

### 7. Useful Commands
```bash
./.venv/bin/swarmbot status
./.venv/bin/swarmbot channels list
./.venv/bin/swarmbot heartbeat status
./.venv/bin/swarmbot daemon shutdown
```

---

## 🧠 Architecture

- 4-Layer Memory:
  - L1 Whiteboard (session workspace)
  - L2 Hot Memory (short-term + todo)
  - L3 Warm Memory (daily sequential logs)
  - L4 Cold Memory (QMD vector DB)
- 3 Loops:
  - Inference Loop (8 steps: analysis → collection → planning → inference → evaluation → translation → organization)
  - Overthinking Loop (background read-only compression to QMD)
  - Overaction Loop (refine QMD with web, cleanup warm memory, self-optimization)

---

## Troubleshooting

- pip “externally managed”: use `python3 scripts/bootstrap.py` to install into `.venv/`.
- LLM timeout: reduce `--max-tokens` or concurrency; adjust provider timeouts.
- Feishu not receiving: ensure `channels feishu` is enabled and gateway is running.

---

## License

MIT License

All code power by trae & tomoko

