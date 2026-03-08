# SwarmBot 编程规格说明书（v0.6 当前实现基线）

**版本**: v0.6（已落地基线）  
**用途**: 固化当前实现状态，作为后续 v0.6.x 优化/回归对照基准  
**时间**: 2026-03-08  

---

## 第一部分：当前实现状态（v0.6）

### 一、系统架构概览

#### 1.1 核心组件

SwarmBot 当前由以下核心组件构成：

1. **CLI** - 命令行入口（onboard/run/gateway/daemon/provider/channels）
2. **Daemon** - 后台守护与健康检查
3. **SwarmManager** - 多架构会话编排与 Phase 化流程
4. **InferenceLoop** - 8 步主推理循环（含自组织增强）
5. **OverthinkingLoop** - 记忆压缩归档（Hot/Warm → Cold）
6. **OveractionLoop** - 主动行动与系统自检循环（含手动触发）
7. **Memory System** - Whiteboard + Hot + Warm + Cold(QMD)
8. **Tool System** - ToolAdapter + ToolRegistry + Skill 体系
9. **Gateway** - 外部消息通道编排（Feishu 等）

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
    ├── memory/
    └── qmd/
```

---

### 二、核心流程（当前实现）

#### 2.1 SwarmManager.chat（Phase 1~4）

**Phase 1: Boot**
- 加载/恢复会话白板与 checkpoint 关键状态
- 注入 swarmboot 上下文

**Phase 2: Architecture Execution**
- 根据 architecture 路由执行（sequential/concurrent/mixture 等）
- 多 Agent 执行与工具调用

**Phase 3: Persist**
- 写入会话缓存、checkpoint、白板核心键

**Phase 4: Master**
- 加载 `masteragentboot.md`
- 加载并注入 `SOUL.md` 到 Master Prompt
- 由 Master 生成最终用户响应

---

#### 2.2 InferenceLoop（Step 1~8）

**Step 1: Metadata Initialization**
- 初始化 whiteboard 元信息（session_id/loop_id/input）

**Step 2: Problem Analysis（自组织）**
- 固定数量 Analyst 并行
- 每个分析 worker 可产出 `self_defined_role / required_tools / confidence`
- 聚合为 `problem_analysis` 与 `worker_roles`

**Step 3: Information Collection（自组织）**
- 固定数量 Collector 并行
- 工具门控由 Planner 多数投票
- 记录 `collection_tool_gate` 与 `collection_worker_roles`

**Step 4: Action Planning（任务化）**
- Planner 输出任务切分
- 当前任务结构统一为 `tasks: [{id, desc, required_skills}]`
- 不在该阶段硬分配具体 worker

**Step 5: Inference（任务认领 + 并行执行）**
- 建立 worker 池（数量来自 `swarm.max_agents`）
- 最多 3 轮任务认领（带冲突消解）
- 兜底强制分配未认领任务
- 记录 `task_assignments`
- 按角色+技能并行执行任务

**Step 6: Evaluation（自组织）**
- 固定数量 Evaluator 并行投票
- 支持 evaluator 自定义评估角色并记录 `evaluation_roles`
- FAIL 时触发 Re-Planning

**Step 7: Output Translation**
- Master 汇总 `inference_conclusions`
- 可选工具门控（translation_tool_gate）

**Step 8: Organization & Persistence**
- 抽取热记忆增量与温记忆事实
- 持久化组织结果

---

### 三、技能系统（当前实现）

#### 3.1 SkillRegistry（统一技能源）

已落地统一技能注册器：
- `BASE_SKILLS`：基础共享能力
- `ROLE_SKILLS`：预定义角色技能
- `DOMAIN_SKILLS`：动态域推断技能
- `register_role(role, skills)`：运行时扩展
- `get_skills(role)`：角色技能集合
- `get_skills_for_task(role, task_desc, required_skills)`：任务增强技能

#### 3.2 集成状态

- InferenceLoop `_create_worker` 已接入 SkillRegistry
- SwarmSession `_apply_skills` 已接入 SkillRegistry
- ToolRegistry 执行时支持参数过滤与上下文注入

---

### 四、Overaction / Overthinking（当前实现）

#### 4.1 OveractionLoop

已实现：
1. QMD refine
2. Warm memory cleanup
3. Self-optimization todo 注入
4. Proactive checks：
   - 交互超时检查
   - Todo 积压检查
   - 系统资源检查（内存/磁盘）
   - 自我诊断摘要
   - 洞察分享写入 Hot Memory
5. 手动 `trigger(reason)` 触发

#### 4.2 OverthinkingLoop

已实现：
- 定时读取 Hot/Warm
- 结构化压缩并写入 Cold(QMD)
- 失败兜底日志

---

### 五、配置系统（当前实现）

#### 5.1 config.json 关键节

```json
{
  "providers": [],
  "swarm": {},
  "overthinking": {},
  "overaction": {
    "enabled": true,
    "interval_minutes": 60,
    "check_interaction": true,
    "check_tasks": true,
    "check_system": true,
    "interaction_timeout_hours": 4
  },
  "tools": {},
  "channels": {},
  "daemon": {}
}
```

#### 5.2 Boot 文件状态

| 文件 | 位置 | 状态 |
|------|------|------|
| swarmboot.md | `~/.swarmbot/boot/` | 已启用 proactive-action-first 人设 |
| masteragentboot.md | `~/.swarmbot/boot/` | 已启用 |
| SOUL.md | `~/.swarmbot/boot/` | Phase 4 已实际注入 |

---

### 六、功能对照（v0.6 基线）

#### 6.1 已实现

- SOUL.md Phase 4 真实加载与注入
- SkillRegistry 统一技能系统
- Inference 自组织角色与任务认领流程
- Overaction 独立配置节与主动检查
- Overaction 手动 trigger
- bootstrap 安装增强（含可选回归依赖）
- README/README_EN 回归指引增强

#### 6.2 现存问题（待 v0.6.x）

- 任务认领与冲突协商仍是轻量多数决，尚未形成显式协商协议
- 回归脚本对“模型服务不可用”缺少 fail-fast 诊断分层
- Overthinking 外部事件检查与 Overaction 事件触发链仍需体系化增强
- OpenClaw 风格 BOOT/IDENTITY/USER/HEARTBEAT 全模板联动尚未完整落地

---

### 七、基线结论

当前 v0.6 已完成从“固定角色 + 静态工具”到“角色自组织 + 任务认领 + 统一技能 + 主动检查”的核心跃迁，可作为后续 v0.6.5/v0.6.x 的稳定基线。  
后续优化应重点面向：**工具执行能力对齐、调度能力对齐、外部事件驱动对齐、回归稳定性对齐**。
