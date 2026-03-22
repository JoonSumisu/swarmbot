# Swarmbot 全链路测试计划 (v0.3)

## 1. 测试目标
验证 Swarmbot 在集成 Loop、Dynamic Skills、飞书通道及本地模型 (`gpt-oss-20b`) 后的端到端功能稳定性。

## 2. 环境配置检查
- [x] **模型配置**: `gpt-oss-20b` (http://100.110.110.250:8888/v1)
- [x] **飞书配置**: AppID `cli_a906cade05f8dcc2`
- [x] **Gateway**: 端口 `18990`
- [x] **代码状态**: 已修复 Gateway 返回类型、Skill 注入、Loop 白板生命周期

## 3. 测试用例

### Case 1: 服务启动与飞书握手
- **操作**: 运行 `swarmbot gateway --port 18990`
- **预期日志**: 
  - `Starting nanobot gateway on port 18990`
  - `Channels enabled: feishu`
  - 无 Python 报错或 traceback。

### Case 2: 基础对话 (Ping-Pong)
- **操作**: 在飞书对机器人发送 "Hello" 或 "你好"。
- **预期**:
  - 机器人回复 "你好！我是 Swarmbot..." (基于 SOUL.md)。
  - 日志显示 `[SwarmRoute] Processing: 你好`。

### Case 3: 动态角色与 Skill 调用 (复杂任务)
- **操作**: 发送指令："请帮我搜索关于 'MCP Protocol' 的最新介绍，并总结它的核心架构。"
- **预期流程**:
  1. **Planner**: 识别任务，决定角色 `['researcher', 'summarizer']`。
  2. **Role Assignment**: 
     - `researcher` 获得 `web_search`, `browser_read` 权限。
     - `summarizer` 获得 `web_search` 权限。
  3. **Execution**:
     - `researcher` 调用 `web_search("MCP Protocol latest introduction")`。
     - `researcher` 将结果写入 Whiteboard。
     - `summarizer` 读取 Whiteboard，生成总结。
  4. **Master**: 输出最终总结给用户。
- **验证点**: 检查日志中是否有 `[ToolExec] Executing web_search` 和 `Injecting skills ... into researcher`。

### Case 4: Loop 上下文记忆 (Whiteboard Persistence)
- **操作**: 
  1. 发送："我的项目代号是 'Project X'。"
  2. 发送："请为我之前的项目写一个简单的 Python Hello World 脚本，文件名带上代号。"
- **预期**:
  - 第二步的 Coder Agent 能从 Whiteboard/Memory 中读取到 "Project X"。
  - 生成的文件名或内容包含 `project_x`。
  - **关键**: 确认 Loop 结束（Master 回复后），Whiteboard 被清除（日志 `Whiteboard cleared for next task`）。

### Case 5: 错误处理与降级
- **操作**: 模拟断网或模型超时（可跳过，视环境而定）。
- **预期**: Gateway 捕获异常，通过飞书返回友好错误提示，而不是无响应。

## 4. 日志验证方案

### 实时日志监控
在终端运行：
```bash
tail -f ~/.swarmbot/logs/gateway.log
```

### 关键日志特征 (Grep)
验证 Skill 注入：
```bash
grep "Injecting skills" ~/.swarmbot/logs/gateway.log
```
验证工具调用：
```bash
grep "Tool call:" ~/.swarmbot/logs/gateway.log
```
验证飞书消息发送：
```bash
grep "Response to feishu" ~/.swarmbot/logs/gateway.log
```

## 5. 执行记录
| 时间 | 用例 | 状态 | 备注 |
|------|------|------|------|
|      | Case 1 | Pending | 待启动 |
|      | Case 2 | Pending | 待交互 |
|      | Case 3 | Pending |      |
|      | Case 4 | Pending |      |

---
**注意**: 请确保本地网络能访问 `100.110.110.250`，且飞书回调地址已正确配置为本机的公网映射地址（如使用内网穿透）。
