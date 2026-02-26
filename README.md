# Swarmbot

[中文](README.md) | [English](README_EN.md)

**Swarmbot (v0.4.1)** 是一个基于 **[swarms](https://github.com/kyegomez/swarms)** 和 **nanobot** 架构的多 Agent 集群智能系统，专为本地部署和私有 LLM 接口设计。

它集成了 **QMD 三层记忆系统**（短期工作记忆、共享白板、长期向量知识库），支持通过 **Feishu (飞书/Lark)** 等 IM 通道进行交互，并具备 **Overthinking**（后台深度思考与自我进化）能力。

> **核心理念**: "All-in-One" —— 将网关、记忆、工具链和多智能体编排融合在一个轻量级进程中。

---

## 🌟 版本 v0.4.1 更新亮点

*   **Gateway In-Process**: 彻底移除了对外部 `nanobot` 进程的依赖。Gateway 现在直接作为 Swarmbot 的子模块运行，大幅降低了部署复杂度和资源占用。
*   **Feishu Channel Restore**: 修复并增强了 Feishu 通道支持，包括消息清洗、Markdown 格式修正和长文本自动截断。
*   **Skill System Optimization**: 移除了对 CLI 工具的依赖，改为纯 Python 实现的本地技能发现与加载机制，性能显著提升。
*   **Robust Dependencies**: 修复了 `json_repair` 等关键依赖缺失问题，增强了容错性。

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

## 🧩 核心特性

### 1. 多智能体编排 (Swarm Orchestration)
基于 `swarms` 框架，支持多种协作架构：
*   **Auto**: 根据任务自动动态生成角色与流程（默认）。
*   **Sequential**: 线性流水线，适合 SOP 任务。
*   **Mixture of Experts (MoE)**: 动态专家网络，支持多轮辩论。

### 2. 三层记忆系统 (Tri-Layer Memory)
*   **LocalMD**: 短期会话日志。
*   **Whiteboard**: 内存中的共享白板，用于 Agent 间实时信息同步与状态管理。
*   **QMD**: 基于向量检索的长期知识库，存储持久化经验与文档。

### 3. 通道集成 (Channels)
*   **Feishu (飞书)**: 完整支持接收消息、回复（含 Markdown）、图片理解（需模型支持）。
*   在 `config.json` 中配置 `channels.feishu` 即可启用。

### 4. 自我进化 (Overthinking)
*   **后台思考**: 空闲时自动启动 `Overthinking Loop`，对历史交互进行复盘。
*   **经验沉淀**: 将成功/失败的经验提炼为方法论写入 QMD。

---

## 🛠️ 开发与贡献

请参阅 [开发文档](docs/development.md) 了解架构细节与贡献指南。

## 📄 License

MIT License
