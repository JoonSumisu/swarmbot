# SwarmAgentLoop 架构与运行机制详解

**版本**: v0.4.1  
**最后更新**: 2026-02-26

本文档详细描述了 Swarmbot v0.4.1 的核心运行循环 (Loop)、记忆系统架构以及多智能体协作流程。这是基于当前代码库 (`swarmbot.core`, `swarmbot.swarm`, `swarmbot.memory`) 的真实实现说明。

---

## 1. 核心架构图

```mermaid
graph TD
    User[用户 (Feishu/CLI)] --> Gateway[Gateway Server]
    Gateway --> Loop[SwarmAgentLoop]
    Loop --> Manager[SwarmManager]
    
    subgraph "SwarmManager Execution"
        Manager -->|1. Boot| MemoryContext[Context Builder]
        MemoryContext -->|Retrieve| QMD[QMD (L3 长期记忆)]
        MemoryContext -->|Restore| Whiteboard[Whiteboard (L2 共享白板)]
        MemoryContext -->|Load| LocalMD[LocalMD (L1 短期记忆)]
        
        Manager -->|2. Orchestrate| Architecture{架构选择}
        Architecture -->|Auto/Concurrent| AgentGroup[Agent Swarm]
        
        subgraph "CoreAgent Loop"
            Agent[CoreAgent] -->|Think| LLM[LLM (OpenAI/Local)]
            LLM -->|Tool Call| ToolAdapter[Tool Adapter]
            ToolAdapter -->|Exec| Tools[Native Tools]
            Tools -->|Result| Agent
        end
        
        AgentGroup --> Agent
        Agent -->|Result| Manager
    end
    
    Manager -->|3. Cleanup| Log[Session Log]
    Manager -->|4. Respond| Loop
    Loop --> User
    
    subgraph "Background Process"
        Overthinking[Overthinking Loop] -->|Optimize| QMD
        Overthinking -->|Archive| Log
    end
```

---

## 2. 运行循环 (The Loop) 详解

Swarmbot 的处理流程是同步与异步结合的，主要分为 **Ingress**, **Swarm Execution**, **Egress** 三个阶段。

### 2.1 Ingress (接入层)
*   **Gateway**: `swarmbot.gateway.server` 启动 Native Server，监听 Feishu WebSocket。
*   **Interception**: `SwarmAgentLoop` 拦截消息，屏蔽系统心跳，提取 `session_id` (Chat ID)。

### 2.2 Swarm Execution (核心执行层)
由 `SwarmManager.chat()` 驱动，分为三个相位：

#### Phase 1: Boot (启动与上下文构建)
在调用 LLM 之前，系统会构建“全息上下文”：
1.  **System Soul**: 加载 `SOUL.md` (核心人设) 或 `swarmboot.md` (系统引导)。
2.  **Memory Retrieval (L3)**: 根据用户输入，从 QMD 向量库中检索 Top-K 相关文档（经验、知识）。
3.  **Whiteboard Restoration (L2)**: 恢复当前任务的结构化状态（如待办事项、当前进度）。
4.  **Local History (L1)**: 读取最近 N 轮对话记录。

#### Phase 2: Orchestration & Agent Loop (编排与执行)
这是最复杂的环节。默认采用 `Concurrent` 或 `Auto` 架构。

*   **Agent 初始化**: 创建 `CoreAgent`，注入特定的 Role (如 `Planner`, `Coder`) 和 Skills。
*   **CoreAgent Step (单体循环)**:
    1.  **Prompt 组装**: 将 Soul + System Instructions + QMD Context + Whiteboard + History + User Input 组合成最终 Prompt。
    2.  **LLM 推理**: 调用模型。
    3.  **Tool Execution (ReAct)**:
        *   如果模型返回 `tool_calls`，`ToolAdapter` 会执行对应的 Python 函数（如 `web_search`, `python_exec`）。
        *   执行结果被追加到消息历史 (`role: tool`)。
        *   **递归调用**: Agent 会再次调用 LLM，传入工具结果，进行下一轮思考（最多 3 轮）。
        *   **Final Answer**: 当模型不再调用工具或达到轮次上限时，生成最终文本回复。

#### Phase 3: Cleanup & Persistence (清理与持久化)
1.  **日志记录**: 将完整的交互过程（输入、思维链、工具结果、最终回复、白板快照）写入 `chat_log_{session_id}_{date}.md`。
2.  **QMD 候选写入**: 如果白板中有标记为 `fact_checked=true` 的新知识，将其加入 QMD 写入队列。
3.  **Master Interpretation**: 主 Agent 对所有子 Agent 的结果进行最终汇总和润色。

### 2.3 Egress (输出层)
*   **Sanitization**: 清洗回复内容（去除 `<think>` 标签，截断过长文本，修正 Markdown）。
*   **Delivery**: 通过 `FeishuChannel` 发送回用户。

---

## 3. 记忆系统 (Tri-Layer Memory)

Swarmbot 拥有完整的三层记忆体系，确保短期对话流畅且具备长期学习能力。

### L1: LocalMD (短期工作记忆)
*   **存储**: 本地文件系统 (`chat_log_*.md`)。
*   **内容**: 原始对话流、思维链 (CoT)。
*   **作用**: 维持当前会话的上下文连贯性。
*   **管理**: 每次对话前读取最近片段；由 Overthinking 进程定期归档。

### L2: Whiteboard (共享白板)
*   **存储**: 内存对象 (Session 级) + JSON 快照。
*   **内容**: 结构化任务状态。
    *   `task_specification`: 任务定义。
    *   `execution_plan`: 执行计划步骤。
    *   `current_state`: 当前状态 (PLANNING, EXECUTING, REVIEWING)。
    *   `knowledge_graph`: 提取的实体关系。
*   **作用**: 让多个 Agent (如 Coder 和 Reviewer) 共享同一个任务视图，避免信息孤岛。
*   **操作**: Agent 通过 `whiteboard_update(key, value)` 工具主动读写。

### L3: QMD (长期向量记忆)
*   **存储**: SQLite (FTS5 + 向量模拟) / Chroma (可选)。
*   **内容**:
    *   **Facts**: 确认的事实。
    *   **Rules**: 用户偏好、系统规则。
    *   **Experiences**: 成功/失败的经验教训。
    *   **Documents**: 上传的文档片段。
*   **作用**: 跨会话的知识复用。
*   **机制**: 
    *   **Read**: `SwarmManager` 在 Boot 阶段自动检索。
    *   **Write**: `OverthinkingLoop` 在后台异步提炼 LocalMD，将高价值信息写入 QMD。

---

## 4. 工具与技能 (Native Tooling)

Swarmbot 摒弃了复杂的外部 CLI 调用，全面转向 **Native Python Tools**。

### 核心内置工具
| 工具名称 | 描述 | 关键参数 |
| :--- | :--- | :--- |
| `python_exec` | **上帝工具**。执行受限 Python 代码，可编排其他工具。 | `code` |
| `web_search` | 联网搜索 (Brave API)。 | `query` |
| `file_read` / `write` | 读写工作区文件。 | `path`, `content` |
| `whiteboard_update` | 更新共享白板状态。 | `key`, `value` |
| `skill_summary` | 列出可用技能。 | - |
| `skill_load` | 加载特定技能的详细用法。 | `name` |

### 技能扩展 (Skills)
*   位于 `workspace/skills/` 目录。
*   每个技能是一个文件夹，包含 `SKILL.md` (定义与 Prompt) 和可选的 `scripts/`。
*   Agent 可以通过 `skill_load` 动态学习新技能，无需重启。

---

## 5. Overthinking (后台进化)

Swarmbot 不仅仅是被动响应，它拥有一个后台进程 `OverthinkingLoop`。

*   **触发**: 系统空闲时自动运行。
*   **职责**:
    1.  **记忆整理**: 压缩旧的 `LocalMD` 日志。
    2.  **经验提炼**: 分析最近的对话，提取成功经验写入 `QMD`。
    3.  **系统优化**: 动态调整 `swarmboot.md` (System Prompt)，自我进化。
    4.  **主动规划**: 生成 `future_plan.md`，规划未来的系统改进。

---

## 6. 安装与依赖

### 环境要求
*   Python 3.10+
*   Dependencies: `swarms`, `lark-oapi`, `litellm`, `pydantic`, `json_repair`

### 安装命令
```bash
git clone https://github.com/JoonSumisu/swarmbot.git
cd swarmbot
pip install .
```

### 启动
```bash
# 启动 Gateway (Native Mode)
swarmbot gateway
```
