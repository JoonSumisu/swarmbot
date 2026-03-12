# Swarms Agent 源码流程深度解读

本文基于 `kyegomez/swarms` 源码（本地路径：`/root/swarms_upstream`）梳理 Agent 的执行机制，重点回答：

- Agent 是如何初始化的
- `run -> _run / _run_autonomous_loop` 如何循环
- 工具调用、handoff、MCP 如何接入
- 何时结束、如何“自我判断”
- 多 Agent 编排如何路由

---

## 1. Agent 核心类与入口

Swarms 的核心 Agent 在：

- `swarms/structs/agent.py`
- 类名：`Agent`

关键代码点：

- `__init__`：`agent.py:349`
- `run`：`agent.py:4653`
- `_run`（标准循环）：`agent.py:1531`
- `_run_autonomous_loop`（auto 模式）：`agent.py:2147`

---

## 2. 初始化阶段：Agent 在启动时做了什么

`Agent.__init__` 参数非常多，分为几类：

1. **模型与采样**：`model_name / temperature / top_p / max_tokens / timeout`
2. **循环控制**：`max_loops / stopping_condition / stopping_func / loop_interval`
3. **工具体系**：`tools / tool_schema / tool_choice / tools_list_dictionary / tool_retry_attempts`
4. **外部协议**：`mcp_url / mcp_urls / mcp_config / mcp_configs`
5. **协作能力**：`handoffs / capabilities / max_subagent_depth`
6. **记忆与状态**：`short_memory / long_term_memory / autosave / load_state_path`
7. **自动化特性**：`plan_enabled / rag_every_loop / reasoning_prompt_on / react_on`

初始化主链（按执行顺序）：

1. `setup_config()`
2. `short_memory_init()`
3. `setup_tools()`
4. `handle_tool_schema_ops()`（若有 schema）
5. `handle_sop_ops()`（若有 SOP）
6. handoff 注入（若配置 handoffs）
7. `tool_handling()`
8. `llm_handling()`（若未外部注入 llm）
9. `reliability_check()`

这意味着 Agent 在真正执行任务前，会先把“能力平面”（模型、工具、协作、记忆）一次性搭好。

---

## 3. 运行入口：run 如何分流

`run()` 是统一入口，核心分流逻辑是：

1. `max_loops == "auto"` → 进入 `_run_autonomous_loop`
2. 否则若 `imgs` 不为空 → `run_multiple_images`
3. 否则若 `n > 1` → 重复运行
4. 默认 → `_run`

此外 `run()` 还做了：

- 空任务时进入交互输入
- `skills_dir` 存在时按 task 加载 skills
- callback 优先级处理（调用参数优先于实例默认）
- 异常时 fallback model 切换

---

## 4. 标准循环 `_run`：最常用执行路径

`_run` 的主流程可以概括为：

1. **预处理**
   - 自动生成 prompt（可选）
   - 能力检查（如图像）
   - 任务写入 short memory
   - RAG 查询（一次或每轮）
   - 计划阶段 `plan()`（可选）

2. **主循环**（`while loop_count < max_loops`）
   - 构造 task prompt（含 transforms）
   - 调用 `call_llm`
   - `parse_llm_output`
   - 响应写回 memory
   - 如果响应含 tool calls：
     - handoff 工具优先处理
     - `tool_execution_retry` 执行普通工具
     - `mcp_tool_handling` 执行 MCP 工具
   - 检查停止条件
   - 交互模式处理（若启用）
   - loop_interval sleep（若设置）

3. **结束输出**
   - `history_output_formatter` 按 `output_type` 输出

---

## 5. autonomous 模式 `_run_autonomous_loop`：三阶段闭环

当 `max_loops="auto"` 时，不是简单轮询，而是“规划-执行-总结”三阶段：

### 5.1 规划阶段（Planning）

- 注入规划工具：`create_plan / think / subtask_done / complete_task` 等
- 可叠加 handoff 工具
- 通过 LLM + `create_plan` 产出子任务列表（含 step_id、依赖、优先级）
- 有最大规划尝试次数保护

### 5.2 执行阶段（Execution）

外层循环：

- `while not _all_subtasks_complete()`
- 有 `MAX_SUBTASK_ITERATIONS` 全局上限

内层循环（每个子任务）：

- `while not subtask_done and subtask_iterations < MAX_SUBTASK_LOOPS`
- 执行模式是：**思考 -> 工具 -> 观察 -> 再决策**

关键状态推进：

- 调用 `subtask_done(task_id=...)` 会标记当前子任务完成/失败
- 调用 `complete_task(...)` 会直接结束整个任务并进入总结输出

防死循环机制：

- 连续 `think` 次数受 `max_consecutive_thinks` 限制
- 超限会注入系统提示强制行动

### 5.3 总结阶段（Summary）

- 调 `_generate_final_summary()`
- 优先看是否触发 `complete_task` 工具结果
- 否则按子任务状态手工拼接总结

---

## 6. “如何结束”与“如何自我判断”

Swarms Agent 的“自我判断”主要不是单一评分函数，而是多重机制组合：

1. **循环终止条件**
   - 达到 `max_loops`
   - `stopping_condition(response)` 为真
   - `stopping_func(response)` 为真
   - 交互模式收到退出命令

2. **autonomous 子任务收敛**
   - `_all_subtasks_complete()` 全部完成
   - `complete_task` 明确宣告完成
   - 命中 `MAX_SUBTASK_LOOPS / MAX_SUBTASK_ITERATIONS` 强制停止

3. **异常与重试**
   - 单轮内 `retry_attempts` 重试
   - 全模型失败时 fallback model 迁移

4. **工具结果回流到记忆**
   - 每次工具执行结果写回 short memory
   - 下一轮 LLM 基于新上下文继续判断

所以它的“自我判断”是**基于循环中的状态反馈和工具证据逐步收敛**，而非单步判定。

---

## 7. 工具、handoff、MCP 的接入位置

### 7.1 普通工具

- 工具定义在 `tools_list_dictionary` / `tools`
- 运行中通过 `tool_execution_retry` 和底层执行器调用

### 7.2 handoff

- 初始化时注入 handoff 工具 schema
- run 循环中检测 `handoff_task` 调用并分发给目标 agent

### 7.3 MCP

- 若配置 `mcp_url/mcp_config`，在循环中调用 `mcp_tool_handling`
- MCP 作为外部工具协议层被并入同一执行环

---

## 8. 多 Agent 编排：SwarmRouter

多 Agent 不由 `Agent` 单类完成，而是通过 `SwarmRouter` 工厂路由：

1. `_create_swarm()` 按 `swarm_type` 动态创建具体编排器
2. `_run()` 把 task/tasks 转发给具体 swarm 的 `run()`
3. 支持顺序、并发、重排、图工作流等结构

这层是“编排平面”，`Agent` 是“执行平面”。

---

## 9. 与本项目（swarmbot）的关系

当前 `swarmbot` 不是直接跑 swarms 原生 Agent，而是自研 `CoreAgent + InferenceLoop`：

- 自研 Agent：`swarmbot/core/agent.py`
- Loop 编排：`swarmbot/loops/inference.py`
- 会话管理：`swarmbot/swarm/manager.py`

因此可把 swarms 源码当作可参考实现：

1. Agent 生命周期管理参考
2. autonomous 子任务循环参考
3. SwarmRouter 编排抽象参考

---

## 10. 一句话总结

Swarms 的 Agent 本质是一个“可配置循环执行器”：

- 标准模式用 `_run` 做多轮 LLM + 工具反馈闭环
- autonomous 模式用“计划-执行-总结”三阶段做结构化收敛
- 通过 stopping 条件、子任务状态、工具回流和迭代上限保障可终止性与稳定性。

