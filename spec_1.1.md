# SwarmBot 编程规格说明书（v1.1 当前实现基线）

**版本**: v1.1.0  
**用途**: 固化 v1.1 实装状态，作为后续 v1.1.x 回归与优化基线  
**时间**: 2026-03-12  

---

## 一、v1.1 核心升级

### 1.1 推理编排升级

v1.1 在 InferenceLoop 中完成以下关键能力：

1. **framework_doc 严格落地**
   - PLANNING 阶段输出 required-only framework_doc
   - 增加字段完整性校验与 fallback 兜底
2. **Skill / Tool 双通道解耦**
   - Skill Discovery：`skill_summary / skill_load / skill_fetch`
   - Tool Decision：仅负责最小工具集合
3. **Supervisor 控制增强**
   - 控制动作幂等键
   - 阶段锁（stage_lock）
   - 提前收敛评分触发 `promote_to_master`
4. **Whiteboard 平衡模型**
   - 保留关键信息（control/plan/evidence）
   - 长文本沉到外部存储（Warm/Cold/EvidenceStore）

---

## 二、关键数据结构

### 2.1 Whiteboard（L1）新增结构

```json
{
  "wb_control": {
    "stage": "INIT|ANALYSIS|COLLECTION|PLANNING|EXECUTION|EVALUATION|MASTER_OUTPUT|ORGANIZATION|DONE",
    "stage_lock": "string",
    "retry_count": 0,
    "control_actions": []
  },
  "wb_plan": {
    "framework_doc": {},
    "task_status": {},
    "checkpoints": []
  },
  "wb_evidence": {
    "critical_facts": [],
    "critical_quotes": [],
    "external_refs": []
  }
}
```

### 2.2 framework_doc（required-only）

必填字段：

- `schema_version`
- `objective`
- `scope`
- `hard_constraints`
- `task_breakdown`
- `acceptance_criteria`
- `checkpoint_plan`
- `rollback_strategy`
- `early_finish_rules`

task 级必填：

- `task_id`
- `title`
- `description`
- `priority`
- `dependencies`
- `definition_of_done`
- `worker_assignment`
- `recommended_skills`
- `recommended_tools`
- `skill_selection_policy`
- `tool_selection_policy`

---

## 三、执行链路（v1.1）

1. **ANALYSIS**：问题分析与路由  
2. **COLLECTION**：信息收集与证据补采  
3. **PLANNING**：生成 framework_doc 并校验  
4. **SKILL DISCOVERY**：加载/拉取技能说明书  
5. **TOOL DECISION**：按任务计算最小工具集合  
6. **EXECUTION**：先任务分配，再 worker 局部自治（功能优先级 + 角色）  
7. **EVALUATION**：按 acceptance_criteria 结构化评估  
8. **MASTER_OUTPUT**：汇总输出  
9. **ORGANIZATION**：Hot/Warm 组织化写入

---

## 四、提前收敛评分

定义：

- `key_task_completion_rate`
- `confidence_score`
- `consistency_score`
- `evidence_coverage`

综合分：

`final_confidence = 0.5*confidence_score + 0.2*consistency_score + 0.2*evidence_coverage + 0.1*key_task_completion_rate`

触发条件：

- `key_task_completion_rate >= 0.80`
- `final_confidence >= 0.78`
- `hard_constraints` 无违反

满足后 Supervisor 可触发 `promote_to_master`。

---

## 五、Tool 与 Skill 边界（v1.1 强约束）

### 5.1 Tool

Tool 是可执行能力，例如：

- `web_search`
- `browser_read`
- `file_read`
- `python_exec`
- `shell_exec`

### 5.2 Skill

Skill 是任务处理说明书（SKILL.md），用于指导策略，不直接执行系统动作。

### 5.3 规则

- Skill 不等于 Tool
- Tool Decision 不能把 Skill 当工具调用
- Skill Discovery 与 Tool Decision 分开计数、分开重试

---

## 六、测试与验证（本次落地）

### 6.1 分段验证

1. 语法编译验证：
   - `python -m py_compile swarmbot/loops/inference.py swarmbot/memory/whiteboard.py`
2. 单次 smoke：
   - 运行 InferenceLoop 并检查 whiteboard 中 `framework_doc_validation/skill_discovery/supervisor_metrics/wb_evidence`

### 6.2 整体回归

本地模型：`unsloth/qwen3-coder-next`

- `scripts/eval_inference_benchmark.py --quick`
- `scripts/eval_analysis_routing.py`
- `scripts/eval_subtask_async.py`
- `timeout 20 python -m swarmbot.gateway.server`（网关与飞书通道烟测）

---

## 七、依赖与版本

- 包版本：`1.1.0`
- README/README_EN 已同步 v1.1 说明
- Gateway 启动版本日志已更新为 `v1.1.0`

---

## 八、v1.1 基线结论

v1.1 已将“文档方案”落地为“可执行编排能力”：  
**framework_doc 严格化、Skill/Tool 解耦、Supervisor 幂等控制、Whiteboard 平衡模型** 已进入主执行链。  
后续 v1.1.x 建议重点：并行化 Tool Gate 投票、强化 Skill 远程检索策略、完善 acceptance_criteria 评估可解释性。
