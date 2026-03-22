# Swarmbot v2.0.2

[English](README.md) | [中文](README.md)

**Swarmbot (v2.0.2)** 是一个基于 **GatewayMasterAgent + CommunicationHub** 架构的多 Agent 智能系统，支持本地 OpenAI 兼容接口模型与 QMD 四层记忆系统。

> **核心理念**: "All-in-One" —— 网关编排、记忆管理、工具链和多智能体推理融合在一个轻量级进程中。

---

## 核心架构 (v2.0.2)

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
| **BundleGovernor** | Bundle 生命周期管理：暂停/恢复/淘汰 |

---

## 记忆系统 (L1-L4 + L1.5)

| 层级 | 类型 | 说明 |
|------|------|------|
| L1 | Whiteboard | 会话级临时工作区 |
| L1.5 | SessionMemory | chat_id 索引，7天TTL |
| L2 | HotMemory | 全局待办/计划，跨会话 |
| L3 | WarmMemory | 每日归档日志 |
| L4 | ColdMemory | QMD 语义向量库 |

---

## 推理工具

| 工具 | 说明 | 人在回路 |
|------|------|----------|
| `standard` | 标准 8 步推理 | 否 |
| `supervised` | 带暂停点，需确认 | 是 |
| `swarms` | 多 Worker 协作 | 否 |
| `subswarm` | 异步子任务编排 | 可选 |

### 8 步标准推理流程

```
1. Analysis    → 意图分析 (无工具)
2. Collection  → 上下文收集 (web_search, browser, file)
3. Planning    → 生成行动计划 (JSON)
4. Execution   → 并行执行任务
5. Evaluation  → 质量评估 (3 workers voting)
6. Translation → 生成最终回复
7. Organization → 响应整理
8. Output      → 返回结果
```

---

## SkillPool (能力固化池)

SkillPool 从 Bundle 执行经验中生成可复用 Skills，支持 MasterAgent 和 AutonomousEngine 使用：

- **SkillGenerator**: 从高质量执行生成 Skills
- **SkillOptimizer**: 基于使用统计优化
- **SkillRecommender**: 任务-Skill 智能匹配

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
│   ├── whiteboard.py        # L1
│   ├── session_memory.py    # L1.5
│   ├── hot_memory.py        # L2
│   ├── warm_memory.py       # L3
│   └── cold_memory.py       # L4
├── autonomous/               # 自主引擎
│   └── engine.py            # BundleGovernor
├── skill_pool.py            # 能力固化池
└── nanobot/                  # 通道集成
```

---

## 测试

### 运行测试

```bash
# 11项检查清单
python3 tests/test_full_integration.py --model qwen3.5-35b-a3b --base-url http://100.110.110.250:7788

# 冒烟测试
python3 tests/smoke_test_v2.py --quick

# SubSwarm 测试
python3 tests/test_subswarm.py --quick
```

### 测试结果 (v2.0.2)

| 测试 | 结果 |
|------|------|
| 11项检查清单 | ✅ 11/11 |
| 冒烟测试 | ✅ 8/8 |
| SubSwarm | ✅ 4/4 |

---

## BundleGovernor

BundleGovernor 负责 Bundle 生命周期管理：

| 状态 | 说明 |
|------|------|
| active | 正常运行 |
| paused | 暂停 (效率 < 0.3) |
| retired | 淘汰 (效率 < 0.15) |

### 效能评分维度

- 成功率 (30%)
- 平均执行时间 (20%)
- 价值产出 (30%)
- 资源效率 (20%)

---

## 文档

- [AGENTS.md](AGENTS.md) - 开发指南
- [swarmbot/boot/inference_tools.md](swarmbot/boot/inference_tools.md) - 推理工具配置

---

## License

MIT License

---

## 👥 Contributors

- [JoonSumisu](https://github.com/JoonSumisu) - Original Author
- [opencode](https://opencode.ai) - v2.0.2 Architecture Enhancement
