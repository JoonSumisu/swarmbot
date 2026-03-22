# AGENTS.md - Swarmbot Development Guide (v2.0.2)

This document provides guidelines for agents working on the Swarmbot codebase.

---

## 1. Build, Lint, and Test Commands

### Installation (Python)
```bash
# Standard installation
python3 scripts/bootstrap.py

# Development/editable mode (code changes take effect immediately)
python3 scripts/bootstrap.py --editable

# With evaluation dependencies
python3 scripts/bootstrap.py --mode venv --with-eval-deps
```

### Running Tests
```bash
# Run a single test file
./.venv/bin/python -m pytest tests/test_nanobot_config_bridge.py -v

# Run a single test class
./.venv/bin/python -m pytest tests/test_nanobot_config_bridge.py::TestNanobotConfigBridge -v

# Run all tests with unittest
./.venv/bin/python -m unittest discover -s tests -v

# Regression tests for logic traps
./.venv/bin/python scripts/eval_logic_traps.py --model qwen3-coder-next --tag test_$(date +%Y%m%d)

# E2E smoke tests
./.venv/bin/python tests/smoke_test_full_e2e.py --quick

# Bundle optimization experiments
./.venv/bin/python tests/experiment_bundle_optimization.py --phase all
```

### TypeScript (nanobot bridge)
```bash
cd swarmbot/nanobot/bridge
npm install
npm run build    # TypeScript compilation
npm run dev      # Build and run in dev mode
```

### Running the Application
```bash
# Initialize config
swarmbot onboard

# CLI interactive mode (使用 MasterAgent)
swarmbot run

# Start gateway (带 MasterAgent)
swarmbot gateway

# Start daemon
swarmbot daemon start

# Check status
swarmbot status
```

---

## 2. Code Style Guidelines

### 2.1 Python Style Conventions

**Imports**
- Use `from __future__ import annotations` at the top of all Python files
- Group imports: stdlib, third-party, local/relative
- Use relative imports within the package: `from ..module import something`

**Type Annotations**
- Use `from __future__ import annotations` for forward references
- Use built-in types directly in annotations: `List`, `Dict`, `Optional`

**Naming Conventions**
- Classes: `PascalCase` (e.g., `SwarmbotConfig`, `InferenceLoop`)
- Functions/methods: `snake_case` (e.g., `load_config`, `save_config`)
- Private members: prefix with `_` (e.g., `_internal_state`)

**Dataclasses for Configuration**
- Use `@dataclass` for configuration objects
- Use `field(default_factory=...)` for mutable defaults

**Error Handling**
- Catch specific exceptions, not bare `except:`
- Include context in error messages

**Logging**
- Use `print()` for CLI output and visible logs
- Include context in log messages: `[Component] Action: details`

### 2.2 TypeScript Style Conventions

**Configuration** (tsconfig.json)
- Target: ES2022
- Module: ESNext
- Strict mode: enabled
- ESM interop: enabled

---

## 3. Project Structure

```
swarmbot/
├── boot/                     # Boot files (SOUL.md, inference_tools.md, etc.)
├── cli.py                    # CLI entry point
├── config_manager.py         # Configuration loading
├── llm_client.py             # LLM client wrapper
├── daemon.py                 # Background process management
├── gateway/                  # Gateway components
│   ├── server.py             # HTTP server + Hub integration
│   ├── orchestrator.py       # GatewayMasterAgent
│   └── communication_hub.py  # Shared message queue (chatroom)
├── loops/                    # Inference tools
│   ├── base.py               # BaseInferenceTool abstract class
│   ├── inference_standard.py # Standard 8-step inference
│   ├── inference_supervised.py # Human-in-the-loop inference
│   ├── inference_swarms.py   # Multi-worker inference
│   └── skill_registry.py     # Skill registry
├── memory/                   # Memory system
│   ├── whiteboard.py         # L1: Session-level temporary
│   ├── hot_memory.py         # L2: Short-term persistent
│   ├── warm_memory.py        # L3: Daily logs
│   └── cold_memory.py        # L4: Semantic vector DB
├── autonomous/               # Autonomous engine
│   └── engine.py            # Bundle-based self-optimization
└── nanobot/                  # Channel integrations
```

---

## 4. Architecture (v2.0.2)

### Core Flow
```
用户输入 (CLI / 飞书)
    │
    ▼
GatewayServer
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  CommunicationHub (共享聊天室)                     │
│  - Hub 消息队列，所有组件通过它通信                 │
└─────────────────────────────────────────────────────┘
    │                    │                     │
    ▼                    ▼                     ▼
MasterAgent          InferenceTools        Autonomous
(路由+演绎+转发)    (standard/supervised)  (Bundle)
```

### GatewayMasterAgent Responsibilities
1. **路由决策**: LLM 浅思考判断走 simple_direct 还是推理工具
2. **Hub 通信**: 发送/接收消息
3. **结果演绎**: 推理工具结果经过 MasterAgent 加工
4. **人在回路转发**: 推理工具暂停时转发给用户确认
5. **连续对话**: 读取上下文
6. **记忆读取**: Whiteboard / Hot / Warm / QMD

### Inference Tools
| Tool | 说明 | 人在回路 |
|------|------|----------|
| `standard` | 标准8步推理 | 否 |
| `supervised` | 人在回路推理 | 是 (ANALYSIS_REVIEW, PLAN_REVIEW) |
| `swarms` | 多Worker协作 | 否 |

### CommunicationHub Message Types
- `TASK_REQUEST` / `TASK_RESULT`: MasterAgent ↔ InferenceTool
- `SUSPEND_REQUEST` / `RESUME_REQUEST`: 人在回路
- `AUTONOMOUS_REQUEST` / `AUTONOMOUS_STATUS`: MasterAgent ↔ Autonomous
- `HUMAN_IN_LOOP_REQUEST` / `RESPONSE`: 转发用户确认

---

## 5. Testing Guidelines

### Smoke Test Checklist (11项)

| # | 验证项 | 测试方法 |
|---|--------|----------|
| 1 | MasterAgent 人设/boot/skill/记忆/工具 | 基础对话验证 |
| 2 | 简单问题直接回复 | 发送简单问候 |
| 3 | MasterAgent 读取记忆 | 询问之前保存的内容 |
| 4 | 连续对话 | 多轮对话验证上下文 |
| 5 | 推理工具执行 | 发送复杂问题 |
| 6 | MasterAgent 演绎结果 | 检查结果是否经过加工 |
| 7 | 推理工具使用记忆 | 检查 Whiteboard/Hot/Warm/QMD 读写 |
| 8 | 推理工具使用 Skill/Tool | 验证技能调用 |
| 9 | 人在回路 | 发送需要确认的复杂任务 |
| 10 | Autonomous Bundle 设计 | 发送需要自主研究的任务 |
| 11 | Bundle 自我优化 | 验证优化效果 |

---

## 6. Adding New Components

### Adding a new Inference Tool
1. Create class inheriting `BaseInferenceTool` in `swarmbot/loops/`
2. Implement `run(user_input, session_id)` method
3. Add config to `boot/inference_tools.md`
4. **No code changes needed in MasterAgent**

### Adding a new Channel
1. Create class in `swarmbot/nanobot/channels/`
2. Inherit from `BaseChannel`
3. Register in `ChannelManager`
