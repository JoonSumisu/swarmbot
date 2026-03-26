# Swarmbot v2.4.0

**Swarmbot (v2.4.0)** 是一个基于 **CoreAgent 统一架构**的多 Agent 智能系统，支持本地 OpenAI 兼容接口模型与统一 SQLite 记忆系统。

> **核心理念**: "All-in-One" —— CoreAgent 统一入口，自评估循环，智能委托推理。

---

## 核心架构 (v2.4.0)

### 架构图

```
用户输入 (CLI / 飞书)
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     GatewayMasterAgent                               │
│  • 加载 SOUL.md（唯一有角色设定的组件）                              │
│  • 构建上下文（记忆、技能、工具）                                    │
│  • 调用 CoreAgent 统一处理                                           │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        CoreAgent                                     │
│  ─────────────────────────────────────────────────────────────────  │
│  • 加载记忆上下文（对话历史 + 关键事实 + 冷记忆）                    │
│  • 加载可用技能列表                                                  │
│  • 使用工具调用（file_read, web_search...）                          │
│  • 自评估循环 → decision: stop / continue / delegate                 │
└─────────────────────────────────────────────────────────────────────┘
    │
    │ delegate (复杂推理任务)
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Inference Loop (Worker)                         │
│  • 不加载 SOUL.md（无角色设定，工具化设计）                          │
│  • 加载 inference_boot.md + 工具定义                                 │
│  • 专注执行具体任务，不与用户对话                                     │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     AutonomousEngine                                 │
│  • 不加载 SOUL.md（无角色设定）                                       │
│  • Bundle 定时任务 + ReflectionEngine                                │
└─────────────────────────────────────────────────────────────────────┘
```

### CoreAgent 核心思想

**所有任务都走 CoreAgent 循环**：
1. **简单任务** → 1-2 次迭代 → stop
2. **中度任务** → 多次迭代 → stop
3. **复杂任务** → 自评估发现需要委托 → delegate → 启用 Inference Loop

### Boot 结构

```
~/.swarmbot/boot/
├── master/                          # MasterAgent 专用（唯一有 SOUL.md）
│   ├── SOUL.md                      # 角色设定
│   ├── IDENTITY.md                  # 身份标识
│   ├── USER.md                      # 用户偏好
│   └── masteragentboot.md           # MasterAgent 行为指南
├── inference/                       # 推理工具专用（无 SOUL.md）
│   ├── inference_boot.md            # 推理流程定义
│   ├── inference_tools.md           # 工具注册表
│   └── swarmboot.md                 # Swarm 配置
├── autonomous/                      # AutonomousEngine 专用（无 SOUL.md）
│   └── autonomous_boot.md           # 自主行为定义
├── shared/                          # 共享配置
│   ├── TOOLS.md                     # 工具定义
│   └── HEARTBEAT.md                 # 心跳配置
└── boot_config.json                 # Boot 加载配置
```

---

## 记忆系统 (v2.2.0)

### 统一 SQLite 记忆管理器

| 表名 | 用途 | 说明 |
|------|------|------|
| `conversations` | 对话记录 | 实时记录每轮对话 |
| `key_facts` | 关键事实 | LLM 提取的重要信息 |
| `episodes` | 冷记忆/归档 | Compact 写入 |
| `entities` | 实体追踪 | 用户信息、技术栈等 |
| `relations` | 实体关系 | 图遍历支持 |
| `autonomous_actions` | 自主动作记录 | AutonomousEngine 执行记录 |

### 图遍历能力

```python
# 递归 CTE 图遍历
MemoryManager.traverse_graph(start_entity, relation_types, max_depth)

# 最短路径查询
MemoryManager.find_shortest_path(from_entity, to_entity)

# 邻居查询
MemoryManager.get_entity_neighbors(entity_id)
```

---

## 推理工具

| 工具 | 说明 | 人在回路 |
|------|------|----------|
| `standard` | 标准推理 (4步) | 否 |
| `supervised` | 带暂停点，需确认 | 是 |
| `swarms` | 多 Worker 协作 | 否 |
| `subswarm` | 异步子任务编排 | 可选 |

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
```

### 3. 配置模型

```bash
swarmbot provider add \
  --base-url "http://127.0.0.1:8000/v1" \
  --api-key "sk-xxxx" \
  --model "qwen3-coder-next"
```

---

## 项目结构

```
swarmbot/
├── core/                      # CoreAgent 统一核心
│   ├── agent.py              # CoreAgent 实现
│   ├── agent_config.py       # 配置
│   ├── assessment.py         # 自评估
│   └── boot_loader.py        # Boot 加载器
├── gateway/                   # 网关组件
│   ├── server.py             # HTTP 服务器
│   ├── orchestrator.py       # GatewayMasterAgent
│   └── communication_hub.py  # 消息队列
├── loops/                     # 推理工具
│   ├── inference_standard.py # 标准推理
│   ├── inference_supervised.py # 人在回路
│   ├── inference_swarms.py   # 多Worker
│   └── inference_subswarm.py # 异步子任务
├── memory/                    # 记忆系统
│   ├── memory_manager.py     # 统一 SQLite 记忆管理器
│   ├── whiteboard.py         # 临时白板
│   └── cold_memory.py        # 冷记忆接口
├── autonomous/                # 自主引擎
│   ├── engine.py             # BundleGovernor
│   └── reflection.py         # 反思引擎
├── channels/                  # 通道集成
│   ├── feishu.py             # 飞书
│   ├── slack.py              # Slack
│   ├── discord.py            # Discord
│   └── ...
├── skills/                    # 技能目录
└── tools/                     # 工具适配器
```

---

## License

MIT License

---

## Contributors

- [JoonSumisu](https://github.com/JoonSumisu) - Original Author
- [opencode](https://opencode.ai) - CoreAgent Architecture
