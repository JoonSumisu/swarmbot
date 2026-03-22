# Autonomous 全量设计文档 v2.3（设计稿）

## 0. 文档定位

- 本文档是 **设计文档**，不包含实现指令与代码改动。
- 目标：完整定义 Autonomous 体系的主编排能力。
- 范围：架构、配置、Bundle 范式、冲突治理、测试体系、落地方案、验收标准。

---

## 1. 现状与核心问题

### 1.1 现状

- 当前系统已有 Inference 主链路、Overthinking、Overaction、QMD/Hot/Warm 记忆体系。
- 已出现 Autonomous 初版接入，但职责边界与治理机制未完整收敛。
- 文档与代码存在阶段性偏差：Bundle 配置、Action 泛化、Provider 独立性仍不充分。

### 1.2 必须解决的问题

1. Autonomous 需要单独的语言模型 provider 配置。  
2. Action 不应“首批硬编码”，应是通用能力层，由 Engine 编排调用。  
3. Bundle 需要统一范式、生命周期与测试标准。  
4. Bundle 来源存在两路（用户创建 / 系统自生），需防重复、防冲突、防失控。  
5. 需要可观测、可审计、可回滚，不影响主会话响应能力。  

---

## 2. 设计目标与原则

### 2.1 目标

- 用 Autonomous 统一后台自治能力：监控、决策、执行、学习、治理。
- 保持主会话低延迟；后台自治与聊天链路硬隔离。
- 保留并复用现有记忆资产（Hot/Warm/QMD）与工具资产（web_search/file/tooling）。

### 2.2 原则

- **单一职责**：Monitor 只监控，Decision 只决策，Action 只执行。  
- **强治理**：所有 Bundle 可追踪、可审批、可限额、可撤销。  
- **配置优先**：Bundle、策略、阈值、provider 全部配置化。  
- **渐进落地**：设计允许分阶段启用，保证稳定。  
- **安全优先**：高风险动作默认需审批。  

---

## 3. 全局架构（目标态）

```text
Monitor Layer (Composite Bundle Runtime)
  -> MonitorQueueItem (变化 + 评判标准 + 处理范式 + 证据)
Decision Layer (AutonomousEngine, Streaming Planner)
  -> ActionQueueItem (能力调用计划 + 风险 + 优先级 + 预算)
Action Layer (Generic Worker Fabric)
  -> ActionResult / ProgressEvent / EvalResult
```

### 3.1 关键边界

- Inference Loop 不直接依赖 Autonomous 内部状态。
- Autonomous 通过事件与存储交互，不侵入用户会话白板。
- Action Worker 统一抽象，不绑定“首批 action”。
- Monitor 与 Action 都通过队列串接，Decision 以流水线方式持续消费与决策。
- 记忆整理与证据写入由 `core.memory_foundation` 默认 Bundle 承担，不再作为独立层抽象。

### 3.2 默认不可移除 Bundle（Default, Unremovable）

以下 Bundle 为系统保底能力，状态为 `active + locked`，不可删除，只能参数化调整：

1. `core.memory_foundation`  
   - 职责：记忆整理、拓展、沉淀为理论/经验/事实。  
   - 写入：Hot/Warm/QMD（含质量门禁）。  

2. `core.boot_optimizer`  
   - 职责：自动优化 boot/system prompt 相关资产。  
   - 来源：继承原 Overaction 的系统优化能力。  

3. `core.system_hygiene`  
   - 职责：基础健康检查、异常归档、必要提醒。  
   - 限制：高风险动作必须审批。  

4. `core.bundle_governor`  
   - 职责：持续检查 Bundle 重复、冲突、可合并性与结构合法性。  
   - 机制：每次 Bundle 新增/变更都触发一次治理扫描。  

说明：

- 这四个 Bundle 确保三层结构始终成立：监控输入、决策编排、执行反馈。
- 用户或自生 Bundle 不能覆盖/删除 core Bundle，只能在其外层扩展。
- `core.bundle_governor` 是入口守门器，负责把“新增 Bundle”纳入目录账本并做冲突治理。

---

## 4. Autonomous 专属 Provider 设计

### 4.1 目标

- Autonomous 使用独立 provider 组，不与对话主链路争抢同一模型配额与温度策略。

### 4.2 配置模型（设计）

在 `config.json` 增加 `autonomous.providers`，并支持角色路由：

```json
{
  "autonomous": {
    "enabled": true,
    "tick_seconds": 20,
    "providers": [
      {
        "name": "auto-primary",
        "base_url": "...",
        "api_key": "...",
        "model": "...",
        "temperature": 0.3,
        "max_tokens": 4096
      },
      {
        "name": "auto-backup",
        "base_url": "...",
        "api_key": "...",
        "model": "...",
        "temperature": 0.2,
        "max_tokens": 4096
      }
    ],
    "model_routing": {
      "decision": "auto-primary",
      "self_optimizer": "auto-primary",
      "summary": "auto-backup"
    }
  }
}
```

### 4.3 运行策略

- Autonomous Provider 失败时仅在 Autonomous 内部 failover，不影响主会话 provider。
- 设独立限流（RPS、并发、token budget）与独立熔断统计。

---

## 5. Action 统一范式（非“首批 action”）

### 5.1 定义

- Action 是通用“手脚层”，不是固定业务动作清单。
- Engine 输出 `DecisionPlan`，Action Fabric 根据能力注册表选择 Worker 执行。
- 任何 Bundle 都不能直连具体函数；必须经过 Decision 到 Action 的标准派发。
- Action 可引入 Swarm 能力：每个任务可动态指定 `1-10` 个 worker 和合适的架构模式。
- 当 Action 走 Swarm 模式时，TaskList 由 Decision 先行拆分，再下发给 Action 层分配 worker。

### 5.2 核心抽象

- `Capability`: 可执行能力描述（如 memory.compact / system.diagnose / web.research）。  
- `Worker`: 能力执行器，可同步或异步。  
- `DecisionPlan`: 目标、输入、风险级别、超时、重试、回调策略。  
- `ActionResult`: 标准结果（ok/error_code/output/artifacts/metrics）。  
- `SwarmProfile`: 执行编排参数（workers=1..10, architecture=auto/tree/mesh/pipeline, max_turns）。
- `TaskList`: 标准任务清单（原子任务、依赖、验收标准、优先级）。

### 5.3 编排方式

- Engine 不直接写死函数调用；只根据 Trigger + Policy + Bundle 提供的评判标准生成计划。
- Engine 负责生成 TaskList，并决定是否启用 Swarm。
- Action Fabric 执行时进行：
  - 能力匹配
  - 执行 Decision 下发的 SwarmProfile（不反向改写）
  - 按 TaskList 依赖顺序执行
  - worker 基于 TaskList 自选择角色
  - 资源预算检查
  - 风险审批检查
  - 进度事件上报

---

## 6. Bundle 范式（体系化 Monitor Layer）

### 6.0 Bundle 新定义（复合自动任务文件夹）

Bundle 不是“单条监控规则”，而是一个**复合任务包**，包含监测、执行、评判与脚本资产。  
每个 Bundle 是一个标准化目录，示意如下：

```text
bundle_x/
  bundle.yaml
  monitor/
    rules.yaml
    extractors.py
  action_templates/
    plan.md
    scripts/
  skills/
    SKILL.md
    resources/
  eval/
    rubric.yaml
    pass_fail_rules.yaml
  memory/
    patterns.md
```

Decision Layer 读取的不是“变化文本”，而是 `变化 + 标准 + 方法 + 证据 + 评估规则` 的完整包。

### 6.1 Bundle 规范结构

每个 Bundle 必须包含：

- `bundle_id`（全局唯一）
- `source`（`user` / `self_generated`）
- `namespace`（如 `system`, `project`, `domain.economy`）
- `objective`（监控目标）
- `trigger_rule`（事件触发/阈值触发/组合触发）
- `dedup_key`（去重键）
- `conflict_key`（互斥键）
- `policy`（优先级、风险、审批、预算）
- `lifecycle`（状态机配置）
- `action_template`（推荐能力，不是硬编码动作）
- `eval_rubric`（评判标准、通过阈值、重试条件）
- `skill_refs`（可加载技能与脚本资源）
- `observability`（日志、指标、告警渠道）

### 6.4 Bundle 总目录与索引账本

为满足全局治理，定义统一目录与索引：

```text
~/.swarmbot/bundles/
  core/
  user/
  self_generated/
  _registry/
    bundles_index.jsonl
    bundles_catalog.md
```

规则：

- 每次新增 Bundle 必须写入 `bundles_index.jsonl`（名称、功能、来源、dedup_key、conflict_key、状态）。
- `core.bundle_governor` 每轮扫描索引并产出治理结论（保留/合并/冻结/待审）。
- 索引账本是冲突仲裁唯一事实源，禁止“只落目录不入索引”。

### 6.2 生命周期状态机

`draft -> pending_review -> active -> paused -> retired`

异常分支：

- `rejected`（审批拒绝）
- `frozen`（冲突/失控保护触发）

### 6.3 Bundle 类型

- `sentinel`：长期系统监控  
- `long_running`：阶段性持续任务  
- `one_off`：一次性事件任务  
- `learning`：记忆驱动的自生实验任务（强约束）  

---

## 7. Bundle 双来源治理（用户创建 + 自生创建）

### 7.1 来源路径

1. **用户主动创建**：通过 swarmbot 指令/API 进入 `draft`。  
2. **系统自生创建**：由记忆整理/证据增量触发候选 Bundle，进入 `pending_review`。  
3. **核心默认创建**：系统启动时加载 `core.*`，直接 `active + locked`。  
4. **新增写账本**：任一来源新增时，先登记索引，再进入治理流转。  

### 7.2 去重策略

三层去重：

1. **规则去重**：`dedup_key` + `namespace` 完全一致直接合并。  
2. **语义去重**：目标文本 embedding 相似度超过阈值（如 0.88）进入合并流程。  
3. **时窗去重**：短时重复创建（如 10 分钟内）默认折叠为同一实例。  
4. **核心保护**：任何候选 Bundle 命中 `core.*` 冲突键时，只允许附加子任务，不允许替换核心定义。  

### 7.3 冲突策略

冲突判断依据：

- 同 `conflict_key`、方向相反、同时 `active`。

冲突解法：

1. `core.*` 最高优先级，不参与普通冲突淘汰。  
2. 用户来源优先于自生来源。  
3. 高风险 Bundle 互斥执行。  
4. 冲突无法自动解时进入 `pending_review`。  

### 7.4 失控防护（不可控创建）

- 全局配额：总 Bundle 上限、每命名空间上限、每小时新增上限。  
- 来源配额：`self_generated` 上限低于 `user`。  
- 风险闸门：高风险自生 Bundle 必须审批。  
- 冷却时间：同目标失败后进入冷却，不可立即重建。  
- 审计追踪：所有创建/合并/拒绝/冻结写治理日志。  
- 结构校验：Bundle 目录必须通过 schema + 资源完整性校验，否则拒绝激活。  

---

## 8. Decision Layer 设计（流水线队列）

### 8.1 输入

- Monitor 的 `MonitorQueueItem[]`
- 当前 Bundle 状态快照
- 资源预算（并发、token、IO）
- 治理策略（审批、禁行窗口、优先级）

### 8.2 输出

- `ActionQueueItem[]`（可并发）
- `DeferredPlan[]`（延期执行）
- `RejectedPlan[]`（拒绝并说明原因）

### 8.3 决策流程

1. 从 MonitorQueue 顺序读取（支持批次窗口）  
2. 结合 Bundle 内 `eval_rubric/action_template/skill_refs` 做计划生成  
3. 产出 TaskList（含验收标准与依赖图）  
4. 去重与冲突仲裁  
5. 风险分级（L0~L3）  
6. 预算分配与调度  
7. 写入 ActionQueue 并持续消费回执（流式决策）  

### 8.4 双队列模型

- `monitor_queue`：只接收 Bundle 输出的标准化监测包。  
- `action_queue`：只接收 Decision 生成的能力调用计划。  

该模型保证 Decision 可以“一边读取监测，一边决定行动”，形成稳定流水线。  
Action 执行结果、评估结果、进度轨迹都内嵌在 `ActionQueueItem` 生命周期中，不单独设 `result_queue`。

### 8.5 Action 回执闭环（你要求的二次决策）

每个 Action 完成后必须回传 `ActionResult + EvalResult` 到 Autonomous。  
Autonomous 对每条回执执行二次判定：

1. `re_evaluate`：需要重评估（上下文变化或评判标准未满足）。  
2. `retry`：允许重试（未达阈值且仍在预算内）。  
3. `complete`：任务完成并归档。  
4. `retire_task`：执行完成后删除一次性任务/临时 Bundle。  
5. `escalate`：升级到审批或人工确认。  

这样保证 Action 不是“一次执行即结束”，而是受 Autonomous 持续编排。

### 8.6 单一 Action 通道（含终端汇报）

以下事项都统一建模为 `action_type` 并进入 `action_queue`：

- `execute_task`（执行任务）
- `update_bundle`（修改 Bundle 状态/配置）
- `loop_optimize`（继续 loop 优化）
- `gateway_report`（向 Gateway/终端汇报）

即：修改状态、继续优化、最终汇报都属于 Action，不走额外控制通道。

---

## 9. Progress Update 与结果回传范式

### 9.1 进度事件标准

统一事件：

- `accepted`
- `running.stage_changed`
- `running.progress`
- `waiting.approval`
- `completed`
- `failed`
- `cancelled`

### 9.2 分段回传策略

- 长结果按块分段（固定上限）回传。  
- 同时生成摘要（结论、关键证据、后续建议）。  
- 可按 `task_id` 查询全量结果与阶段轨迹。  

---

## 10. 记忆与证据协同

### 10.1 写入原则

- 事件事实写 Warm。  
- 可复用经验写 QMD。  
- 证据型增量写 `~/.swarmbot/evidence/<domain>/incremental.jsonl`。  

### 10.2 自生 Bundle 来源

- 来自记忆整理的候选模式（反复出现的问题、长期风险、高价值重复任务）。  
- 候选必须经过治理器打分：价值、风险、重复度、资源成本。  

---

## 11. 测试体系（必须先有设计验收再实现）

### 11.1 Bundle 范式测试

- **Schema 测试**：字段完整性、默认值、兼容迁移。  
- **Bundle 目录测试**：脚本、skill、rubric、模板资源完整性。  
- **Lifecycle 测试**：状态机合法流转、异常流转拦截。  
- **Dedup 测试**：规则/语义/时窗三层去重正确率。  
- **Conflict 测试**：互斥策略与优先级策略正确性。  
- **Core Lock 测试**：默认不可移除 Bundle 不可被删除/替换。  
- **Registry 测试**：新增 Bundle 必须写索引，漏写立即失败。  

### 11.2 决策与执行测试

- **Decision Determinism**：同输入同策略输出稳定。  
- **Budget Test**：超预算下正确降级/排队。  
- **Risk Gate Test**：高风险计划进入审批而非直接执行。  
- **Progress Protocol Test**：阶段事件顺序与完整性。  
- **Pipeline Test**：monitor_queue/action_queue 顺序、吞吐与回压行为。  
- **Swarm Profile Test**：1-10 worker 与架构模式选择符合任务复杂度策略。  
- **TaskList Test**：Swarm 模式下先拆任务再执行，且依赖顺序正确。  
- **Role Selection Test**：worker 根据任务清单自选择角色且覆盖关键任务。  
- **Closed Loop Test**：Action 回执后可触发重评估/重试/完成/删除分支。  
- **Gateway Report Test**：终端汇报是否通过 `gateway_report` Action 统一下发。  

### 11.3 双来源治理测试

- 用户创建与自生创建同目标时正确合并。  
- 冲突任务自动仲裁失败时正确进入待审。  
- 自生任务超额时触发冻结与告警。  

### 11.4 性能与稳定性测试

- 监控 tick 压测（高 Bundle 数量下 CPU/内存上限）。  
- 长期运行稳定性（24h/72h soak）。  
- 故障注入（provider 超时、worker 崩溃、QMD 写失败）恢复能力。  

---

## 12. 落地策略（设计阶段）

### 12.1 阶段化启用

1. 先落地治理层与观测层  
2. 启用 Monitor + Decision，Action 先影子运行  
3. 小流量启用真实执行  
4. 全量启用并保留可回退开关  

### 12.2 回滚策略

- 任意阶段可一键切回安全配置。
- 切换不影响主会话与记忆完整性。

---

## 13. 配置草案（摘要）

```json
{
  "autonomous": {
    "enabled": true,
    "tick_seconds": 20,
    "max_concurrent_actions": 3,
    "default_locked_bundles": [
      "core.memory_foundation",
      "core.boot_optimizer",
      "core.system_hygiene",
      "core.bundle_governor"
    ],
    "providers": [],
    "model_routing": {},
    "queues": {
      "monitor_queue_size": 1000,
      "action_queue_size": 500,
      "decision_batch_window_ms": 800
    },
    "swarm_execution": {
      "worker_min": 1,
      "worker_max": 10,
      "architectures": ["auto", "tree", "mesh", "pipeline"],
      "require_tasklist_before_dispatch": true,
      "role_selection_mode": "self_select_by_tasklist"
    },
    "bundle_registry": {
      "root_dir": "~/.swarmbot/bundles",
      "index_file": "~/.swarmbot/bundles/_registry/bundles_index.jsonl",
      "catalog_file": "~/.swarmbot/bundles/_registry/bundles_catalog.md",
      "require_registry_write_on_create": true
    },
    "bundle_governance": {
      "max_total": 200,
      "max_self_generated": 40,
      "max_create_per_hour": 20,
      "semantic_dedup_threshold": 0.88,
      "require_approval_risk_level": "L2"
    },
    "monitor": {
      "bundle_sources": {
        "user_enabled": true,
        "self_generated_enabled": true
      }
    }
  }
}
```

---

## 14. 验收标准（设计完成定义）

- 已定义 Autonomous 独立 provider 与路由策略。  
- 已定义通用 Action Fabric，不依赖“首批 action”概念。  
- 已定义 Bundle 复合文件夹范式、状态机与治理机制。  
- 已定义默认不可移除 core Bundle 机制。  
- 已定义 Monitor→Decision→Action 双队列流水线模型。  
- 已定义 Bundle 总目录与索引账本强约束。  
- 已定义 Action 回执后二次决策闭环。  
- 已定义 Action 引入 Swarm（1-10 workers + 架构选择）机制。  
- 已定义 Swarm 模式下 TaskList 先行与 worker 自选角色约束。  
- 已定义双来源去重/冲突/防失控机制。  
- 已定义覆盖功能、治理、性能、稳定性的测试体系。  

---

## 15. 本版结论

- v2.3 将 Autonomous 定义为“可治理的自治操作系统”，而非“后台脚本集合”。  
- 先完成治理与测试范式，再进入实现，可显著降低冲突与失控风险。  
- 本文档可直接作为后续实现与评审基线。  
