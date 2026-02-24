# SwarmBot 三层记忆与五阶段主循环架构设计草案

> 本文档用于记录当前已实现的三层记忆改动，以及后续规划的五阶段渐进式 SwarmBot Loop 架构，作为后续迭代的设计基准线。

## 1. 当前实现回顾：三层记忆体系

三层记忆由 `QMDMemoryStore` 统一封装，对应文件：

- Whiteboard（MemoryMap）：[memory/qmd.py](file:///root/swarmbot/swarmbot/memory/qmd.py)
- LocalMD（本地日志）：[memory/qmd.py](file:///root/swarmbot/swarmbot/memory/qmd.py)
- QMD（长期知识库）：[memory/qmd_wrapper.py](file:///root/swarmbot/swarmbot/memory/qmd_wrapper.py)
- Swarm 主循环入口 / Boot：[swarm/manager.py](file:///root/swarmbot/swarmbot/swarm/manager.py)
- Overthinking 整理循环：[loops/overthinking.py](file:///root/swarmbot/swarmbot/loops/overthinking.py)

### 1.1 Whiteboard（活跃工作区）

Whiteboard 对应 `MemoryMap`，是当前会话的结构化任务工作区。

核心特性：

- 内部存储为 `_data: Dict[str, Any]`，初始化时自动调用 `ensure_task_frame()` 补全核心结构。
- 核心字段（与 2.1.1 设计对齐）：
  - `task_specification: Object`
  - `execution_plan: Object`
  - `current_state: Enum`（INIT/PLANNING/EXECUTING/VERIFYING/FINALIZING 等）
  - `loop_counter: Integer`
  - `completed_subtasks: Array`
  - `pending_subtasks: Array`
  - `intermediate_results: Object`
  - `content_registry: Array`
  - `checkpoint_data: Object`
  - `qmd_candidates: Array`（新增，用于标记要持久化到 QMD 的条目）

接口能力：

- `update(key, value)`：更新指定键。
- `get(key)`：读取指定键。
- `get_snapshot()`：以 JSON 字符串导出当前白板快照，用于作为 system message 注入各 Agent。
- `ensure_task_frame()`：在任意时刻补全上述核心字段，避免 Agent 读到空结构。
- `clear(preserve_core=True)`：
  - `True`：只保留核心结构，清理临时键（例如 `current_task_context`、临时结果），支持跨循环渐进式推进。
  - `False`：完全清空后重新初始化核心结构。

### 1.2 LocalMD（本地日志）

LocalMD 由 `LocalMDStore` 实现，位置同上。主要职责是：

- 按 session + 日期的维度记录结构化的 Loop 日志。
- 通过文件锁实现追加写入的原子性。

文件命名：

- 每个会话每天一个文件：
  - `chat_log_<session_id>_<date>.md`

首次写入时的 YAML 头（front matter）：

```markdown
---
session_id: <session_id>
date: 2026-02-24
task_type: general
loops: 0
final_status: running
---
```

每轮主循环结束时追加一个 Loop 块（由 `SwarmManager._persist_log` 写入）：

```markdown
## Loop <loop_counter> [HH:MM:SS] - State: <current_state>

### Input

<用户原始输入>

### Result (snippet)

<截断后的结果片段>

### Whiteboard Snapshot

```json
{ ... 当前 Whiteboard 完整 JSON ... }
```
```

这与“LocalMD 作为结构化、机器可读的短期存储”的设计目标一致，后续 Overthinking 可以基于这些 Loop 块做进一步整理。

### 1.3 QMD（结构化知识库）

QMD 使用嵌入式 SQLite 实现，封装为 `EmbeddedQMD`：

- 支持 collection 概念：可用于区分 `task_patterns` / `domain_knowledge` / `user_preferences` / `tool_experiences` 等。
- 若环境支持 FTS5：
  - 使用 `documents_fts` 虚表，提供 BM25-like 的全文检索能力。
- 否则 fallback 到普通表 + LIKE 搜索。

当前接口：

- `add(content, collection="default", meta=None)`：
  - 自动创建 collection；
  - 对 content 与 meta 做 UTF-8 清洗，再写入数据库。
- `search(query, collection=None, limit=5)`：
  - 如果有 FTS5：使用 `MATCH` + `ORDER BY rank LIMIT limit`；
  - 否则：使用 `LIKE` + `ORDER BY created_at DESC LIMIT limit`。

QMDMemoryStore 对外：

- `persist_to_qmd(content, collection)`: 包装 `EmbeddedQMD.add`，并在文件系统中同步生成 `memory_*.md` 备份。
- `search(query, collection=None, limit=5)`: 直接透传到 EmbeddedQMD。
- `get_context(agent_id, limit, query)`：整合 Whiteboard / Local events / QMD 搜索结果形成多层 context。

当前尚未实现向量检索与 BM25 融合排序，后续可在此基础上增加 embedding 表与混合得分逻辑。

## 2. 已实现的记忆流动机制

本节对应 2.2 的“读取流 / 写入流 / 整理流”，记录当前代码级落地情况。

### 2.1 读取流（Read Flow）

入口：`SwarmManager.chat(user_input, session_id)` 中的 Phase 1 `_boot_swarm_context`。

顺序如下：

1. **检查点恢复（P0）**
   - 从 LocalMD 缓存目录读取 `checkpoint_<session_id>.json`。
   - 若存在且为字典，则逐键写回 Whiteboard。
   - 随后执行：
     - `loop_counter = loop_counter + 1`
     - `current_state = "PLANNING"`

2. **LocalMD 检索（P1）**
   - 读取当日当前 session 的日志：
     - `chat_log_<session_id>_<date>.md`
   - 按 `\n## Loop ` 切分所有 Loop 块。
   - 对每个 Loop 块计算与当前 `user_input` 的简单字符串相关性得分：
     - 若输入含空格：按空格切词，统计每个 term 在该 Loop 文本中的出现次数之和。
     - 若输入无空格（如纯中文）：若整句出现在 Loop 中，则记 1 分，否则 0。
   - 按 `(score, index)` 逆序排序，取得分最高的最多 5 个 Loop，若全为 0，则退化为最近 3 个 Loop。
   - 将合并后的文本作为 `md_excerpt` 注入 Whiteboard 的 `current_task_context.md`。

3. **QMD 语义搜索（P2，当前基于 FTS/BM25）**
   - 根据 `user_input` 长度动态设置 `limit`：
     - 长度 < 40：`limit = 3`
     - 40–119：`limit = 5`
     - ≥ 120：`limit = 10`
   - 调用 `session.memory.search(user_input, limit=limit)`。
   - 拼接结果形成 `qmd_context`，写入 `current_task_context.qmd`。

4. **Boot / 工具 / Skill 加载（P3）**
   - SwarmBoot：
     - 读取 `~/.swarmbot/boot/swarmboot.md` 或包内默认。
     - 首次加载后缓存到 `SwarmManager._swarmboot_cache`，之后每轮直接复用。
   - MasterAgentBoot：
     - 同理缓存到 `_masterboot_cache`。
   - 工具与 Skill：
     - 由 `NanobotSkillAdapter.get_tool_definitions()` 提供全集；
     - 在 `CoreAgent.step()` 内按角色和 `ctx.skills` 做过滤。

5. **上下文组装与注入**
   - 构造 `structured_context`：
     - `swarmboot_config`
     - `prompt`
     - `qmd`
     - `md`
     - `session_id`
     - `system_capabilities`（daemon/cron/heartbeat/skills 路径与 CLI）
   - 写入：`whiteboard.update("current_task_context", structured_context)`。
   - `QMDMemoryStore.get_context()` 会在后续为各 Agent 拼接 context 时，将 Whiteboard snapshot 作为高优先级 system message 注入。

### 2.2 写入流（Write Flow）

1. **推理中：Whiteboard 实时写入**
   - 通过工具 `whiteboard_update`，由各 Agent 使用。
   - 系统提示中对 Whiteboard 使用有明确约束：
     - 白板被视为结构化工作区，核心字段固定。
     - 写入时推荐使用对象格式，至少包含：
       - `content`：具体内容
       - `source`：信息来源（web_search/user/qmd 等）
       - `fact_checked`：是否已通过工具核实
     - 需要持久化到 QMD 的条目应追加到 `qmd_candidates` 列表，并设置：
       - `confidence_score`（0–1）
       - `verification_status`（如 pending/verified）

2. **循环结束：写入 LocalMD（Loop 级结构化日志）**
   - `SwarmManager._persist_log` 会在每次 `chat()` 完成后：
     - 读取 Whiteboard 当前数据；
     - 写入一个带 loop 编号、时间戳与状态的 Loop 块到对应的 `chat_log_<session_id>_<date>.md` 文件中。

3. **循环结束：筛选写入 QMD（flag_for_qmd）**
   - 在 `_persist_log` 中遍历 Whiteboard 的 `qmd_candidates` 列表：
     - 跳过：
       - 无 `content`；
       - `confidence_score <= 0.7`；
       - `verification_status == "pending"`。
     - 满足条件的条目：
       - `collection = item.collection or "core_memory"`；
       - 除 `content` 外其余字段全部写入 `meta`；
       - 调用 `session.memory.persist_to_qmd(content, collection)`。
   - 这实现了“主循环结束时才对高置信、已验证的内容进行长期持久化”的策略。

4. **循环结束：检查点持久化**
   - `_persist_log` 同时从 Whiteboard 中抽取核心键：
     - `task_specification`
     - `execution_plan`
     - `current_state`
     - `loop_counter`
     - `completed_subtasks`
     - `pending_subtasks`
     - `intermediate_results`
     - `content_registry`
     - `checkpoint_data`
   - 写入 `checkpoint_<session_id>.json`，供下一次 Boot 阶段恢复。

5. **Whiteboard 清理策略**
   - 在 `SwarmManager.chat` 的 Phase 3 之后：
     - 调用 `whiteboard.clear(preserve_core=True)`。
   - 核心结构与关键状态（包括 loop_counter 等）得以保留，临时键（如本轮的 current_task_context）被清除，为下一轮循环保留一个“洁净但持续”的工作区。

### 2.3 整理流（Consolidation Flow）

由 Overthinking 循环负责，位置：`loops/overthinking.py`。

1. **_step_consolidate_short_term：LocalMD → QMD**
   - 遍历 LocalMD 缓存目录中所有当天文件：
     - 匹配 `chat_log_*_<date>.md`。
   - 将所有文件内容拼接为一个大文本 `joined`。
   - 构造整理 prompt：
     - 要求模型提取关键事实、决策和洞见，忽略闲聊。
   - 只取 `joined` 的最后约 4000 字符作为输入窗口。
   - 将生成的 summary 以：
     - `# Memory Consolidation <date>` 标题
     - 写入 QMD 的 `core_memory` collection。

2. **_step_expand_thoughts：基于 QMD 的反思**
   - 构造问题式 prompt，请模型基于最近记忆提出潜在长期影响和待调查问题。
   - 将结果写入 QMD 的 `thoughts` collection。

3. **_step_autonomous_exploration：自我优化探索**
   - 创建新的 `SwarmManager`（共享同一份配置）。
   - 构造 `SYSTEM_OVERTHINKING_MODE` 特化 prompt，让 Swarm 自主选择一个改进方向（如优化 SOUL、验证工具等），执行并输出结构化日志。
   - 日志写入 `workspace/exploration_logs/explore_*.md`。

当前 Overthinking 仍按固定间隔触发，但由于主循环已经能在每轮结束时同步持久化高置信度条目，Overthinking 更偏向“日终整理”和“长期反思”，两者互为补充。

## 3. 目标架构：五阶段渐进式主循环（设计）

> 本节是未来版本 SwarmBot Loop 的目标形态，目前尚未完全落地实现，仅作为设计草案保存在文档中。

### 3.1 五阶段主循环概览

目标是从“单次执行即结束”的模式，升级为状态机驱动的五阶段渐进式循环，每次调用 `chat()` 不再视为完整生命周期，而是一次循环中的一个或多个阶段执行。

五个阶段：

- P1: 初始提示（Initial Prompting）
  - 目标：深度理解用户需求，识别任务类型、范围、约束与策略。
  - 输出：结构化任务规格书（Task Specification），写入 Whiteboard 的 `task_specification`。
  - 终止条件：需求解析完成、关键信息无歧义；否则向用户澄清或使用默认值。

- P2: 计划制定（Planning）
  - 目标：将任务规格书转化为可执行路线图。
  - 输出：带依赖关系的子任务 DAG、里程碑定义，写入 Whiteboard 的 `execution_plan`、`pending_subtasks`、`checkpoint_data`。
  - 终止条件：计划通过自洽性检查、资源评估可行；否则简化计划或请求更多资源。

- P3: 执行与中间检查（Execution & Mid-Plan Check）
  - 目标：按计划执行子任务，监控进度与质量。
  - 输出：子任务完成标记、`completed_subtasks` 更新、`intermediate_results` 填充、偏差报告。
  - 终止条件：
    - 所有子任务完成 → 可进入 P4/P5。
    - 触发重规划条件 → 切换到 P2 或 REPLANNING 状态。

- P4: 格式验证（Format Verification）
  - 目标：验证结构完整性、数据一致性、引用可追溯性、格式合规与语义完整性。
  - 输出：验证报告、修正指令；更新 `checkpoint_data` 与 `content_registry`。
  - 终止条件：
    - 验证通过且存在更多子任务 → 返回 P3；
    - 验证通过且已达最终里程碑 → 进入 P5；
    - 验证失败 → REPLANNING 或返回 P3 补充特定内容。

- P5: 最终生成（Finalize Response）
  - 目标：聚合所有阶段性成果，生成完整交付物。
  - 输出：最终报告/代码/分析文档；执行摘要、关键发现列表、行动优先级排序。
  - 终止条件：
    - 交付物生成并持久化成功 → COMPLETED；
    - 若仍存在待处理子任务或不满足质量门槛 → 可以回到 P3 再进行一轮补充执行。

关键差异点：

- 五个阶段构成“一次循环迭代”，而非完整的请求回合。
- P5 完成后并不必然终止，可根据 Whiteboard 中的状态评估是否需要更多迭代（如仍有 `pending_subtasks` 或验证评分不足）。

### 3.2 P1 与 Whiteboard 的映射（任务规格书）

P1 主要作用是填充 Whiteboard 的 `task_specification`，包含：

- 精化后的目标陈述；
- 任务类型（如代码审查、功能分析、Bug 修复、架构设计、性能优化等）；
- 关键分析维度（安全/性能/可维护性/可测试性等）；
- 预估复杂度等级；
- 选定的执行策略（深度优先/广度优先/风险驱动/依赖导向）；
- 初始子任务草案；
- 待用户澄清的问题列表。

P1 的内部逻辑：

- 任务类型识别：
  - 关键词信号（"review"、"分析"、"fix" 等）。
  - 代码片段特征（文件名、语言、结构模式）。
  - 历史任务相似度（QMD 检索）。
- 约束识别：
  - 时间限制、深度要求、范围边界、格式偏好等。
- 策略选择：
  - 根据任务类型与预估 Token 预算，从预定义策略库中选择执行模式。

最终由一个负责 P1 的 Planner Agent，将这些信息写入 Whiteboard，并把 `current_state` 从 `INIT` 转为 `PLANNING` / `EXECUTING`。

### 3.3 P2：计划制定与 DAG 构建

P2 负责将 `task_specification` 转化为 `execution_plan`：

- 分解层级：
  - L0：phase 级目标（phase_security_audit 等）。
  - L1：task 级具体任务（task_security_01_sql_injection 等）。
  - L2：op 级原子操作（单次工具调用可以完成）。
  - L3：step 级微步骤（单轮推理）。
- 依赖关系：
  - 数据流依赖：A → B。
  - 控制流依赖：A ⊳ B。
  - 资源依赖：A ∥ B。
  - 软依赖：A ⇢ B。
- 里程碑：
  - M1 架构认知、M2 深度分析、M3 综合整合、M4 质量门控。

Whiteboard 中的对应字段：

- `execution_plan`：存储 DAG 与里程碑定义。
- `pending_subtasks`：维护就绪队列（按优先级排序）。
- `checkpoint_data`：记录当前位于哪一阶段、哪个里程碑以及关键路径位置。

### 3.4 P3：执行与中间检查

在 P3 中：

- 从 Whiteboard/检查点恢复完整执行上下文；
- 根据 DAG 与资源状况，从 `pending_subtasks` 中选择下一批任务；
- 调用工具与模型执行，生成中间产物并写入：
  - `intermediate_results`
  - `completed_subtasks`
  - `content_registry`
- 自检与中间验证：
  - 简单一致性/完整性检查；
  - 若失败，触发重试或任务重分解。

防重复机制（规划中）：

- 维护“已完成工作注册表”，记录每个子任务的输出摘要与语义指纹（例如 MinHash 或 embedding hash）。
- 新内容生成前：
  - 计算与历史指纹相似度；
  - 相似度 >0.85：提示模型专注差异；
  - 相似度 >0.95：直接引用历史结果，跳过重新生成。

Whiteboard 中的 `current_state` 在这一阶段一般为 `"EXECUTING"`。

### 3.5 P4：格式验证

P4 将 P3 的中间产物与整体目标对齐，从以下维度验证：

- 结构完整性：章节/字段是否齐全（Schema 校验）。
- 数据一致性：不同部分引用的数据是否一致。
- 引用可追溯：每个结论是否有明确证据来源。
- 格式合规：是否符合用户指定的格式（Markdown / JSON / 表格）。
- 语义完整性：结论是否充分支撑原始目标。

多 Agent 协作方式：

- critic：独立审查内容。
- summarizer：综合形成验证报告。
- planner：根据报告决策是继续执行、重规划还是进入最终生成。

Whiteboard 中将：

- 在 `content_registry` 记录各产出与其验证状态。
- 在 `checkpoint_data` 中记录最新验证结果与下一步建议。
- 将 `current_state` 切换为 `"VERIFYING"` / `"REPLANNING"` / `"FINALIZING"`。

### 3.6 P5：最终生成

P5 聚合所有子任务的输出形成统一交付物：

- 结果聚合：
  - 按任务类型选择聚合维度（代码审查按模块、功能分析按用户故事、架构评估按质量属性）。
- 一致性校验：
  - 全局检查术语、数据引用、逻辑一致性；
  - 冲突时基于置信度加权裁决。
- 质量增强：
  - 生成执行摘要（约 300 字，包含任务概览、核心结论、关键风险、行动建议）；
  - 将关键发现高亮，并按重要性排序；
  - 对行动项做影响-努力矩阵排序。

P5 完成后：

- 若所有里程碑达成且用户需求满足：
  - `current_state = "COMPLETED"`；
  - 写入 QMD 与 LocalMD。
- 若仍有 `pending_subtasks` 或验证评分不足：
  - 根据策略返回 P3 再进行一轮执行；
  - 即 P5 并非必然终点，而是可能启动新一轮循环的节点。

### 3.7 循环状态机（规划）

状态集合（S）：

- `INIT`：初始化，等待任务规格。
- `PLANNING`：计划制定中。
- `EXECUTING`：执行子任务。
- `VERIFYING`：验证中间结果。
- `REPLANNING`：计划调整/异常恢复。
- `FINALIZING`：最终生成。
- `COMPLETED`：任务完成。
- `ERROR`：不可恢复错误。
- `PAUSED`：用户暂停。

典型转换规则（T）：

- `T(INIT, task_spec_ready) → PLANNING`
- `T(PLANNING, plan_validated) → EXECUTING`
- `T(EXECUTING, milestone_reached) → VERIFYING`
- `T(EXECUTING, all_tasks_complete) → FINALIZING`
- `T(VERIFYING, verification_passed ∧ more_tasks) → EXECUTING`
- `T(VERIFYING, verification_passed ∧ final_milestone) → FINALIZING`
- `T(VERIFYING, verification_failed) → REPLANNING`
- `T(REPLANNING, new_plan_ready) → EXECUTING`
- `T(FINALIZING, output_generated) → COMPLETED`
- `T(any, unrecoverable_error) → ERROR`
- `T(any, user_interrupt) → PAUSED`
- `T(PAUSED, user_resume) → 恢复前一状态`

#### 3.2.1 状态定义与转换规则（补充）

- 上述状态集合 S 与转换规则 T 将映射到 Whiteboard 的 `current_state` 字段以及事件信号（如 `task_spec_ready`、`plan_validated` 等）。
- 关键设计点：
  - INIT → PLANNING：由 P1 任务规格书生成完成触发。
  - PLANNING → EXECUTING：由 P2 计划通过自洽性与资源可行性检查触发。
  - EXECUTING ↔ VERIFYING：通过里程碑达成与验证结果在 P3/P4 间往返。
  - FINALIZING → EXECUTING：允许在 P5 检测到未达标或新增工作后回到执行阶段，实现真正的多轮渐进式循环，而非“一次执行即结束”。
- 未来实现中，Whiteboard 的 `current_state` 字段将直接对齐上述状态集合，并由 `SwarmManager` 或专门的状态机引擎驱动阶段切换。

#### 3.2.2 终止条件精细化

终止条件按“硬终止 / 软终止 / 智能终止”三层设计：

- **硬终止（资源与用户驱动）**
  - 全局超时：
    - 条件：单次任务累计运行时间超过 30 分钟。
    - 作用：资源保护与用户体验保障。
    - 响应：强制保存当前检查点与关键结果，返回部分结果，并将状态置为 `ERROR` 或 `COMPLETED_WITH_LIMITS`（未来可扩展状态）。
  - 最大 Token 消耗：
    - 条件：累计 Token 消耗超过 100K。
    - 作用：控制成本与避免过长对话。
    - 响应：触发上下文压缩与降级输出（例如只保留摘要与关键结论）。
  - 用户显式取消：
    - 条件：用户主动发出取消指令。
    - 作用：尊重用户主权。
    - 响应：立即终止当前循环，持久化审计日志与关键中间结果。

- **软终止（局部控制）**
  - 阶段超时：
    - 条件：P1 超过 2 分钟、P2 超过 5 分钟、P3 单轮执行超过 10 分钟。
    - 响应：触发降级策略（降低分析深度、缩小范围）或进入 REPLANNING。
  - 单步最大迭代次数：
    - 条件：同一子任务连续迭代超过 5 次仍未达成目标。
    - 响应：标记当前路径失败，尝试替代路径或调整任务拆分。
  - 连续失败次数：
    - 条件：连续 3 次关键步骤失败（工具调用失败、验证失败等）。
    - 响应：触发重规划或将任务升级为“需要人工介入”的状态。

- **智能终止（任务完成信号）**
  - LLM 无进一步工具调用意图：
    - 条件：模型多轮返回中均未提出新的工具调用或子任务。
    - 响应：视为潜在完成信号，进入 P4/P5 做最终验证。
  - 所有里程碑达成：
    - 条件：M1–M4 均标记完成，且无未处理高风险项。
    - 响应：直接进入 P5，聚合最终输出。
  - 质量门控通过：
    - 条件：综合质量评分（结构、数据、引用、语义）> 0.85。
    - 响应：可提前终止后续低收益迭代，节约资源。

终止决策建议采用“多维评估 + 投票机制”：各维度分别给出“继续 / 终止”建议，再由上层控制器综合决策。

#### 3.2.3 异常恢复机制

异常恢复围绕“检测 → 即时响应 → 恢复策略 → 升级条件”四步展开：

- 模型调用失败：
  - 检测方式：API 错误码 / 超时。
  - 即时响应：指数退避重试（例如 1s → 2s → 4s）。
  - 恢复策略：在多次失败后切换备用模型或简化提示（减少上下文长度与复杂度）。
  - 升级条件：连续 3 次重试失败，将当前子任务标记为失败，并交由 REPLANNING 阶段处理。

- 工具执行失败：
  - 检测方式：工具返回异常、超时或明显错误结果。
  - 即时响应：更换等效工具、调整参数或缩小输入规模。
  - 恢复策略：
    - 对非关键步骤：可以跳过或降级，并在 Whiteboard 中标记依赖阻塞。
    - 对关键工具失败：触发子任务重分解或重新规划执行路径。
  - 升级条件：关键工具多次失败或无法找到替代时，将任务标记为需要人工介入。

- 记忆操作失败（LocalMD/QMD）：
  - 检测方式：检索超时、写入冲突或持久化异常。
  - 即时响应：降级到本地缓存或内存结构，异步重试持久化。
  - 恢复策略：
    - 简化记忆加载（只读摘要、不加载全量历史）。
    - 在 Whiteboard 中记录异常，以便后续 Overthinking 处理。
  - 升级条件：多次持久化失败或关键检查点无法写入时，提示用户并停用部分高级记忆功能。

- 计划执行失败：
  - 检测方式：子任务反复失败、整体进度明显停滞。
  - 即时响应：局部重分解当前子任务、调整执行策略（例如从深度优先改为广度优先）。
  - 恢复策略：
    - 全局重规划：在 REPLANNING 阶段重新评估任务范围与优先级。
  - 升级条件：核心路径上的关键子任务无法完成时，将任务标记为失败并请求人工接管。

- 验证持续失败：
  - 检测方式：同一子任务或同一维度在 P4 一再无法通过验证。
  - 即时响应：
    - 适度放宽验证标准（例如从 100% 覆盖降到采样检查）。
    - 要求模型明确列出“不足之处”和“潜在风险”。
  - 恢复策略：
    - 重新分解子任务，分派给不同的 Agent 或采用不同的工具组合。
  - 升级条件：用户明确要求更严格标准，或验证失败集中在高风险区域。

上述异常恢复策略将结合 Whiteboard 的 `checkpoint_data`、`content_registry` 与 LocalMD/ QMD 日志，实现“可回放、可审计、可恢复”的执行路径。

### 3.3 记忆感知的状态持久化

#### 3.3.1 检查点机制

检查点在关键状态转换时自动保存，包含完整的状态快照，主要内容包括：

- 任务状态：
  - 内容：状态机当前状态、循环序号等。
  - 存储格式：JSON。
  - 压缩策略：无。
  - 保留策略：最近 10 个检查点。
- 执行计划：
  - 内容：DAG 完整结构、当前进度与里程碑状态。
  - 存储格式：JSON + GraphML（未来可扩展到图表示）。
  - 压缩策略：图结构压缩与去重。
  - 保留策略：最近 5 个版本。
- 子任务进度：
  - 内容：各子任务状态与输出摘要。
  - 存储格式：JSON。
  - 压缩策略：以摘要替代详细输出。
  - 保留策略：最近 5 个版本。
- 中间产物集合：
  - 内容：完整输出与引用关系。
  - 存储格式：文件系统 + 索引。
  - 压缩策略：内容寻址去重。
  - 保留策略：任务完成前保留，任务结束后按策略归档。
- 上下文摘要：
  - 内容：Whiteboard 核心内容与关键决策。
  - 存储格式：JSON + Markdown。
  - 压缩策略：结构化压缩与多轮摘要。
  - 保留策略：最近 10 份摘要。
- 元数据：
  - 内容：时间戳、Token 消耗、异常记录等。
  - 存储格式：JSON。
  - 压缩策略：无。
  - 保留策略：长期保留，用于审计与统计。

典型检查点触发条件：

- 状态转换（例如 INIT→PLANNING、EXECUTING→VERIFYING 等）。
- 循环迭代边界（每 N 次迭代）。
- 风险信号（异常率上升、进度停滞）。
- 用户显式请求（如“保存进度”、“稍后继续”）。

#### 3.3.2 Whiteboard 生命周期管理

Whiteboard 在一个任务中的生命周期可分为四个阶段：

- 循环开始时：
  - 内容：从检查点恢复或初始化任务状态。
  - 持久化策略：从最近检查点完整加载到内存。
  - 清理策略：不清理，保留上次循环的核心进度。
- 循环进行中：
  - 内容：当前子任务、中间结果、状态变更等实时更新。
  - 持久化策略：每个关键步骤将增量变更同步到 LocalMD/检查点临时区。
  - 清理策略：不清理，以便随时回滚。
- 循环结束时：
  - 内容：筛选重要信息（进度、关键决策、风险），准备写入 LocalMD 与 QMD。
  - 持久化策略：结构化序列化（Loop 块 + Whiteboard Snapshot + qmd_candidates）。
  - 清理策略：保留核心进度（任务标识、循环序号、状态、已完成/待处理子任务、关键决策、风险预警），清除详细中间结果（完整输出、工具调用细节、临时计算等）。
- 任务完成时：
  - 内容：最终摘要与关键路径信息，准备归档。
  - 持久化策略：持久化到“任务历史”或专用 QMD collection。
  - 清理策略：完全清空 Whiteboard，与任务解绑。

#### 3.3.3 跨循环状态传递

跨循环状态传递通过三层机制实现：

- 即时传递（同任务内）：
  - 通过检查点实现精确恢复，支持从任意检查点继续执行。
  - 检查点采用“基础状态完整存储 + 迭代间增量记录 + 索引文件”的策略，既保证恢复精度，又控制存储成本。

- 短期传递（跨任务、同会话）：
  - 通过 LocalMD 保留最近 N 个任务的摘要信息与关键决策。
  - 检索时兼顾时效性与任务相似性（任务类型、目标领域、使用工具/资源等）。

- 长期传递（跨会话）：
  - 通过 QMD 将 Overthinking 整理后的知识沉淀为结构化条目。
  - 检索时采用混合策略：语义相似度 + 关键词匹配 + 时间衰减加权。

这三层传递机制与 Whiteboard + LocalMD + QMD 的架构一一对应，使得 SwarmBot 能在多轮、跨任务、跨会话的时间尺度上保持连贯的任务推进与知识演化。

## 4. 核心组件重构与后续实现（草案）

本节描述在现有 SwarmBot 代码基础上，为支持三层记忆与五阶段主循环所需要的核心组件改造方案，重点聚焦 SwarmManager 与 CoreAgent。

### 4.1 SwarmManager 改造

#### 4.1.1 会话管理增强

目标：在 `get_session` 层面支持“循环状态恢复”，并为每个会话维护独立的循环状态机实例与迭代计数器。

设计示意：

```python
def get_session(session_id: str, resume_from_checkpoint: bool = True) -> SwarmSession:
    session = session_store.get(session_id)
    if session is None:
        session = create_new_session(session_id)
    
    if resume_from_checkpoint:
        latest_checkpoint = checkpoint_store.get_latest(session_id)
        if latest_checkpoint:
            session.restore_from_checkpoint(latest_checkpoint)
    
    # 初始化循环状态机
    session.state_machine = LoopStateMachine(
        initial_state=session.checkpoint_state or State.INIT
    )
    session.iteration_counter = session.checkpoint_iteration or 0
    
    return session
```

关键点：

- `SwarmSession` 持有：
  - `state_machine: LoopStateMachine`：驱动五阶段状态转换（INIT/PLANNING/...）。
  - `iteration_counter: int`：记录当前循环迭代次数，用于终止条件与日志标记。
- 状态机负责“当前处于哪个阶段/状态”，多 Agent 架构负责“在 EXECUTING 等阶段内具体如何协作”。

#### 4.1.2 `_boot_swarm_context` 优化

在保留现有功能（Boot 配置加载、QMD 检索、LocalMD 读取、system_capabilities 构建）的基础上，增加：

- 从最近检查点恢复 Whiteboard 核心状态；
- 初始化循环状态（`current_state` / `loop_counter`）；
- 将更丰富的任务与历史信息写入 Whiteboard，例如：

```json
{
  "meta": {
    "iteration": 3,
    "state": "EXECUTING",
    "checkpoint_id": "chk_20240224_143052"
  },
  "task_context": {
    "specification": { "...": "..." },
    "current_subtask": "security_audit_sql_injection",
    "completed_tasks": ["architecture_overview", "dependency_analysis"],
    "pending_tasks": ["performance_review", "final_report"]
  },
  "history_summary": {
    "total_tokens_consumed": 24500,
    "key_decisions": ["..."],
    "risk_alerts": ["..."]
  },
  "original_prompt": "...",
  "retrieved_memories": {
    "localmd": "...",
    "qmd": "...",
    "system_capabilities": { "...": "..." }
  }
}
```

该结构可以作为 Whiteboard 中 `current_task_context` 的扩展版本，便于各 Agent 在不同阶段快速感知任务进度与风险。

#### 4.1.3 循环控制核心 `_run_loop_iteration`

新增一个“单次循环迭代执行器”，由状态机驱动，根据当前状态调用 P1–P5（甚至扩展为 P6）的具体实现，并在每次迭代结束时保存检查点与决策结果。

示意伪代码：

```python
async def _run_loop_iteration(self, session: SwarmSession, user_input: str) -> LoopResult:
    """执行单次循环迭代，返回继续/终止/重规划决策"""
    
    current_state = session.state_machine.current_state
    
    if current_state == State.INIT:
        result = await self._p1_initial_prompting(session, user_input)
        session.state_machine.transition(State.PLANNING)
        
    elif current_state == State.PLANNING:
        result = await self._p2_planning(session)
        session.state_machine.transition(State.EXECUTING)
        
    elif current_state == State.EXECUTING:
        result = await self._p3_execution(session)
        if result.all_tasks_complete:
            session.state_machine.transition(State.FINALIZING)
        else:
            session.state_machine.transition(State.VERIFYING)
            
    elif current_state == State.VERIFYING:
        result = await self._p4_verification(session)
        if result.verification_passed:
            if result.all_complete:
                session.state_machine.transition(State.FINALIZING)
            else:
                session.state_machine.transition(State.EXECUTING)
        else:
            session.state_machine.transition(State.REPLANNING)
            
    elif current_state == State.REPLANNING:
        result = await self._p5_replanning(session)
        session.state_machine.transition(State.EXECUTING)
        
    elif current_state == State.FINALIZING:
        result = await self._p6_finalization(session)
        session.state_machine.transition(State.COMPLETED)
    
    # 保存检查点
    await self._save_checkpoint(session)
    
    # 迭代间决策
    decision = self._make_iteration_decision(session, result)
    return LoopResult(
        output=result.output,
        decision=decision,  # CONTINUE / TERMINATE / REPLAN / ESCALATE
        next_prompt=result.next_prompt if decision == Decision.CONTINUE else None
    )
```

要点：

- `_run_loop_iteration` 不直接决定“整体结束”，而是返回一个决策枚举，由上层控制器根据终止条件（见 3.2.2）综合判断。
- 每轮迭代后都调用 `_save_checkpoint`，利用 3.3 中描述的检查点机制保证可恢复性。

### 4.2 CoreAgent 增强

#### 4.2.1 状态感知的消息构建

`CoreAgent._build_messages` 需要从“单轮对话视角”升级为“状态感知的 Loop 视角”，在构造消息时注入循环状态与任务进度：

```python
def _build_messages(self, session: SwarmSession, user_input: str) -> List[Message]:
    messages: List[Message] = []
    
    # 1. 系统提示：动态组装
    system_prompt = self._assemble_system_prompt(session)
    messages.append(SystemMessage(content=system_prompt))
    
    # 2. 上下文注入：分层加载（Whiteboard + LocalMD + QMD 摘要）
    context = self._load_context(session)
    if context:
        messages.append(ContextMessage(content=context))
    
    # 3. 历史交互：按 Token 预算智能截断
    history = self._load_history(session, max_tokens=self.history_budget)
    messages.extend(history)
    
    # 4. 当前输入
    messages.append(UserMessage(content=user_input))
    
    return messages

def _assemble_system_prompt(self, session: SwarmSession) -> str:
    components = [
        self.soul,                                # 角色定义 / SOUL
        self._format_task_progress(session),      # 任务进度与里程碑信息
        self._format_whiteboard_summary(session), # Whiteboard 核心摘要
        self.tool_definitions,                    # 工具与 Skill 定义
        self._format_state_guidance(session),     # 当前状态指导（INIT/EXECUTING/VERIFYING 等）
    ]
    return "\n\n".join([c for c in components if c])
```

这样，Agent 在不同状态下会收到不同的“状态指导”和任务进度摘要，而不是每轮都重复同样的系统提示。

#### 4.2.2 工具调用扩展（循环感知）

为支持 Agent 参与循环管理，需要新增一组“状态控制工具”：

| 工具名称            | 功能说明                                     | 典型调用时机                  |
|---------------------|----------------------------------------------|-------------------------------|
| `check_progress`    | 查询当前任务进度、里程碑状态、待处理队列     | 每阶段开始、执行中评估        |
| `update_plan`       | 动态调整执行计划（增删改子任务）             | 发现新依赖或遭遇障碍时        |
| `request_replanning`| 请求全局重规划，触发 REPLANNING 状态         | 计划严重偏离、资源耗尽时      |
| `summarize_for_localmd` | 生成 LocalMD 持久化摘要                   | 子任务完成、循环结束前        |
| `flag_for_qmd`      | 标记内容待 QMD 整理（写入 `qmd_candidates`） | 识别具有长期价值的知识时      |

这些工具与现有的文件/代码/搜索类工具并列，但服务于“Loop 管理”而非业务本身。

#### 4.2.3 输出解析增强（循环控制信号）

LLM 输出解析层需要识别“循环控制信号”，以便由文本输出驱动状态机决策。例如：

- `<continue>`：
  - 格式：可采用 XML 标签或专用标记（如 `<<continue>>`）。
  - 含义：Agent 认为当前阶段已完成，可以继续到下一轮迭代或下一个阶段。
  - 响应：由上层根据当前 `current_state` 和终止条件，将决策设置为 `Decision.CONTINUE`，并构造下一轮的 `next_prompt`。
- 其他信号（规划中）：
  - `<replan>`：请求进入 REPLANNING。
  - `<terminate>`：建议终止任务并输出当前最佳结果。
  - `<escalate>`：建议升级为人工处理或更高级别审查。

解析逻辑可以与工具调用解析放在同一层，对输出文本进行模式匹配与结构化提取，将“业务内容”与“控制信号”分离，保障循环控制的可预期性与安全性。

后续的落地实现可以按以下步骤推进：

1. 在现有 SwarmManager.chat 内，引入显式的“阶段调度器”，而不仅是一次性架构执行：
   - 根据 `current_state` 决定本次调用要执行的阶段（或阶段组合）。
   - 将 P1/P2/P3/P4/P5 的逻辑拆分为独立方法或策略对象。

2. 为 Task Specification 与 Execution Plan 设计稳定的 Whiteboard Schema：
   - 统一子任务命名规范与 DAG 表示方式。
   - 约定里程碑字段结构，方便验证与回退。

3. 将现有的多 Agent 架构（sequential/concurrent/mixture/hierarchical 等）映射到不同阶段的不同执行模式：
   - 例如在 P3 中采用 concurrent + consensus；
   - 在 P4 中采用 critic + summarizer + planner 协作。

4. 引入“已完成工作注册表”与 MinHash/embedding 指纹，防止 P3 中的重复劳动。

5. 渐进式迁移：
   - 初期在不破坏当前接口的前提下，将部分逻辑（特别是 P1/P2/P4）先内化到现有 pipeline 中；
   - 逐步引入状态机驱动，最终形成稳定的多轮循环控制结构。

本设计文档用于确保后续在实现五阶段主循环与状态机时，有清晰的目标与与现状的映射，不依赖口头记忆。后续每次迭代完成后，可在本文件基础上追加“实现进度”小节。 
