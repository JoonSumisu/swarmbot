# Swarmbot

Swarmbot (v1.0.0) is a multi-agent collective intelligence system designed for local/private LLMs. It integrates a 4-layer memory system and a 3-loop self-evolution architecture.

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

This repo includes a bootstrap installer with a direct-install-first strategy and post-install checks:

- Prefer `pipx` (global `swarmbot` command, no manual venv activation)
- Fallback to `pip --user`
- Final fallback to `.venv`
- Add `--with-eval-deps` to install regression-eval dependencies in one step
- Validate core imports (`swarmbot`, `gateway`, `lark-oapi`, `swarms`) after install

```bash
git clone https://github.com/JoonSumisu/swarmbot.git
cd swarmbot
python3 scripts/bootstrap.py
```

You can also force a specific mode:

```bash
python3 scripts/bootstrap.py --mode pipx
python3 scripts/bootstrap.py --mode user
python3 scripts/bootstrap.py --mode venv
python3 scripts/bootstrap.py --mode venv --with-eval-deps
python3 scripts/bootstrap.py --skip-check
```

Optional:
```bash
bash scripts/bootstrap.sh
# Windows PowerShell:
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
```

After installation (pipx/user mode):
```bash
swarmbot --help
swarmbot daemon start
```

If you use `venv` mode:
```bash
./.venv/bin/swarmbot --help
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
  --model "qwen3-coder-next" \
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

### Loop Profiles and Worker Allocation

Inference keeps the same 8 phases, while profile controls worker counts, retries, and context budget:

| Profile | analysis_workers | collection_workers | evaluation_workers | max_eval_loops | context_limit |
|:--|--:|--:|--:|--:|--:|
| `lean` | 1 | 1 | 2 | 2 | 3500 |
| `balanced` | 2 | 2 | 3 | 3 | 6000 |
| `swarm_max` | 3 | 3 | 3 | 3 | 9000 |

In `auto`, the system analyzes first, then selects profile with 3 no-tool votes (majority rule).

### Parallel Execution Model

- Analysis / Collection / Evaluation workers run in parallel.
- Inference tasks from the plan run in parallel.
- Multiple `tool_calls` returned in one LLM turn are executed concurrently.
- Tool-gate/profile-gate voting requests are sent concurrently.

### Auto-Run Behavior (Overthinking / Overaction)

- `swarmbot gateway` starts both loops automatically when `overthinking.enabled=true`.
- `swarmbot daemon start` manages gateway + overthinking process with restart/self-heal behavior by default.

---

## Troubleshooting

- pip “externally managed”: use `python3 scripts/bootstrap.py` to install into `.venv/`.
- LLM timeout: reduce `--max-tokens` or concurrency; adjust provider timeouts.
- Feishu not receiving: ensure `channels feishu` is enabled and gateway is running.

---

## Regression Evaluation

Run these after core logic changes:

```bash
./.venv/bin/python scripts/eval_logic_traps.py --model qwen3-coder-next --tag reg_$(date +%Y%m%d_%H%M)
./.venv/bin/python scripts/eval_local_agent.py --tag reg_local_$(date +%Y%m%d_%H%M) --limit 4
```

Outputs are saved under `artifacts/` for before/after comparison.

---

## Runtime Verification Checklist

Use this checklist after upgrades:

1. Start daemon and verify subprocesses:
```bash
./.venv/bin/swarmbot daemon start
pgrep -af "swarmbot.daemon|swarmbot.cli gateway|swarmbot.cli overthinking"
```

2. Validate end-to-end flow in logs:
- Ingress received
- Inference loop starts
- Outbound published/dispatched
- Feishu send success (or text fallback path)

3. Validate tool-call behavior:
- Check CoT lines with `calls tool:` for `whiteboard_update`, `context_policy_update`, `skill_summary`, `skill_load`.

4. Validate EvoMap/Whiteboard:
- EvoMap in this project maps to `MemoryMap/Whiteboard`.
- Confirm key updates through runtime tool calls.

5. Validate background loops:
- Overthinking cycle adds entries into Cold Memory.
- Overaction cycle runs refinement and warm-memory cleanup.

---

## Docs

- [Architecture](docs/ARCHITECTURE.md)
- [Loop Optimization Plan](docs/LOOP_PROFILE_PLAN.md)
- [Memory and Loop Architecture](docs/memory_and_loop_architecture.md)

---

## License

MIT License

All code power by trae & tomoko
