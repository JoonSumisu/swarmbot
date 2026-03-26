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

from ..config_manager import ProviderConfig, WORKSPACE_PATH, load_config
from ..core.agent import CoreAgent, AgentContext
from ..core.agent_config import CoreAgentConfig
from ..llm_client import OpenAICompatibleClient
from ..memory.memory_manager import MemoryManager
from ..swarm.manager import SwarmManager
from .reflection import ReflectionEngine


@dataclass
class MonitorQueueItem:
    event_id: str
    bundle_id: str
    source: str
    kind: str
    severity: str
    detected_at: int
    evidence: Dict[str, Any] = field(default_factory=dict)
    eval_rubric_ref: str = ""
    action_template_ref: str = ""
    skill_refs: List[str] = field(default_factory=list)
    policy: Dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""


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
    budget: Dict[str, Any] = field(default_factory=dict)
    deadline_ts: int = 0
    retry_policy: Dict[str, Any] = field(default_factory=lambda: {"max_retries": 1})
    approval_required: bool = False
    idempotency_key: str = ""
    state: str = "planned"
    progress_events: List[Dict[str, Any]] = field(default_factory=list)
    action_result: Dict[str, Any] = field(default_factory=dict)
    eval_result: Dict[str, Any] = field(default_factory=dict)
    decision_feedback: Dict[str, Any] = field(default_factory=dict)
    reported_to_gateway: bool = False


@dataclass
class BundleLifecycleState:
    """Bundle 生命周期状态"""
    bundle_id: str
    state: str
    created_at: float
    last_execution: float
    pause_reason: Optional[str] = None
    retire_reason: Optional[str] = None
    pause_count: int = 0
    total_runtime_seconds: float = 0.0


@dataclass
class BundleEvaluationResult:
    """Bundle 效能评估结果"""
    bundle_id: str
    efficiency_score: float
    success_rate: float
    avg_execution_time: float
    total_executions: int
    recent_failures: int
    value_output_score: float
    resource_efficiency_score: float
    recommendation: str
    evaluated_at: float = field(default_factory=time.time)


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
            if not self._check_optimization_cooldown(now_ts):
                evidence["optimization_blocked"] = "cooldown"
            elif not self._check_hourly_limit(now_ts):
                evidence["optimization_blocked"] = "hourly_limit"
            elif not self._check_stability():
                evidence["optimization_blocked"] = "instability"
        eid = str(uuid.uuid4())
        return MonitorQueueItem(
            event_id=eid,
            bundle_id=self.bundle_id,
            source="core",
            kind="memory_foundation",
            severity="medium",
            detected_at=now_ts,
            evidence=evidence,
            idempotency_key=f"{self.bundle_id}:{now_ts}",
        )


class _BootOptimizerBundle(_Bundle):
    def check(self, now_ts: int) -> MonitorQueueItem | None:
        if not self.due(now_ts):
            return None
        self.mark(now_ts)
        evidence = {"reason": "periodic_boot_optimize"}
        if self.should_optimize(now_ts):
            evidence["optimization_eligible"] = True
            evidence["require_validation"] = bool(self.anti_over_opt.get("require_improvement_validation", False))
        else:
            evidence["optimization_eligible"] = False
            if not self._check_optimization_cooldown(now_ts):
                evidence["optimization_blocked"] = "cooldown"
            elif not self._check_hourly_limit(now_ts):
                evidence["optimization_blocked"] = "hourly_limit"
        eid = str(uuid.uuid4())
        return MonitorQueueItem(
            event_id=eid,
            bundle_id=self.bundle_id,
            source="core",
            kind="boot_optimize",
            severity="low",
            detected_at=now_ts,
            evidence=evidence,
            idempotency_key=f"{self.bundle_id}:{now_ts}",
        )


class _SystemHygieneBundle(_Bundle):
    def __init__(self, bundle_id: str, interval_seconds: int, disk_ratio: float, mem_ratio: float):
        super().__init__(bundle_id, interval_seconds)
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
                    idempotency_key=f"{self.bundle_id}:{now_ts}",
                )
        except Exception:
            return None
        return None


class _BundleGovernorBundle(_Bundle):
    def __init__(self, bundle_id: str, interval_seconds: int, index_file: str, anti_over_opt: Dict[str, Any] | None = None):
        super().__init__(bundle_id, interval_seconds, anti_over_opt)
        self.index_file = Path(os.path.expanduser(index_file))
        self.max_consecutive = int(self.anti_over_opt.get("max_consecutive_optimizations", 999)) if self.anti_over_opt else 999
        self.consecutive_optimizations = 0

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
            idempotency_key=f"{self.bundle_id}:{now_ts}",
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
                issues.append({"type": "duplicate", "key": key, "bundle_ids": [seen[key], r.get("bundle_id")]})
            else:
                seen[key] = r.get("bundle_id")
        return issues


class _ReflectionBundle(_Bundle):
    """反思 Bundle - 每小时随机探索一小段记忆"""
    def __init__(self, bundle_id: str, interval_seconds: int, anti_over_opt: Dict[str, Any] | None = None):
        super().__init__(bundle_id, interval_seconds, anti_over_opt)
        self.reflection_engine = None  # 在运行时初始化

    def check(self, now_ts: int) -> MonitorQueueItem | None:
        if not self.due(now_ts):
            return None
        if self.reflection_engine is None:
            return None
        if not self.reflection_engine.is_due():
            return None
        self.mark(now_ts)
        eid = str(uuid.uuid4())
        return MonitorQueueItem(
            event_id=eid,
            bundle_id=self.bundle_id,
            source="core",
            kind="reflection",
            severity="low",
            detected_at=now_ts,
            evidence={"reason": "periodic_reflection"},
            idempotency_key=f"{self.bundle_id}:{now_ts}",
        )


class _ActionRunner:
    def __init__(self, stop_event: threading.Event, max_workers: int = 3):
        self.stop_event = stop_event
        import concurrent.futures

        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=max(1, max_workers))

    def submit(self, fn, *args, **kwargs):
        return self.pool.submit(fn, *args, **kwargs)

    def shutdown(self):
        self.pool.shutdown(wait=False)


class AutonomousEngine:
    def __init__(self, stop_event: threading.Event):
        self.stop_event = stop_event
        self.config = load_config()
        self.workspace = WORKSPACE_PATH
        self.cold = MemoryManager.get_instance()
        queues_cfg = getattr(self.config.autonomous, "queues", {}) or {}
        self.monitor_queue = deque(maxlen=max(50, int(queues_cfg.get("monitor_queue_size", 1000))))
        self._action_capacity = max(20, int(queues_cfg.get("action_queue_size", 500)))
        self.action_queue: Dict[str, ActionQueueItem] = {}
        self._action_order = deque()
        self._futures: Dict[str, Any] = {}
        self._diag_path = Path(self.workspace) / "autonomous_diagnostics.jsonl"
        self._gateway_report_path = Path(self.workspace) / "autonomous_gateway_reports.jsonl"
        self._swarm_manager: SwarmManager | None = None
        self.runner = _ActionRunner(stop_event, max_workers=int(getattr(self.config.autonomous, "max_concurrent_actions", 3)))
        self.bundles = self._build_bundles()
        self._max_retry = 1

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
        boot_cfg = monitor.get("long_task_reporter", {}) if isinstance(monitor, dict) else {}
        sys_cfg = monitor.get("system_health", {}) if isinstance(monitor, dict) else {}

        mem_bundle_config = self._load_bundle_config("core.memory_foundation")
        mem_anti_opt = self._get_anti_over_opt_params(mem_bundle_config)
        bundles.append(_MemoryFoundationBundle("core.memory_foundation", int(mem_cfg.get("interval_minutes", 30)) * 60, mem_anti_opt))

        boot_bundle_config = self._load_bundle_config("core.boot_optimizer")
        boot_anti_opt = self._get_anti_over_opt_params(boot_bundle_config)
        bundles.append(_BootOptimizerBundle("core.boot_optimizer", int(boot_cfg.get("interval_minutes", 20)) * 60, boot_anti_opt))

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
                max(60, int(boot_cfg.get("interval_minutes", 5)) * 60),
                str(registry.get("index_file", "~/.swarmbot/bundles/_registry/bundles_index.jsonl")),
                gov_anti_opt,
            )
        )

        # Reflection Bundle - 每小时随机探索记忆
        ref_cfg = monitor.get("reflection", {}) if isinstance(monitor, dict) else {}
        ref_bundle_config = self._load_bundle_config("core.reflection")
        ref_anti_opt = self._get_anti_over_opt_params(ref_bundle_config)
        self._reflection_bundle = _ReflectionBundle(
            "core.reflection",
            int(ref_cfg.get("interval_minutes", 60)) * 60,
            ref_anti_opt,
        )
        bundles.append(self._reflection_bundle)

        return bundles

    def start(self):
        # Initialize ReflectionEngine
        from ..llm_client import OpenAICompatibleClient
        llm = OpenAICompatibleClient.from_provider(providers=self.config.providers)
        reflection_engine = ReflectionEngine(
            memory_manager=self.cold,
            llm=llm,
            config=self.config,
        )
        # Connect to reflection bundle
        if hasattr(self, '_reflection_bundle'):
            self._reflection_bundle.reflection_engine = reflection_engine
        
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()
        print("[Autonomous] Engine started.")

    def stop(self):
        self.stop_event.set()
        self.runner.shutdown()

    def _log_diag(self, row: Dict[str, Any]):
        try:
            self._diag_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._diag_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _append_gateway_report(self, row: Dict[str, Any]):
        try:
            self._gateway_report_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._gateway_report_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _to_provider(self, d: Dict[str, Any]) -> ProviderConfig:
        p = ProviderConfig()
        for k, v in d.items():
            if hasattr(p, k):
                setattr(p, k, v)
        return p

    def _autonomous_runtime_config(self):
        cfg = copy.deepcopy(self.config)
        providers = getattr(cfg.autonomous, "providers", []) or []
        if isinstance(providers, list) and providers:
            cfg.providers = [self._to_provider(p) for p in providers if isinstance(p, dict)]
        return cfg

    def _get_swarm_manager(self) -> SwarmManager:
        if self._swarm_manager is None:
            self._swarm_manager = SwarmManager.from_swarmbot_config(self._autonomous_runtime_config())
        return self._swarm_manager

    def _collect_monitor_events(self, now_ts: int):
        """收集监控事件 - Bundle 主动触发"""
        for b in self.bundles:
            # 检查 Bundle 是否到期
            if not b.due(now_ts):
                continue
            
            # Bundle 到期，检查并触发事件
            item = b.check(now_ts)
            if item is not None:
                # 主动触发事件到 Hub
                self._trigger_bundle_event(b, item)
                self.monitor_queue.append(item)

    def _trigger_bundle_event(self, bundle: _Bundle, item: MonitorQueueItem):
        """Bundle 主动触发事件到 Hub"""
        try:
            # 记录事件到记忆
            self.cold.add(
                content=f"bundle_triggered bundle={bundle.bundle_id} kind={item.kind} severity={item.severity}",
                meta={"source": "autonomous", "event": "bundle_triggered"},
            )
            
            # 发送事件通知（如果有 Hub）
            if hasattr(self, 'hub') and self.hub:
                from ..gateway.communication_hub import MessageSender, MessageType
                self.hub.send(
                    msg_type=MessageType.SYSTEM_STATUS,
                    content=f"[Bundle 事件] {bundle.bundle_id}: {item.kind} ({item.severity})",
                    sender=MessageSender.AUTONOMOUS,
                    recipient=MessageSender.MASTER_AGENT,
                    metadata={
                        "event_id": item.event_id,
                        "bundle_id": bundle.bundle_id,
                        "kind": item.kind,
                        "severity": item.severity,
                    }
                )
        except Exception as e:
            print(f"[Autonomous] Bundle event trigger error: {e}")

    def _loop(self):
        """主循环 - 支持 Bundle 主动触发"""
        tick = max(5, int(getattr(self.config.autonomous, "tick_seconds", 30)))
        
        while not self.stop_event.is_set():
            try:
                self._reload_config_if_needed()
                now_ts = int(time.time())
                
                # 1. 处理已完成的任务
                self._flush_done()
                
                # 2. 收集 Bundle 事件（主动触发）
                self._collect_monitor_events(now_ts)
                
                # 3. 决策并创建任务
                self._decision_from_monitor()
                
                # 4. 分发执行
                self._dispatch_actions()
                
                # 5. 处理 Hub 消息（如果有）
                self._process_hub_messages()
                
            except Exception as e:
                print(f"[Autonomous] Loop error: {e}")
            
            if self.stop_event.wait(tick):
                break

    def _process_hub_messages(self):
        """处理 Hub 消息（Bundle 主动触发的事件）"""
        # 未来实现：监听 Hub 消息，处理外部触发的事件
        pass

    def _dispatch_actions(self):
        cap = int(getattr(self.config.autonomous, "max_concurrent_actions", 3))
        running = len(self._futures)
        if running >= cap:
            return
        for pid in list(self._action_order):
            if len(self._futures) >= cap:
                break
            item = self.action_queue.get(pid)
            if item is None or item.state != "planned":
                continue
            item.state = "running"
            item.progress_events.append({"ts": int(time.time()), "event": "accepted"})
            fut = self.runner.submit(self._run_action, copy.deepcopy(item))
            self._futures[pid] = fut

    def _flush_done(self):
        for pid, fut in list(self._futures.items()):
            if not fut.done():
                continue
            try:
                res = fut.result()
            except Exception as e:
                res = {
                    "state": "failed",
                    "action_result": {"ok": False, "summary": str(e)},
                    "eval_result": {"pass": False, "reason": "future_exception"},
                    "progress_events": [{"ts": int(time.time()), "event": "failed", "stage": "future_exception"}],
                    "reported_to_gateway": False,
                    "finished_at": int(time.time()),
                }
            self._on_action_done(pid, res)
            self._futures.pop(pid, None)

    def _reload_config_if_needed(self):
        self.config = load_config()

class BundleGovernor:
    """
    Bundle 管理者 - 负责 Bundle 生命周期管理

    功能:
    1. 效能评估：定期评估每个 Bundle 的表现
    2. 自动暂停：低效能 Bundle 自动暂停
    3. 自动恢复：暂停的 Bundle 定期尝试恢复
    4. 淘汰机制：长期低效能 Bundle 被淘汰
    5. 状态追踪：记录 Bundle 生命周期状态
    """

    EFFICIENCY_PAUSE_THRESHOLD = 0.3
    EFFICIENCY_RETIRE_THRESHOLD = 0.15
    RECENT_FAILURE_THRESHOLD = 5
    PAUSE_CHECK_INTERVAL = 300
    AUTO_RESUME_INTERVAL = 1800
    RETIRE_AFTER_PAUSES = 3

    def __init__(self, bundles_path: Path):
        self.bundles_path = bundles_path
        self.lifecycle_states: Dict[str, BundleLifecycleState] = {}
        self.evaluation_history: Dict[str, List[BundleEvaluationResult]] = {}
        self.paused_bundles: Set[str] = set()
        self.retired_bundles: Set[str] = set()
        self._load_lifecycle_states()

    def _load_lifecycle_states(self):
        lifecycle_file = self.bundles_path / "_registry" / "lifecycle_states.json"
        if lifecycle_file.exists():
            try:
                with open(lifecycle_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for bundle_id, state_data in data.items():
                    self.lifecycle_states[bundle_id] = BundleLifecycleState(**state_data)
            except Exception as e:
                print(f"[BundleGovernor] Failed to load lifecycle states: {e}")

    def _save_lifecycle_states(self):
        lifecycle_file = self.bundles_path / "_registry" / "lifecycle_states.json"
        lifecycle_file.parent.mkdir(parents=True, exist_ok=True)

        data = {}
        for bundle_id, state in self.lifecycle_states.items():
            data[bundle_id] = {
                "bundle_id": state.bundle_id,
                "state": state.state,
                "created_at": state.created_at,
                "last_execution": state.last_execution,
                "pause_reason": state.pause_reason,
                "retire_reason": state.retire_reason,
                "pause_count": state.pause_count,
                "total_runtime_seconds": state.total_runtime_seconds,
            }

        with open(lifecycle_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def register_bundle(self, bundle_id: str):
        if bundle_id not in self.lifecycle_states:
            now = time.time()
            self.lifecycle_states[bundle_id] = BundleLifecycleState(
                bundle_id=bundle_id,
                state="active",
                created_at=now,
                last_execution=now,
            )
            self._save_lifecycle_states()

    def evaluate_bundle_performance(self, bundle_id: str) -> BundleEvaluationResult:
        bundle_path = self.bundles_path / bundle_id
        memory_dir = bundle_path / "memory"

        execution_history = self._load_jsonl(memory_dir / "execution_history.jsonl")
        eval_results = self._load_jsonl(memory_dir / "eval_results.jsonl")
        optimization_records = self._load_jsonl(memory_dir / "optimization_records.jsonl")

        total_executions = len(execution_history)
        if total_executions == 0:
            return BundleEvaluationResult(
                bundle_id=bundle_id,
                efficiency_score=0.5,
                success_rate=0.5,
                avg_execution_time=0.0,
                total_executions=0,
                recent_failures=0,
                value_output_score=0.5,
                resource_efficiency_score=0.5,
                recommendation="keep",
            )

        success_count = sum(1 for e in eval_results if e.get("grade", "C") in ["A", "B"])
        success_rate = success_count / max(1, len(eval_results))

        avg_execution_time = self._compute_avg_execution_time(execution_history)
        time_score = self._compute_time_score(avg_execution_time)

        skill_generated = len(optimization_records)
        problems_solved = sum(1 for e in eval_results if e.get("grade") == "A")
        value_score = min(1.0, (skill_generated * 0.5 + problems_solved) / max(1, total_executions))

        recent_failures = self._count_recent_failures(eval_results, last_n=5)
        resource_score = max(0.0, 1.0 - (recent_failures / 5))

        efficiency_score = (
            success_rate * 0.3 +
            time_score * 0.2 +
            value_score * 0.3 +
            resource_score * 0.2
        )

        recommendation = self._generate_recommendation(efficiency_score, recent_failures, total_executions)

        result = BundleEvaluationResult(
            bundle_id=bundle_id,
            efficiency_score=efficiency_score,
            success_rate=success_rate,
            avg_execution_time=avg_execution_time,
            total_executions=total_executions,
            recent_failures=recent_failures,
            value_output_score=value_score,
            resource_efficiency_score=resource_score,
            recommendation=recommendation,
        )

        if bundle_id not in self.evaluation_history:
            self.evaluation_history[bundle_id] = []
        self.evaluation_history[bundle_id].append(result)

        return result

    def _load_jsonl(self, path: Path) -> List[Dict]:
        if not path.exists():
            return []
        records = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except Exception:
            pass
        return records

    def _compute_avg_execution_time(self, execution_history: List[Dict]) -> float:
        times = []
        for record in execution_history:
            if "execution_time" in record:
                times.append(record["execution_time"])
            elif "start_ts" in record and "end_ts" in record:
                times.append(record["end_ts"] - record["start_ts"])
        return sum(times) / len(times) if times else 0.0

    def _compute_time_score(self, avg_time: float) -> float:
        if avg_time == 0:
            return 0.5
        if avg_time < 30:
            return 1.0
        if avg_time < 180:
            return 0.8
        if avg_time < 600:
            return 0.5
        return 0.2

    def _count_recent_failures(self, eval_results: List[Dict], last_n: int = 5) -> int:
        recent = eval_results[-last_n:] if len(eval_results) >= last_n else eval_results
        return sum(1 for e in recent if e.get("grade", "C") in ["C", "D"])

    def _generate_recommendation(self, efficiency_score: float, recent_failures: int, total_executions: int) -> str:
        if efficiency_score < self.EFFICIENCY_RETIRE_THRESHOLD:
            return "retire"
        if efficiency_score < self.EFFICIENCY_PAUSE_THRESHOLD or recent_failures >= self.RECENT_FAILURE_THRESHOLD:
            return "pause"
        if efficiency_score < 0.5:
            return "optimize"
        return "keep"

    def should_execute(self, bundle_id: str) -> bool:
        if bundle_id in self.retired_bundles:
            return False
        if bundle_id in self.paused_bundles:
            state = self.lifecycle_states.get(bundle_id)
            if state and state.state == "paused":
                last_exec = state.last_execution
                if time.time() - last_exec >= self.AUTO_RESUME_INTERVAL:
                    return self._try_resume_bundle(bundle_id)
            return False
        return True

    def pause_bundle(self, bundle_id: str, reason: str = "low_efficiency"):
        if bundle_id in self.paused_bundles:
            return

        self.paused_bundles.add(bundle_id)
        state = self.lifecycle_states.get(bundle_id)
        if state:
            state.state = "paused"
            state.pause_reason = reason
            state.pause_count += 1
            self._save_lifecycle_states()

        print(f"[BundleGovernor] Paused bundle: {bundle_id} (reason: {reason})")

        if state and state.pause_count >= self.RETIRE_AFTER_PAUSES:
            self.retire_bundle(bundle_id, "too_many_pauses")

    def retire_bundle(self, bundle_id: str, reason: str = "low_efficiency"):
        self.retired_bundles.add(bundle_id)
        if bundle_id in self.paused_bundles:
            self.paused_bundles.remove(bundle_id)

        state = self.lifecycle_states.get(bundle_id)
        if state:
            state.state = "retired"
            state.retire_reason = reason
            self._save_lifecycle_states()

        print(f"[BundleGovernor] Retired bundle: {bundle_id} (reason: {reason})")

    def _try_resume_bundle(self, bundle_id: str) -> bool:
        if bundle_id in self.evaluation_history:
            recent_evals = self.evaluation_history[bundle_id][-3:]
            if recent_evals:
                avg_score = sum(e.efficiency_score for e in recent_evals) / len(recent_evals)
                if avg_score >= self.EFFICIENCY_PAUSE_THRESHOLD + 0.1:
                    self.paused_bundles.discard(bundle_id)
                    state = self.lifecycle_states.get(bundle_id)
                    if state:
                        state.state = "active"
                        state.pause_reason = None
                        self._save_lifecycle_states()
                    print(f"[BundleGovernor] Auto-resumed bundle: {bundle_id}")
                    return True
        return False

    def run_evaluation_cycle(self, bundles: Dict[str, Any]) -> List[BundleEvaluationResult]:
        results = []
        for bundle_id in bundles:
            if bundle_id in self.retired_bundles:
                continue
            eval_result = self.evaluate_bundle_performance(bundle_id)
            results.append(eval_result)

            if eval_result.recommendation == "pause":
                self.pause_bundle(bundle_id, "low_efficiency")
            elif eval_result.recommendation == "retire":
                self.retire_bundle(bundle_id, "low_efficiency")
            elif eval_result.recommendation == "optimize":
                print(f"[BundleGovernor] Bundle {bundle_id} needs optimization (score: {eval_result.efficiency_score:.2f})")

        return results

    def get_bundle_status(self, bundle_id: str) -> Dict[str, Any]:
        state = self.lifecycle_states.get(bundle_id)
        if not state:
            return {"state": "unknown"}

        return {
            "state": state.state,
            "created_at": state.created_at,
            "last_execution": state.last_execution,
            "pause_count": state.pause_count,
            "pause_reason": state.pause_reason,
            "retire_reason": state.retire_reason,
            "total_runtime_seconds": state.total_runtime_seconds,
            "is_paused": bundle_id in self.paused_bundles,
            "is_retired": bundle_id in self.retired_bundles,
        }

    def get_all_statuses(self) -> Dict[str, Dict[str, Any]]:
        return {
            bundle_id: self.get_bundle_status(bundle_id)
            for bundle_id in self.lifecycle_states
        }
