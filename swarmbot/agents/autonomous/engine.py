from __future__ import annotations

import copy
import json
import os
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ..base import BaseAgent, AgentConfig
from .loop import AutonomousLoop
from ...config_manager import ProviderConfig, WORKSPACE_PATH, load_config
from ...memory.cold_memory import ColdMemory
from ...loops.overthinking import OverthinkingLoop
from ...loops.overaction import OveractionLoop


@dataclass
class MonitorQueueItem:
    event_id: str
    bundle_id: str
    source: str
    kind: str
    severity: str
    detected_at: int
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionQueueItem:
    plan_id: str
    event_id: str
    bundle_id: str
    kind: str
    action_type: str
    task_list: List[Dict[str, Any]] = field(default_factory=list)
    swarm_profile: Dict[str, Any] = field(default_factory=dict)
    risk_level: str = "L1"
    state: str = "planned"
    action_result: Dict[str, Any] = field(default_factory=dict)


class _Bundle:
    def __init__(self, bundle_id: str, interval_seconds: int, anti_over_opt: Dict[str, Any] | None = None):
        self.bundle_id = bundle_id
        self.interval_seconds = max(10, interval_seconds)
        self.last_run = 0
        self.anti_over_opt = anti_over_opt or {}
        self.last_optimization_ts = 0
        self.optimization_count_this_hour = 0
        self.hourly_reset_ts = int(time.time()) // 3600
        self.smoothing_window = int(self.anti_over_opt.get("smoothing_window", 5))
        self.stability_threshold = float(self.anti_over_opt.get("stability_threshold", 0.2))
        self.pause_on_instability = bool(self.anti_over_opt.get("pause_on_instability", False))
        self.recent_efficiencies: List[float] = []

    def due(self, now_ts: int) -> bool:
        return now_ts - self.last_run >= self.interval_seconds

    def mark(self, now_ts: int):
        self.last_run = now_ts

    def _check_optimization_cooldown(self, now_ts: int) -> bool:
        min_interval = int(self.anti_over_opt.get("min_optimization_interval", 0))
        if min_interval > 0 and now_ts - self.last_optimization_ts < min_interval:
            return False
        return True

    def _check_hourly_limit(self, now_ts: int) -> bool:
        max_per_hour = int(self.anti_over_opt.get("max_optimization_per_hour", 999))
        current_hour = now_ts // 3600
        if current_hour > self.hourly_reset_ts:
            self.optimization_count_this_hour = 0
            self.hourly_reset_ts = current_hour
        return self.optimization_count_this_hour < max_per_hour

    def _check_stability(self) -> bool:
        if not self.pause_on_instability or len(self.recent_efficiencies) < self.smoothing_window:
            return True
        values = self.recent_efficiencies[-self.smoothing_window:]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        cv = (variance ** 0.5) / mean if mean > 0 else 0
        return cv <= self.stability_threshold

    def should_optimize(self, now_ts: int) -> bool:
        if not self._check_optimization_cooldown(now_ts):
            return False
        if not self._check_hourly_limit(now_ts):
            return False
        if not self._check_stability():
            return False
        return True

    def record_optimization(self, now_ts: int):
        self.last_optimization_ts = now_ts
        self.optimization_count_this_hour += 1

    def record_efficiency(self, efficiency: float):
        self.recent_efficiencies.append(efficiency)
        if len(self.recent_efficiencies) > self.smoothing_window * 3:
            self.recent_efficiencies = self.recent_efficiencies[-self.smoothing_window * 2:]

    def check(self, now_ts: int) -> MonitorQueueItem | None:
        return None


class _MemoryFoundationBundle(_Bundle):
    def check(self, now_ts: int) -> MonitorQueueItem | None:
        if not self.due(now_ts):
            return None
        self.mark(now_ts)
        evidence = {"reason": "periodic_memory_foundation"}
        if self.should_optimize(now_ts):
            evidence["optimization_eligible"] = True
        else:
            evidence["optimization_eligible"] = False
        eid = str(uuid.uuid4())
        return MonitorQueueItem(
            event_id=eid,
            bundle_id=self.bundle_id,
            source="core",
            kind="memory_foundation",
            severity="medium",
            detected_at=now_ts,
            evidence=evidence,
        )


class _SystemHygieneBundle(_Bundle):
    def __init__(self, bundle_id: str, interval_seconds: int, disk_ratio: float, mem_ratio: float, anti_over_opt: Dict[str, Any] | None = None):
        super().__init__(bundle_id, interval_seconds, anti_over_opt)
        self.disk_ratio = disk_ratio
        self.mem_ratio = mem_ratio

    def check(self, now_ts: int) -> MonitorQueueItem | None:
        if not self.due(now_ts):
            return None
        self.mark(now_ts)
        try:
            import shutil
            import psutil

            du = shutil.disk_usage(os.path.expanduser("~"))
            vm = psutil.virtual_memory()
            free_disk = (du.free / du.total) if du.total > 0 else 1.0
            free_mem = (vm.available / vm.total) if vm.total > 0 else 1.0
            if free_disk < self.disk_ratio or free_mem < self.mem_ratio:
                eid = str(uuid.uuid4())
                return MonitorQueueItem(
                    event_id=eid,
                    bundle_id=self.bundle_id,
                    source="core",
                    kind="system_hygiene",
                    severity="high",
                    detected_at=now_ts,
                    evidence={"free_disk_ratio": round(free_disk, 4), "free_mem_ratio": round(free_mem, 4)},
                )
        except Exception:
            pass
        return None


class _BundleGovernorBundle(_Bundle):
    def __init__(self, bundle_id: str, interval_seconds: int, index_file: str, anti_over_opt: Dict[str, Any] | None = None):
        super().__init__(bundle_id, interval_seconds, anti_over_opt)
        self.index_file = Path(os.path.expanduser(index_file))

    def check(self, now_ts: int) -> MonitorQueueItem | None:
        if not self.due(now_ts):
            return None
        self.mark(now_ts)
        issues = self._scan_issues()
        if not issues:
            return None
        eid = str(uuid.uuid4())
        return MonitorQueueItem(
            event_id=eid,
            bundle_id=self.bundle_id,
            source="core",
            kind="bundle_governance",
            severity="medium",
            detected_at=now_ts,
            evidence={"issues": issues[:20], "issue_count": len(issues)},
        )

    def _scan_issues(self) -> List[Dict[str, Any]]:
        if not self.index_file.exists():
            return []
        rows: List[Dict[str, Any]] = []
        for line in self.index_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
        seen = {}
        issues: List[Dict[str, Any]] = []
        for r in rows:
            key = f"{r.get('namespace','')}::{r.get('dedup_key','')}"
            if key in seen:
                issues.append({"type": "duplicate", "key": key})
            else:
                seen[key] = r.get("bundle_id")
        return issues


class AutonomousAgent(BaseAgent):
    """Autonomous Agent - 封装 AutonomousEngine"""

    def __init__(self, stop_event: threading.Event):
        agent_config = AgentConfig(
            agent_id="autonomous",
            role="autonomous",
            max_iterations=5,
            enable_tools=True
        )
        super().__init__(agent_config)
        
        self.stop_event = stop_event
        self.config = load_config()
        self.workspace = WORKSPACE_PATH
        self.cold = ColdMemory()
        
        # 监控队列
        queues_cfg = getattr(self.config.autonomous, "queues", {}) or {}
        self.monitor_queue = deque(maxlen=max(50, int(queues_cfg.get("monitor_queue_size", 1000))))
        self.action_queue: Dict[str, ActionQueueItem] = {}
        
        # Bundle
        self.bundles = self._build_bundles()
        
        # Loop
        self.loop = AutonomousLoop(self, {
            "max_iterations": 5,
            "time_budget": 300,
            "anti_over_optimization": {
                "min_interval": 3600,
                "max_per_hour": 2,
                "stability_threshold": 0.2,
                "pause_on_instability": True
            }
        })
        
        # 诊断路径
        self._diag_path = Path(self.workspace) / "autonomous_diagnostics.jsonl"
        
        # 执行统计
        self.execution_count = 0
        self.success_count = 0

    def _load_bundle_config(self, bundle_id: str) -> Dict[str, Any]:
        bundle_path = Path.home() / ".swarmbot" / "bundles" / bundle_id / "bundle.json"
        if bundle_path.exists():
            try:
                with open(bundle_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _get_anti_over_opt_params(self, bundle_config: Dict[str, Any]) -> Dict[str, Any]:
        targets = bundle_config.get("optimization_targets", [])
        if targets and isinstance(targets, list):
            return {k: v for k, v in targets[0].items() if k not in ["target_id", "metric_name", "current_threshold", "direction", "feedback_source"]}
        return {}

    def _build_bundles(self) -> List[_Bundle]:
        monitor = getattr(self.config.autonomous, "monitor", {}) or {}
        registry = getattr(self.config.autonomous, "bundle_registry", {}) or {}
        bundles: List[_Bundle] = []
        mem_cfg = monitor.get("memory_organizer", {}) if isinstance(monitor, dict) else {}
        sys_cfg = monitor.get("system_health", {}) if isinstance(monitor, dict) else {}

        mem_bundle_config = self._load_bundle_config("core.memory_foundation")
        mem_anti_opt = self._get_anti_over_opt_params(mem_bundle_config)
        bundles.append(_MemoryFoundationBundle("core.memory_foundation", int(mem_cfg.get("interval_minutes", 30)) * 60, mem_anti_opt))

        bundles.append(
            _SystemHygieneBundle(
                "core.system_hygiene",
                int(sys_cfg.get("interval_minutes", 10)) * 60,
                float(sys_cfg.get("disk_free_ratio_threshold", 0.1)),
                float(sys_cfg.get("mem_free_ratio_threshold", 0.1)),
            )
        )

        gov_bundle_config = self._load_bundle_config("core.bundle_governor")
        gov_anti_opt = self._get_anti_over_opt_params(gov_bundle_config)
        bundles.append(
            _BundleGovernorBundle(
                "core.bundle_governor",
                300,
                str(registry.get("index_file", "~/.swarmbot/bundles/_registry/bundles_index.jsonl")),
                gov_anti_opt,
            )
        )
        return bundles

    def think(self, context) -> str:
        """思考"""
        return "Autonomous thinking..."

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """执行工具"""
        return {"status": "ok"}

    def evaluate(self, output: str, context) -> Dict[str, Any]:
        """评估"""
        return {
            "bundle_efficiency": self.calc_bundle_efficiency(),
            "success_rate": self.calc_success_rate(),
            "quality": 0.8
        }

    # Bundle 评估方法 (AutonomousLoop 需要)
    def calc_bundle_efficiency(self) -> float:
        """计算 Bundle 效率"""
        if self.execution_count == 0:
            return 0.5
        return self.success_count / self.execution_count

    def calc_success_rate(self) -> float:
        """计算成功率"""
        return self.calc_bundle_efficiency()

    def calc_resource_usage(self) -> float:
        """计算资源使用"""
        return 0.3  # 默认值

    def calc_conflict_rate(self) -> float:
        """计算冲突率"""
        return 0.05  # 默认值

    def apply_bundle_modification(self, bundle_id: str, modifications: Dict[str, Any]) -> bool:
        """应用 Bundle 修改"""
        try:
            bundle_path = Path.home() / ".swarmbot" / "bundles" / bundle_id / "bundle.json"
            if bundle_path.exists():
                with open(bundle_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                config.update(modifications)
                with open(bundle_path, "w", encoding="utf-8") as f:
                    json.dump(config, f, ensure_ascii=False, indent=2)
                return True
        except Exception:
            pass
        return False

    def revert_bundle_modification(self):
        """回退 Bundle 修改"""
        pass


# 别名 - 保持向后兼容
AutonomousEngine = AutonomousAgent


def create_autonomous_engine(stop_event: threading.Event) -> AutonomousAgent:
    """工厂函数"""
    return AutonomousAgent(stop_event)
