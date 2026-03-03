# Swarmbot

[中文](README.md) | [English](README_EN.md)

**Swarmbot (v0.5.0)** 是一个基于 **[swarms](https://github.com/kyegomez/swarms)** 和 **nanobot** 架构的多 Agent 集群智能系统，专为本地部署和私有 LLM 接口设计。

它集成了 **QMD 四层记忆系统**（白板、热记忆、温记忆、冷记忆）与 **三环自进化架构**（推理、反思、行动），支持通过 **Feishu (飞书/Lark)** 等 IM 通道进行交互。

> **核心理念**: "All-in-One" —— 将网关、记忆、工具链和多智能体编排融合在一个轻量级进程中。

---

## 🌟 版本 v0.5.0 更新亮点

*   **3-Loop Architecture**: 
    *   **Inference Loop**: 8 步标准推理（分析-搜集-规划-执行-评估-转译-整理）。
    *   **Overthinking Loop**: 后台只读压缩，将短期记忆转化为长期知识 (QMD)。
    *   **Overaction Loop**: 主动进化，基于知识库进行联网补充、自我优化与记忆清理。
*   **4-Layer Memory**:
    *   L1 **Whiteboard**: 会话级临时白板。
    *   L2 **Hot Memory**: 1-7天短期记忆与待办 (Todo)。
    *   L3 **Warm Memory**: 时序性每日日志。
    *   L4 **Cold Memory**: 语义向量数据库 (QMD)。
*   **Native Feishu Integration**: 深度优化的飞书通道支持。

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

---

## 📖 文档

*   **[架构详解 (Architecture)](docs/ARCHITECTURE.md)**: 深入了解 Swarmbot 的核心循环、三层记忆系统和多 Agent 编排机制。

---

## 📄 License

MIT License
