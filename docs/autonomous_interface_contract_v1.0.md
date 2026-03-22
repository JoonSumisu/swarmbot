# Autonomous 接口契约清单 v1.2（正式开发文档）

## 1. 文档目的

- 本文档用于指导 Autonomous 后续开发，定义可落地的接口契约与状态机约束。
- 以当前代码可复用能力为基线，清除非必要叙述，仅保留开发必需信息。
- 本文档与 `autonomous_architecture_full_v2.0.md`（v2.2 设计稿）配套使用。

---

## 2. 范围与边界

- 范围：
  - Monitor/Decision/Action 三层交互契约
  - Bundle 目录与注册账本契约
  - Action层 Swarms 组件契约（TaskList + 自选角色）
  - Action 回执闭环契约
- 边界：
  - 不定义具体业务 Bundle 内容
  - 不定义具体模型 prompt 文案
  - 不包含实现代码
  - Swarms 仅属于 Action 层执行组件；是否启用由 Decision 层决定

---

## 3. 核心可行性结论（AGI 式自律协同）

在精炼结构下，系统可形成“类 AGI 的自律协同最小闭环”：

1. **感知**：Bundle 复合监测输出结构化监测包。  
2. **决策**：AutonomousEngine 基于规则、预算、风险持续规划，并决定是否启用 swarms。  
3. **行动**：Action Fabric 默认单Agent执行，必要时调用 swarms 组件做多Agent协同。  
4. **反思**：ActionResult + EvalResult 回流，触发重评估/重试/完成/退役。  
5. **记忆**：`core.memory_foundation` 进行经验沉淀与模式反馈。  

该闭环具备泛化、自稳态、可治理三要素，满足“自律协同”的工程可行性。

---

## 4. 默认 Core Bundle 契约（不可移除）

以下条目必须存在于 `default_locked_bundles`，状态固定 `active + locked`：

- `core.memory_foundation`
- `core.boot_optimizer`
- `core.system_hygiene`
- `core.bundle_governor`

约束：

- 不可删除，不可替换，仅允许参数更新。
- 任意新增 Bundle 若与 `core.*` 冲突，仅允许附加子任务，不允许覆盖定义。

---

## 5. Bundle 文件系统契约

## 5.1 目录契约

```text
~/.swarmbot/bundles/
  core/
  user/
  self_generated/
  _registry/
    bundles_index.jsonl
    bundles_catalog.md
```

## 5.2 Bundle 包契约

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

## 5.3 注册账本契约

`bundles_index.jsonl` 每行对象必须包含：

- `bundle_id` string
- `name` string
- `source` enum(`core`,`user`,`self_generated`)
- `namespace` string
- `objective` string
- `dedup_key` string
- `conflict_key` string
- `status` enum(`draft`,`pending_review`,`active`,`paused`,`retired`,`rejected`,`frozen`)
- `version` string
- `created_at` int
- `updated_at` int

强约束：

- 新增 Bundle 流程必须“先写 index，再进入治理流转”。
- 漏写 index 视为非法创建，必须失败。

---

## 6. 队列消息契约（两条线）

总原则：

- 仅保留两条队列：`MonitorQueue` 与 `ActionQueue`。
- 不设独立 `ResultQueue`；执行结果属于 `ActionQueueItem` 生命周期内字段。
- 无论是编程执行、Bundle 状态变更、继续 loop 优化、还是向 Gateway 汇报，统一建模为 Action。

## 6.1 MonitorQueueItem

```json
{
  "event_id": "string",
  "bundle_id": "string",
  "source": "core|user|self_generated",
  "kind": "string",
  "severity": "low|medium|high|critical",
  "detected_at": 0,
  "evidence": {},
  "eval_rubric_ref": "string",
  "action_template_ref": "string",
  "skill_refs": [],
  "policy": {},
  "idempotency_key": "string"
}
```

## 6.2 ActionQueueItem

```json
{
  "plan_id": "string",
  "event_id": "string",
  "bundle_id": "string",
  "task_list": [],
  "swarm_profile": {},
  "risk_level": "L0|L1|L2|L3",
  "budget": {},
  "deadline_ts": 0,
  "retry_policy": {},
  "approval_required": false,
  "idempotency_key": "string",
  "action_type": "execute_task|update_bundle|loop_optimize|gateway_report",
  "state": "planned|running|succeeded|failed|cancelled",
  "progress_events": [],
  "action_result": {},
  "eval_result": {},
  "decision_feedback": {}
}
```

字段说明（关键）：

- `action_type`：统一动作类型，覆盖执行、配置更新、优化循环、终端汇报。
- `state/progress_events`：Action 的过程状态与进度轨迹。
- `action_result/eval_result`：执行结果与评估结果，作为同一 Action 项的回执。
- `decision_feedback`：Decision 对本 Action 的二次判定结果。

## 6.3 Action 回执内嵌契约

```json
{
  "plan_id": "string",
  "state": "succeeded|failed|cancelled",
  "action_result": {},
  "eval_result": {},
  "decision_feedback": {
    "next_action": "re_evaluate|retry|complete|retire_task|escalate",
    "reason": "string",
    "retry_count": 0,
    "new_plan_required": false,
    "archive_required": true
  },
  "finished_at": 0,
  "reported_to_gateway": false
}
```

---

## 7. Action层 Swarms 组件契约（重点）

## 7.0 执行模式契约

Action 层执行模式：

- `single_agent`：默认模式，低复杂度任务直接执行。  
- `swarms`：增强模式，调用 swarms 组件进行多Agent编排。  

约束：

- 是否进入 `swarms` 由 Decision 依据复杂度、预算、时效决策。
- Decision 先完成 TaskList 拆分，再决定 `single_agent` 或 `swarms`。
- Monitor 不依赖 swarms，只输出监测包。

## 7.1 TaskList 契约（Decision 强制生成）

`task_list` 每项必须包含：

- `task_id` string
- `title` string
- `acceptance` string
- `priority` enum(`high`,`medium`,`low`)
- `depends_on` string[]
- `required_capability` string
- `status` enum(`pending`,`running`,`done`,`failed`)

约束：

- TaskList 由 Decision 层生成，禁止 Action 层反向定义任务清单。
- Swarms 模式下必须先生成 TaskList，禁止直接派发执行。
- 必须包含可验收标准 `acceptance`，否则不得进入执行。

## 7.2 SwarmProfile 契约

```json
{
  "workers": 1,
  "architecture": "auto|tree|mesh|pipeline",
  "max_turns": 16,
  "role_selection_mode": "self_select_by_tasklist"
}
```

约束：

- `workers` 范围 `[1,10]`。
- `role_selection_mode=self_select_by_tasklist` 为强制项。
- worker 必须依据 TaskList 的任务类型自选择角色，并在计划内声明角色覆盖关系。

实现基线：

- swarmbot 已包含 `swarms` 依赖，可作为 Action 层多Agent执行组件接入。
- 该组件定位是 Action 执行加速器，不改变 Monitor/Decision 的职责边界。

---

## 8. Decision 二次闭环契约（Action内闭环）

Autonomous 必须消费 `ActionQueueItem.action_result + eval_result` 并回写 `decision_feedback`：

```json
{
  "plan_id": "string",
  "next_action": "re_evaluate|retry|complete|retire_task|escalate",
  "reason": "string",
  "retry_count": 0,
  "new_plan_required": false,
  "archive_required": true
}
```

行为定义：

- `re_evaluate`：上下文变化或评判标准未满足，重新规划。  
- `retry`：在预算内重试当前计划。  
- `complete`：完成并归档。  
- `retire_task`：完成后退役一次性任务或临时 Bundle。  
- `escalate`：升级审批/人工确认。  

回写约束：

- `decision_feedback` 必须写回同一 `plan_id` 的 `ActionQueueItem`。
- 若 `next_action` 不是 `complete`，Decision 必须继续生成下一条 `ActionQueueItem`。
- `gateway_report` 必须作为标准 Action 执行并更新 `reported_to_gateway=true`。

---

## 9. 生命周期与治理契约

## 9.1 Bundle 生命周期

`draft -> pending_review -> active -> paused -> retired`  
异常：`rejected`、`frozen`

## 9.2 去重与冲突

- 去重：规则去重 + 语义去重 + 时窗去重。
- 冲突：同 `conflict_key` 且策略互斥时，按 `core > user > self_generated` 仲裁。
- `core.bundle_governor` 周期执行治理扫描并输出操作建议：`keep|merge|freeze|review`。

## 9.3 失控防护

- 总量上限、来源上限、新增速率上限、失败冷却、审批门槛。
- 触发保护时状态改为 `frozen` 并写审计日志。

---

## 10. 配置契约（与现有代码兼容扩展）

`autonomous` 配置最小契约：

```json
{
  "autonomous": {
    "enabled": true,
    "tick_seconds": 20,
    "max_concurrent_actions": 3,
    "providers": [],
    "model_routing": {},
    "default_locked_bundles": [],
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
    }
  }
}
```

---

## 11. 与当前代码的映射基线

- Gateway 消息与子任务轨道：`swarmbot/gateway/server.py`
- Autonomous 基础数据结构：`swarmbot/autonomous/engine.py`
- 现有路由与执行主链：`swarmbot/loops/inference.py`
- 现有后台能力来源：`swarmbot/loops/overthinking.py`、`swarmbot/loops/overaction.py`
- 配置基线：`swarmbot/config_manager.py`

用途：

- 作为实现时的兼容参照，避免接口漂移。

---

## 12. 开发验收清单（接口层）

- Bundle 新增是否强制写入 registry。  
- 是否仅保留 MonitorQueue 与 ActionQueue 两条线。  
- Action 结果是否内嵌在 ActionQueueItem（无独立 ResultQueue）。  
- TaskList 是否由 Decision 生成并驱动执行模式选择。  
- worker 是否基于 TaskList 自选角色并可追踪。  
- Action 回执是否触发同 plan_id 的二次决策回写。  
- 终端汇报是否通过 `gateway_report` Action 统一下发。  
- core Bundle 是否不可移除且不可被替换。  

---

## 13. 版本说明

- v1.2：清理历史表述后的正式开发基线，采用两队列模型与决策归一。  
