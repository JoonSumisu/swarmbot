# Swarmbot 系统设计文档 (v0.5.4)

本文档旨在详尽描述 Swarmbot 的当前系统架构、核心组件设计、配置逻辑及调用链路，防止未来开发中的功能回归或错误覆写。

## 1. 系统概览 (Architecture Overview)

Swarmbot 是一个基于 **Nanobot** 框架演进的多 Agent 协作系统（Swarm），支持本地与云端 LLM 模型。其核心理念是去中心化的 Agent 协作（MoE - Mixture of Experts）与持久化记忆（QMD - Quantum Memory Drive）。

### 核心特性
- **双层架构**：底层基于 Nanobot 提供工具与通道支持，上层 SwarmManager 管理多 Agent 协作。
- **纯粹的 LLM 客户端**：通过 `OpenAICompatibleClient` 直接对接 LiteLLM，移除了复杂的中间件 Provider 抽象。
- **本地优先**：原生支持 vLLM 等本地推理端点，自动归一化 OpenAI 兼容接口。
- **守护进程 (Daemon)**：后台管理 Gateway、Overthinking Loop 和健康检查。

---

## 2. 核心组件设计

### 2.1 LLM Client (`swarmbot.llm_client`)
**职责**：负责所有与 LLM 的交互，是系统唯一的出口。
- **实现**：`OpenAICompatibleClient`。
- **依赖**：直接调用 `litellm.completion` / `acompletion`。
- **配置**：
  - 仅接受 `LLMConfig` 对象。
  - **关键逻辑**：
    - **禁止自动 URL 修正**：不再自动为本地 IP 追加 `/v1`，完全尊重用户配置的 `base_url`。
    - **日志抑制**：默认关闭 LiteLLM 的 `debug_info` 和 `drop_params` 警告。
    - **错误处理**：包含重试机制（Exponential Backoff）和 Schema 错误降级（自动重试不带工具的请求）。

### 2.2 配置管理 (`swarmbot.config_manager`)
**职责**：加载和保存全局配置。
- **路径**：`~/.swarmbot/config.json`。
- **数据结构**：
  - `providers`: 列表，但 CLI 逻辑目前强制仅使用第一个作为 Primary。
  - `swarm`: 定义 `max_agents`, `architecture` 等。
  - `daemon`: 定义后台服务行为（Gateway, Overthinking 启停）。
  - `channels`: 定义消息通道（Feishu, Telegram 等）。
- **默认行为**：
  - `daemon.manage_gateway`: **True** (默认启动 Gateway)。
  - `daemon.manage_overthinking`: **True** (默认启动 Overthinking)。

### 2.3 守护进程 (`swarmbot.daemon`)
**职责**：作为系统常驻进程，维持核心服务运行。
- **启动方式**：`swarmbot daemon start`。
- **管理服务**：
  1.  **Gateway** (`swarmbot.cli gateway`): 处理外部消息（Feishu 等）并分发给 Swarm。
  2.  **Overthinking** (`swarmbot.cli overthinking start`): 后台自主思考循环。
- **机制**：
  - 使用 `subprocess.Popen` 启动子进程。
  - 自动重启崩溃的子进程。
  - 定期备份配置与 Boot 文件。

### 2.4 网关与消息路由 (`swarmbot.gateway`)
**职责**：连接外部消息通道与内部推理循环。
- **实现**：`GatewayServer`。
- **流程**：
  1.  初始化 Channels (如 Feishu)。
  2.  接收 `InboundMessage`。
  3.  将消息放入线程池，调用 `InferenceLoop.run()`。
  4.  获取结果并封装为 `OutboundMessage` 返回。
- **注意**：不再使用 `nanobot` 的 AgentLoop，而是直接使用 Swarmbot 的 `InferenceLoop`。

### 2.5 推理循环 (`swarmbot.loops.inference`)
**职责**：处理单次用户请求的完整生命周期。
- **流程 (SOP)**：
  1.  **Analysis**: 分析用户意图（无工具）。
  2.  **Collection**: 收集上下文与记忆（有工具）。
  3.  **Planning**: 生成行动计划（JSON）。
  4.  **Execution**: 执行计划中的任务（多 Agent 并行/串行）。
  5.  **Evaluation**: 评估结果质量。
  6.  **Response**: 生成最终回复。
- **记忆交互**：
  - Whiteboard (L1): 瞬时记忆，仅在 Loop 内有效。
  - HotMemory (L2): 短期记忆，持久化到工作区。

---

## 3. 关键调用链路

### 3.1 用户发送消息 (CLI/Feishu)
```mermaid
[User] -> [Channel (Feishu)] -> [MessageBus] -> [GatewayServer]
                                                      |
                                          (ThreadPoolExecutor)
                                                      v
                                              [InferenceLoop]
                                                      |
                                            [OpenAICompatibleClient]
                                                      |
                                                  (LiteLLM)
                                                      v
                                              [Local/Remote LLM]
```

### 3.2 守护进程启动
```mermaid
[CLI: daemon start] -> [Daemon Process]
                            |-- (Spawn) --> [Gateway Process]
                            |-- (Spawn) --> [Overthinking Process]
                            |-- (Loop)  --> [Health Check / Backup]
```

---

## 4. 维护与防回归指南

1.  **禁止恢复 `nanobot.providers`**：
    -   系统已彻底解耦 `nanobot` 的 provider 抽象。任何新功能必须通过 `llm_client.py` 实现。
    -   `litellm_provider.py` 应保持为空或被删除状态（目前已精简）。

2.  **本地模型兼容性**：
    -   所有 URL 处理逻辑必须在 `llm_client.py` 中显式处理，**严禁**隐式修改用户输入的 `base_url`（如自动加 `/v1`），除非是明确的协议适配层。
    -   配置中必须明确区分 `openai/` 前缀的使用场景（LiteLLM 路由需求）。

3.  **Daemon 默认值**：
    -   `config_manager.py` 中 `DaemonConfig` 的 `manage_gateway` 和 `manage_overthinking` 必须默认为 `True`，确保开箱即用。

4.  **依赖管理**：
    -   `nanobot` 目录下的代码仅作为工具库（Bus, Channels, Tools）保留，**不应**包含核心 Agent 逻辑。

---

## 5. 当前版本状态 (v0.5.4)
- **状态**：Stable
- **已知问题修复**：
  - 修复了本地模型因自动追加 `/v1` 导致的 404 错误。
  - 修复了 LiteLLM 日志过噪问题。
  - 修复了 Daemon 不自动启动 Gateway 的问题。
