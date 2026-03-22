from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class MessageType(str, Enum):
    TASK_REQUEST = "task_request"
    TASK_RESULT = "task_result"
    SUSPEND_REQUEST = "suspend_request"
    RESUME_REQUEST = "resume_request"
    AUTONOMOUS_REQUEST = "autonomous_request"
    AUTONOMOUS_STATUS = "autonomous_status"
    AUTONOMOUS_RESULT = "autonomous_result"
    HUMAN_IN_LOOP_REQUEST = "human_in_loop_request"
    HUMAN_IN_LOOP_RESPONSE = "human_in_loop_response"
    USER_FEEDBACK = "user_feedback"
    SYSTEM_INFO = "system_info"
    SUBSWARM_REQUEST = "subswarm_request"
    SUBSWARM_RESULT = "subswarm_result"
    SUBSWARM_STATUS = "subswarm_status"
    COORDINATION_REQUEST = "coordination_request"
    HEARTBEAT = "heartbeat"


class MessageSender(str, Enum):
    MASTER_AGENT = "master_agent"
    INFERENCE_TOOL = "inference_tool"
    AUTONOMOUS = "autonomous"
    USER = "user"
    SUBSWARM = "subswarm"
    COORDINATOR = "coordinator"


@dataclass
class HubMessage:
    msg_id: str
    msg_type: MessageType
    sender: MessageSender
    recipient: str
    content: str
    session_id: str = ""
    topic: str = ""  # Topic for organizing related messages
    swarm_id: str = ""  # Swarm group ID for coordinating multiple subswarms
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: int = field(default_factory=lambda: int(time.time()))
    consumed: bool = False
    consumed_at: int = 0


class CommunicationHub:
    def __init__(self, workspace_path: str):
        self.workspace_path = Path(workspace_path)
        self._messages_file = self.workspace_path / "hub_messages.jsonl"
        self._read_pos = 0
        self._write_lock = threading.Lock()
        self._read_lock = threading.Lock()
        self._id_counter = 0
        self._ensure_file()

    def _ensure_file(self):
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        if not self._messages_file.exists():
            self._messages_file.touch()

    def _generate_id(self) -> str:
        self._id_counter += 1
        return f"hub-{int(time.time()*1000)}-{self._id_counter}"

    def send(
        self,
        msg_type: MessageType,
        content: str,
        sender: MessageSender,
        recipient: str,
        session_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        topic: str = "",
        swarm_id: str = "",
    ) -> str:
        msg = HubMessage(
            msg_id=self._generate_id(),
            msg_type=msg_type,
            sender=sender,
            recipient=recipient,
            content=content,
            session_id=session_id,
            topic=topic,
            swarm_id=swarm_id,
            metadata=metadata or {},
        )
        with self._write_lock:
            with open(self._messages_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(msg.__dict__, ensure_ascii=False) + "\n")
        return msg.msg_id

    def send_task_request(
        self, tool_id: str, user_input: str, session_id: str, sender: MessageSender = MessageSender.MASTER_AGENT
    ) -> str:
        return self.send(
            MessageType.TASK_REQUEST,
            user_input,
            sender,
            tool_id,
            session_id,
            {"tool_id": tool_id},
        )

    def send_task_result(
        self, result: str, session_id: str, success: bool = True, error: Optional[str] = None
    ) -> str:
        return self.send(
            MessageType.TASK_RESULT,
            result,
            MessageSender.INFERENCE_TOOL,
            MessageSender.MASTER_AGENT,
            session_id,
            {"success": success, "error": error},
        )

    def send_suspend_request(
        self,
        reason: str,
        checkpoint_name: str,
        checkpoint_data: Dict[str, Any],
        session_id: str,
    ) -> str:
        return self.send(
            MessageType.SUSPEND_REQUEST,
            reason,
            MessageSender.INFERENCE_TOOL,
            MessageSender.MASTER_AGENT,
            session_id,
            {"checkpoint_name": checkpoint_name, "checkpoint_data": checkpoint_data},
        )

    def send_resume_request(self, user_feedback: str, session_id: str) -> str:
        return self.send(
            MessageType.RESUME_REQUEST,
            user_feedback,
            MessageSender.MASTER_AGENT,
            MessageSender.INFERENCE_TOOL,
            session_id,
        )

    def send_autonomous_request(
        self, content: str, bundle_id: str, session_id: str = ""
    ) -> str:
        return self.send(
            MessageType.AUTONOMOUS_REQUEST,
            content,
            MessageSender.MASTER_AGENT,
            MessageSender.AUTONOMOUS,
            session_id,
            {"bundle_id": bundle_id},
        )

    def send_autonomous_status(
        self, content: str, bundle_id: str, status: str, session_id: str = ""
    ) -> str:
        return self.send(
            MessageType.AUTONOMOUS_STATUS,
            content,
            MessageSender.AUTONOMOUS,
            MessageSender.MASTER_AGENT,
            session_id,
            {"bundle_id": bundle_id, "status": status},
        )

    def send_human_in_loop_request(
        self, content: str, loop_id: str, stage: str, checkpoint_data: Dict[str, Any]
    ) -> str:
        return self.send(
            MessageType.HUMAN_IN_LOOP_REQUEST,
            content,
            MessageSender.INFERENCE_TOOL,
            MessageSender.MASTER_AGENT,
            loop_id,
            {"stage": stage, "checkpoint_data": checkpoint_data},
        )

    def send_human_in_loop_response(
        self, content: str, loop_id: str, accepted: bool = True
    ) -> str:
        return self.send(
            MessageType.HUMAN_IN_LOOP_RESPONSE,
            content,
            MessageSender.MASTER_AGENT,
            MessageSender.INFERENCE_TOOL,
            loop_id,
            {"accepted": accepted},
        )

    def send_user_feedback(self, content: str, session_id: str) -> str:
        return self.send(
            MessageType.USER_FEEDBACK,
            content,
            MessageSender.USER,
            MessageSender.MASTER_AGENT,
            session_id,
        )

    def send_subswarm_request(
        self,
        subswarm_id: str,
        tool_id: str,
        task: str,
        session_id: str,
        swarm_id: str,
        topic: str,
        max_execution_time: int = 60,
    ) -> str:
        return self.send(
            MessageType.SUBSWARM_REQUEST,
            task,
            MessageSender.MASTER_AGENT,
            subswarm_id,
            session_id,
            {"tool_id": tool_id, "max_execution_time": max_execution_time},
            topic=topic,
            swarm_id=swarm_id,
        )

    def send_subswarm_result(
        self,
        subswarm_id: str,
        result: str,
        session_id: str,
        swarm_id: str,
        topic: str,
        success: bool = True,
        error: Optional[str] = None,
    ) -> str:
        return self.send(
            MessageType.SUBSWARM_RESULT,
            result,
            MessageSender.SUBSWARM,
            MessageSender.MASTER_AGENT,
            session_id,
            {"success": success, "error": error},
            topic=topic,
            swarm_id=swarm_id,
        )

    def send_subswarm_status(
        self,
        subswarm_id: str,
        status: str,
        session_id: str,
        swarm_id: str,
        topic: str,
        progress: float = 0.0,
    ) -> str:
        return self.send(
            MessageType.SUBSWARM_STATUS,
            status,
            MessageSender.SUBSWARM,
            MessageSender.MASTER_AGENT,
            session_id,
            {"progress": progress},
            topic=topic,
            swarm_id=swarm_id,
        )

    def send_heartbeat(
        self,
        sender_id: str,
        sender_type: MessageSender,
        session_id: str,
        swarm_id: str,
        topic: str,
        status: str = "alive",
    ) -> str:
        return self.send(
            MessageType.HEARTBEAT,
            status,
            sender_type,
            MessageSender.MASTER_AGENT,
            session_id,
            {"sender_id": sender_id},
            topic=topic,
            swarm_id=swarm_id,
        )

    def send_coordination_request(
        self,
        content: str,
        session_id: str,
        swarm_id: str,
        topic: str,
        requires_human_decision: bool = False,
    ) -> str:
        return self.send(
            MessageType.COORDINATION_REQUEST,
            content,
            MessageSender.SUBSWARM,
            MessageSender.MASTER_AGENT,
            session_id,
            {"requires_human_decision": requires_human_decision},
            topic=topic,
            swarm_id=swarm_id,
        )

    def recv(self, recipient: str, session_id: Optional[str] = None, blocking: bool = False, timeout: int = 30) -> Optional[HubMessage]:
        import time as time_module
        
        start_time = time_module.time()
        while True:
            with self._read_lock:
                if self._messages_file.exists():
                    try:
                        with open(self._messages_file, "r", encoding="utf-8") as f:
                            f.seek(self._read_pos)
                            lines = f.readlines()
                            self._read_pos = f.tell()
                    except Exception:
                        return None
                else:
                    return None

            for line in lines:
                line = (line or "").strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    msg = HubMessage(**data)
                except Exception:
                    continue
                
                if msg.recipient == recipient:
                    if session_id and msg.session_id != session_id:
                        continue
                    if not msg.consumed:
                        return msg
            
            if not blocking:
                return None
            
            if time_module.time() - start_time > timeout:
                return None
            
            time_module.sleep(0.5)

    def get_unconsumed_messages(
        self, recipient: str, session_id: Optional[str] = None
    ) -> List[HubMessage]:
        messages = []
        if not self._messages_file.exists():
            return messages
        
        try:
            with open(self._messages_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = (line or "").strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        msg = HubMessage(**data)
                    except Exception:
                        continue
                    
                    if msg.recipient == recipient and not msg.consumed:
                        if session_id and msg.session_id != session_id:
                            continue
                        messages.append(msg)
        except Exception:
            pass
        
        return messages

    def mark_consumed(self, msg_id: str) -> bool:
        if not self._messages_file.exists():
            return False
        
        updated = []
        found = False
        try:
            with open(self._messages_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = (line or "").strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if data.get("msg_id") == msg_id:
                            data["consumed"] = True
                            data["consumed_at"] = int(time.time())
                            found = True
                        updated.append(json.dumps(data, ensure_ascii=False))
                    except Exception:
                        updated.append(line)
            
            if found:
                with open(self._messages_file, "w", encoding="utf-8") as f:
                    f.write("\n".join(updated) + "\n")
        except Exception:
            return False
        
        return found

    def get_messages_by_session(self, session_id: str, limit: int = 50) -> List[HubMessage]:
        messages = []
        if not self._messages_file.exists():
            return messages
        
        try:
            with open(self._messages_file, "r", encoding="utf-8") as f:
                count = 0
                for line in reversed(list(f)):
                    if count >= limit:
                        break
                    line = (line or "").strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        msg = HubMessage(**data)
                    except Exception:
                        continue
                    
                    if msg.session_id == session_id:
                        messages.append(msg)
                        count += 1
        except Exception:
            pass
        
        return list(reversed(messages))

    def clear_old_messages(self, before_timestamp: int) -> int:
        if not self._messages_file.exists():
            return 0
        
        updated = []
        count = 0
        try:
            with open(self._messages_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = (line or "").strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        msg = HubMessage(**data)
                    except Exception:
                        continue
                    
                    if msg.created_at < before_timestamp:
                        count += 1
                        continue
                    updated.append(json.dumps(data, ensure_ascii=False))
            
            with open(self._messages_file, "w", encoding="utf-8") as f:
                f.write("\n".join(updated) + "\n")
        except Exception:
            return 0
        
        return count

    def get_messages_by_swarm(
        self, swarm_id: str, session_id: Optional[str] = None, msg_types: Optional[List[MessageType]] = None
    ) -> List[HubMessage]:
        messages = []
        if not self._messages_file.exists():
            return messages
        
        try:
            with open(self._messages_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = (line or "").strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        msg = HubMessage(**data)
                    except Exception:
                        continue
                    
                    if msg.swarm_id == swarm_id:
                        if session_id and msg.session_id != session_id:
                            continue
                        if msg_types and msg.msg_type not in msg_types:
                            continue
                        messages.append(msg)
        except Exception:
            pass
        
        return messages

    def get_subswarm_results(self, swarm_id: str, session_id: str) -> List[HubMessage]:
        return self.get_messages_by_swarm(
            swarm_id, session_id, [MessageType.SUBSWARM_RESULT]
        )

    def get_subswarm_heartbeats(self, swarm_id: str, session_id: str) -> List[HubMessage]:
        return self.get_messages_by_swarm(
            swarm_id, session_id, [MessageType.HEARTBEAT]
        )

    def get_coordination_requests(self, swarm_id: str, session_id: str) -> List[HubMessage]:
        return self.get_messages_by_swarm(
            swarm_id, session_id, [MessageType.COORDINATION_REQUEST]
        )

    def wait_for_all_subswarms(
        self,
        swarm_id: str,
        session_id: str,
        expected_count: int,
        timeout: int = 120,
    ) -> List[HubMessage]:
        import time as time_module
        
        start = time_module.time()
        while time_module.time() - start < timeout:
            results = self.get_subswarm_results(swarm_id, session_id)
            if len(results) >= expected_count:
                return results
            time_module.sleep(0.5)
        
        return self.get_subswarm_results(swarm_id, session_id)

    def get_swarm_status(self, swarm_id: str, session_id: str) -> Dict[str, Any]:
        heartbeats = self.get_subswarm_heartbeats(swarm_id, session_id)
        results = self.get_subswarm_results(swarm_id, session_id)
        coords = self.get_coordination_requests(swarm_id, session_id)
        
        return {
            "swarm_id": swarm_id,
            "alive_count": len(heartbeats),
            "result_count": len(results),
            "coordination_requests": len(coords),
            "requires_human_decision": any(c.metadata.get("requires_human_decision", False) for c in coords),
        }
