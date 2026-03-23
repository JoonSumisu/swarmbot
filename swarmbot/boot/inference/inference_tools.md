# Inference Tools Configuration

本文件定义了 MasterAgent 可用的推理工具集合。每个工具独立实现，通过配置驱动加载。

---

## 工具列表

### 1. standard (标准推理工具)

**工具 ID**: `standard`

**类名**: `StandardInferenceTool`

**模块路径**: `swarmbot.loops.inference_standard`

**描述**: 标准的 8 步推理流程，适合大多数复杂问题。不需要人在回路。

**适用场景**:
- 需要多步骤分析和推理的任务
- 需要收集外部信息的任务
- 需要评估和验证的任务
- 不需要用户中途确认的常规任务

**推理步骤**:
1. **Analysis**: 意图分析 (无工具)
2. **Collection**: 上下文收集 (web_search, browser, file tools)
3. **Planning**: 生成行动计划 (JSON)
4. **Execution**: 执行任务 (并行 workers)
5. **Evaluation**: 质量评估 (3 workers voting)
6. **Translation**: 生成最终回复
7. **Organization**: 响应整理
8. **Output**: 返回结果

**不需要人在回路**: 是

---

### 2. supervised (人在回路推理)

**工具 ID**: `supervised`

**类名**: `SupervisedInferenceTool`

**模块路径**: `swarmbot.loops.inference_supervised`

**描述**: 带有暂停点的推理流程，在关键步骤需要用户确认后才能继续。

**适用场景**:
- 高风险任务 (涉及金钱、法律、安全)
- 需要用户确认分析方向的任务
- 需要用户确认执行计划的任务
- 复杂的多阶段任务

**推理步骤**:
1. **Analysis**: 意图分析 (无工具)
2. **COLLECTION**: 上下文收集
3. **[BREAKPOINT] ANALYSIS_REVIEW**: 暂停等待用户确认分析方向
4. **PLANNING**: 生成行动计划
5. **[BREAKPOINT] PLAN_REVIEW**: 暂停等待用户确认执行计划
6. **Execution**: 执行任务
7. **Evaluation**: 质量评估
8. **Translation**: 生成最终回复
9. **Organization**: 响应整理
10. **Output**: 返回结果

**需要人在回路**: 是

**暂停点**:
- `ANALYSIS_REVIEW`: 分析方向确认
- `PLAN_REVIEW`: 执行计划确认

---

### 3. swarms (多Worker协作)

**工具 ID**: `swarms`

**类名**: `SwarmsInferenceTool`

**模块路径**: `swarmbot.loops.inference_swarms`

**描述**: 使用 Swarms 框架的多 Agent 协作推理，适合需要多角色同时分析的任务。

**适用场景**:
- 需要多角度分析的任务
- 需要角色扮演的任务 (如客服、会议)
- 需要并行处理的任务
- 复杂的多主体任务

**特点**:
- 使用 Swarms 的 SwarmManager
- 支持多种架构: concurrent, mixture, group_chat, hierarchical
- 自动决策 Agent 数量和角色
- 不需要人在回路

**不需要人在回路**: 是

---

### 4. subswarm (异步子任务编排)

**工具 ID**: `subswarm`

**类名**: `SubSwarmInferenceTool`

**模块路径**: `swarmbot.loops.inference_subswarm`

**描述**: 解耦 MasterAgent 和推理工具，允许 MasterAgent 异步分发多个子任务，通过 Hub 协调结果。需要多个子任务并行执行的复杂任务。

**适用场景**:
- 需要多个独立子任务同时执行的任务
- 需要 MasterAgent 协调多个推理结果的场景
- 需要子任务之间相互通信的场景
- 超大规模任务分解

**特点**:
- MasterAgent 异步分发子任务 (subtasks)
- 每个子任务有独立的 topic 用于组织
- 子任务通过 Hub 发送心跳
- 子任务完成后发送结果到 Hub
- MasterAgent 收集结果并协调输出
- 可设置最大并发数
- 支持人在回路协调 (需要用户决策时)

**不需要人在回路**: 否 (支持协调)

**协调流程**:
```
MasterAgent → Hub → SubTask1 (topic: research)
MasterAgent → Hub → SubTask2 (topic: analysis)
MasterAgent → Hub → SubTask3 (topic: coding)

SubTask1 → Hub → Heartbeat (alive)
SubTask2 → Hub → Heartbeat (alive)
SubTask3 → Hub → Heartbeat (alive)

SubTask1 → Hub → Result (topic: research)
SubTask2 → Hub → Result (topic: analysis)
SubTask3 → Hub → Result (topic: coding)

Hub → MasterAgent (收集所有结果)
MasterAgent → 用户 (协调后的最终结果)
```

---

## 使用方法

### MasterAgent 加载工具流程

```python
# 1. 读取 inference_tools.md
tools = load_inference_tools_config()

# 2. 解析工具定义
for tool_def in tools:
    tool_id = tool_def["tool_id"]
    class_name = tool_def["class_name"]
    module_path = tool_def["module_path"]
    
    # 3. 动态导入
    module = importlib.import_module(module_path)
    tool_class = getattr(module, class_name)
    
    # 4. 注册到 MasterAgent
    master_agent.register_tool(tool_id, tool_class)
```

### 添加新工具

1. 在 `swarmbot/loops/` 目录创建新模块 (如 `inference_custom.py`)
2. 继承 `BaseInferenceTool` 基类
3. 实现 `run()` 方法
4. 在 `inference_tools.md` 添加配置
5. **无需修改 MasterAgent 代码**

---

## 工具选择策略

MasterAgent 使用 LLM 浅思考决定使用哪个工具：

| 场景 | 推荐工具 |
|------|----------|
| 简单对话、寒暄、直接回答 | simple_direct (内置) |
| 常规复杂任务 | `standard` |
| 需要用户确认的任务 | `supervised` |
| 多角色协作任务 | `swarms` |
