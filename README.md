# Swarmbot

[中文](README.md) | [English](README_EN.md)

Swarmbot 是一个运行在本地环境中的 **多 Agent 集群智能系统 (Multi-Agent Swarm System)**。

当前版本以 **[swarms](https://github.com/kyegomez/swarms)** 的多智能体编排能力与 **QMD（三层记忆）** 为核心，nanobot 仅以 vendored 源码形式保留少量兼容性组件，不再对外暴露网关/cron 管理接口，专注为本地/私有 OpenAI 兼容接口提供稳健的任务规划与执行能力。

开发文档见 [development.md](file:///root/swarmbot/docs/development.md)。

> **核心理念**: 通过 Swarm 多智能体 + 本地三层记忆，把一次性对话升级为可持续演进的长期任务工作流。

---

## 🌟 核心架构 v0.3.1 (Emergency Update)

Swarmbot 不是简单的组件堆叠，而是实现了“三位一体”的深度融合，在 v0.3.1 中形成了更稳定的本地运行架构与 **Tri-Boot 认知系统**，并增强了**容灾与自律**能力：

### 1. High Availability & Connectivity
*   **Provider Failover (New)**: 支持配置主备 LLM Provider。当主 Provider (如本地 vLLM) 请求失败时，自动无缝切换至备用 Provider (如云端 API 或其他本地实例)，确保服务高可用。
*   **Connectivity Test**:
    *   可以使用 `test_feishu_send.py` 中的 “🔍 Swarmbot Connectivity Test: Active Send” 作为 Feishu 连通性探针；
    *   生产环境建议 **最多每小时执行一次**（例如通过系统级 cron），以平衡「异常发现速度」与「额外请求开销」。

### 2. Intelligent Session Management (New)
*   **Topic Relevance Filtering**: 在加载历史会话上下文时，引入智能相关性评分机制。仅保留与当前用户输入（Topic）强相关的历史片段，有效隔离无关话题干扰，提升 Context 纯度。
*   **Automated Compression**: 结合 Overthinking 机制，自动识别并压缩/归档陈旧的会话日志，保持 Workspace 轻量化，防止 Token 浪费。

### 3. Enhanced Overthinking (Self-Evolution)
*   **Boot Optimization**: Overthinking Loop 具备优化自身启动配置 (`swarmboot.md`) 的能力。基于长期记忆与任务复盘，自动调整系统 Prompt 与行为准则。
*   **Proactive Communication**: 能够基于记忆中的待办事项或重要发现，主动通过配置的 Channel (如 Feishu) 向用户发起沟通，不再是被动等待指令。
*   **Future Planning**: 在空闲时自主规划 `.swarmbot` 内部的未来行动路径（代码优化、知识整理等），并将计划写入 QMD。
*   **Tri-Boot System**:
    - **Swarm Boot (Instinct)**: `swarmbot/boot/swarmboot.md` - 理性大脑。
    - **Master Agent Boot (Consciousness)**: `swarmbot/boot/masteragentboot.md` - 人格与意识。
    - **Overthinking Boot (Subconscious)**: `loops/overthinking.py` - 潜意识与自我进化。

### 4. Swarm Orchestration (Swarms Integrated)
*   **来源**: 集成 `swarms` 框架的多智能体编排逻辑。
*   **作用**: 管理 Agent 间的协作流。
*   **架构支持**:
    *   `Sequential`: 线性流水线（适合 SOP）。
    *   `Concurrent`: 并行执行（默认；更适合小模型/本地模型）。
    *   `Hierarchical`: 层级指挥（Director -> Workers）。
    *   `Mixture of Experts (MoE)`: 动态专家网络，支持多轮辩论与共识达成。
    *   `State Machine`: 动态状态机（适合 Code Review 循环）。
    *   `Auto`: 大模型可选；根据任务自动选择架构，并动态生成专用 Agent 角色（存在一定随机性）。

### 4. Core Agent
*   **来源**: 以轻量化后的 `CoreAgent` 为核心，不再直接依赖运行时 nanobot AgentLoop。
*   **作用**: 作为 Swarm 中的执行单元，负责与 LLM 对话、调用工具并协调记忆。
*   **特性**: 
    *   **Tool Adapter**: 所有内置工具（文件操作、Shell 执行、浏览器、白板、Swarm 控制、`context_policy_update` 等）都通过 `tools/adapter.py` 暴露为 OpenAI 格式的 Tool，由 `ToolAdapter` 统一注册到 Swarm 的工具中心。
    *   **Node.js 零依赖**: 已移除 OpenClaw Bridge 与 Node.js 依赖，整个工具体系完全基于 Python 实现。
    *   **Web Search**: 集成本地浏览器/HTTP 抓取能力，用于获取 2024–2026 年的最新信息。
    *   **记忆优先**: 在构造提示词时优先从白板 + QMD 中抽取与当前问题强相关的上下文，并通过 `context_policy` 控制截断策略。

### 5. Tool & Skill Orchestration (Swarm-Level)
*   **统一工具空间**: 所有工具（文件/网络/执行/记忆/自我控制）都通过 `tools/adapter.py` 暴露为 OpenAI Tool，核心包括：
    *   文件与系统：`file_read`, `file_write`, `shell_exec`
    *   网络与浏览器：`web_search`, `browser_open`, `browser_read`
    *   记忆与协调：`whiteboard_update`
    *   自我控制：`swarm_control`（修改架构/Provider/Overthinking 等）
*   **Skill 支持**:
    *   本地技能：自动扫描 `~/.swarmbot/workspace/skills` 与内置 `swarmbot/nanobot/skills`，通过 `skill_summary` 列出，并用 `skill_load` 按需加载 `SKILL.md` 以节省 token。
    *   EvoMap 技能：可以使用 `skill_fetch` 工具从例如 `https://evomap.ai/skill.md` 获取远程 `SKILL.md`，缓存为本地技能目录（如 `skills/evomap/`），之后通过 `skill_summary` / `skill_load` 查看与复用。
*   **Swarm 级调用**: 在 Swarm 架构中，`planner/master` 等核心 Agent 会默认加载全部工具与技能签名，能够在推理过程中主动选择、组合和调用这些工具/skills 完成复杂任务，而不仅仅是单 Agent 的被动调用。

### 4. Tri-Layer Memory (QMD Powered)
*   **来源**: 基于 `qmd` 提供的本地向量检索引擎。
*   **作用**: 为 Agent 提供不同时间跨度的记忆支持。
*   **三层体系**:
    1.  **LocalMD (Short-term)**: 本地 Markdown 日志缓存，实时记录每日会话，作为短期工作记忆。
    2.  **MemoryMap (Whiteboard)**: 内存中的共享白板，存储任务全局状态、关键决策快照，确保多 Agent 信息同步。
    3.  **QMD (Long-term)**: 基于向量 + BM25 的持久化知识库，支持对历史文档和笔记的语义检索。
    4.  **Context Policy**: 白板摘要、本地历史与 QMD 检索结果的长度和条数由 Whiteboard 中的 `context_policy` 控制，LLM 可通过 `context_policy_update` 工具在每次推理前动态设置不同场景下的上下文预算（例如复杂运维诊断 vs 轻量问答）。

### 6. Overthinking Loop (Deep Thinking)
*   **功能**: 空闲时的后台深度思考循环（可选）。
*   **能力**:
    *   **记忆整理**: 从 LocalMD 提取关键事实与决策，按照「Facts / Experiences / Theories」三类结构化写入 QMD，方便后续检索与重用。
    *   **自我拓展**: 基于现有记忆进行逻辑推演，主动发现知识盲区，并生成新的假设与理论。
    *   **经验沉淀**: 将单次任务的成功/失败经验转化为通用的方法论，并记录在 QMD 的长期记忆集合中。
*   **工作机制**: 
    1.  监控用户空闲状态。
    2.  启动思考者 (Thinker Agent) 对近期日志进行反思。
    3.  生成 `# Reflection` 和 `# Insight` 并写入向量数据库。
    4.  激进清理短期日志，保持系统轻量化。

### 6. 记忆工作流（建议理解方式）
*   **收到 Prompt**: 查询 QMD + 当日 LocalMD 摘要，读取 `swarmboot.md`，并把结构化的 Prompt + 记忆注入 Whiteboard（`current_task_context`）。
*   **Swarm 执行中**: 各节点应优先读取 Whiteboard，确保对任务的共同理解；中间产物也会写入 Whiteboard。
*   **对话结束**: 白板内容会被整理写入 LocalMD（摘要/结论），然后清空 Whiteboard。
*   **Master 解释**: Master Agent 读取 `masteragentboot.md`，将 Swarm 的理性结果转化为符合人设的感性回复。
*   **空闲时**: Overthinking 将 LocalMD 进一步整理为可检索的长期记忆写入 QMD，并进行记忆“经验化/理论化”扩展。

---

## 快速开始

1. **安装依赖**
   ```bash
   chmod +x scripts/install_deps.sh
   ./scripts/install_deps.sh
   ```
   *脚本会自动尝试将 `swarmbot` 命令添加到系统路径。如果成功，你可以直接使用 `swarmbot` 命令；否则请使用生成的 `./swarmbot_run` 脚本。*

2. **初始化**
   ```bash
   # 如果 swarmbot 命令可用：
   swarmbot onboard
   
   # 或者使用 wrapper 脚本：
   ./swarmbot_run onboard
   ```

3. **配置模型提供方**
   ```bash
   # 添加自定义 OpenAI 兼容接口（例如本地模型）
   # 注意：请勿将真实 API Key / 内网地址提交到仓库
   swarmbot provider add --base-url "http://127.0.0.1:8000/v1" --api-key "YOUR_API_KEY" --model "your-model-name" --max-tokens 8192
   ```

4. **运行**
   ```bash
   swarmbot run
   # 或
   ./swarmbot_run run
   ```

### 4. 切换架构（Concurrent / Auto）
```bash
# 小模型/本地模型：默认 concurrent
./swarmbot_run config --architecture concurrent

# 大模型可启用 auto（存在一定随机性，适合更强的模型）
./swarmbot_run config --architecture auto --auto-builder true
```

### 5. 升级 (Update) [v0.2 新增]
```bash
# 拉取最新代码并保留个性化配置
./swarmbot_run update
```

---

## 推荐运行模板：守护进程 + 定时任务 + Heartbeat

本节给出一套**推荐模板**，用于开机后默认启动 Swarmbot 守护进程，并启用基础的定时任务和 Heartbeat。

### 1. 推荐的 daemon 配置片段

在 `~/.swarmbot/config.json` 中增加（或合并）如下段落：

```jsonc
"daemon": {
  // 配置/Boot 发生变化时才备份
  "backup_interval_seconds": 60,
  // 每小时做一次 LLM / Channel 健康检查
  "health_check_interval_seconds": 3600,
  // 可选：将备份同步到远端目录（例如 SMB 挂载点）
  // "backup_remote_path": "/mnt/swarmbot_backup",

  // 是否由 daemon 管理 gateway 与 Overthinking
  "manage_gateway": true,
  "manage_overthinking": false,

  // 子进程异常退出后的重启冷却时间（秒）
  "gateway_restart_delay_seconds": 10,
  "overthinking_restart_delay_seconds": 10
}
```

推荐做法：
- 开发调试阶段：先只打开 `manage_gateway`，确认网关与飞书等通道稳定；
- 稳定后，再考虑将 `manage_overthinking` 设为 `true`，让后台思考循环由 daemon 托管。

启动守护进程：

```bash
swarmbot daemon start
```

守护进程状态与健康检查结果会写入：

```bash
~/.swarmbot/daemon_state.json
```

其中包括：
- 最近一次备份时间与哈希
- LLM 健康状态（`llm_health`）
- Channel 健康状态（`channels.feishu` 等）
- gateway / overthinking 等子进程的 PID 与 last_start 时间

### 2. 推荐的 Heartbeat 模板

在 `~/.swarmbot/workspace/HEARTBEAT.md` 中可以使用如下推荐模板：

```markdown
# HEARTBEAT 任务清单（示例）

> 说明：Heartbeat 每次触发时，会读取本文件并尝试执行其中的任务。
> 建议只保留当前真正需要定期检查/维护的事项。

## 每次 HEARTBEAT 必做

- [ ] 检查 ~/.swarmbot/daemon_state.json 中的 llm_health 与 channels 状态，
      如发现异常，请在本文件下方追加「告警记录」。
- [ ] 检查最近 24h 的对话日志中是否有未完成的 TODO，将必要的信息写入 QMD。

## 定期维护建议

- [ ] 每天整理当天的关键决策与结论，写入一个「日报」文件。
- [ ] 每周检查一次 cron 任务列表，删除不再需要的任务。

## 告警记录

- （由 Agent 在执行 HEARTBEAT 后追加简短记录）
```

相关命令：

```bash
# 查看当前 HEARTBEAT 状态（是否存在、是否有待办）
swarmbot heartbeat status

# 立即执行一次 HEARTBEAT（会按照上面模板中的说明去检查任务）
swarmbot heartbeat trigger
```

### 3. 推荐的定时任务模板（系统级 cron）

当前版本中，Swarmbot 内置的 `swarmbot cron` 管理接口已禁用，仅保留配置结构用于兼容旧版本。生产环境推荐使用 **系统级 cron / 任务编排平台** 来调度以下命令：

```bash
# 每 60 分钟执行一次 HEARTBEAT（轻量自检）
swarmbot heartbeat trigger

# 每 60 分钟执行一次 Feishu 连通性检测（可选）
cd /root/swarmbot && python test_feishu_send.py
```

上述模板实现：
- Heartbeat：每小时唤醒一次 Agent，按照 `HEARTBEAT.md` 模板执行检查与记载；
- Connectivity Test：最多每小时向指定 Feishu 会话发送一次 “Swarmbot Connectivity Test: Active Send”，既能发现通道异常，又避免过于频繁的探测带来噪音与额外负载。

### 4. 开机默认启动（systemd 示例）

以下以 Linux + systemd 为例，给出一个推荐模板（需要 root 或合适权限手动配置）：

1. 创建 systemd service（示例路径：`/etc/systemd/system/swarmbot-daemon.service`）：

   ```ini
   [Unit]
   Description=Swarmbot Daemon
   After=network-online.target
   Wants=network-online.target

   [Service]
   Type=simple
   User=YOUR_LINUX_USER
   WorkingDirectory=/root/swarmbot
   ExecStart=/usr/bin/env swarmbot daemon start
   ExecStop=/usr/bin/env swarmbot daemon shutdown
   Restart=on-failure
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

2. 重新加载并启用服务：

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable swarmbot-daemon
   sudo systemctl start swarmbot-daemon

   # 查看状态
   sudo systemctl status swarmbot-daemon
   ```

注意：
- `User` 与 `WorkingDirectory` 请根据你的实际环境调整；
- 配置文件仍然位于当前用户的 `~/.swarmbot/config.json`；
- 请勿把真实的 `base_url`/`api_key` 之类敏感信息提交到仓库（仅写在本地 `config.json` 中）。

---

## 📖 CLI 功能详解

Swarmbot 提供了一套完整的命令行工具来管理 Agent 集群。

### 0. 配置文件位置
*   **配置文件**：`~/.swarmbot/config.json`
*   **Swarmbot 工作目录**：`~/.swarmbot/workspace`
*   **Boot 配置目录**：`~/.swarmbot/boot/` (含 `SOUL.md`, `TOOLS.md` 等)

### 1. `swarmbot onboard`
*   **功能**：初始化配置和工作区。
*   **做什么**：
    *   创建 `~/.swarmbot` 目录与 `config.json`
    *   创建 `~/.swarmbot/workspace`
    *   初始化内置 nanobot 网关所需目录（无需额外安装 nanobot）

### 2. `swarmbot run`
*   **功能**：启动交互式对话会话（本地调试）。
*   **行为**：循环读取终端输入，调用 SwarmManager 执行并输出结果。
*   **架构**：默认 `concurrent`（小模型更稳），可通过 `swarmbot config` 修改。

### 3. `swarmbot config`
*   **功能**：查看/修改 Swarm 工作模式（写入 `~/.swarmbot/config.json`）。
*   **常用参数**：
    *   `--agent-count <int>`：Swarm agent 数量
    *   `--architecture <name>`：选择架构（`concurrent`/`sequential`/`mixture`/`hierarchical`/`state_machine`/`auto` 等）
    *   `--max-turns <int>`：对话最大轮数（`0` 为不限制）
    *   `--auto-builder <true|false>`：是否启用 AutoSwarmBuilder（通常配合 `--architecture auto`）
*   示例：

```bash
./swarmbot_run config --architecture concurrent --agent-count 4
./swarmbot_run config --architecture auto --auto-builder true
```

### 4. `swarmbot provider`
*   **功能**：配置模型提供方（OpenAI 兼容接口）。
*   **子命令**：
    *   `provider add`：新增/覆盖 provider（仅保留一个）
    *   `provider delete`：清空 provider 配置（恢复默认）

```bash
# 本地模型配置示例（支持 Ollama, vLLM, LM Studio 等）
# 兼容 openai 格式，不再强制依赖 openai/ 前缀
./swarmbot_run provider add --base-url http://127.0.0.1:11434/v1 --api-key dummy --model llama3 --max-tokens 8192

# 远程模型配置示例
./swarmbot_run provider add --base-url https://api.moonshot.cn/v1 --api-key YOUR_API_KEY --model kimi-k2-turbo-preview --max-tokens 126000
```

### 5. `swarmbot status`
*   **功能**：打印当前 Swarmbot 状态（Provider/Swarm/Overthinking）。

### 6. `swarmbot gateway`
*   **功能**：启动多渠道网关（由 Swarmbot 接管并路由到 SwarmManager）。
*   **特性**：
    *   **默认后台运行**：v0.2+ 版本优化了启动逻辑，gateway 默认以守护进程（后台）方式运行，不占用当前终端。
    *   **日志输出**：启动后会提示日志文件位置（通常在 `~/.swarmbot/logs/gateway.log`）。
    *   **多渠道支持**：飞书、Slack、Telegram 等（统一从 `~/.swarmbot/config.json` 读取渠道配置）。
*   **使用方法**：
    ```bash
    # 启动网关（后台运行）
    swarmbot gateway
    
    # 查看运行日志
    tail -f ~/.swarmbot/logs/gateway.log
    ```


### 7. `swarmbot tool / channels / cron / agent / skill`
*   **功能**：管理内置 nanobot 的工具与通道能力（后续会逐步迁移为 Swarmbot 原生实现）。

### 9. `swarmbot overthinking`
*   **功能**：管理空闲时的后台深度思考循环。
*   **特性**：支持事实整理、经验提炼与自我理论拓展。
*   **子命令**：
    *   `overthinking setup`：配置开关/周期/步数
    *   `overthinking start`：前台启动循环（开发/调试用）

### 10. `swarmbot update` [v0.2.8]
*   **功能**：更新核心代码。
*   **特性**：
    *   保留 `swarmbot/boot/` 下的所有个性化配置。
    *   自动处理依赖更新与内置 Gateway 的迁移。

---

## 🗂️ 目录结构与模块说明

### 顶层目录
*   `swarmbot/`：Python 包主体（核心逻辑都在这里）
*   `tests/`：集成测试与单元测试（含 leaderboard_eval）
*   `scripts/`：安装/依赖脚本（例如安装 qmd、浏览器依赖）
*   `docs/`：[v0.2 新增] 开发文档

### `swarmbot/` 包内模块
*   [cli.py](swarmbot/cli.py)：命令行入口与子命令实现（onboard/run/config/provider/gateway 等）
*   [config_manager.py](swarmbot/config_manager.py)：配置文件读写与默认值（`~/.swarmbot/config.json`）
*   [config.py](swarmbot/config.py)：SwarmConfig/LLMConfig（给 SwarmManager 内部使用的配置结构）
*   [llm_client.py](swarmbot/llm_client.py)：OpenAI 兼容客户端封装（统一 completion 调用）
*   [gateway_wrapper.py](swarmbot/gateway_wrapper.py)：接管 nanobot gateway 的消息处理，将消息路由到 SwarmManager

### 启动与认知 (Boot) [v0.2 新增]
*   [boot/swarmboot.md](swarmbot/boot/swarmboot.md)：Swarm 启动配置
*   [boot/masteragentboot.md](swarmbot/boot/masteragentboot.md)：Master Agent 启动配置
*   [boot/SOUL.md](swarmbot/boot/SOUL.md)：人格核心
*   [boot/TOOLS.md](swarmbot/boot/TOOLS.md)：工具权限策略

### 多智能体编排（Swarm）
*   [swarm/manager.py](swarmbot/swarm/manager.py)：SwarmManager（架构选择、并发执行、共识裁决、白板注入/清理）
*   [swarm/agent_adapter.py](swarmbot/swarm/agent_adapter.py)：与 swarms 侧的适配/桥接（如有）

### Agent 核心（Core）
*   [core/agent.py](swarmbot/core/agent.py)：CoreAgent（组装消息、工具调用循环、把结果写入记忆）

### 记忆系统（Memory）
*   [memory/qmd.py](swarmbot/memory/qmd.py)：三层记忆实现（Whiteboard/LocalMD/QMD 搜索）
*   [memory/base.py](swarmbot/memory/base.py)：记忆存储的接口基类

### 工具系统（Tools）
*   [tools/adapter.py](swarmbot/tools/adapter.py)：工具适配器（file_read/file_write/web_search/shell_exec 等）
*   [tools/policy.py](swarmbot/tools/policy.py)：[v0.2 新增] 工具权限控制
*   [tools/openclaw_bridge.py](swarmbot/tools/openclaw_bridge.py)：[v0.2 新增] OpenClaw 桥接
*   [tools/browser/local_browser.py](swarmbot/tools/browser/local_browser.py)：本地无头浏览器/网页读取（用于 web_search/browser_read）

### 后台整理（Overthinking）
*   [loops/overthinking.py](swarmbot/loops/overthinking.py)：空闲时整理 LocalMD → 写入 QMD，并进行压缩/拓展

### 中间件与状态机
*   [middleware/long_horizon.py](swarmbot/middleware/long_horizon.py)：长程任务规划实验（WorkMapMemory/HierarchicalTaskGraph）
*   [statemachine/engine.py](swarmbot/statemachine/engine.py)：状态机执行引擎（适合“写-评审-再写”循环）

## 📊 测试与评估
*   单元测试：`python -m unittest discover -s tests -p "test*.py" -v`
*   评估脚本：`tests/integration/leaderboard_eval.py`（请使用你自己的模型与服务端点运行，避免在仓库中硬编码私有信息）

### PCM / Leaderboard 结果（历史记录）
在早期实验中，基于 `openbmb/AgentCPM-Explore-GGUF` 作为底座模型，在官方 PCM leaderboard 评测中：
*   本架构能够**完整跑通全部评测任务**（存在一定随机性），这也是当初设计 Swarm+Tri-Boot+工具/Skill 体系的重要依据之一。
*   该结果体现了当前架构在中文 Agent 任务上的适配能力与可行性，后续可以作为调优与回归测试的参考基线。

> 注：上述成绩属于历史实验结果，仅说明架构能力，不保证在任意模型/版本下都能复现；如需复现，请结合你自己的服务端点与模型权重，在本地重新运行 leaderboard 评估脚本。

### Evaluation 调整说明
为减少误判与更贴近真实使用，本项目对评分脚本做了小幅鲁棒性调整：
*   Persona anti-pattern 从泛化的 “User/Assistant” 改为更精确的标记（避免误伤 UserA）
*   部分赛题引入中英文/同义词匹配（例如 table/表格、rumor/leak/传闻/爆料）
*   Coding 评分避免依赖单一关键词（如 backtrack），以输出可用代码为主

---

## 🧩 飞书（Feishu）配置
Swarmbot 的唯一配置文件为 `~/.swarmbot/config.json`，飞书配置也在此处完成。
1. 在飞书开放平台创建应用并获取 `app_id/app_secret`
2. 将飞书配置写入 `~/.swarmbot/config.json` 的 `channels.feishu`
3. 启动网关：

```bash
swarmbot gateway
```

示例（请替换为你自己的值）：

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

## 🔮 Future Plans

将来计划会集中于 swarm 的调优和 overthinking 的功能，我相信 overthinking 可能会带来很有趣的变化，理想的情况下我认为需要基于个大显存的 3090+ 或者 Mac Pro 去长时间的让其 overthinking，可惜我没有，希望有人能帮我测试以下该想法能不能算是一个路线。

---

## 升级更新

目前推荐使用 git 进行手动更新：

```bash
cd swarmbot
git pull
./scripts/install_deps.sh
```

*注意：`swarmbot update` 命令目前已禁用，请使用上述方法进行更新。*

## 贡献指南

---

## License
MIT

---

**Acknowledgement**: 
*   This project is built upon the excellent work of [nanobot](https://github.com/HKUDS/nanobot), [swarms](https://github.com/kyegomez/swarms), and [qmd](https://github.com/tobi/qmd).
*   All code generated by **Trae & Tomoko**.
