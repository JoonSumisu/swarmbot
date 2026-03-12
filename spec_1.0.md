# SwarmBot 编程规格说明书（v1.0 正式基线）

**版本**: v1.0.0  
**用途**: 固化 v1.0 当前实现状态，作为后续 v1.0.x 优化与回归基准  
**时间**: 2026-03-12  

---

## 第一部分：当前实现状态（v1.0）

### 一、系统架构概览

#### 1.1 核心组件

SwarmBot v1.0 由以下核心组件组成：

1. **CLI** - 统一入口（onboard/run/gateway/daemon/provider/channels）
2. **Daemon** - 进程托管与健康恢复
3. **GatewayServer** - 消息总线与外部通道（Feishu）调度
4. **InferenceLoop** - 8 步推理主循环（路由、分析、收集、规划、执行、评估、转译、归档）
5. **AutonomousEngine** - 自治编排引擎（MonitorQueue + ActionQueue 双线）
6. **OverthinkingLoop** - 记忆压缩归档（Hot/Warm -> Cold）
7. **OveractionLoop** - 主动行动、系统诊断与优化
8. **SwarmManager** - 多 Agent 架构执行器（swarms 集成）
9. **Memory System** - Whiteboard + Hot + Warm + Cold(QMD) + EvidenceStore
10. **Tool/Skill System** - ToolRegistry + SkillRegistry + Boot 体系

---

#### 1.2 运行目录（默认）

```text
~/.swarmbot/
├── config.json
├── boot/
│   ├── swarmboot.md
│   ├── masteragentboot.md
│   └── SOUL.md
├── logs/
└── workspace/
    ├── hot_memory.md
    ├── autonomous_diagnostics.jsonl
    ├── autonomous_gateway_reports.jsonl
    ├── memory/
    └── qmd/
```

---

### 二、核心流程（当前实现）

#### 2.1 Gateway 流程

1. 启动时读取配置并初始化消息总线与通道
2. `autonomous.enabled=true` 时启动 `AutonomousEngine`
3. 持续消费 InboundMessage，按 `preview_route` 决定直答或后台子任务
4. 后台子任务支持进度播报、摘要回传、分段结果回传
5. 新增 `autonomous_gateway_reports.jsonl` 轮询，把自治回执统一转发到终端通道

---

#### 2.2 InferenceLoop（Step 1~8）

**Step 1: Metadata Initialization**
- 初始化 whiteboard 元信息（session/loop/input）

**Step 2: Problem Analysis**
- 并行 analyst 分析并生成 `problem_analysis`
- 产出自定义角色与工具建议

**Step 3: Information Collection**
- 先进行无工具收集，再经工具门控决定是否工具补采
- 对法律/商业/政策等证据型任务可强制证据补采

**Step 4: Action Planning**
- planner 输出 `tasks[{id,desc,required_skills}]`
- 任务层不做固定 worker 绑定

**Step 5: Inference**
- worker 先认领任务（多轮协商）后并行执行
- 产出 `task_assignments` 与 `inference_conclusions`

**Step 6: Evaluation**
- evaluator 并行投票，失败可触发 re-planning

**Step 7: Translation**
- master 汇总输出，带工具门控与硬约束校准

**Step 8: Organization**
- 写入 Hot/Warm，归档总结并更新证据增量

---

#### 2.3 AutonomousEngine（v1.0 新基线）

v1.0 的 Autonomous 采用“**两条线 + 统一 Action 通道**”：

1. **MonitorQueue**：接收 bundle 监测事件
2. **ActionQueue**：承载决策计划、执行状态、执行结果、评估结果、二次决策反馈

关键实现点：

- `TaskList` 由 Decision 生成
- 是否启用 swarms 由 Decision 决定
- Action 统一类型：
  - `execute_task`
  - `update_bundle`
  - `loop_optimize`
  - `gateway_report`
- 无独立 ResultQueue，结果内嵌于 ActionQueueItem 生命周期

---

### 三、Autonomous 默认 Core Bundle（当前实现）

默认激活并锁定：

1. `core.memory_foundation`
2. `core.boot_optimizer`
3. `core.system_hygiene`
4. `core.bundle_governor`

实现状态：

- memory_foundation -> OverthinkingLoop 记忆整理
- boot_optimizer -> OveractionLoop 优化循环触发
- system_hygiene -> 资源阈值诊断触发
- bundle_governor -> registry 索引重复/冲突扫描

---

### 四、配置系统（v1.0）

#### 4.1 autonomous 配置关键节

```json
{
  "autonomous": {
    "enabled": true,
    "tick_seconds": 30,
    "max_concurrent_actions": 3,
    "providers": [],
    "model_routing": {},
    "default_locked_bundles": [
      "core.memory_foundation",
      "core.boot_optimizer",
      "core.system_hygiene",
      "core.bundle_governor"
    ],
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
    }
  }
}
```

---

### 五、安装与依赖（v1.0）

#### 5.1 bootstrap 脚本能力

`scripts/bootstrap.py` 当前支持：

- 模式：`auto/pipx/user/venv`
- 选项：`--editable`、`--with-eval-deps`、`--skip-check`
- 自动 Python 版本检查（>=3.10）
- 安装后模块可用性检查：
  - `swarmbot`
  - `swarmbot.gateway.server`
  - `swarmbot.loops.inference`
  - `lark_oapi`
  - `swarms`

#### 5.2 平台脚本

- Linux/macOS：`scripts/bootstrap.sh`
- Windows：`scripts/bootstrap.ps1`（支持参数透传）

---

### 六、Gateway + Feishu 可用性要求

#### 6.1 配置要求

必须在 `channels.feishu` 配置：

- `app_id`
- `app_secret`
- `encrypt_key`（可空）
- `verification_token`（可空）

#### 6.2 启动要求

```bash
./.venv/bin/swarmbot gateway
```

可用性判定：

- 网关进程启动成功
- Feishu Channel 初始化成功
- WebSocket 长连建立成功
- 消息可进可出

---

### 七、功能对照（v1.0 基线）

#### 7.1 已实现（当前版本）

- 两线自治模型（MonitorQueue + ActionQueue）
- Action 统一通道（执行、状态更新、loop 优化、终端汇报）
- TaskList 由 Decision 生成并驱动 swarms 选择
- gateway_report 回执落地与网关轮询转发
- Autonomous 配置节完整接入 config_manager
- Inference 路由增强、证据增量沉淀
- 安装脚本增加安装后可用性检查
- README/README_EN 升级到 v1.0 安装与验证说明

#### 7.2 当前边界

- InferenceLoop 的 Supervisor 化调度尚未实现
- SwarmLoop 的“阶段可中断/重跑”能力尚未实现
- Token 成本控制仍以 profile/context_limit 为主，尚未形成分层增量协议

---

### 八、测试与验收标准（v1.0）

#### 8.1 语法与导入

- `python -m py_compile` 覆盖核心模块无错误
- bootstrap 安装后可通过 post-install check

#### 8.2 路由与异步

- `scripts/eval_analysis_routing.py` 路由准确率达标
- `scripts/eval_subtask_async.py` 并发子任务不阻塞主请求

#### 8.3 推理回归

- `scripts/eval_inference_benchmark.py` 核心指标通过（routing/legal/business/think）

#### 8.4 网关联调

- gateway 可启动，Feishu 通道可建立连接
- Autonomous 可启动并产生诊断日志
- gateway_report 可被网关轮询并转发

---

### 九、v1.0 结论

v1.0 已完成从“Loop 级推理系统”向“**自治编排 + 双线决策执行 + 统一 Action 通道**”的升级，具备工程化持续演进基础。  
后续 v1.0.x 优化重点应聚焦：**Inference Supervisor 化、分层增量请求协议、白板降噪与强约束测试校准**。
