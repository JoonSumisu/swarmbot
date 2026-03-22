# InferenceLoop / SwarmLoop 架构优化设计（v1.0 文档修订版）

## 1. 文档目的

- 在不改代码前提下，重新定义 InferenceLoop/SwarmLoop 的高效率目标架构
- 明确 Supervisor 的效率职责：异常纠偏、阶段中断、提前收敛、快速输出
- 统一术语为 **PLANNING 驱动拆分**，避免“Decision”语义混乱
- 给出可执行的流程、状态、数据模型与测试校准标准

---

## 2. 当前痛点（as-is）

### 2.1 主要瓶颈

1. 异常处理偏被动：worker 出错后，纠偏和重试不够快  
2. 阶段收敛偏慢：已有明确结论时，未充分触发“提前结束 + master 输出”  
3. token 利用偏粗：请求粒度较大，跨阶段上下文重复注入  
4. 计划产物偏轻：`tasks[]` 可执行约束不足，不足以稳定驱动全流程  
5. whiteboard 信息偏杂：控制信号与业务内容混在一起

### 2.2 术语问题（本次已修正）

- 文档中的“Decision 拆分/分配”统一改为 **PLANNING 拆分/分配**
- “Tool Decision Request”保留为请求名，但语义定义为：  
  **基于 PLANNING 推荐的 skill + tool，计算最小可行工具集合**

---

## 3. 目标架构（to-be）

### 3.1 总体目标

1. **高效率控制**：尽快发现错误、尽快纠偏、尽快收敛输出  
2. **分层请求**：每次只处理一个最小问题单元，降低 token 与失败扩散  
3. **规划先行**：先由 PLANNING 输出结构化 framework_doc，再执行  
4. **自治执行**：EXECUTION worker 在分配约束内自主选择功能优先级或角色  
5. **可测可校准**：每一步有指标、有日志、有可回放证据

### 3.2 顶层状态机

`INIT -> ANALYSIS -> PLANNING -> TOOL_DECISION -> EXECUTION -> EVALUATION -> MASTER_OUTPUT -> ORGANIZATION -> DONE`

支持控制动作：

- `interrupt(stage, reason)`
- `rerun(stage, reason)`
- `terminate(stage, reason)`
- `promote_to_master(reason)`（提前收敛输出）

---

## 4. Supervisor 高效率控制面设计

### 4.1 设计意图

Supervisor 不是旁路监控器，而是“效率与稳定性总控器”：

1. **异常快速纠偏**：worker 异常时立刻停止该执行链，自动选择“重试/替换/降级”  
2. **输入动态调整**：按失败原因实时调整 prompt、约束、上下文片段  
3. **提前收敛输出**：一旦结论置信度达阈值，立即推进 master 输出  
4. **全局成本控制**：持续监控 token、耗时、重试次数，避免系统拖慢

### 4.2 运行职责

- 监控 worker 心跳、错误类型、结果置信度、阶段耗时
- 对每个阶段计算 `continue / adjust / stop / promote_to_master`
- 管理重试预算与降级路径
- 输出控制日志用于回放与评估

### 4.3 核心策略

1. **异常策略**
   - 可恢复错误：重试同 worker（限制次数）
   - 角色不匹配错误：更换 worker 角色/功能优先级
   - 工具失败错误：收缩工具集合并切换候选工具
   - 连续失败：终止当前子任务并回退到 PLANNING 检查点
2. **提前结束策略**
   - 使用关键任务完成率与置信度评分双阈值
   - 结论一致性达到阈值
   - 风险与证据完整性满足最低门槛
   - 满足后立即进入 `MASTER_OUTPUT`
3. **prompt 调整策略**
   - 缩小指令范围（只保留当前子任务）
   - 增加硬约束（禁用偏题输出）
   - 增加失败反馈（上一轮错误摘要）

### 4.4 提前收敛评分规则（定稿）

统一使用以下指标：

1. `key_task_completion_rate`：关键任务完成率（0~1）
2. `confidence_score`：结论置信度（0~1）
3. `consistency_score`：多 worker 结论一致性（0~1）
4. `evidence_coverage`：关键结论证据覆盖率（0~1）

综合分：

`final_confidence = 0.5 * confidence_score + 0.2 * consistency_score + 0.2 * evidence_coverage + 0.1 * key_task_completion_rate`

触发 `promote_to_master` 条件：

- `key_task_completion_rate >= 0.80`
- `final_confidence >= 0.78`
- 不存在 `hard_constraints` 违反项

---

## 5. PLANNING 驱动模型（本次重定义重点）

### 5.1 PLANNING 必须产出 framework_doc（而非仅 tasks）

`framework_doc` 建议包含：

- `objective`
- `scope`（in_scope/out_scope）
- `hard_constraints`
- `task_breakdown`（原子任务 + 依赖）
- `worker_recommendation`（每个任务推荐 skill/tool）
- `acceptance_criteria`
- `checkpoint_plan`
- `rollback_strategy`
- `early_finish_rules`

### 5.2 PLANNING 拆分与分配规则

1. 按目标拆分原子任务（可形成 DAG）  
2. 对每个任务输出推荐 `skills[]` 与 `tools[]`  
3. 给每个拆分任务分配执行 worker（owner 或候选组），仅分配任务，不指定角色  
4. 记录任务优先级、依赖关系、完成定义

---

## 6. EXECUTION 与 Tool Decision Request 协同

### 6.1 EXECUTION worker 自主机制

在已分配任务前提下，EXECUTION worker 再进行局部自治：

1. 先选择 **功能优先级**（例如：检索优先 /推理优先 /校验优先）  
2. 再确定 **执行角色**（PLANNING 不预设角色，worker 自主选择并解释原因）  
3. 在 supervisor 约束内执行，不得越出 framework_doc 的范围

### 6.2 Tool Decision Request（语义修正版）

Tool Decision Request 的职责是：

- 输入：PLANNING 推荐 `skills/tools` + EXECUTION 当前功能优先级  
- 输出：当前子任务的 **最小工具集合** 与替代路径

决策逻辑：

1. 先评估任务是否需要工具（可纯推理则禁工具）  
2. 必要时从推荐集合中选最小子集  
3. 工具失败时生成降级集合（备用最小集）

---

## 7. 关键歧义详细说明与解决方案

### 7.1 skill 与 tool 的边界定义问题（对应问题3）

问题说明：

- `tool` 与 `skill` 在语义上是两个不同功能层：
  - `tool`：可执行能力（如 `web_search`、`shell_exec`、`python_exec`、`browser_read`）
  - `skill`：处理问题的方法说明书（SKILL.md），用于指导策略与步骤
- 若把 skill 直接当作 tool 映射，执行层会混乱，导致“把说明书当执行器”。

解决方案：

1. 明确双通道流程：
   - Skill 通道：`skill_summary / skill_load / skill_fetch`（可在线拉取合适技能说明书）
   - Tool 通道：Tool Decision Request 只负责选择执行工具集合
2. PLANNING 阶段同时输出：
   - `recommended_skills`（说明书清单）
   - `recommended_tools`（执行工具候选）
3. EXECUTION 先装载 skill 指南，再按 Tool Decision 的最小工具集合执行
4. 仅当工具失败时才扩展工具集合，不把 skill 作为工具替代

执行规则：

- 优先级顺序：`任务目标 > skill装载 > tool最小集合 > tool降级集合`
- Skill 装载失败不等于工具失败，需分开计数与重试

### 7.2 whiteboard 外部索引一致性问题（对应问题4）

问题说明：

- 白板若只保留索引，会造成调试与阶段判断信息不足，且容易出现“看不到关键上下文”的误判。
- 白板若保留全部原文，会引起噪声、token 膨胀、历史污染。
- 需要“关键信息 + 外部内容”的平衡结构，而不是单纯索引化。

解决方案：

1. 白板采用双层内容模型：
   - 核心层（必须在白板）：阶段结论、关键约束、关键证据摘要
   - 外部层（放外部存储）：长原文、完整检索结果、附件全文
2. 所有外部引用采用 `evidence_id + version + checksum`
3. 写入白板前验证索引有效性，master 输出前二次验证
4. 在开发中通过压测与回归确定白板“摘要长度阈值”和“外部拉取阈值”

执行规则：

- 白板中禁止写入无版本号外部引用
- 白板必须保留可独立理解当前阶段的最小关键信息
- 每次重跑阶段必须刷新本阶段新增引用

### 7.3 Supervisor 幂等与并发控制问题（对应问题5）

问题说明：

- 当 `interrupt/rerun/terminate` 被重复触发，可能出现重复执行、状态覆盖、并发污染。

解决方案：

1. 每个控制动作携带 `control_action_id`，重复 ID 直接忽略  
2. 每阶段引入 `stage_lock`，同一阶段同一时刻只允许一个控制动作生效  
3. 状态迁移必须满足状态机白名单，不允许跨越非法状态

执行规则：

- 控制动作幂等键：`session_id + stage + control_action_id`
- 非法迁移立即拒绝并写入 `supervisor_decision_log`

---

## 8. 分层请求协议（最高效率版本）

每个子任务按以下请求链执行：

1. **Task Check Request**  
   - 校验任务目标、约束、完成标准是否清晰
2. **Skill Discovery Request**  
   - 通过 `skill_summary / skill_load / skill_fetch` 确定当前任务最合适的技能说明书
3. **Tool Decision Request**  
   - 基于推荐 tool + 当前功能优先级，计算最小工具集合（不负责技能检索）
4. **Execute Request**  
   - 装载已选 skill 说明书，仅带当前任务必需上下文执行
5. **Evaluate Request**  
   - 只检查该任务的验收项与风险项
6. **Supervisor Control Tick**  
   - 决定继续、纠偏、重跑、提前收敛

优势：

- token 按任务切片，避免整链重复上下文
- 异常隔离在子任务内，不污染全局流程
- 可在任意任务完成后触发提前 master 输出

---

## 9. Whiteboard 平衡模型（关键信息 + 外部内容）

建议 whiteboard 保留三类核心对象，并允许少量关键外部摘要：

1. `wb_control`：阶段状态、预算、重试计数、控制动作  
2. `wb_plan`：framework_doc 摘要、任务状态、检查点  
3. `wb_evidence`：
   - `critical_facts`（关键事实摘要）
   - `critical_quotes`（短引用）
   - `external_refs`（外部长内容索引）

规则：

- 白板保留“可支持阶段判断”的关键信息，不保留长原文
- 长文本与完整证据沉到外部存储（Warm/Cold/EvidenceStore）
- 关键摘要与外部索引的比例在开发中通过测试校准
- master 输出阶段按需拉取外部内容，不全量回灌

---

## 10. framework_doc 严格 Schema（required-only）

`framework_doc` 不使用 optional 字段，所有字段 required：

```json
{
  "schema_version": "1.0",
  "objective": "string",
  "scope": {
    "in_scope": ["string"],
    "out_scope": ["string"]
  },
  "hard_constraints": ["string"],
  "task_breakdown": [
    {
      "task_id": "string",
      "title": "string",
      "description": "string",
      "priority": "high|medium|low",
      "dependencies": ["task_id"],
      "definition_of_done": ["string"],
      "worker_assignment": {
        "owner_worker_id": "string",
        "candidate_worker_ids": ["string"]
      },
      "recommended_skills": ["string"],
      "recommended_tools": ["string"],
      "skill_selection_policy": "local_first|remote_allowed",
      "tool_selection_policy": "minimal_set_first"
    }
  ],
  "acceptance_criteria": ["string"],
  "checkpoint_plan": [
    {
      "checkpoint_id": "string",
      "checkpoint_name": "string",
      "enter_condition": "string",
      "exit_condition": "string"
    }
  ],
  "rollback_strategy": [
    {
      "trigger": "string",
      "rollback_to": "checkpoint_id",
      "action": "string"
    }
  ],
  "early_finish_rules": {
    "key_task_completion_rate_threshold": 0.8,
    "final_confidence_threshold": 0.78,
    "must_no_hard_constraint_violation": true
  }
}
```

说明：

- `recommended_skills` 仅表示技能说明书，不表示可执行工具
- `recommended_tools` 仅表示可调用工具
- 若 `skill_selection_policy=remote_allowed`，则可在 Skill Discovery Request 中使用 `skill_fetch` 在线拉取

---

## 11. 最高效率优先的执行准则

1. **先收敛后扩展**：能直达结论时不进入重型流程  
2. **先最小工具后补充**：默认无工具，必要再最小启用  
3. **先任务局部成功再全局汇总**：避免全局大失败  
4. **先可验证输出再润色**：先通过验收，再做表达优化  
5. **先提前结束判断再继续计算**：每阶段都允许“立即输出”

---

## 12. 效率审查结论与下版开发并入项

### 12.1 效率审查结论（认可并纳入）

1. tool gate 当前多轮决策可并行化，减少阶段等待  
2. PLANNING 需从轻量 `tasks[]` 升级到严格 `framework_doc`  
3. EXECUTION 建议“先分配再自治”，减少反复认领损耗  
4. EVALUATION 需按验收条款逐条校验，不仅多数投票
5. skill 与 tool 双通道分离后，能减少角色混乱与无效工具调用

### 12.2 下版开发并入清单

1. 实现 `final_confidence` 评分与 `promote_to_master` 触发  
2. 实现 required-only `framework_doc` 校验器  
3. 实现 Skill Discovery Request（`skill_summary/load/fetch`）与 Tool Decision 解耦  
4. 实现 whiteboard 平衡模型与外部引用一致性校验（id/version/checksum）  
5. 实现 Supervisor 控制动作幂等键与阶段锁  
6. 实现按 `acceptance_criteria` 的结构化评估器

---

## 13. 可测试校准标准

### 13.1 Supervisor 效率指标

- 异常检测延迟（从错误到纠偏动作）
- 单次错误恢复成功率
- 提前收敛触发率
- 无效重试占比

### 13.2 Token 与时延指标

- 单任务平均 token
- 全流程 token 降幅（对比单次大请求）
- P50/P95 响应时延

### 13.3 计划执行一致性指标

- framework_doc 约束遵循率
- 任务完成定义命中率
- 回滚后成功恢复率

### 13.4 输出质量指标

- 结论正确率
- 证据覆盖率
- 提前输出后返工率

---

## 14. 最终期望（优化后定稿）

1. 通过 Supervisor 实现“实时纠偏 + 动态中断 + 提前收敛”  
2. 通过 PLANNING 驱动拆分、推荐 skill/tool、分配 worker，形成稳定执行骨架  
3. 通过 EXECUTION 的局部自治，提升任务匹配度与执行速度  
4. 通过 Tool Decision Request 的最小集合策略，显著降低 token 与工具成本  
5. 通过 Whiteboard 平衡模型（关键信息 + 外部内容），降低噪声并提升系统稳定性  
6. 通过可测可回放标准，实现持续优化与工程化校准
