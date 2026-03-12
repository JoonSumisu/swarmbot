# InferenceLoop / SwarmLoop 当前架构与优化方向（v1.0 设计文档）

## 1. 文档目的

- 说明当前 InferenceLoop/SwarmLoop 的真实执行结构
- 在不改代码前提下，给出后续优化方向与可测试目标
- 对齐“更动态、低 token、强稳态、可校准”的最终演进目标

---

## 2. 当前架构现状（as-is）

## 2.1 执行主链

当前 InferenceLoop 是固定 8 步：

1. Metadata 初始化  
2. Analysis（并行 analyst）  
3. Collection（先无工具，再按门控工具补采）  
4. Planning（生成 tasks）  
5. Inference（任务认领 + 并行执行）  
6. Evaluation（并行 evaluator 投票）  
7. Translation（master 汇总）  
8. Organization（Hot/Warm 持久化）  

特征：

- 有门控（tool gate / route gate / profile gate）
- 有重试（evaluation fail -> replanning）
- 有任务认领机制（claim rounds + fallback assign）
- 有白板作为主上下文容器

## 2.2 Whiteboard 当前承载

Whiteboard 当前保存了大量阶段数据：

- `problem_analysis`
- `information_gathering`
- `action_plan`
- `task_assignments`
- `inference_conclusions`
- `evaluation_report`
- `final_response`
- 多个 gate 决策记录

问题：

- 承载内容偏宽，噪声与重复字段较多
- 缺少显式“阶段控制平面”（谁可中断/回滚/重跑）

## 2.3 SwarmLoop 当前形态

- 任务由 planner 输出 `tasks[]`
- worker 进行多轮认领（3 轮）
- 按角色 + skills 并发执行
- evaluator 决定是否通过

问题：

- 计划更偏任务列表，不是可执行“框架文档”
- 缺少强约束计划执行协议（plan contract）
- 缺少 supervisor 统一调度层

---

## 3. 你提出的目标（to-be）

你提出的六个方向可归纳为：

1. **Supervisor 控制平面**：监控 whiteboard 与全流程，可中断、重跑、结束任意阶段  
2. **多次请求降 token**：先任务检查，再工具决策，再执行，分层增量请求  
3. **Whiteboard 降噪**：只保留关键状态与证据指针  
4. **先细分再自治**：先做细粒度任务分配，再由执行体局部决策  
5. **Planner 升级为框架文档生成器**：计划不止 tasks，要有目标、约束、验收、回退、检查点  
6. **动态稳态 + 可测试校准**：全过程可测、可回放、可对齐标准

---

## 4. v1.0.x 优化架构提案（不改代码版）

## 4.1 新增 Supervisor 层（控制面）

在逻辑上引入 `Supervisor`，职责：

- 维护全局状态机：`INIT -> ANALYSIS -> COLLECTION -> PLANNING -> EXECUTION -> EVALUATION -> TRANSLATION -> ORGANIZATION -> DONE`
- 提供控制动作：
  - `interrupt(stage)`
  - `rerun(stage, reason)`
  - `terminate(stage, reason)`
  - `resume(from_stage)`
- 持续监控白板健康：
  - token 预算
  - 缺证据风险
  - 任务漂移风险

输出：

- `supervisor_decision_log`
- `stage_transition_log`
- `safety_guard_log`

## 4.2 分层请求协议（Token 控制核心）

将一次大请求拆成“多次小请求”：

1. **Check Request**：确认任务边界与约束  
2. **Tool Decision Request**：最小工具集合决策  
3. **Execute Request**：仅携带该任务所需最小上下文  
4. **Evaluate Request**：仅评估必要字段  

要求：

- 每次请求携带严格上下文预算（context_budget）
- 上下文优先引用“证据指针”而非大段原文

## 4.3 Whiteboard 最小化模型

建议将 whiteboard 拆成三层：

- `wb_control`：阶段、状态、中断点、预算
- `wb_plan`：结构化计划文档摘要与检查点
- `wb_evidence_index`：证据索引、引用、可信度

原则：

- 不保存长文本原文，只保存摘要和引用键
- 长内容落到外部存储（Warm/Cold/EvidenceStore）

## 4.4 Planner 产物升级为 FrameworkDoc

将 planner 输出从 `tasks[]` 升级为 `framework_doc`：

- `objective`
- `scope/in_scope/out_scope`
- `hard_constraints`
- `task_breakdown`（细分任务）
- `acceptance_criteria`
- `risk_register`
- `rollback_strategy`
- `checkpoint_plan`
- `evidence_requirements`

执行要求：

- 任何阶段动作必须引用 `framework_doc` 的目标与约束
- evaluator 按 `acceptance_criteria` 判定

## 4.5 细分任务先分配，再自治决策

执行策略：

1. Decision 先做任务原子化拆分（含依赖 DAG）
2. 分配初始 owner（或候选组）
3. worker 在 owner 约束内进行微决策（工具选择、步骤顺序）
4. supervisor 审核偏差并可回滚到检查点

---

## 5. 可测试标准（你要的“可校准”）

## 5.1 控制面测试

- Interrupt Test：任意阶段中断后可恢复
- Rerun Test：指定阶段重跑不会污染无关阶段状态
- Terminate Test：提前终止后资源正确释放

## 5.2 Token 成本测试

- Single-shot vs Multi-shot token 对比
- 平均每阶段 token 占用上限
- 超预算降级策略是否生效

## 5.3 白板质量测试

- whiteboard 关键字段完整率
- 噪声字段比例
- 证据索引命中率

## 5.4 计划执行一致性测试

- 实际执行是否偏离 framework_doc
- 验收条款覆盖率
- 失败后回滚与重规划成功率

---

## 6. 最终期望（完善版）

结合你的目标，最终期望可明确为：

1. **动态可控**：任何阶段可被 Supervisor 调整，不再“一条路跑到底”  
2. **低成本稳态**：通过多次小请求把上下文压小，降低 token 与失败代价  
3. **信息高信噪比**：whiteboard 仅存关键状态与索引，减少噪声与漂移  
4. **执行可追责**：任务拆分、分配、执行、评估都可回放审计  
5. **规划可执行**：planner 输出工程化 framework_doc，而非简化任务清单  
6. **质量可校准**：有明确指标与回归测试，能持续优化而不失控

---

## 7. 建议落地顺序（下一阶段）

1. 先引入 Supervisor 状态机与日志，不改业务逻辑  
2. 再做请求分层协议与 context_budget  
3. 同步做 whiteboard 最小化改造  
4. 最后升级 planner 输出为 framework_doc 并接 evaluator 验收

该顺序可在稳定性与收益之间取得最佳平衡。
