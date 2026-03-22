# Autonomous Engine Bundle 自优化实验设计

**版本**: v1.0
**创建日期**: 2026-03-22
**实验目标**: 验证 MasterAgent → Autonomous Engine → Bundle → 自优化闭环

---

## 实验概述

本实验测试 Swarmbot v2.0 的核心自洽能力：
1. **MasterAgent 向 Autonomous Engine 请求创建新 Bundle**
2. **Bundle 执行并产生评估分数**
3. **低分触发优化机制**
4. **观察优化后 Bundle 质量是否提升**

---

## 实验架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         MasterAgent                             │
│  (1) 用户请求：创建一个监控 Twitter API 可用性的 Bundle            │
│  (5) 接收优化报告                                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Autonomous Engine                          │
│  (2) 解析请求 → 生成 Bundle 配置 → 注册到 Bundle Registry          │
│  (4) 接收低分评估 → 触发优化流程                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Bundle: twitter_monitor                      │
│  (3) 周期性执行 → 产出报告 → 接收 eval_score                     │
│  (6) 接收优化指令 → 更新 run.py → 重新执行                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 实验阶段

### Phase 1: Bundle 创建请求

**输入**: MasterAgent 收到用户请求
```
"请创建一个 Bundle，每小时检查一次 Twitter API 的可用性，
如果检测到故障，记录故障时间和类型，并生成日报。"
```

**预期输出**:
- Bundle ID: `custom.twitter_api_monitor`
- 配置文件：`~/.swarmbot/bundles/custom.twitter_api_monitor/bundle.json`
- 执行脚本：`~/.swarmbot/bundles/custom.twitter_api_monitor/run.py`

**验证点**:
- [ ] Bundle 目录结构完整
- [ ] bundle.json 包含正确的 interval_seconds (3600)
- [ ] run.py 可执行且语法正确
- [ ] Bundle 注册到 `_registry/bundles_index.jsonl`

---

### Phase 2: Bundle 执行与评估

**执行流程**:
1. Autonomous Engine 每 30 秒 tick 检查 Bundle 是否到期
2. 到期时执行 `run.py`
3. 产出写入 `memory/execution_history.jsonl`
4. 生成评估分数 (0-1)

**评估维度**:
| 维度 | 权重 | 说明 |
|------|------|------|
| 任务完成率 | 40% | 是否完成预定任务 |
| 输出质量 | 30% | 输出是否有用、准确 |
| 资源效率 | 15% | CPU/内存/Token 使用 |
| 错误处理 | 15% | 异常处理是否完善 |

**预期输出**:
```json
{
  "bundle_id": "custom.twitter_api_monitor",
  "execution_id": "exec-001",
  "timestamp": 1711123456,
  "status": "completed",
  "eval_score": 0.65,
  "metrics": {
    "task_completion": 0.8,
    "output_quality": 0.6,
    "resource_efficiency": 0.7,
    "error_handling": 0.5
  }
}
```

---

### Phase 3: 低分触发优化

**触发条件**: `eval_score < 0.7`

**优化流程**:
1. Autonomous Engine 发送 `optimization_request` 到 CommunicationHub
2. MasterAgent 消费消息并分析低分原因
3. 生成优化建议写入 `memory/optimization_records.jsonl`
4. 更新 Bundle 配置或 run.py

**预期优化建议**:
```json
{
  "bundle_id": "custom.twitter_api_monitor",
  "optimization_id": "opt-001",
  "trigger_score": 0.65,
  "issues": [
    {"dimension": "error_handling", "suggestion": "添加 Twitter API 限流处理"},
    {"dimension": "output_quality", "suggestion": "增加故障分类详细度"}
  ],
  "proposed_changes": [
    {"file": "run.py", "change": "添加 exponential backoff 重试逻辑"},
    {"file": "bundle.json", "change": "增加 error_types 配置项"}
  ]
}
```

---

### Phase 4: 优化后复测

**验证流程**:
1. 应用优化后重新执行 Bundle
2. 收集新的评估分数
3. 对比优化前后分数变化

**成功标准**:
- 优化后 `eval_score` 提升 >= 15%
- 至少一个维度分数提升 >= 20%

---

## 实验脚本

### 1. 创建 Bundle 请求脚本

```python
# tests/experiment_bundle_optimization.py - Part 1
import requests
import json

def request_bundle_creation():
    """Phase 1: 请求创建 Bundle"""
    payload = {
        "user_input": "请创建一个 Bundle，每小时检查一次 Twitter API 的可用性",
        "chat_id": "experiment-001",
        "sender": "experiment"
    }

    response = requests.post(
        "http://127.0.0.1:18790/chat",
        json=payload
    )

    print(f"Bundle 创建请求响应：{response.json()}")
    return response.json()
```

### 2. Bundle 执行监控脚本

```python
# tests/experiment_bundle_optimization.py - Part 2
import json
from pathlib import Path
from datetime import datetime

class BundleExecutionMonitor:
    def __init__(self, bundle_id):
        self.bundle_id = bundle_id
        self.workspace = Path.home() / ".swarmbot/workspace"

    def get_execution_history(self):
        history_file = (
            Path.home() / f".swarmbot/bundles/{self.bundle_id}/memory/execution_history.jsonl"
        )
        if not history_file.exists():
            return []

        executions = []
        with open(history_file) as f:
            for line in f:
                data = json.loads(line)
                if data.get("bundle_id") == self.bundle_id:
                    executions.append(data)
        return executions

    def get_avg_score(self):
        executions = self.get_execution_history()
        if not executions:
            return None
        scores = [e.get("eval_score", 0) for e in executions]
        return sum(scores) / len(scores)

    def wait_for_executions(self, min_count=3, timeout_seconds=3600):
        """等待至少 N 次执行"""
        import time
        start = time.time()
        while time.time() - start < timeout_seconds:
            history = self.get_execution_history()
            if len(history) >= min_count:
                return history
            time.sleep(60)
        return history
```

### 3. 优化效果分析脚本

```python
# tests/experiment_bundle_optimization.py - Part 3
class OptimizationAnalyzer:
    def __init__(self, bundle_id):
        self.bundle_id = bundle_id
        self.monitor = BundleExecutionMonitor(bundle_id)

    def analyze_optimization_effect(self, optimization_timestamp):
        """分析优化效果"""
        history = self.monitor.get_execution_history()

        before_opt = [
            e for e in history
            if e.get("timestamp", 0) < optimization_timestamp
        ]
        after_opt = [
            e for e in history
            if e.get("timestamp", 0) > optimization_timestamp
        ]

        if not before_opt or not after_opt:
            return None

        before_avg = sum(e.get("eval_score", 0) for e in before_opt) / len(before_opt)
        after_avg = sum(e.get("eval_score", 0) for e in after_opt) / len(after_opt)

        improvement = (after_avg - before_avg) / max(0.01, before_avg)

        return {
            "bundle_id": self.bundle_id,
            "before_avg": before_avg,
            "after_avg": after_avg,
            "improvement_pct": improvement * 100,
            "before_count": len(before_opt),
            "after_count": len(after_opt),
        }
```

---

## 实验执行步骤

### Step 1: 准备环境

```bash
# 确保 Daemon 运行
./.venv/bin/swarmbot daemon start

# 验证 Autonomous Engine 运行
cat ~/.swarmbot/logs/daemon_gateway.log | grep "Autonomous"
```

### Step 2: 发送 Bundle 创建请求

```bash
python tests/experiment_bundle_optimization.py --phase create \
  --prompt "请创建一个 Bundle，每 30 分钟检查一次 GitHub API 状态"
```

### Step 3: 监控 Bundle 执行

```bash
python tests/experiment_bundle_optimization.py --phase monitor \
  --bundle-id "custom.github_api_monitor" \
  --min-executions 5
```

### Step 4: 注入低分评估（模拟真实场景）

```bash
python tests/experiment_bundle_optimization.py --phase inject \
  --bundle-id "custom.github_api_monitor" \
  --eval-score 0.5
```

### Step 5: 等待并分析优化结果

```bash
python tests/experiment_bundle_optimization.py --phase analyze \
  --bundle-id "custom.github_api_monitor"
```

---

## 预期结果

### 成功场景

| 指标 | 目标值 | 说明 |
|------|--------|------|
| Bundle 创建成功率 | 100% | 请求后 5 分钟内创建完成 |
| Bundle 执行率 | >= 90% | 计划执行次数 vs 实际执行 |
| 优化触发率 | 100% | 低分后触发优化 |
| 优化有效率 | >= 70% | 优化后分数提升 >= 15% |

### 失败场景分析

| 失败点 | 可能原因 | 解决方案 |
|--------|----------|----------|
| Bundle 创建失败 | LLM 无法解析请求 | 改进 prompt 模板 |
| Bundle 不执行 | interval 配置错误 | 检查 bundle.json |
| 评估分数异常 | 评估逻辑 bug | 检查 eval 代码 |
| 优化不触发 | CommunicationHub 消息未消费 | 检查 MasterAgent 状态 |

---

## 数据收集与分析

### 收集的数据

1. **Bundle 配置**: `bundle.json` 内容变化
2. **执行历史**: `execution_history.jsonl` 每次执行记录
3. **优化记录**: `optimization_records.jsonl` 优化建议
4. **Gateway 日志**: `daemon_gateway.log` 系统日志

### 分析方法

```python
import pandas as pd
import matplotlib.pyplot as plt

# 读取执行历史
executions = pd.read_json(
    "~/.swarmbot/bundles/custom.github_api_monitor/memory/execution_history.jsonl",
    lines=True
)

# 绘制分数趋势图
plt.figure(figsize=(10, 6))
plt.plot(executions["timestamp"], executions["eval_score"], marker="o")
plt.axhline(y=0.7, color="r", linestyle="--", label="目标分数 0.7")
plt.xlabel("时间")
plt.ylabel("评估分数")
plt.title("Bundle 优化效果趋势")
plt.legend()
plt.savefig("artifacts/bundle_optimization_trend.png")
```

---

## 实验报告模板

```markdown
# Bundle 自优化实验报告

## 实验信息
- 实验日期: YYYY-MM-DD
- Bundle ID: custom.xxx
- 初始版本: v1
- 优化版本: v2

## 执行统计
| 指标 | 优化前 | 优化后 | 变化 |
|------|--------|--------|------|
| 平均分数 | 0.xx | 0.xx | +xx% |
| 执行次数 | xx | xx | - |
| 成功率 | xx% | xx% | +xx% |

## 优化内容
1. 修改点 1
2. 修改点 2

## 结论
- [ ] 优化有效
- [ ] 优化无效
- [ ] 需要进一步优化
```

---

## 附录：Bundle 目录结构

```
~/.swarmbot/bundles/custom.twitter_api_monitor/
├── bundle.json           # Bundle 配置
├── run.py                # 执行脚本
├── memory/
│   ├── execution_history.jsonl  # 执行历史
│   └── optimization_records.jsonl # 优化记录
└── README.md             # Bundle 说明
```

### bundle.json 示例

```json
{
  "bundle_id": "custom.twitter_api_monitor",
  "name": "Twitter API 监控",
  "objective": "每小时检查 Twitter API 可用性并记录故障",
  "interval_seconds": 3600,
  "success_metrics": {
    "min_uptime": 0.99,
    "max_response_time_ms": 5000
  },
  "constraints": [
    "每次执行不超过 5 分钟",
    "Token 使用不超过 10000 tokens"
  ],
  "version": "1.0",
  "created_at": "2026-03-22T12:00:00Z",
  "updated_at": "2026-03-22T12:00:00Z"
}
```
