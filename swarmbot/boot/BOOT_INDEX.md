# Boot Files Index

## 架构说明

Swarmbot 采用分层 Boot 架构，不同组件加载不同的配置：

```
swarmbot/boot/
├── master/                    # MasterAgent 专用
│   ├── SOUL.md              # 核心人格
│   ├── IDENTITY.md          # 身份定位
│   ├── USER.md              # 用户偏好
│   └── masteragentboot.md    # MasterAgent 专用逻辑
│
├── autonomous/              # AutonomousEngine 专用
│   └── autonomous_boot.md   # 自主引擎配置
│
├── inference/               # 推理工具
│   ├── inference_tools.md     # 工具列表
│   └── inference_boot.md     # 推理共享逻辑
│
└── shared/                 # 共享配置
    ├── TOOLS.md            # 工具描述
    └── HEARTBEAT.md        # 心跳配置
```

## 组件职责

### MasterAgent
- 路由决策
- Hub 通信
- 结果演绎
- 人在回路转发

### AutonomousEngine
- Bundle 管理
- 自我优化
- 后台自驱

### Inference Tools
| 工具 | 说明 | 人在回路 |
|------|------|----------|
| standard | 标准 8 步推理 | 否 |
| supervised | 带暂停点 | 是 |
| swarms | 多 Worker | 否 |
| subswarm | 异步子任务 | 可选 |

## 加载方式

每个组件只加载自己需要的 Boot 文件，避免信息过载。
