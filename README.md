# Swarmbot v2.2.0

[English](README.md) | [中文](README.md)

**Swarmbot (v2.2.0)** 是一个基于 **GatewayMasterAgent + CommunicationHub** 架构的多 Agent 智能系统，支持本地 OpenAI 兼容接口模型与统一 SQLite 记忆系统。

> **核心理念**: "All-in-One" —— 网关编排、记忆管理、工具链和多智能体推理融合在一个轻量级进程中。

---

## 核心架构 (v2.2.0)

### 架构图

```
用户输入 (CLI / 飞书)
    │
    ▼
GatewayServer
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  CommunicationHub (共享聊天室)                       │
│  - Hub 消息队列，所有组件通过它通信                 │
└─────────────────────────────────────────────────────┘
    │                    │                     │
    ▼                    ▼                     ▼
GatewayMasterAgent    InferenceTools      AutonomousEngine
(路由+演绎+转发)      (standard/swarms)    (BundleGovernor)
```

### 核心组件

| 组件 | 说明 |
|------|------|
| **GatewayMasterAgent** | 智能网关核心：路由决策、结果演绎、人在回路 |
| **CommunicationHub** | FIFO 消息队列：topic/swarm_id 组织消息 |
| **InferenceTools** | 可插拔推理工具：standard/supervised/swarms/subswarm |
| **AutonomousEngine** | Bundle 自主引擎：后台自优化 |
| **ReflectionEngine** | 自主反思：每小时随机探索记忆，判断推展性 |

---

## 记忆系统 (v2.2.0)

### 统一 SQLite 记忆管理器

| 表名 | 用途 | 说明 |
|------|------|------|
| `conversations` | 对话记录 | 实时记录每轮对话 |
| `key_facts` | 关键事实 | LLM 提取的重要信息 |
| `episodes` | 知识片段 | 冷记忆，包含归档数据 |
| `entities` | 实体追踪 | 用户信息、技术栈等 |
| `relations` | 实体关系 | 实体间的关联 |
| `autonomous_actions` | 自主动作记录 | AutonomousEngine 执行记录 |

### 记忆流转

```
用户输入
    │
    ▼
MasterAgent (simple_direct / 推理模式)
    ├── 读取: conversations + key_facts + episodes
    └── 写入: conversations (实时)

会话 > 30 轮 → Auto Compact
    ├── 保留最近10轮对话
    └── 归档旧轮次到 episodes

后台线程: extract_facts_from_turn
    ├── LLM 提取关键事实
    └── 写入 key_facts + entities

AutonomousEngine (每小时)
    ├── ReflectionEngine 随机探索记忆
    ├── 判断推展性
    └── 30% 概率行动（整理/学习/提议）
```

---

## 推理工具

| 工具 | 说明 | 人在回路 |
|------|------|----------|
| `standard` | 标准推理 (4步) | 否 |
| `supervised` | 带暂停点，需确认 | 是 |
| `swarms` | 多 Worker 协作 | 否 |
| `subswarm` | 异步子任务编排 | 可选 |

### 标准推理流程

```
1. Analysis    → 意图分析 + 上下文收集 (无工具)
2. Planning    → 生成行动计划 (JSON)
3. Execution   → 并行执行任务 (最多3个)
4. Evaluation  → 质量评估 (完成率>=70%)
```

结果通过 Hub 发送给 MasterAgent，由 MasterAgent 演绎后回复用户。

---

## AutonomousEngine

### Bundles

| Bundle | 间隔 | 用途 |
|--------|------|------|
| `core.memory_foundation` | 30分钟 | 记忆整理 |
| `core.boot_optimizer` | 20分钟 | Boot 优化 |
| `core.system_hygiene` | 10分钟 | 磁盘/内存检查 |
| `core.bundle_governor` | 5分钟 | Bundle 冲突检测 |
| `core.reflection` | 60分钟 | 自主反思 |

### ReflectionEngine

```
每小时一次
    │
    ▼
随机获取记忆起点
    │
    ▼
时间线探索（最多5次追问）
    │
    ▼
LLM 判断推展性
    │
    ├── 没有 → 什么都不做 (60%)
    ├── 需要整理 → 整理记忆 (15%)
    ├── 需要学习 → 搜索补充 (20%)
    └── 可以行动 → 提议给用户 (5%)
```

---

## 快速开始

### 1. 安装

```bash
git clone https://github.com/JoonSumisu/swarmbot.git
cd swarmbot
python3 scripts/bootstrap.py
```

### 2. 首次启动

```bash
swarmbot onboard          # 初始化配置
swarmbot run             # CLI 交互模式
swarmbot gateway         # 启动网关
swarmbot daemon start    # 启动守护进程
```

### 3. 配置模型

```bash
swarmbot provider add \
  --base-url "http://127.0.0.1:8000/v1" \
  --api-key "sk-xxxx" \
  --model "qwen3-coder-next"
```

---

## CLI 命令

| 命令 | 说明 |
|------|------|
| `swarmbot run` | CLI 交互模式 (MasterAgent) |
| `swarmbot gateway` | 启动网关服务 |
| `swarmbot daemon start` | 启动守护进程 |
| `swarmbot status` | 查看状态 |
| `swarmbot onboard` | 初始化配置 |

### CLI 交互命令

| 命令 | 说明 |
|------|------|
| `/clear` | 清除会话状态 |
| `/compact` | 压缩会话历史 |
| `/status` | 查看会话状态 |
| `/quit` | 退出 |

---

## 项目结构

```
swarmbot/
├── boot/                     # Boot 文件 (SOUL.md, inference_tools.md)
├── cli.py                    # CLI 入口
├── config_manager.py         # 配置管理
├── llm_client.py            # LLM 客户端
├── daemon.py                 # 守护进程
├── gateway/                  # 网关组件
│   ├── server.py            # HTTP 服务器
│   ├── orchestrator.py     # GatewayMasterAgent
│   ├── communication_hub.py # 消息队列
│   └── subswarm_manager.py  # 子任务管理
├── loops/                    # 推理工具
│   ├── base.py             # 基类
│   ├── inference_standard.py # 标准推理
│   ├── inference_supervised.py # 人在回路
│   ├── inference_swarms.py  # 多Worker
│   └── inference_subswarm.py # 异步子任务
├── memory/                   # 记忆系统
│   ├── memory_manager.py    # 统一 SQLite 记忆管理器
│   ├── whiteboard.py        # 临时白板
│   └── cold_memory.py       # 冷记忆接口
├── autonomous/               # 自主引擎
│   ├── engine.py            # BundleGovernor
│   └── reflection.py        # 反思引擎
└── nanobot/                  # 通道集成
```

---

## 测试

### 运行测试

```bash
# 快速测试
python3 tests/quick_test.py

# 完整 8 轮记忆测试
python3 -c "
from swarmbot.config_manager import load_config, WORKSPACE_PATH
from swarmbot.gateway.orchestrator import GatewayMasterAgent
orch = GatewayMasterAgent(WORKSPACE_PATH, load_config())
turns = ['你好，我是张三', '我住在北京', '你还记得我叫什么名字吗？']
for t in turns:
    print(orch.handle_message(t, 'test'))
"
```

### 测试结果 (v2.2.0)

| 测试 | 结果 |
|------|------|
| 8 轮记忆测试 | ✅ 8/8 |
| 记忆回忆 | ✅ 正确 |
| 平均响应时间 | ✅ 11.2s |

---

## License

MIT License

---

## 👥 Contributors

- [JoonSumisu](https://github.com/JoonSumisu) - Original Author
- [opencode](https://opencode.ai) - v2.2.0 Memory System Architecture
