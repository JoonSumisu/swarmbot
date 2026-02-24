# 开发文档 (v0.4.1)

## 🏗️ 架构概览

Swarmbot v0.4.1 采用了 **In-Process Gateway** 架构，将核心组件紧密集成在同一个 Python 环境中。

### 核心组件

1.  **SwarmManager (`swarmbot.swarm.manager`)**:
    *   系统的中枢大脑。
    *   负责管理 `SwarmSession`，维护 Agent 状态与记忆。
    *   调度多智能体架构（Sequential, MoE, Auto 等）。

2.  **SwarmAgentLoop (`swarmbot.swarm.agent_adapter`)**:
    *   这是 Swarmbot 对 nanobot `AgentLoop` 的扩展与替换。
    *   它拦截了标准的消息处理流程，将其路由到 `SwarmManager`。
    *   实现了 Feishu 消息的特殊处理（格式清洗、截断）。

3.  **Gateway (`swarmbot.cli.cmd_gateway`)**:
    *   启动入口。它不再是外部进程，而是直接在 CLI 中初始化 `nanobot` 组件。
    *   在启动前，它会动态 Patch `nanobot.agent.loop.AgentLoop`，将其替换为 `SwarmAgentLoop`。

4.  **ToolAdapter (`swarmbot.tools.adapter`)**:
    *   统一的工具注册中心。
    *   将 Python 函数（如 `file_read`, `web_search`, `python_exec`）封装为 OpenAI Tool 格式。
    *   实现了纯 Python 的技能加载逻辑 (`skill_summary`, `skill_load`)。

## 📦 依赖管理

项目使用 `pyproject.toml` 管理依赖。核心依赖包括：

*   `swarms`: 多智能体框架基础。
*   `httpx`, `pydantic`: 基础网络与数据验证。
*   `json_repair`: 增强 LLM 输出 JSON 的解析鲁棒性。
*   `litellm`: 统一的大模型接口调用。
*   `loguru`, `typer`, `rich`: CLI 与日志体验。

安装依赖：
```bash
pip install .
```

## 🔧 开发指南

### 1. 本地运行 Gateway
在开发过程中，推荐直接运行 Gateway 来测试改动：
```bash
python -m swarmbot.cli gateway
```
这会启动 Web Server (默认 18790 端口) 并开始监听配置的通道（如 Feishu）。

### 2. 调试 Agent 逻辑
可以使用 `swarmbot run` 命令进入 CLI 交互模式，直接测试 Agent 的回复逻辑，无需通过 Feishu。

### 3. 添加新工具
在 `swarmbot/tools/adapter.py` 的 `_load_skills` 方法中注册新工具：
```python
self._register_builtin(
    "my_new_tool",
    "Description of what it does",
    ["arg1", "arg2"],
    self._my_new_tool_impl
)
```

### 4. 提交代码
在提交前，请确保：
*   版本号已更新 (`pyproject.toml` 和 `swarmbot/__init__.py`)。
*   没有硬编码的 API Key 或 Secret。
*   执行简单的冒烟测试（如 `python -m swarmbot.cli --help`）。

## 🧪 测试

目前主要依赖手动测试与集成测试脚本。
*   `tests/` 目录下包含部分单元测试。
*   可以使用 `configure_test.py` (未提交) 快速配置本地测试环境。

## 🤝 贡献

欢迎提交 Pull Request！请遵循 GitHub Flow 工作流。
