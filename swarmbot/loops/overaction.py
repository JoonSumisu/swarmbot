import threading
import time
import os
import json
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from ..core.agent import CoreAgent, AgentContext
from ..llm_client import OpenAICompatibleClient
from ..memory.hot_memory import HotMemory
from ..memory.warm_memory import WarmMemory
from ..memory.cold_memory import ColdMemory
from ..config_manager import load_config
from .definitions import OVERACTION_REFINE_PROMPT, OVERACTION_OPT_PROMPT

class OveractionLoop:
    def __init__(self, stop_event: threading.Event):
        self.stop_event = stop_event
        self.config = load_config()
        workspace = getattr(self.config, "workspace_path", os.path.expanduser("~/.swarmbot/workspace"))
        self.workspace = workspace
        self.over_cfg = getattr(self.config, "overaction", None)
        self.hot_memory = HotMemory(workspace)
        self.warm_memory = WarmMemory(workspace)
        self.cold_memory = ColdMemory()
        self.llm = OpenAICompatibleClient.from_provider(providers=self.config.providers)
        self.agent = CoreAgent(
            AgentContext(
                "overactor",
                "Overaction Agent",
                skills={"web_search": True, "python_exec": True, "file_read": True, "hot_memory_update": True},
            ),
            self.llm,
            self.cold_memory,
            hot_memory=self.hot_memory
        )
        self._schedule_state_path = Path(self.workspace) / "overaction_schedule_state.json"
        self._diag_log_path = Path(self.workspace) / "logs" / "conversation_metrics.jsonl"
        self._outbox_path = Path(self.workspace) / "proactive_outbox.jsonl"
        self._delivery_state_path = Path(self.workspace) / "proactive_delivery_state.json"
        self._cycle_delivery_count = 0

    def start(self):
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()
        print("[Overaction] Loop started.")

    def stop(self):
        self.stop_event.set()

    def _loop(self):
        while not self.stop_event.is_set():
            self.config = load_config()
            self.over_cfg = getattr(self.config, "overaction", None)
            if self.over_cfg is not None and not getattr(self.over_cfg, "enabled", True):
                if self.stop_event.wait(30):
                    break
                continue
            interval = 3600
            if self.over_cfg is not None:
                try:
                    interval = max(60, int(getattr(self.over_cfg, "interval_minutes", 60)) * 60)
                except:
                    interval = 3600
            if self.stop_event.wait(interval):
                break
            try:
                self._process_cycle(reason="scheduled")
            except Exception as e:
                print(f"[Overaction] Error: {e}")

    def trigger(self, reason: str = "manual", events: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        return self._process_cycle(reason=reason, events=events or [])

    def _append_hot_note(self, note: str) -> None:
        if not note:
            return
        current = self.hot_memory.read()
        if note in current:
            return
        self.hot_memory.update(current + f"\n\n### Overaction Note\n- {note}")

    def _load_delivery_state(self) -> Dict[str, Any]:
        try:
            if self._delivery_state_path.exists():
                return json.loads(self._delivery_state_path.read_text(encoding="utf-8"))
        except:
            pass
        return {"last_announce_ts": 0}

    def _save_delivery_state(self, state: Dict[str, Any]) -> None:
        try:
            self._delivery_state_path.parent.mkdir(parents=True, exist_ok=True)
            self._delivery_state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except:
            pass

    def _in_quiet_hours(self, spec: str, now_dt: datetime.datetime) -> bool:
        try:
            a, b = [x.strip() for x in str(spec).split("-", 1)]
            ah, am = [int(x) for x in a.split(":")]
            bh, bm = [int(x) for x in b.split(":")]
            cur = now_dt.hour * 60 + now_dt.minute
            start = ah * 60 + am
            end = bh * 60 + bm
            if start <= end:
                return start <= cur < end
            return cur >= start or cur < end
        except:
            return False

    def _append_proactive_outbox(self, message: str, reason: str, channel: str = "default", priority: str = "normal") -> bool:
        cfg = self.over_cfg
        policy = getattr(cfg, "proactive_delivery", {}) if cfg is not None else {}
        if not bool(policy.get("enabled", True)):
            return False
        now_dt = datetime.datetime.now()
        if self._in_quiet_hours(str(policy.get("quiet_hours", "23:00-08:00")), now_dt):
            return False
        max_per_cycle = int(policy.get("max_per_cycle", 2))
        if self._cycle_delivery_count >= max(1, max_per_cycle):
            return False
        state = self._load_delivery_state()
        now_ts = int(time.time())
        min_interval = int(policy.get("min_interval_minutes", 30)) * 60
        last_ts = int(state.get("last_announce_ts", 0))
        if now_ts - last_ts < max(0, min_interval):
            return False
        payload = {
            "ts": now_ts,
            "channel": channel,
            "priority": priority,
            "reason": reason,
            "message": message.strip(),
        }
        try:
            self._outbox_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._outbox_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            state["last_announce_ts"] = now_ts
            self._save_delivery_state(state)
            self._cycle_delivery_count += 1
            return True
        except:
            return False

    def _load_schedule_state(self) -> Dict[str, Any]:
        try:
            if self._schedule_state_path.exists():
                return json.loads(self._schedule_state_path.read_text(encoding="utf-8"))
        except:
            pass
        return {"last_run": {}}

    def _save_schedule_state(self, state: Dict[str, Any]) -> None:
        try:
            self._schedule_state_path.parent.mkdir(parents=True, exist_ok=True)
            self._schedule_state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except:
            pass

    def _task_due(self, task: Dict[str, Any], now_ts: int, state: Dict[str, Any]) -> bool:
        sched = task.get("schedule") if isinstance(task.get("schedule"), dict) else {}
        kind = str(sched.get("kind") or "").lower()
        name = str(task.get("name") or f"task_{abs(hash(json.dumps(task, ensure_ascii=False, sort_keys=True))) % 100000}")
        last_run = int(state.get("last_run", {}).get(name, 0))
        if kind == "every":
            every_ms = int(sched.get("everyMs") or 0)
            if every_ms <= 0:
                return False
            return (now_ts * 1000 - last_run * 1000) >= every_ms
        if kind == "at":
            at_raw = str(sched.get("at") or "").strip()
            if not at_raw:
                return False
            try:
                at_ts = int(datetime.datetime.fromisoformat(at_raw.replace("Z", "+00:00")).timestamp())
            except:
                return False
            return now_ts >= at_ts and last_run < at_ts
        if kind == "cron":
            expr = str(sched.get("expr") or "").strip()
            parts = expr.split()
            if len(parts) != 5:
                return False
            minute, hour, dom, mon, dow = parts
            now = datetime.datetime.now()
            checks = [
                minute in ["*", str(now.minute)],
                hour in ["*", str(now.hour)],
                dom in ["*", str(now.day)],
                mon in ["*", str(now.month)],
                dow in ["*", str((now.weekday() + 1) % 7)],
            ]
            if all(checks):
                return now_ts - last_run >= 50
            return False
        return False

    def _execute_scheduled_task(self, task: Dict[str, Any], cycle_result: Dict[str, Any]) -> Dict[str, Any]:
        payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
        delivery = task.get("delivery") if isinstance(task.get("delivery"), dict) else {}
        mode = str(delivery.get("mode") or "none")
        name = str(task.get("name") or "unnamed")
        kind = str(payload.get("kind") or "agentTurn")
        msg = str(payload.get("message") or "")
        output = {"name": name, "payload_kind": kind, "delivery": mode, "ok": True}
        if kind == "agentTurn" and msg:
            self._append_hot_note(f"调度任务触发[{name}]：{msg}")
            output["action"] = "hot_memory_note"
        else:
            self._append_hot_note(f"调度任务触发[{name}]")
        if mode == "announce":
            channel = str(delivery.get("channel") or "default")
            self._append_hot_note(f"调度交付[{name}] -> {channel}")
            output["announce_channel"] = channel
            announce_msg = msg or f"调度任务触发：{name}"
            output["announced"] = self._append_proactive_outbox(
                message=announce_msg,
                reason=f"scheduled:{name}",
                channel=channel,
                priority="normal",
            )
        elif mode == "webhook":
            output["webhook"] = str(delivery.get("url") or "")
        cycle_result.setdefault("scheduled_actions", []).append(output)
        return output

    def _run_task_scheduling(self, cycle_result: Dict[str, Any]) -> None:
        cfg = self.over_cfg
        if cfg is None:
            return
        tasks = list(getattr(cfg, "scheduled_tasks", []) or [])
        if not tasks:
            cycle_result["scheduled_actions"] = []
            return
        state = self._load_schedule_state()
        now_ts = int(time.time())
        due: List[Dict[str, Any]] = [t for t in tasks if isinstance(t, dict) and self._task_due(t, now_ts, state)]
        for task in due:
            name = str(task.get("name") or f"task_{abs(hash(json.dumps(task, ensure_ascii=False, sort_keys=True))) % 100000}")
            self._execute_scheduled_task(task, cycle_result)
            state.setdefault("last_run", {})[name] = now_ts
        self._save_schedule_state(state)
        cycle_result["scheduled_due_count"] = len(due)

    def _append_diag_metric(self, record: Dict[str, Any]) -> None:
        try:
            self._diag_log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._diag_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except:
            pass

    def _run_self_diagnosis(self, cycle_result: Dict[str, Any]) -> None:
        cfg = self.over_cfg
        enabled = bool(getattr(cfg, "self_diagnosis", {}).get("enabled", True)) if cfg is not None else True
        if not enabled:
            return
        now = int(time.time())
        hot = self.hot_memory.read()
        warm_files = self.warm_memory.list_files()
        record = {
            "ts": now,
            "hot_len": len(hot),
            "warm_files": len(warm_files),
            "disk_ratio": self._read_mem_available_ratio(),
            "mem_ratio": self._read_memory_available_ratio(),
        }
        self._append_diag_metric(record)
        retention_days = int(getattr(cfg, "self_diagnosis", {}).get("log_retention_days", 7)) if cfg is not None else 7
        try:
            if self._diag_log_path.exists():
                lines = self._diag_log_path.read_text(encoding="utf-8").splitlines()
                keep = []
                cutoff = now - retention_days * 86400
                for ln in lines[-2000:]:
                    try:
                        item = json.loads(ln)
                        if int(item.get("ts", 0)) >= cutoff:
                            keep.append(ln)
                    except:
                        pass
                self._diag_log_path.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
        except:
            pass
        cycle_result["self_diagnosis_metric"] = record

    def _last_interaction_hours(self) -> float:
        now = time.time()
        latest = 0.0
        hot_path = Path(self.workspace) / "hot_memory.md"
        if hot_path.exists():
            latest = max(latest, hot_path.stat().st_mtime)
        for f in self.warm_memory.list_files():
            try:
                latest = max(latest, f.stat().st_mtime)
            except:
                pass
        if latest <= 0:
            return 9999.0
        return (now - latest) / 3600.0

    def _read_mem_available_ratio(self) -> float:
        try:
            vm = os.statvfs(self.workspace)
            return float(vm.f_bavail) / max(1.0, float(vm.f_blocks))
        except:
            return 1.0

    def _read_memory_available_ratio(self) -> float:
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                text = f.read()
            kv = {}
            for line in text.splitlines():
                parts = line.split(":")
                if len(parts) >= 2:
                    kv[parts[0].strip()] = int(parts[1].strip().split()[0])
            total = float(kv.get("MemTotal", 0))
            avail = float(kv.get("MemAvailable", 0))
            if total <= 0:
                return 1.0
            return avail / total
        except:
            return 1.0

    def _extract_todos(self, hot_text: str) -> List[str]:
        todos: List[str] = []
        for line in (hot_text or "").splitlines():
            s = line.strip()
            if s.startswith("- [ ]"):
                todos.append(s)
        return todos

    def _run_proactive_checks(self, cycle_result: Dict[str, Any]) -> None:
        cfg = self.over_cfg
        if cfg is None:
            return
        interaction_timeout = int(getattr(cfg, "interaction_timeout_hours", 4))
        if bool(getattr(cfg, "check_interaction", True)):
            idle_hours = self._last_interaction_hours()
            cycle_result["idle_hours"] = round(idle_hours, 2)
            if idle_hours >= interaction_timeout:
                msg = f"检测到你已 {idle_hours:.1f} 小时未互动，我在这里，是否需要我帮你整理一下当前待办？"
                self._append_hot_note(f"长时间未交互({idle_hours:.1f}h)，建议生成一条简短关心消息。")
                self._append_proactive_outbox(msg, reason="idle_timeout", priority="normal")
        hot = self.hot_memory.read()
        if bool(getattr(cfg, "check_tasks", True)):
            todos = self._extract_todos(hot)
            cycle_result["pending_todo_count"] = len(todos)
            if len(todos) >= 3:
                self._append_hot_note(f"待办任务较多({len(todos)}项)，建议触发温和提醒并按优先级清理。")
                self._append_proactive_outbox(
                    f"你目前有 {len(todos)} 项待办，我可以先帮你按优先级排一个可执行顺序。",
                    reason="todo_backlog",
                    priority="normal",
                )
        if bool(getattr(cfg, "check_system", True)):
            disk_ratio = self._read_mem_available_ratio()
            mem_ratio = self._read_memory_available_ratio()
            cycle_result["disk_available_ratio"] = round(disk_ratio, 4)
            cycle_result["memory_available_ratio"] = round(mem_ratio, 4)
            if disk_ratio < 0.1:
                self._append_hot_note(f"磁盘可用率偏低({disk_ratio:.1%})，建议清理缓存或归档旧日志。")
                self._append_proactive_outbox(
                    f"系统提示：磁盘可用率仅 {disk_ratio:.1%}，建议尽快清理缓存或归档日志。",
                    reason="disk_low",
                    priority="high",
                )
            if mem_ratio < 0.1:
                self._append_hot_note(f"内存可用率偏低({mem_ratio:.1%})，建议降低并发并检查异常进程。")
                self._append_proactive_outbox(
                    f"系统提示：内存可用率仅 {mem_ratio:.1%}，建议降低并发并检查异常进程。",
                    reason="mem_low",
                    priority="high",
                )
        diag = {
            "warm_files": len(self.warm_memory.list_files()),
            "hot_memory_len": len(hot),
            "qmd_probe_len": len(self.cold_memory.search_text("insight", limit=3) or ""),
        }
        cycle_result["self_diagnosis"] = diag
        self._append_hot_note(f"系统自检完成: warm_files={diag['warm_files']}, hot_len={diag['hot_memory_len']}.")
        recent_insight = self.cold_memory.search_text("pattern insight summary", limit=5)
        if recent_insight:
            trimmed = str(recent_insight).strip()[:300]
            self._append_hot_note(f"近期洞察: {trimmed}")
            cycle_result["insight_shared"] = True
        else:
            cycle_result["insight_shared"] = False

    def _process_cycle(self, reason: str = "scheduled", events: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        print(f"[Overaction] Cycle: Refining and Self-Optimizing ({reason})...")
        self._cycle_delivery_count = 0
        cycle_result: Dict[str, Any] = {"reason": reason, "events": events or []}
        for e in events or []:
            title = str(e.get("title") or e.get("type") or "external_event")
            summary = str(e.get("summary") or "")
            self._append_hot_note(f"外部事件触发[{title}] {summary}".strip())
            if summary:
                self._append_proactive_outbox(
                    f"检测到外部事件：{title}。{summary}",
                    reason=f"external:{title}",
                    priority="high",
                )
        recent_qmd = self.cold_memory.search_text("recent facts", limit=10)
        refine_prompt = OVERACTION_REFINE_PROMPT.format(recent_qmd=recent_qmd)
        self.agent.step(refine_prompt)
        all_warm = self.warm_memory.list_files()
        today_str = time.strftime("%Y-%m-%d")
        cleaned_files = []
        for f in all_warm:
            if today_str not in f.name:
                print(f"[Overaction] Cleaning up old Warm Memory: {f.name}")
                self.warm_memory.delete_file(f.name)
                cleaned_files.append(f.name)
        cycle_result["cleaned_warm_files"] = cleaned_files
        opt_prompt = OVERACTION_OPT_PROMPT
        res = self.agent.step(opt_prompt)
        try:
            import re
            match = re.search(r"\{.*\}", res, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                if data.get("todo"):
                    self.hot_memory.append_todo(f"Self-Opt: {data['todo']}")
                    cycle_result["self_opt_todo"] = data["todo"]
                if data.get("boot_update"):
                    cycle_result["boot_update"] = data.get("boot_update")
        except:
            pass
        self._run_task_scheduling(cycle_result)
        self._run_self_diagnosis(cycle_result)
        self._run_proactive_checks(cycle_result)
        return cycle_result
