# SwarmAgentLoop 架构设计文档

**版本**: v0.4.1  
**状态**: 已实现 (Native Gateway Phase 3)

---

## 1. 概述

`SwarmAgentLoop` 是 Swarmbot 的核心执行引擎，它接管了原 `nanobot` 的单体 Agent 循环，将其扩展为支持多 Agent 协作 (Swarm) 的处理流程。它不仅负责消息的接收与回复，还深度集成了记忆系统、工具链和通道适配。

## 2. 核心流程 (The Loop)

### 2.1 消息拦截与路由
当一条消息从 IM 通道（如 Feishu）进入系统时，流程如下：

1.  **Ingress (Gateway)**: `FeishuChannel` 接收 WebSocket 事件，封装为 `InboundMessage`。
2.  **Intercept**: `SwarmAgentLoop._process_message` 拦截该消息。
3.  **Route**: 
    *   如果是系统消息（心跳等），直接忽略。
    *   如果是用户消息，提取 `session_id`（通常是 `chat_id`）。
4.  **Delegate**: 将消息内容和会话 ID 传递给 `SwarmManager.chat()`。

### 2.2 思考与执行 (Swarm Manager)
`SwarmManager` 内部维护了 `SwarmSession`，执行以下逻辑：

1.  **Context Building**:
    *   加载 **LocalMD** (短期记忆): 最近 N 轮对话历史。
    *   加载 **Whiteboard** (共享白板): 当前任务状态、待办事项。
    *   检索 **QMD** (长期记忆): 相关的知识库文档片段。

2.  **Agent Orchestration (多智能体编排)**:
    *   **Auto Mode**: 根据用户意图，动态选择或创建一个 Agent（如 `Coder`, `Researcher`）。
    *   **MoE Mode**: 召集多个专家 Agent 进行一轮或多轮“辩论”，最后由主 Agent 总结。

3.  **Tool Execution**:
    *   Agent 生成 Tool Call 请求（如 `web_search`, `python_exec`）。
    *   `ToolAdapter` 执行本地 Python 函数。
    *   结果写回 Context，Agent 进行下一轮思考。

4.  **Response Generation**:
    *   Agent 生成最终回复文本。

### 2.3 结果处理与回复
1.  **Sanitization**:
    *   `SwarmAgentLoop` 对回复进行清洗。
    *   **Feishu 特有**: 
        *   截断超过 4000 字符的文本。
        *   修正 Markdown 代码块格式（防止 Feishu 渲染错误）。
2.  **Egress**: 
    *   构造 `OutboundMessage`。
    *   通过 `MessageBus` 发送回原通道。

---

## 3. 工具系统设计

Swarmbot 采用 **Native Python Tooling**，不再依赖外部 CLI。

*   **注册机制**: 在 `swarmbot/tools/adapter.py` 中集中注册。
*   **内置工具**:
    *   `web_search`: 使用 Brave Search API。
    *   `file_ops`: 读写工作区文件。
    *   `python_exec`: 安全执行 Python 代码片段。
    *   `skill_management`: 动态加载 `workspace/skills` 下的自定义技能。

## 4. 记忆系统设计

记忆是 Swarmbot 的核心差异化特性，分为三层：

| 层级 | 名称 | 存储介质 | 用途 | 生命周期 |
| :--- | :--- | :--- | :--- | :--- |
| **L1** | **LocalMD** | 内存 / JSON | 对话上下文，短期意图保持 | 会话级 (Session) |
| **L2** | **Whiteboard** | 内存 / JSON | 跨 Agent 协作的状态同步，任务清单 | 任务级 (Task) |
| **L3** | **QMD** | 向量数据库 (Chroma) | 长期知识、经验沉淀、文档检索 | 永久 (Permanent) |

**调用时机**:
*   **Read**: 每轮对话开始前，自动检索 QMD 并注入 System Prompt。
*   **Write**: 
    *   **LocalMD**: 自动追加。
    *   **Whiteboard**: Agent 主动调用 `update_whiteboard` 工具。
    *   **QMD**: 通过 `Overthinking` 进程在后台异步提炼并写入。

---

## 5. 通道适配 (Feishu Native)

为解决 `nanobot` 依赖问题，Feishu 通道已重构为原生实现：

*   **依赖**: `lark-oapi` (官方 SDK)。
*   **模式**: WebSocket 长连接 (无需公网 IP)。
*   **配置**: 直接读取 `config.json` 中的 `channels.feishu` 字段。
*   **特性**: 支持文本、富文本解析、图片消息（预留接口）。

---

## 6. 下一步演进

*   **Transport Layer**: 进一步抽象 Transport 层，支持更多协议（HTTP, gRPC）。
*   **Sandboxing**: 增强 Python 执行环境的隔离性（Docker/WASM）。
