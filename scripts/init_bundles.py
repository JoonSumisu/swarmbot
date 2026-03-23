#!/usr/bin/env python3
"""
Initialize Bundle folder structure for Autonomous Engine.

Creates default core bundles with:
- bundle.json (configuration)
- README.md (documentation)
- run.py (execution script)
- eval_rubric.md (evaluation criteria)
- optimization.md (optimization targets)
- memory/ (execution history, eval results, optimization records)
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, Any

# Bundle definitions
BUNDLES = {
    "core.memory_foundation": {
        "interval_seconds": 1800,  # 30 min
        "objective": "高效整理记忆，提升知识复用率",
        "success_metrics": {
            "compression_rate": {"target": 0.5, "direction": "minimize"},
            "retrieval_accuracy": {"target": 0.8, "direction": "maximize"}
        },
        "constraints": [
            "不影响主会话响应时间",
            "压缩过程不可阻塞主线程",
            "需使用移动平均计算效率",
            "波动大于 20% 时暂停优化"
        ],
        "optimization_targets": [
            {
                "target_id": "t1",
                "metric_name": "compression_rate",
                "current_threshold": 0.5,
                "direction": "minimize",
                "feedback_source": "both",
                "smoothing_window": 5,
                "stability_threshold": 0.2,
                "pause_on_instability": True
            }
        ],
        "feedback_loop": {
            "enabled": True,
            "trigger": "on_eval_fail",
            "via": "gateway"
        },
    },
    "core.boot_optimizer": {
        "interval_seconds": 1200,  # 20 min
        "objective": "优化启动提示词，提升系统初始响应质量",
        "success_metrics": {
            "boot_prompt_score": {"target": 0.8, "direction": "maximize"},
            "user_satisfaction": {"target": 0.7, "direction": "maximize"}
        },
        "constraints": [
            "不改变核心系统行为",
            "优化需经过 A/B 测试验证",
            "优化冷却时间至少 1 小时",
            "单次优化幅度不超过 5%"
        ],
        "optimization_targets": [
            {
                "target_id": "t1",
                "metric_name": "boot_prompt_score",
                "current_threshold": 0.5,  # 更严格才触发
                "direction": "maximize",
                "feedback_source": "auto_eval",
                "min_optimization_interval": 3600,  # 1小时冷却
                "max_optimization_per_hour": 2,
                "require_improvement_validation": True
            }
        ],
        "feedback_loop": {
            "enabled": True,
            "trigger": "on_low_score",
            "via": "gateway"
        },
    },
    "core.system_hygiene": {
        "interval_seconds": 600,  # 10 min
        "objective": "监控系统健康状态，预防资源耗尽",
        "success_metrics": {
            "disk_free_ratio": {"target": 0.1, "direction": "maximize"},
            "memory_free_ratio": {"target": 0.1, "direction": "maximize"},
            "cpu_usage": {"target": 0.8, "direction": "minimize"},
            "api_success_rate": {"target": 0.95, "direction": "maximize"},
            "bundle_failure_rate": {"target": 0.1, "direction": "minimize"}
        },
        "constraints": [
            "不删除用户重要文件",
            "告警阈值需合理避免误报",
            "监控不应影响系统性能"
        ],
        "optimization_targets": [
            {
                "target_id": "t1",
                "metric_name": "disk_free_ratio",
                "current_threshold": 0.1,
                "direction": "maximize",
                "feedback_source": "system"
            },
            {
                "target_id": "t2",
                "metric_name": "api_success_rate",
                "current_threshold": 0.95,
                "direction": "maximize",
                "feedback_source": "system"
            }
        ],
        "feedback_loop": {
            "enabled": True,
            "trigger": "on_threshold_breach",
            "via": "gateway"
        },
    },
    "core.bundle_governor": {
        "interval_seconds": 300,  # 5 min
        "objective": "检测 Bundle 冲突，维护系统稳定性",
        "success_metrics": {
            "conflict_detection_rate": {"target": 1.0, "direction": "maximize"},
            "false_positive_rate": {"target": 0.0, "direction": "minimize"}
        },
        "constraints": [
            "不误删活跃 Bundle",
            "冲突判定需有明确证据",
            "优化冷却时间至少 2 小时",
            "最多连续优化 3 次"
        ],
        "optimization_targets": [
            {
                "target_id": "t1",
                "metric_name": "conflict_detection_rate",
                "current_threshold": 0.95,
                "direction": "maximize",
                "feedback_source": "both",
                "min_optimization_interval": 7200,  # 2小时冷却
                "max_optimization_per_hour": 1,
                "max_consecutive_optimizations": 3
            }
        ],
        "feedback_loop": {
            "enabled": True,
            "trigger": "on_conflict_detected",
            "via": "gateway"
        },
    },
    "core.memory_foundation": {
        "interval_seconds": 1800,  # 30 min
        "objective": "高效整理记忆，提升知识复用率",
        "success_metrics": {
            "compression_rate": {"target": 0.5, "direction": "minimize"},
            "retrieval_accuracy": {"target": 0.8, "direction": "maximize"}
        },
        "constraints": [
            "不影响主会话响应时间",
            "压缩过程不可阻塞主线程",
            "需使用移动平均计算效率",
            "波动大于 20% 时暂停优化"
        ],
        "optimization_targets": [
            {
                "target_id": "t1",
                "metric_name": "compression_rate",
                "current_threshold": 0.5,
                "direction": "minimize",
                "feedback_source": "both",
                "smoothing_window": 5,  # 移动平均窗口
                "stability_threshold": 0.2,  # 波动阈值
                "pause_on_instability": True
            }
        ],
        "feedback_loop": {
            "enabled": True,
            "trigger": "on_eval_fail",
            "via": "gateway"
        },
    },


def create_bundle_json(bundle_id: str, bundle_config: Dict[str, Any]) -> Dict[str, Any]:
    """Create bundle.json content."""
    now = int(time.time())
    return {
        "bundle_id": bundle_id,
        "objective": bundle_config["objective"],
        "interval_seconds": bundle_config["interval_seconds"],
        "success_metrics": bundle_config["success_metrics"],
        "constraints": bundle_config["constraints"],
        "optimization_targets": bundle_config["optimization_targets"],
        "feedback_loop": bundle_config["feedback_loop"],
        "meta": {
            "source": "core",
            "namespace": "default",
            "status": "active",
            "version": "1.0.0",
            "created_at": now,
            "updated_at": now
        }
    }


def create_readme(bundle_id: str, bundle_config: Dict[str, Any]) -> str:
    """Create README.md content."""
    bundle_name = bundle_id.split(".")[-1].replace("_", " ").title()

    content = f"""# {bundle_name} Bundle

## 目的
{bundle_config["objective"]}

## 触发条件
- 每 {bundle_config["interval_seconds"] // 60} 分钟执行一次

## 执行流程
1. 检查触发条件
2. 执行核心任务
3. 记录执行结果
4. 更新评估指标

## 输出
- 执行状态
- 关键指标
- 异常报告（如有）

## 评估标准
详见 [eval_rubric.md](./eval_rubric.md)

## 优化目标
详见 [optimization.md](./optimization.md)
"""
    return content


def create_run_py(bundle_id: str, bundle_config: Dict[str, Any]) -> str:
    """Create run.py content."""
    bundle_name = bundle_id.split(".")[-1]

    # Different run.py logic per bundle type
    if bundle_name == "memory_foundation":
        execute_logic = '''    # 1. 读取 Hot Memory
    hot_memory_path = Path(workspace_path) / "hot_memory.json"
    if not hot_memory_path.exists():
        return {"status": "skipped", "reason": "no_hot_memory"}

    with open(hot_memory_path, "r", encoding="utf-8") as f:
        hot_memory = json.load(f)

    # 2. 分析记忆价值
    valuable_memories = [m for m in hot_memory if m.get("value_score", 0) > 0.7]

    # 3. 压缩到 QMD (placeholder)
    compressed_count = len(valuable_memories)
    compression_rate = compressed_count / max(1, len(hot_memory))

    return {
        "status": "success",
        "compressed_count": compressed_count,
        "compression_rate": compression_rate,
        "details": f"压缩 {compressed_count} 条记忆到 QMD"
    }'''
    elif bundle_name == "boot_optimizer":
        execute_logic = '''    # 1. 读取当前启动提示词
    boot_path = Path.home() / ".swarmbot" / "boot"
    if not boot_path.exists():
        return {"status": "skipped", "reason": "no_boot_files"}

    # 2. 分析提示词效果 (placeholder)
    # 实际实现需要 LLM 评估

    return {
        "status": "success",
        "boot_prompt_score": 0.75,
        "suggestions": [],
        "details": "启动提示词分析完成"
    }'''
    elif bundle_name == "system_hygiene":
        execute_logic = '''    import shutil
    import os
    import time
    from pathlib import Path

    workspace_path = context.get("workspace_path", str(Path.home() / ".swarmbot" / "workspace"))

    # ========== 1. CPU 使用率监控 ==========
    def get_cpu_usage():
        """获取 CPU 使用率 (Linux)"""
        try:
            with open("/proc/stat", "r") as f:
                line = f.readline()
            parts = line.split()
            if parts[0] == "cpu":
                user, nice, system, idle = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
                total = user + nice + system + idle
                idle_ratio = idle / total if total > 0 else 0.5
                return 1.0 - idle_ratio
        except:
            pass
        return 0.5  # fallback

    cpu_usage = get_cpu_usage()

    # ========== 2. 磁盘空间监控 ==========
    total, used, free = shutil.disk_usage("/")
    disk_free_ratio = free / total

    # ========== 3. 内存使用率监控 ==========
    def get_memory_usage():
        """获取内存使用率 (Linux)"""
        try:
            with open("/proc/meminfo", "r") as f:
                lines = f.readlines()
            mem_info = {}
            for line in lines:
                parts = line.split()
                if len(parts) >= 2:
                    mem_info[parts[0].rstrip(":")] = int(parts[1])
            mem_total = mem_info.get("MemTotal", 1)
            mem_available = mem_info.get("MemAvailable", mem_info.get("MemFree", 0))
            return 1.0 - (mem_available / mem_total)
        except:
            return 0.5

    memory_usage = get_memory_usage()
    memory_free_ratio = 1.0 - memory_usage

    # ========== 4. API 成功率分析 ==========
    def analyze_api_success_rate():
        """分析最近 API 调用成功率"""
        log_path = Path(workspace_path) / "../logs"
        success_count = 0
        error_count = 0

        # 读取最近的日志文件
        try:
            log_file = log_path / "gateway.log"
            if log_file.exists():
                with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()[-500:]  # 最近 500 行

                for line in lines:
                    if "API call" in line or "completion" in line:
                        if "error" in line.lower() or "failed" in line.lower():
                            error_count += 1
                        else:
                            success_count += 1
        except:
            pass

        total_calls = success_count + error_count
        if total_calls == 0:
            return 1.0  # 无数据时假设正常

        return success_count / total_calls

    api_success_rate = analyze_api_success_rate()

    # ========== 5. Bundle 失败率追踪 ==========
    def analyze_bundle_failure_rate():
        """分析 Bundle 执行失败率"""
        bundles_path = Path.home() / ".swarmbot" / "bundles"
        total_executions = 0
        failed_executions = 0

        try:
            if bundles_path.exists():
                for bundle_dir in bundles_path.iterdir():
                    if bundle_dir.is_dir() and not bundle_dir.name.startswith("_"):
                        history_file = bundle_dir / "memory" / "execution_history.jsonl"
                        if history_file.exists():
                            with open(history_file, "r", encoding="utf-8", errors="ignore") as f:
                                lines = f.readlines()[-100:]  # 最近 100 条

                            for line in lines:
                                total_executions += 1
                                if '"status": "error"' in line or '"status":"error"' in line:
                                    failed_executions += 1
        except:
            pass

        if total_executions == 0:
            return 0.0  # 无执行记录

        return failed_executions / total_executions

    bundle_failure_rate = analyze_bundle_failure_rate()

    # ========== 6. 健康状态判定 ==========
    # 计算综合健康评分
    issues = []
    warning_count = 0
    critical_count = 0

    # CPU 检查
    if cpu_usage > 0.9:
        critical_count += 1
        issues.append(f"CPU 使用率过高：{cpu_usage*100:.1f}%")
    elif cpu_usage > 0.7:
        warning_count += 1
        issues.append(f"CPU 使用率偏高：{cpu_usage*100:.1f}%")

    # 磁盘检查
    if disk_free_ratio < 0.05:
        critical_count += 1
        issues.append(f"磁盘空间不足：{disk_free_ratio*100:.1f}%")
    elif disk_free_ratio < 0.1:
        warning_count += 1
        issues.append(f"磁盘空间偏少：{disk_free_ratio*100:.1f}%")

    # 内存检查
    if memory_free_ratio < 0.05:
        critical_count += 1
        issues.append(f"内存不足：{memory_free_ratio*100:.1f}%")
    elif memory_free_ratio < 0.1:
        warning_count += 1
        issues.append(f"内存偏少：{memory_free_ratio*100:.1f}%")

    # API 成功率检查
    if api_success_rate < 0.8:
        critical_count += 1
        issues.append(f"API 成功率过低：{api_success_rate*100:.1f}%")
    elif api_success_rate < 0.9:
        warning_count += 1
        issues.append(f"API 成功率偏低：{api_success_rate*100:.1f}%")

    # Bundle 失败率检查
    if bundle_failure_rate > 0.3:
        critical_count += 1
        issues.append(f"Bundle 失败率过高：{bundle_failure_rate*100:.1f}%")
    elif bundle_failure_rate > 0.1:
        warning_count += 1
        issues.append(f"Bundle 失败率偏高：{bundle_failure_rate*100:.1f}%")

    # 健康状态判定
    if critical_count > 0:
        health_status = "critical"
    elif warning_count > 0:
        health_status = "warning"
    else:
        health_status = "ok"

    details_parts = [
        f"CPU: {cpu_usage*100:.1f}%",
        f"磁盘：{disk_free_ratio*100:.1f}%",
        f"内存：{memory_free_ratio*100:.1f}%",
        f"API 成功率：{api_success_rate*100:.1f}%",
        f"Bundle 失败率：{bundle_failure_rate*100:.1f}%",
    ]

    if issues:
        details_parts.append("告警：" + "; ".join(issues))

    return {
        "status": health_status,
        "cpu_usage": round(cpu_usage, 3),
        "disk_free_ratio": round(disk_free_ratio, 3),
        "memory_free_ratio": round(memory_free_ratio, 3),
        "api_success_rate": round(api_success_rate, 3),
        "bundle_failure_rate": round(bundle_failure_rate, 3),
        "warning_count": warning_count,
        "critical_count": critical_count,
        "issues": issues,
        "details": ", ".join(details_parts)
    }'''
    elif bundle_name == "bundle_governor":
        execute_logic = '''    # 1. 扫描所有 Bundle
    bundles_path = Path.home() / ".swarmbot" / "bundles"
    if not bundles_path.exists():
        return {"status": "skipped", "reason": "no_bundles"}

    bundle_dirs = [d.name for d in bundles_path.iterdir() if d.is_dir()]

    # 2. 检测冲突 (placeholder - 检查重复/命名冲突)
    conflicts = []
    # 实际实现需要更复杂的冲突检测逻辑

    return {
        "status": "success",
        "bundles_scanned": len(bundle_dirs),
        "conflicts_found": len(conflicts),
        "conflicts": conflicts,
        "details": f"扫描了 {len(bundle_dirs)} 个 Bundle，发现 {len(conflicts)} 个冲突"
    }'''
    else:
        execute_logic = '''    # Default placeholder
    return {
        "status": "success",
        "details": f"{bundle_id} executed"
    }'''

    content = f'''#!/usr/bin/env python3
"""{bundle_id} - 自动化执行程序"""

import json
import time
from pathlib import Path
from typing import Dict, Any


def execute(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    执行 Bundle 任务

    Args:
        context: 包含 workspace_path, config 等

    Returns:
        执行结果
    """
    workspace_path = context.get("workspace_path", str(Path.home() / ".swarmbot" / "workspace"))

{execute_logic}


if __name__ == "__main__":
    result = execute({{"workspace_path": str(Path.home() / ".swarmbot" / "workspace")}})
    print(json.dumps(result, ensure_ascii=False, indent=2))
'''
    return content


def create_eval_rubric(bundle_id: str, bundle_config: Dict[str, Any]) -> str:
    """Create eval_rubric.md content."""
    bundle_name = bundle_id.split(".")[-1].replace("_", " ").title()

    content = f"""# {bundle_name} - 评估标准

## 完整性检查
- [ ] 执行了核心任务
- [ ] 记录了执行结果
- [ ] 更新了执行历史
- [ ] 无错误日志

## 质量评估
| 等级 | 条件 | 说明 |
|------|------|------|
| A    | 所有检查通过，指标优秀 | 超出预期 |
| B    | 所有检查通过，指标良好 | 符合预期 |
| C    | 基本检查通过，指标合格 | 可接受 |
| D    | 有检查未通过或指标差 | 需优化 |

## 通过条件
- 状态为 success
- 无错误日志
- 关键指标达到阈值

## 指标说明
"""

    for metric_name, metric_config in bundle_config["success_metrics"].items():
        direction = "最大化" if metric_config["direction"] == "maximize" else "最小化"
        content += f"- **{metric_name}**: 目标值 {metric_config['target']} ({direction})\n"

    return content


def create_optimization(bundle_id: str, bundle_config: Dict[str, Any]) -> str:
    """Create optimization.md content."""
    bundle_name = bundle_id.split(".")[-1].replace("_", " ").title()
    now = time.strftime("%Y-%m-%d")

    content = f"""# {bundle_name} - 优化目标

## 当前目标
"""

    for target in bundle_config["optimization_targets"]:
        direction = "最大化" if target["direction"] == "maximize" else "最小化"
        content += f"""
### {target["target_id"]}: {target["metric_name"]}
- 当前阈值：{target["current_threshold"]}
- 目标方向：{direction}
- 反馈来源：{target["feedback_source"]}
"""

    content += f"""
## 优化历史
- {now}: 初始阈值设定

## 优化策略
1. 分析低分执行特征，改进算法
2. 根据反馈调整指标权重
3. 定期回顾优化方向
"""

    return content


def init_bundle(bundle_id: str, bundles_path: Path):
    """Initialize a single bundle folder."""
    bundle_path = bundles_path / bundle_id
    memory_path = bundle_path / "memory"

    # Create directories
    bundle_path.mkdir(parents=True, exist_ok=True)
    memory_path.mkdir(parents=True, exist_ok=True)

    bundle_config = BUNDLES[bundle_id]

    # Create bundle.json
    bundle_json = create_bundle_json(bundle_id, bundle_config)
    with open(bundle_path / "bundle.json", "w", encoding="utf-8") as f:
        json.dump(bundle_json, f, ensure_ascii=False, indent=2)
    print(f"  Created: {bundle_path / 'bundle.json'}")

    # Create README.md
    readme = create_readme(bundle_id, bundle_config)
    with open(bundle_path / "README.md", "w", encoding="utf-8") as f:
        f.write(readme)
    print(f"  Created: {bundle_path / 'README.md'}")

    # Create run.py
    run_py = create_run_py(bundle_id, bundle_config)
    with open(bundle_path / "run.py", "w", encoding="utf-8") as f:
        f.write(run_py)
    print(f"  Created: {bundle_path / 'run.py'}")

    # Create eval_rubric.md
    eval_rubric = create_eval_rubric(bundle_id, bundle_config)
    with open(bundle_path / "eval_rubric.md", "w", encoding="utf-8") as f:
        f.write(eval_rubric)
    print(f"  Created: {bundle_path / 'eval_rubric.md'}")

    # Create optimization.md
    optimization = create_optimization(bundle_id, bundle_config)
    with open(bundle_path / "optimization.md", "w", encoding="utf-8") as f:
        f.write(optimization)
    print(f"  Created: {bundle_path / 'optimization.md'}")

    # Create memory files (empty JSONL)
    for memory_file in ["execution_history.jsonl", "optimization_records.jsonl", "eval_results.jsonl"]:
        (memory_path / memory_file).touch()
    print(f"  Created: {memory_path}/*.jsonl")

    print(f"Bundle '{bundle_id}' initialized successfully!")


def main():
    """Main entry point."""
    bundles_root = Path.home() / ".swarmbot" / "bundles"

    print(f"Initializing bundles at: {bundles_root}")
    print()

    for bundle_id in BUNDLES.keys():
        print(f"Initializing {bundle_id}...")
        init_bundle(bundle_id, bundles_root)
        print()

    print("All bundles initialized!")
    print()
    print("Bundle structure:")
    for bundle_id in BUNDLES.keys():
        bundle_path = bundles_root / bundle_id
        print(f"  {bundle_path}/")
        print(f"    ├── bundle.json")
        print(f"    ├── README.md")
        print(f"    ├── run.py")
        print(f"    ├── eval_rubric.md")
        print(f"    ├── optimization.md")
        print(f"    └── memory/")
        print(f"        ├── execution_history.jsonl")
        print(f"        ├── optimization_records.jsonl")
        print(f"        └── eval_results.jsonl")


if __name__ == "__main__":
    main()
