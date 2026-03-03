# Swarmbot

[中文](README.md) | [English](README_EN.md)

**Swarmbot (v0.4.1)** 是一个基于 **[swarms](https://github.com/kyegomez/swarms)** 和 **nanobot** 架构的多 Agent 集群智能系统，专为本地部署和私有 LLM 接口设计。

它集成了 **QMD 四层记忆系统**（白板、热记忆、温记忆、冷记忆），支持通过 **Feishu (飞书/Lark)** 等 IM 通道进行交互，并具备 **Overthinking**（后台深度思考与自我进化）能力。

> **核心理念**: "All-in-One" —— 将网关、记忆、工具链和多智能体编排融合在一个轻量级进程中。

---

## 🌟 版本 v0.4.1 更新亮点

*   **Gateway In-Process**: 彻底移除了对外部 `nanobot` 进程的依赖。Gateway 现在直接作为 Swarmbot 的子模块运行，大幅降低了部署复杂度和资源占用。
*   **Native Loop Architecture**: 重构了核心 Agent 循环 (`CoreAgent Loop`)，支持多轮工具调用与最终自动汇总。
*   **Feishu Channel Restore**: 修复并增强了 Feishu 通道支持，包括消息清洗、Markdown 格式修正和长文本自动截断。
*   **Skill System Optimization**: 移除了对 CLI 工具的依赖，改为纯 Python 实现的本地技能发现与加载机制，性能显著提升。

---

## 🚀 快速开始

### 1. 安装

Swarmbot 支持 Python 3.10+。推荐使用 `pip` 直接安装：

```bash
# 从源码安装
git clone https://github.com/JoonSumisu/swarmbot.git
cd swarmbot
pip install .
```

### 2. 配置

首次运行会自动生成配置文件 `~/.swarmbot/config.json`。你可以手动编辑或使用 CLI 配置：

```bash
# 设置主模型 (支持 OpenAI 兼容接口，如 vLLM, Ollama, DeepSeek 等)
swarmbot provider add \
  --base-url "http://127.0.0.1:8000/v1" \
  --api-key "sk-xxxx" \
  --model "qwen3-coder-30b-instruct" \
  --max-tokens 8192
```

### 3. 启动 Gateway (推荐)

启动网关以接入 IM 通道（如 Feishu）并开启 API 服务：

```bash
# 前台启动
swarmbot gateway

# 或者使用守护进程模式
swarmbot daemon start
```

### 4. 命令行交互 (Debug)

你也可以直接在命令行与 Swarmbot 对话：

```bash
swarmbot run
```

---

## 🧠 核心架构与记忆系统

Swarmbot 采用先进的 **Loop + Memory** 架构，确保智能体在长期交互中保持连贯性与成长性。详细设计请参阅 [架构文档](docs/memory_and_loop_architecture.md)。

### 1. 四层记忆结构 (Memory Layers)

*   **L1 白板 (Whiteboard)**: 
    *   **类型**: 结构化易失记忆 (Session级)。
    *   **内容**: 当前任务的 Prompt、执行计划、Worker 结论、最终答案。
    *   **作用**: Agent 间的实时信息同步，任务结束后归档或清除。
*   **L2 热记忆 (Hot Memory)**: 
    *   **类型**: 短期持久化 (`hot_memory.md`)。
    *   **内容**: 用户的短期上下文（过去/现在/将来）、待办事项 (Todo List)。
    *   **作用**: 维持跨会话的短期连贯性（如：“正如昨天提到的...”）。
*   **L3 温记忆 (Warm Memory)**: 
    *   **类型**: 时序日志 (`memory/YYYY-MM-DD.md`)。
    *   **内容**: 完整记录每天的对话流、结论与事实。
    *   **作用**: 原始数据的追溯与备份。
*   **L4 冷记忆 (Cold Memory / QMD)**: 
    *   **类型**: 语义向量数据库 (QMD)。
    *   **内容**: 经由 **Overthinking** 从温记忆中提炼出的事实、经验、理论。
    *   **作用**: 长期知识复用，支持语义搜索。

### 2. 运行循环 (The Loop)

*   **Ingress**: 接收 Feishu 消息，进行格式清洗。
*   **Boot**: 加载 Soul (人设) + 检索 QMD (冷) + 读取 Hot/Warm (热/温) + 恢复 Whiteboard。
*   **Orchestrate**: 动态编排 Agent（如 Planner -> Coder -> Reviewer）。
*   **Execute**: Agent 执行工具 (Python/WebSearch)，更新 Whiteboard。
*   **Overthinking**: 后台进程在空闲时自动运行，负责将 Warm 转为 Cold，并整理 Hot。

---

## 🧩 核心特性

### 1. 多智能体编排 (Swarm Orchestration)
基于 `swarms` 框架，支持多种协作架构：
*   **Auto**: 根据任务自动动态生成角色与流程（默认）。
*   **Sequential**: 线性流水线，适合 SOP 任务。
*   **Mixture of Experts (MoE)**: 动态专家网络，支持多轮辩论。

### 2. 通道集成 (Channels)
*   **Feishu (飞书)**: 完整支持接收消息、回复（含 Markdown）、图片理解（需模型支持）。
*   在 `config.json` 中配置 `channels.feishu` 即可启用。

### 3. 自我进化 (Overthinking)
*   **后台思考**: 空闲时自动启动 `Overthinking Loop`，对历史交互进行复盘。
*   **经验沉淀**: 将成功/失败的经验提炼为方法论写入 QMD。

---

## 📖 文档

*   **[架构详解 (Memory & Loop)](docs/memory_and_loop_architecture.md)**: 深入了解 Swarmbot 的核心循环、三层记忆系统和多 Agent 编排机制。
*   **[开发指南](docs/development.md)**: 如何贡献代码、添加新工具或适配新通道。

---

## 📄 License

MIT License
