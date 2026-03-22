from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, Future

from .communication_hub import CommunicationHub, HubMessage, MessageSender, MessageType


@dataclass
class SubSwarmConfig:
    max_concurrent: int = 3
    timeout_seconds: int = 120
    heartbeat_interval_seconds: int = 5


@dataclass
class SubSwarmTask:
    task_id: str
    topic: str
    description: str
    tool_id: str
    priority: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SubSwarmResult:
    task_id: str
    topic: str
    success: bool
    content: str = ""
    error: Optional[str] = None
    execution_time: float = 0.0


class SubSwarmWorker(threading.Thread):
    def __init__(
        self,
        worker_id: str,
        task: SubSwarmTask,
        hub: CommunicationHub,
        swarm_id: str,
        session_id: str,
        executor_func: Callable[[str, str], str],
        timeout: int = 60,
    ):
        super().__init__(daemon=True)
        self.worker_id = worker_id
        self.task = task
        self.hub = hub
        self.swarm_id = swarm_id
        self.session_id = session_id
        self.executor_func = executor_func
        self.timeout = timeout
        self.start_time = 0.0
        self.result: Optional[SubSwarmResult] = None
        self._stop_event = threading.Event()

    def run(self):
        self.start_time = time.time()
        
        try:
            # 发送开始状态
            self.hub.send_subswarm_status(
                self.worker_id,
                f"开始执行任务: {self.task.description[:50]}...",
                self.session_id,
                self.swarm_id,
                self.task.topic,
                progress=0.1,
            )

            # 执行任务
            result_content = self.executor_func(self.task.description, self.task.task_id)
            
            execution_time = time.time() - self.start_time
            
            self.result = SubSwarmResult(
                task_id=self.task.task_id,
                topic=self.task.topic,
                success=True,
                content=result_content,
                execution_time=execution_time,
            )

            # 发送完成状态
            self.hub.send_subswarm_status(
                self.worker_id,
                f"任务完成: {self.task.description[:50]}",
                self.session_id,
                self.swarm_id,
                self.task.topic,
                progress=1.0,
            )

            # 发送结果
            self.hub.send_subswarm_result(
                self.worker_id,
                result_content,
                self.session_id,
                self.swarm_id,
                self.task.topic,
                success=True,
            )

        except Exception as e:
            execution_time = time.time() - self.start_time
            self.result = SubSwarmResult(
                task_id=self.task.task_id,
                topic=self.task.topic,
                success=False,
                error=str(e),
                execution_time=execution_time,
            )

            # 发送错误
            self.hub.send_subswarm_result(
                self.worker_id,
                f"任务执行失败: {str(e)}",
                self.session_id,
                self.swarm_id,
                self.task.topic,
                success=False,
                error=str(e),
            )

    def stop(self):
        self._stop_event.set()


class SubSwarmManager:
    def __init__(
        self,
        hub: CommunicationHub,
        session_id: str,
        config: Optional[SubSwarmConfig] = None,
    ):
        self.hub = hub
        self.session_id = session_id
        self.config = config or SubSwarmConfig()
        
        self.swarm_id = f"swarm-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        self.tasks: Dict[str, SubSwarmTask] = {}
        self.workers: Dict[str, SubSwarmWorker] = {}
        self.results: List[SubSwarmResult] = []
        self._executor = ThreadPoolExecutor(max_workers=self.config.max_concurrent)
        self._running = False
        self._lock = threading.Lock()

    def add_task(self, topic: str, description: str, tool_id: str = "standard", priority: int = 0, metadata: Optional[Dict] = None) -> str:
        task_id = f"task-{len(self.tasks)}-{uuid.uuid4().hex[:8]}"
        task = SubSwarmTask(
            task_id=task_id,
            topic=topic,
            description=description,
            tool_id=tool_id,
            priority=priority,
            metadata=metadata or {},
        )
        self.tasks[task_id] = task
        return task_id

    def dispatch(self, executor_func: Callable[[str, str], str]) -> Dict[str, Any]:
        with self._lock:
            self._running = True
            
            # 按优先级排序
            sorted_tasks = sorted(self.tasks.values(), key=lambda t: -t.priority)
            
            # 启动 workers
            for task in sorted_tasks:
                worker = SubSwarmWorker(
                    worker_id=f"worker-{task.task_id}",
                    task=task,
                    hub=self.hub,
                    swarm_id=self.swarm_id,
                    session_id=self.session_id,
                    executor_func=executor_func,
                    timeout=self.config.timeout_seconds,
                )
                self.workers[task.task_id] = worker
                worker.start()
        
        return {"swarm_id": self.swarm_id, "task_count": len(self.tasks)}

    def wait_for_completion(self, timeout: Optional[int] = None) -> List[SubSwarmResult]:
        timeout = timeout or self.config.timeout_seconds
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            with self._lock:
                all_done = all(not w.is_alive() for w in self.workers.values())
                if all_done:
                    break
            
            # 检查心跳
            status = self.hub.get_swarm_status(self.swarm_id, self.session_id)
            
            # 检查是否有协调请求需要处理
            coords = self.hub.get_coordination_requests(self.swarm_id, self.session_id)
            if coords:
                for coord in coords:
                    if not coord.consumed:
                        yield_coord_request(coord)
                        self.hub.mark_consumed(coord.msg_id)
            
            time.sleep(0.5)
        
        # 收集结果
        self.results = []
        for worker in self.workers.values():
            if worker.result:
                self.results.append(worker.result)
        
        self._running = False
        return self.results

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            alive = sum(1 for w in self.workers.values() if w.is_alive())
            completed = sum(1 for w in self.workers.values() if w.result is not None)
            total = len(self.workers)
        
        hub_status = self.hub.get_swarm_status(self.swarm_id, self.session_id)
        
        return {
            "swarm_id": self.swarm_id,
            "total_tasks": total,
            "completed": completed,
            "alive_workers": alive,
            "results_collected": len(self.results),
            **hub_status,
        }

    def stop(self):
        for worker in self.workers.values():
            worker.stop()
        self._executor.shutdown(wait=False)
        self._running = False

    def group_results_by_topic(self) -> Dict[str, List[SubSwarmResult]]:
        grouped: Dict[str, List[SubSwarmResult]] = {}
        for result in self.results:
            if result.topic not in grouped:
                grouped[result.topic] = []
            grouped[result.topic].append(result)
        return grouped


def yield_coord_request(coord_msg: HubMessage):
    pass
