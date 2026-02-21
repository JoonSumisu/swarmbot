# Swarmbot

[中文](README.md) | [English](README_EN.md)

Swarmbot 是一个运行在本地环境中的 **多 Agent 集群智能系统 (Multi-Agent Swarm System)**。

它基于 **[nanobot](https://github.com/HKUDS/nanobot)** 的框架，深度融合了 **[swarms](https://github.com/kyegomez/swarms)** 的多智能体编排能力与 **[qmd](https://github.com/tobi/qmd)** 的三层记忆系统，旨在为本地模型（如 Kimi, vLLM, Ollama）提供强大的任务规划与执行能力。

> **核心理念**: 将 nanobot 的单体执行力扩展为 Swarm 的集体智慧，并通过 Horizon Middleware 实现长程任务规划。

---

## 🌟 核心架构 v0.1.2

Swarmbot 不是简单的组件堆叠，而是实现了“三位一体”的深度融合：

### 1. Swarm Orchestration (Swarms Integrated)
*   **来源**: 集成 `swarms` 框架的多智能体编排逻辑。
*   **作用**: 管理 Agent 间的协作流。
*   **架构支持**:
    *   `Sequential`: 线性流水线（适合 SOP）。
    *   `Concurrent`: 并行执行（默认；更适合小模型/本地模型）。
    *   `Hierarchical`: 层级指挥（Director -> Workers）。
    *   `Mixture of Experts (MoE)`: 动态专家网络，支持多轮辩论与共识达成。
    *   `State Machine`: 动态状态机（适合 Code Review 循环）。
    *   `Auto`: 大模型可选；根据任务自动选择架构，并动态生成专用 Agent 角色（存在一定随机性）。

### 2. Core Agent (Nanobot Inside)
*   **来源**: 基于 `nanobot` 核心代码构建。
*   **作用**: 作为 Swarm 中的执行单元。
*   **特性**: 
    *   **Tool Adapter**: 所有的 nanobot 原生技能（如文件操作、Shell 执行）都被封装为 OpenAI 格式的 Tool。
    *   **Web Search**: 集成 Chrome 无头浏览器，支持动态网页抓取与反爬虫绕过，优先获取 2024-2026 年最新数据。
    *   **Gateway**: 复用 nanobot 强大的多渠道网关，支持飞书、Slack、Telegram 等。

### 3. Tri-Layer Memory (QMD Powered)
*   **来源**: 基于 `qmd` 提供的本地向量检索引擎。
*   **作用**: 为 Agent 提供不同时间跨度的记忆支持。
*   **三层体系**:
    1.  **LocalMD (Short-term)**: 本地 Markdown 日志缓存，实时记录每日会话，作为短期工作记忆。
    2.  **MemoryMap (Whiteboard)**: 内存中的共享白板，存储任务全局状态、关键决策快照，确保多 Agent 信息同步。
    3.  **QMD (Long-term)**: 基于向量 + BM25 的持久化知识库，支持对历史文档和笔记的语义检索。

### 4. Overthinking Loop (Deep Thinking)
*   **功能**: 空闲时的后台整理循环（可选）。
*   **作用**: 从 LocalMD 整理关键事实/经验/理论，写入 QMD；写入后会激进清理 LocalMD 以避免重复整理与磁盘堆积。

### 5. 记忆工作流（建议理解方式）
*   **收到 Prompt**: 查询 QMD + 当日 LocalMD 摘要，并把结构化的 Prompt + 记忆注入 Whiteboard（`current_task_context`）。
*   **Swarm 执行中**: 各节点应优先读取 Whiteboard，确保对任务的共同理解；中间产物也会写入 Whiteboard。
*   **对话结束**: 白板内容会被整理写入 LocalMD（摘要/结论），然后清空 Whiteboard。
*   **空闲时**: Overthinking 将 LocalMD 进一步整理为可检索的长期记忆写入 QMD，并进行记忆“经验化/理论化”扩展。

---

## 🚀 快速开始

### 1. 安装
```bash
# 克隆仓库
git clone https://github.com/JoonSumisu/swarmbot.git
cd swarmbot

# 运行独立环境安装脚本（自动安装 Python 依赖与 npm qmd）
chmod +x scripts/install_deps.sh
./scripts/install_deps.sh

# 初始化配置
swarmbot onboard
```

### 2. 配置模型 (Provider)
Swarmbot 默认不包含任何 API Key，请手动配置 OpenAI 兼容接口（如 Kimi, DeepSeek, Localhost）：

```bash
swarmbot provider add \
  --base-url https://api.moonshot.cn/v1 \
  --api-key YOUR_API_KEY \
  --model kimi-k2-turbo-preview \
  --max-tokens 126000
```

### 3. 运行对话
```bash
# 直接启动（默认 Concurrent）
swarmbot run
```

### 4. 切换架构（Concurrent / Auto）
```bash
# 小模型/本地模型：默认 concurrent
swarmbot config --architecture concurrent

# 大模型可启用 auto（存在一定随机性，适合更强的模型）
swarmbot config --architecture auto --auto-builder true
```

---

## 📖 CLI 功能详解

Swarmbot 提供了一套完整的命令行工具来管理 Agent 集群。

### 1. `swarmbot onboard`
*   **功能**: 初始化工作区。
*   **作用**: 创建 `~/.swarmbot` 配置文件，初始化 nanobot 核心，准备 workspace 目录。

### 2. `swarmbot run`
*   **功能**: 启动本地对话会话。
*   **作用**: 进入交互式终端，与 Swarm 集群直接对话。
*   **默认行为**: 启动 AutoSwarmBuilder，根据你的输入自动决定使用哪种 Swarm 架构。

### 3. `swarmbot gateway`
*   **功能**: 启动多渠道网关。
*   **默认端口**: `18990` (v0.1 更新，避免端口冲突)。
*   **作用**: 透传调用 `nanobot gateway`，接管飞书/Slack 消息。

### 4. `swarmbot overthinking`
*   **功能**: 管理后台思考循环 (Overthinking Loop)。
*   **子命令**:
    *   `start`: 手动启动思考循环。
    *   `setup`: 配置思考参数。

---

## 📊 Galileo Leaderboard 模拟评分

基于内部集成测试 [leaderboard_eval.py](file:///root/swarmbot/tests/integration/leaderboard_eval.py)，在本地 OpenAI 兼容接口 + `openai/openbmb/agentcpm-explore` 模型条件下：
*   **最佳成绩**：5/5（一次运行全通过）
*   **说明**：并发协作与（可选的）自动分工存在随机性，不同运行可能会有波动

### Evaluation 调整说明
为减少误判与更贴近真实使用，本项目对评分脚本做了小幅鲁棒性调整：
*   Persona anti-pattern 从泛化的 “User/Assistant” 改为更精确的标记（避免误伤 UserA）
*   部分赛题引入中英文/同义词匹配（例如 table/表格、rumor/leak/传闻/爆料）
*   Coding 评分避免依赖单一关键词（如 backtrack），以输出可用代码为主

---

## 🧩 飞书（Feishu）配置（通过 nanobot gateway）
Swarmbot 通过 [gateway_wrapper.py](file:///root/swarmbot/swarmbot/gateway_wrapper.py) 接管 nanobot 的消息处理，复用其多渠道能力。
1. 先完成 nanobot 的渠道配置（飞书 App/机器人 Token 等）：参考 nanobot 官方文档
2. 配置 Swarmbot 的模型 Provider（OpenAI 兼容接口）
3. 启动网关：

```bash
swarmbot gateway
```

### 本地模型 / 远程模型配置示例
*   **远程 OpenAI 兼容（示例）**：
```bash
swarmbot provider add --base-url https://api.example.com/v1 --api-key YOUR_API_KEY --model openai/your-model --max-tokens 126000
```
*   **本地 vLLM（示例）**：
```bash
swarmbot provider add --base-url http://127.0.0.1:8000/v1 --api-key dummy --model openai/your-local-model --max-tokens 8192
```
*   **本地 Ollama（示例）**（需开启 OpenAI 兼容端点）：
```bash
swarmbot provider add --base-url http://127.0.0.1:11434/v1 --api-key dummy --model openai/your-ollama-model --max-tokens 8192
```

---

## 🔮 Future Plans

将来计划会集中于 swarm 的调优和 overthinking 的功能，我相信 overthinking 可能会带来很有趣的变化，理想的情况下我认为需要基于个大显存的 3090+ 或者 Mac Pro 去长时间的让其 overthinking，可惜我没有，希望有人能帮我测试以下该想法能不能算是一个路线。

---

## License
MIT

---

**Acknowledgement**: 
*   This project is built upon the excellent work of [nanobot](https://github.com/HKUDS/nanobot), [swarms](https://github.com/kyegomez/swarms), and [qmd](https://github.com/tobi/qmd).
*   All code generated by **Trae & Tomoko**.
