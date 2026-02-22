# Swarmbot

[中文](README.md) | [English](README_EN.md)

Swarmbot 是一个运行在本地环境中的 **多 Agent 集群智能系统 (Multi-Agent Swarm System)**。

它融合了 **nanobot（已内置源码，不再依赖 pip 安装）** 的网关/通道能力，并深度集成 **[swarms](https://github.com/kyegomez/swarms)** 的多智能体编排能力与 **QMD（三层记忆）**，旨在为本地/私有 OpenAI 兼容接口提供强大的任务规划与执行能力。

开发文档见 [development.md](file:///root/swarmbot/docs/development.md)。

> **核心理念**: 将 nanobot 的单体执行力扩展为 Swarm 的集体智慧，并通过 Horizon Middleware 实现长程任务规划。

---

## 🌟 核心架构 v0.2.0

Swarmbot 不是简单的组件堆叠，而是实现了“三位一体”的深度融合，在 v0.2.0 中引入了双 Boot 系统：

### 1. Dual Boot System (New in v0.2)
- **Swarm Boot (Instinct)**: 基于 `swarmbot/boot/swarmboot.md` 启动。负责理性拆解任务、调度工具与检索记忆。
- **Master Agent Boot (Consciousness)**: 基于 `swarmbot/boot/masteragentboot.md` 启动。负责接收 Swarm 的执行结果，结合 `SOUL.md` (人格) 与 `IDENTITY.md` (身份) 进行二次解释与用户交互。

### 2. Swarm Orchestration (Swarms Integrated)
*   **来源**: 集成 `swarms` 框架的多智能体编排逻辑。
*   **作用**: 管理 Agent 间的协作流。
*   **架构支持**:
    *   `Sequential`: 线性流水线（适合 SOP）。
    *   `Concurrent`: 并行执行（默认；更适合小模型/本地模型）。
    *   `Hierarchical`: 层级指挥（Director -> Workers）。
    *   `Mixture of Experts (MoE)`: 动态专家网络，支持多轮辩论与共识达成。
    *   `State Machine`: 动态状态机（适合 Code Review 循环）。
    *   `Auto`: 大模型可选；根据任务自动选择架构，并动态生成专用 Agent 角色（存在一定随机性）。

### 3. Core Agent (Nanobot Inside)
*   **来源**: 基于 `nanobot` 核心代码构建。
*   **作用**: 作为 Swarm 中的执行单元。
*   **特性**: 
    *   **Tool Adapter**: 所有的 nanobot 原生技能（如文件操作、Shell 执行）都被封装为 OpenAI 格式的 Tool。
    *   **OpenClaw Bridge**: [v0.2 新增] 支持动态加载 OpenClaw 生态工具。
    *   **Web Search**: 集成 Chrome 无头浏览器，支持动态网页抓取与反爬虫绕过，优先获取 2024-2026 年最新数据。
    *   **Gateway**: 复用 nanobot 强大的多渠道网关，支持飞书、Slack、Telegram 等。

### 4. Tri-Layer Memory (QMD Powered)
*   **来源**: 基于 `qmd` 提供的本地向量检索引擎。
*   **作用**: 为 Agent 提供不同时间跨度的记忆支持。
*   **三层体系**:
    1.  **LocalMD (Short-term)**: 本地 Markdown 日志缓存，实时记录每日会话，作为短期工作记忆。
    2.  **MemoryMap (Whiteboard)**: 内存中的共享白板，存储任务全局状态、关键决策快照，确保多 Agent 信息同步。
    3.  **QMD (Long-term)**: 基于向量 + BM25 的持久化知识库，支持对历史文档和笔记的语义检索。

### 5. Overthinking Loop (Deep Thinking)
*   **功能**: 空闲时的后台深度思考循环（可选）。
*   **能力**:
    *   **记忆整理**: 从 LocalMD 提取关键事实与决策，沉淀为长期记忆 (QMD)。
    *   **自我拓展**: 基于现有记忆进行逻辑推演，主动发现知识盲区，并生成新的假设与理论。
    *   **经验沉淀**: 将单次任务的成功/失败经验转化为通用的方法论。
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

### 10. `swarmbot update` [v0.2 新增]
*   **功能**：更新核心代码。
*   **特性**：保留 `swarmbot/boot/` 下的所有个性化配置（人格、工具策略等）。

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
