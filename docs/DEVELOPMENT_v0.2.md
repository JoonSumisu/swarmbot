# Swarmbot v0.2 开发文档

## 1. 系统概述
Swarmbot 是一个本地优先的多 Agent 集群智能系统，v0.2 版本引入了 **双 Boot 架构**、**动态角色生成** 和 **深度记忆闭环**。

## 2. 核心架构：Dual Boot System
系统采用两阶段启动流程，模拟生物的本能与意识分层。

### 2.1 Swarm Boot (Instinct Layer)
- **配置文件**: `swarmbot/boot/swarmboot.md`
- **职责**: 负责任务的纯理性拆解与执行。
- **输入**: 用户 Prompt + 工具清单 + 文件结构认知。
- **输出**: 结构化的任务结果与白板状态 (Whiteboard Context)。
- **核心组件**:
  - **Tool Cognition**: 自动感知 `TOOLS.md` 定义的权限与 OpenClaw 扩展工具。
  - **MemoryMap**: 实时同步多 Agent 间的任务状态。

### 2.2 Master Agent Boot (Consciousness Layer)
- **配置文件**: `swarmbot/boot/masteragentboot.md`
- **职责**: 负责与用户的最终交互，注入人格与情感。
- **输入**: Swarm 执行结果 + SOUL.md + USER.md。
- **输出**: 符合人设的自然语言回复。
- **核心组件**:
  - **Soul Engine**: 基于 `SOUL.md` 的人格渲染。
  - **Heartbeat**: 主动关怀机制 (`HEARTBEAT.md`)。

## 3. 动态角色生成 (Dynamic Role Generation)
当 `architecture="auto"` 时，Swarmbot 不再使用预设角色，而是：
1. **Planner** 分析用户意图。
2. **AutoBuilder** 动态生成最适合当前任务的角色列表（如 `DirectoryStructureManager`, `PythonExpert`）。
3. **Instantiate** 实时实例化 Agent 并分配工具权限。

## 4. 目录结构说明
```text
swarmbot/
├── boot/                  # [v0.2 新增] 核心认知配置文件
│   ├── swarmboot.md       # Swarm 启动配置
│   ├── masteragentboot.md # Master 启动配置
│   ├── SOUL.md            # 人格设定
│   ├── TOOLS.md           # 工具权限策略
│   └── ...
├── swarm/
│   ├── manager.py         # 编排中枢 (含 Dual Boot 逻辑)
│   └── ...
├── tools/
│   ├── policy.py          # [v0.2 新增] 工具权限控制
│   ├── openclaw_bridge.py # [v0.2 新增] OpenClaw 桥接
│   └── ...
└── ...
```

## 5. 开发指南
### 5.1 添加新工具
1. 在 `swarmbot/tools/` 下实现工具逻辑。
2. 在 `swarmbot/tools/registry.py` 中注册。
3. 在 `swarmbot/boot/TOOLS.md` 中配置权限。

### 5.2 修改人格
直接编辑 `swarmbot/boot/SOUL.md`，无需重启服务（Hot-reload via Boot process）。

### 5.3 升级与维护
使用 `swarmbot update` 命令可拉取最新代码，该命令会自动保留 `boot/` 目录下的个性化配置。
