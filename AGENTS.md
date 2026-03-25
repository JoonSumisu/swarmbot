# AGENTS.md - Swarmbot Development Guide (v2.2.0)

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
│   ├── master/              # MasterAgent boot files
│   ├── inference/           # Inference tool boot files
│   ├── autonomous/          # Autonomous engine boot files
│   └── shared/              # Shared boot files
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
│   ├── inference_standard.py # Standard inference (4 steps)
│   ├── inference_supervised.py # Human-in-the-loop inference
│   ├── inference_swarms.py   # Multi-worker inference
│   └── skill_registry.py     # Skill registry
├── memory/                   # Memory system
│   ├── memory_manager.py    # Unified SQLite memory manager
│   ├── whiteboard.py        # Temporary workspace for inference
│   └── cold_memory.py       # Cold memory interface
├── autonomous/               # Autonomous engine
│   ├── engine.py            # BundleGovernor + self-optimization
│   └── reflection.py        # Reflection engine
└── nanobot/                  # Channel integrations
```

### Key Components

| Component | File | Description |
|-----------|------|-------------|
| GatewayMasterAgent | `gateway/orchestrator.py` | 路由、演绎、人在回路 |
| CommunicationHub | `gateway/communication_hub.py` | FIFO 消息队列 |
| MemoryManager | `memory/memory_manager.py` | 统一 SQLite 记忆管理 |
| ReflectionEngine | `autonomous/reflection.py` | 自主反思引擎 |
| AutonomousEngine | `autonomous/engine.py` | Bundle 自主引擎 |

---

## 4. Architecture (v2.2.0)

### Memory System (统一 SQLite 记忆系统)
```
┌─────────────────────────────────────────────────────────────────────┐
│  MemoryManager (SQLite 单例)                                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  conversations  → 对话记录，实时写入每轮对话                         │
│                                                                      │
│  key_facts      → 关键事实，LLM 提取的重要信息                       │
│                                                                      │
│  episodes       → 知识片段，包含归档数据和冷记忆                     │
│                                                                      │
│  entities       → 实体追踪，用户信息、技术栈等                       │
│                                                                      │
│  relations      → 实体关系，实体间的关联                             │
│                                                                      │
│  autonomous_actions → 自主动作记录                                   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘

Whiteboard → 单次推理内的临时工作区，Loop 完成后清除
```

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
(路由+演绎+转发)    (standard/supervised)  (Bundle + Reflection)
```

### GatewayMasterAgent Responsibilities
1. **路由决策**: LLM 浅思考判断走 simple_direct 还是推理工具
2. **Hub 通信**: 发送/接收消息
3. **结果演绎**: 推理工具结果经过 MasterAgent 加工
4. **人在回路转发**: 推理工具暂停时转发给用户确认
5. **连续对话**: 读取上下文
6. **记忆读写**: MemoryManager (conversations + key_facts + episodes)

### Inference Tools
| Tool | 说明 | 人在回路 |
|------|------|----------|
| `standard` | 标准推理 (4步: 分析/规划/执行/评估) | 否 |
| `supervised` | 人在回路推理 | 是 (ANALYSIS_REVIEW, PLAN_REVIEW) |
| `swarms` | 多Worker协作 | 否 |
| `subswarm` | 异步子任务编排 | 可选 |

### AutonomousEngine Bundles
| Bundle | 间隔 | 用途 |
|--------|------|------|
| `core.memory_foundation` | 30分钟 | 记忆整理 |
| `core.boot_optimizer` | 20分钟 | Boot 优化 |
| `core.system_hygiene` | 10分钟 | 磁盘/内存检查 |
| `core.bundle_governor` | 5分钟 | Bundle 冲突检测 |
| `core.reflection` | 60分钟 | 自主反思 |

### ReflectionEngine
- 每小时随机获取记忆起点
- 时间线探索（最多5次追问）
- LLM 判断推展性
- 30% 概率行动（整理/学习/提议）

---

## 5. Testing Guidelines

### Smoke Test Checklist (8项)

| # | 验证项 | 测试方法 |
|---|--------|----------|
| 1 | MasterAgent 人设/boot/skill/记忆/工具 | 基础对话验证 |
| 2 | 简单问题直接回复 | 发送简单问候 |
| 3 | MasterAgent 读取记忆 | 询问之前保存的内容 |
| 4 | 连续对话 | 多轮对话验证上下文 |
| 5 | 推理工具执行 | 发送复杂问题 |
| 6 | MasterAgent 演绎结果 | 检查结果是否经过加工 |
| 7 | 记忆持久化 | 检查 MemoryManager 记录 |
| 8 | Compact 功能 | 验证 30 轮触发 compact |

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
