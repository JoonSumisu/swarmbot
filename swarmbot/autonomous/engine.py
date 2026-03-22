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
from ..loops.overthinking import OverthinkingLoop
from ..loops.overaction import OveractionLoop
from ..memory.cold_memory import ColdMemory
from ..swarm.manager import SwarmManager


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
    def __init__(self, bundle_id: str, interval_seconds: int):
        self.bundle_id = bundle_id
        self.interval_seconds = max(10, interval_seconds)
        self.last_run = 0

    def due(self, now_ts: int) -> bool:
        return now_ts - self.last_run >= self.interval_seconds

    def mark(self, now_ts: int):
        self.last_run = now_ts

    def check(self, now_ts: int) -> MonitorQueueItem | None:
        return None


class _MemoryFoundationBundle(_Bundle):
    def check(self, now_ts: int) -> MonitorQueueItem | None:
        if not self.due(now_ts):
            return None
        self.mark(now_ts)
        eid = str(uuid.uuid4())
        return MonitorQueueItem(
            event_id=eid,
            bundle_id=self.bundle_id,
            source="core",
            kind="memory_foundation",
            severity="medium",
            detected_at=now_ts,
            evidence={"reason": "periodic_memory_foundation"},
            idempotency_key=f"{self.bundle_id}:{now_ts}",
        )


class _BootOptimizerBundle(_Bundle):
    def check(self, now_ts: int) -> MonitorQueueItem | None:
        if not self.due(now_ts):
            return None
        self.mark(now_ts)
        eid = str(uuid.uuid4())
        return MonitorQueueItem(
            event_id=eid,
            bundle_id=self.bundle_id,
            source="core",
            kind="boot_optimize",
            severity="low",
            detected_at=now_ts,
            evidence={"reason": "periodic_boot_optimize"},
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
    def __init__(self, bundle_id: str, interval_seconds: int, index_file: str):
        super().__init__(bundle_id, interval_seconds)
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
        self.cold = ColdMemory()
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

    def _build_bundles(self) -> List[_Bundle]:
        monitor = getattr(self.config.autonomous, "monitor", {}) or {}
        registry = getattr(self.config.autonomous, "bundle_registry", {}) or {}
        bundles: List[_Bundle] = []
        mem_cfg = monitor.get("memory_organizer", {}) if isinstance(monitor, dict) else {}
        boot_cfg = monitor.get("long_task_reporter", {}) if isinstance(monitor, dict) else {}
        sys_cfg = monitor.get("system_health", {}) if isinstance(monitor, dict) else {}
        bundles.append(_MemoryFoundationBundle("core.memory_foundation", int(mem_cfg.get("interval_minutes", 30)) * 60))
        bundles.append(_BootOptimizerBundle("core.boot_optimizer", int(boot_cfg.get("interval_minutes", 20)) * 60))
        bundles.append(
            _SystemHygieneBundle(
                "core.system_hygiene",
                int(sys_cfg.get("interval_minutes", 10)) * 60,
                float(sys_cfg.get("disk_free_ratio_threshold", 0.1)),
                float(sys_cfg.get("mem_free_ratio_threshold", 0.1)),
            )
        )
        bundles.append(
            _BundleGovernorBundle(
                "core.bundle_governor",
                max(60, int(boot_cfg.get("interval_minutes", 5)) * 60),
                str(registry.get("index_file", "~/.swarmbot/bundles/_registry/bundles_index.jsonl")),
            )
        )
        return bundles

    def start(self):
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
        for b in self.bundles:
            item = b.check(now_ts)
            if item is not None:
                self.monitor_queue.append(item)

    def _build_task_list(self, item: MonitorQueueItem) -> List[Dict[str, Any]]:
        if item.kind == "memory_foundation":
            return [
                {
                    "task_id": f"{item.event_id}-t1",
                    "title": "整理近期记忆并提炼事实经验理论",
                    "acceptance": "写入Warm/QMD并产出可追溯摘要",
                    "priority": "high",
                    "depends_on": [],
                    "required_capability": "memory.compact",
                    "status": "pending",
                }
            ]
        if item.kind == "system_hygiene":
            return [
                {
                    "task_id": f"{item.event_id}-t1",
                    "title": "执行系统健康诊断",
                    "acceptance": "输出关键资源诊断结论",
                    "priority": "high",
                    "depends_on": [],
                    "required_capability": "system.diagnose",
                    "status": "pending",
                },
                {
                    "task_id": f"{item.event_id}-t2",
                    "title": "生成可执行修复建议",
                    "acceptance": "建议可直接转成后续动作",
                    "priority": "medium",
                    "depends_on": [f"{item.event_id}-t1"],
                    "required_capability": "analysis.plan",
                    "status": "pending",
                },
            ]
        if item.kind == "bundle_governance":
            return [
                {
                    "task_id": f"{item.event_id}-t1",
                    "title": "检测Bundle重复冲突并给出合并建议",
                    "acceptance": "输出保留合并冻结待审建议",
                    "priority": "high",
                    "depends_on": [],
                    "required_capability": "bundle.govern",
                    "status": "pending",
                }
            ]
        if item.kind == "boot_optimize":
            return [
                {
                    "task_id": f"{item.event_id}-t1",
                    "title": "评估并优化boot提示词",
                    "acceptance": "输出更新建议与风险评估",
                    "priority": "medium",
                    "depends_on": [],
                    "required_capability": "prompt.optimize",
                    "status": "pending",
                }
            ]
        return [
            {
                "task_id": f"{item.event_id}-t1",
                "title": "执行通用自治任务",
                "acceptance": "生成可验证结果",
                "priority": "medium",
                "depends_on": [],
                "required_capability": "general.execute",
                "status": "pending",
            }
        ]

    def _choose_swarm_mode(self, task_list: List[Dict[str, Any]], severity: str) -> str:
        if severity in ["high", "critical"] or len(task_list) > 1:
            return "swarms"
        return "single_agent"

    def _select_architecture(self, mode: str, task_list: List[Dict[str, Any]]) -> str:
        if mode != "swarms":
            return "auto"
        if len(task_list) >= 3:
            return "tree"
        if len(task_list) == 2:
            return "pipeline"
        return "auto"

    def _swarm_profile(self, mode: str, task_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        se = getattr(self.config.autonomous, "swarm_execution", {}) or {}
        mn = int(se.get("worker_min", 1))
        mx = int(se.get("worker_max", 10))
        workers = 1 if mode == "single_agent" else min(mx, max(mn, len(task_list) + 1))
        return {
            "mode": mode,
            "workers": max(1, min(10, workers)),
            "architecture": self._select_architecture(mode, task_list),
            "max_turns": 16,
            "role_selection_mode": "self_select_by_tasklist",
        }

    def _to_action_type(self, kind: str) -> str:
        if kind in ["bundle_governance"]:
            return "update_bundle"
        if kind in ["memory_foundation", "boot_optimize"]:
            return "loop_optimize"
        return "execute_task"

    def _enqueue_action(self, item: ActionQueueItem):
        if item.plan_id in self.action_queue:
            return
        while len(self._action_order) >= self._action_capacity:
            drop_id = self._action_order.popleft()
            self.action_queue.pop(drop_id, None)
        self._action_order.append(item.plan_id)
        self.action_queue[item.plan_id] = item

    def _decision_from_monitor(self):
        while self.monitor_queue:
            m = self.monitor_queue.popleft()
            task_list = self._build_task_list(m)
            mode = self._choose_swarm_mode(task_list, m.severity)
            profile = self._swarm_profile(mode, task_list)
            plan_id = str(uuid.uuid4())
            aq = ActionQueueItem(
                plan_id=plan_id,
                event_id=m.event_id,
                bundle_id=m.bundle_id,
                kind=m.kind,
                action_type=self._to_action_type(m.kind),
                task_list=task_list,
                swarm_profile=profile,
                risk_level="L2" if m.severity in ["high", "critical"] else "L1",
                budget={"max_seconds": 600, "max_retry": self._max_retry},
                deadline_ts=int(time.time()) + 1200,
                retry_policy={"max_retries": self._max_retry},
                approval_required=m.severity in ["critical"],
                idempotency_key=m.idempotency_key,
            )
            self._enqueue_action(aq)

    def _roles_from_task_list(self, task_list: List[Dict[str, Any]]) -> List[str]:
        roles: List[str] = []
        for t in task_list:
            cap = str(t.get("required_capability", "general")).lower()
            if "memory" in cap:
                roles.append("memory_analyst")
            elif "diagnose" in cap or "system" in cap:
                roles.append("ops_diagnoser")
            elif "bundle" in cap:
                roles.append("governance_auditor")
            elif "prompt" in cap:
                roles.append("prompt_optimizer")
            elif "analysis" in cap:
                roles.append("analyst")
            else:
                roles.append("executor")
        uniq = []
        for r in roles:
            if r not in uniq:
                uniq.append(r)
        return uniq or ["executor"]

    def _swarm_arch_map(self, arch: str) -> str:
        m = {"auto": "auto", "tree": "hierarchical", "mesh": "group_chat", "pipeline": "sequential"}
        return m.get(arch, "auto")

    def _build_swarms_prompt(self, action: ActionQueueItem) -> str:
        return (
            "你是Autonomous Action执行集群。请基于任务清单执行并返回结构化结果。\n"
            f"kind={action.kind}\n"
            f"action_type={action.action_type}\n"
            f"task_list={json.dumps(action.task_list, ensure_ascii=False)}\n"
            f"evidence={json.dumps(action.action_result.get('trigger', {}), ensure_ascii=False)}\n"
            "输出JSON: {\"ok\":true,\"summary\":\"...\",\"details\":\"...\",\"next_suggestion\":\"...\"}"
        )

    def _execute_with_swarms(self, action: ActionQueueItem) -> Dict[str, Any]:
        mgr = self._get_swarm_manager()
        sid = f"autonomous-{action.plan_id[:8]}"
        session = mgr.get_session(sid)
        session.architecture = self._swarm_arch_map(str(action.swarm_profile.get("architecture", "auto")))
        session.resize_swarm(int(action.swarm_profile.get("workers", 1)))
        session.reassign_roles(self._roles_from_task_list(action.task_list))
        prompt = self._build_swarms_prompt(action)
        response = mgr.chat(prompt, session_id=sid)
        return {"ok": bool(str(response).strip()), "summary": "swarms_executed", "details": str(response)}

    def _run_bundle_governance(self) -> Dict[str, Any]:
        for b in self.bundles:
            if isinstance(b, _BundleGovernorBundle):
                issues = b._scan_issues()
                return {"ok": True, "summary": "bundle_governance_scanned", "issues": issues[:30], "issue_count": len(issues)}
        return {"ok": True, "summary": "bundle_governance_no_bundle", "issues": [], "issue_count": 0}

    def _execute_single(self, action: ActionQueueItem) -> Dict[str, Any]:
        if action.kind == "memory_foundation":
            OverthinkingLoop(threading.Event())._process_cycle()
            return {"ok": True, "summary": "memory_foundation_done"}
        if action.kind == "system_hygiene":
            payload = {"title": "system-hygiene", "summary": json.dumps(action.action_result.get("trigger", {}), ensure_ascii=False)}
            result = OveractionLoop(threading.Event()).trigger(reason="autonomous_system_hygiene", events=[payload])
            return {"ok": True, "summary": "system_hygiene_done", "result": result}
        if action.kind == "boot_optimize":
            result = OveractionLoop(threading.Event()).trigger(reason="autonomous_boot_optimize", events=[{"title": "boot-optimize", "summary": "optimize boot prompts"}])
            return {"ok": True, "summary": "boot_optimize_done", "result": result}
        if action.kind == "bundle_governance":
            return self._run_bundle_governance()
        return {"ok": False, "summary": "unknown_kind"}

    def _run_action(self, action: ActionQueueItem) -> Dict[str, Any]:
        started = int(time.time())
        progress = [{"ts": started, "event": "running.stage_changed", "stage": "start"}]
        if action.action_type == "gateway_report":
            msg = {
                "ts": int(time.time()),
                "plan_id": action.plan_id,
                "bundle_id": action.bundle_id,
                "content": action.action_result.get("report", ""),
            }
            self._append_gateway_report(msg)
            progress.append({"ts": int(time.time()), "event": "completed", "stage": "gateway_report"})
            return {
                "state": "succeeded",
                "action_result": {"ok": True, "summary": "gateway_report_done", "message": msg},
                "eval_result": {"pass": True, "reason": "reported"},
                "progress_events": progress,
                "reported_to_gateway": True,
                "finished_at": int(time.time()),
            }
        try:
            if str(action.swarm_profile.get("mode")) == "swarms":
                res = self._execute_with_swarms(action)
            else:
                res = self._execute_single(action)
            ok = bool(res.get("ok"))
            progress.append({"ts": int(time.time()), "event": "completed" if ok else "failed", "stage": "execution"})
            return {
                "state": "succeeded" if ok else "failed",
                "action_result": res,
                "eval_result": {"pass": ok, "reason": "ok" if ok else "execution_failed"},
                "progress_events": progress,
                "reported_to_gateway": False,
                "finished_at": int(time.time()),
            }
        except Exception as e:
            progress.append({"ts": int(time.time()), "event": "failed", "stage": "exception"})
            return {
                "state": "failed",
                "action_result": {"ok": False, "summary": str(e)},
                "eval_result": {"pass": False, "reason": "exception"},
                "progress_events": progress,
                "reported_to_gateway": False,
                "finished_at": int(time.time()),
            }

    def _decide_feedback(self, action: ActionQueueItem) -> Dict[str, Any]:
        retry_count = int(action.decision_feedback.get("retry_count", 0))
        if action.state == "succeeded":
            if action.action_type == "gateway_report":
                return {"next_action": "complete", "reason": "gateway_report_done", "retry_count": retry_count, "new_plan_required": False, "archive_required": True}
            return {"next_action": "complete", "reason": "task_done", "retry_count": retry_count, "new_plan_required": False, "archive_required": True}
        if retry_count < int(action.retry_policy.get("max_retries", self._max_retry)):
            return {"next_action": "retry", "reason": "retry_within_budget", "retry_count": retry_count + 1, "new_plan_required": False, "archive_required": False}
        return {"next_action": "escalate", "reason": "retry_exhausted", "retry_count": retry_count, "new_plan_required": True, "archive_required": True}

    def _enqueue_gateway_report(self, action: ActionQueueItem):
        summary = action.action_result.get("summary") or action.eval_result.get("reason") or "action_done"
        plan_id = str(uuid.uuid4())
        report = ActionQueueItem(
            plan_id=plan_id,
            event_id=action.event_id,
            bundle_id=action.bundle_id,
            kind=action.kind,
            action_type="gateway_report",
            task_list=[],
            swarm_profile={"mode": "single_agent", "workers": 1, "architecture": "auto", "max_turns": 1, "role_selection_mode": "self_select_by_tasklist"},
            risk_level="L0",
            budget={"max_seconds": 60},
            deadline_ts=int(time.time()) + 120,
            retry_policy={"max_retries": 0},
            approval_required=False,
            idempotency_key=f"gateway_report:{action.plan_id}",
            action_result={"report": f"[Autonomous] bundle={action.bundle_id} kind={action.kind} summary={summary}"},
        )
        self._enqueue_action(report)

    def _on_action_done(self, plan_id: str, result: Dict[str, Any]):
        action = self.action_queue.get(plan_id)
        if action is None:
            return
        action.state = str(result.get("state", "failed"))
        action.action_result = dict(result.get("action_result") or {})
        action.eval_result = dict(result.get("eval_result") or {})
        action.progress_events = list(result.get("progress_events") or [])
        action.reported_to_gateway = bool(result.get("reported_to_gateway", False))
        action.decision_feedback = self._decide_feedback(action)
        row = {
            "ts": int(time.time()),
            "plan_id": action.plan_id,
            "bundle_id": action.bundle_id,
            "kind": action.kind,
            "action_type": action.action_type,
            "state": action.state,
            "next_action": action.decision_feedback.get("next_action"),
            "summary": action.action_result.get("summary", ""),
        }
        self._log_diag(row)
        self.cold.add(
            content=f"autonomous_action plan={action.plan_id} bundle={action.bundle_id} kind={action.kind} type={action.action_type} state={action.state} next={action.decision_feedback.get('next_action')}",
            meta={"source": "autonomous_engine", "collection": "autonomous"},
        )
        nxt = action.decision_feedback.get("next_action")
        if nxt == "retry":
            retry_item = copy.deepcopy(action)
            retry_item.plan_id = str(uuid.uuid4())
            retry_item.state = "planned"
            retry_item.progress_events = []
            retry_item.action_result = {}
            retry_item.eval_result = {}
            retry_item.decision_feedback = {"retry_count": int(action.decision_feedback.get("retry_count", 0))}
            self._enqueue_action(retry_item)
        elif nxt == "complete" and action.action_type != "gateway_report":
            self._enqueue_gateway_report(action)

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

    def _loop(self):
        tick = max(5, int(getattr(self.config.autonomous, "tick_seconds", 30)))
        while not self.stop_event.is_set():
            self._reload_config_if_needed()
            now_ts = int(time.time())
            self._flush_done()
            self._collect_monitor_events(now_ts)
            self._decision_from_monitor()
            self._dispatch_actions()
            if self.stop_event.wait(tick):
                break


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
