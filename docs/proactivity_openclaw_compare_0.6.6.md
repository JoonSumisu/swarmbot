# OpenClaw 主动行动机制对齐方案（SwarmBot v0.6.6）

## 1. OpenClaw 侧主动行动要点（提炼）

1. Gateway 常驻，主动能力不依赖临时会话。  
2. Heartbeat 以文件化任务清单驱动，空清单直接静默。  
3. Cron 支持 `at/every/cron`，并有目标通道与投递策略。  
4. 默认安全策略偏保守，未知来源不直接执行。  
5. 主动消息有“该说才说”的节流与静默时段思路。  

## 2. 当前 SwarmBot 状态（改造前）

1. 已有 Overthinking/Overaction 双环，具备主动检查能力。  
2. 已有 scheduled_tasks 与 external_event 触发链。  
3. 主要短板：主动“投递”能力弱，更多写入 hot_memory；缺少统一静默窗口与节流策略。  
4. URL 显式阅读任务在部分场景会先反问澄清，主动性不足。  

## 3. 对齐目标

1. 显式“阅读+URL”指令必须立即执行读取。  
2. Overaction 检测结果可进入可消费 outbox，而不只写内存。  
3. 主动投递需要 quiet hours、最小间隔、单周期上限。  
4. 保持保守默认：仅在命中触发条件时主动输出。  

## 4. 已落地改造

### 4.1 Inference 主动读取规则

- 对“显式阅读/分析 + URL”强制 `need_tools=true`。  
- 强制工具集合：`browser_open/browser_read/web_search/file_read`。  
- 禁止该场景进入“先澄清再执行”路径。  

### 4.2 Overaction 主动投递能力

- 新增 `proactive_outbox.jsonl`。  
- 新增策略：
  - `quiet_hours`
  - `min_interval_minutes`
  - `max_per_cycle`
- 在以下事件可写入 outbox：
  - 调度任务 announce
  - 长时间未交互
  - 待办积压
  - 磁盘/内存告警
  - 外部紧急事件

## 5. 配置建议（v0.6.6）

```json
{
  "overaction": {
    "enabled": true,
    "interval_minutes": 60,
    "interaction_timeout_hours": 4,
    "proactive_delivery": {
      "enabled": true,
      "quiet_hours": "23:00-08:00",
      "min_interval_minutes": 30,
      "max_per_cycle": 2
    }
  }
}
```

## 6. 验收标准

1. URL 指令场景不再反问澄清。  
2. Overaction 触发后可观察到 outbox 新增记录。  
3. quiet hours 内 outbox 不新增。  
4. 高频触发场景下，间隔与单周期上限生效。  
