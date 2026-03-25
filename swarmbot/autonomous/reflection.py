"""
反思引擎 - AutonomousEngine 的自主反思模块
每小时随机探索一小段记忆，判断推展性，决定行动
"""
from __future__ import annotations

import json
import random
import threading
import time
from typing import Any, Dict, List, Optional

from ..memory.memory_manager import MemoryManager
from ..llm_client import OpenAICompatibleClient
from ..config_manager import load_config


class ReflectionEngine:
    """
    反思引擎 - 像人一样偶尔回想记忆
    
    行为：
    1. 每小时触发一次
    2. 随机选取一个记忆起点
    3. 沿时间线探索（可配置深度）
    4. LLM 判断推展性
    5. 30% 概率行动（整理/学习/提议）
    """
    
    def __init__(self, memory_manager: MemoryManager, llm: OpenAICompatibleClient, 
                 hub=None, config=None):
        self.memory = memory_manager
        self.llm = llm
        self.hub = hub
        self.config = config or load_config()
        
        # 从配置读取参数
        ref_cfg = getattr(getattr(self.config, 'autonomous', None), 'reflection', None) or {}
        self.interval_minutes = getattr(ref_cfg, 'interval_minutes', 60) if hasattr(ref_cfg, 'interval_minutes') else 60
        self.chain_size = getattr(ref_cfg, 'chain_size', 3) if hasattr(ref_cfg, 'chain_size') else 3
        self.max_questions = getattr(ref_cfg, 'max_questions', 5) if hasattr(ref_cfg, 'max_questions') else 5
        self.exploration_depth = getattr(ref_cfg, 'exploration_depth', 2) if hasattr(ref_cfg, 'exploration_depth') else 2
        self.action_probability = getattr(ref_cfg, 'action_probability', 0.3) if hasattr(ref_cfg, 'action_probability') else 0.3
        
        self._last_reflection = 0
        self._reflection_count = 0
    
    def is_due(self) -> bool:
        """检查是否应该进行反思"""
        now = time.time()
        return (now - self._last_reflection) >= (self.interval_minutes * 60)
    
    def reflect(self, chain_depth: int = 0) -> Dict[str, Any]:
        """
        执行一次反思
        
        Args:
            chain_depth: 当前连续行动深度（防止无限递归）
        
        Returns:
            反思结果
        """
        if chain_depth >= 3:
            return {"action": "stop", "reason": "max_chain_depth_reached"}
        
        self._last_reflection = time.time()
        self._reflection_count += 1
        
        print(f"[ReflectionEngine] Starting reflection #{self._reflection_count}...")
        
        # 1. 随机获取起点
        start = self._random_start()
        if not start:
            print("[ReflectionEngine] No memories to reflect on")
            return {"action": "nothing", "reason": "no_memories"}
        
        print(f"[ReflectionEngine] Start point: {start.get('content', '')[:50]}...")
        
        # 2. 时间线探索
        exploration = self._explore_timeline(start, max_questions=self.max_questions)
        
        # 3. LLM 判断推展性
        judgment = self._judge_extensibility(exploration)
        
        print(f"[ReflectionEngine] Judgment: {judgment.get('action')} - {judgment.get('reason', '')[:50]}")
        
        # 4. 概率控制 + 行动
        if judgment.get("action") != "nothing":
            if random.random() < self.action_probability:
                result = self._execute_action(judgment)
                
                # 发现有价值信息时，可以连续行动
                if result.get("valuable") and chain_depth < 3:
                    print("[ReflectionEngine] Valuable discovery, chaining reflection...")
                    return self.reflect(chain_depth + 1)
                
                return result
            else:
                print("[ReflectionEngine] Probability check failed, skipping action")
                return {"action": "skipped", "reason": "probability_check_failed"}
        
        return {"action": "nothing", "reason": judgment.get("reason", "no_extensibility")}
    
    def _random_start(self) -> Optional[Dict[str, Any]]:
        """随机选取记忆起点"""
        conn = self.memory._get_conn()
        
        # 随机从 key_facts 或 episodes 中选一个
        tables = ["key_facts", "episodes"]
        table = random.choice(tables)
        
        try:
            row = conn.execute(
                f"SELECT * FROM {table} ORDER BY RANDOM() LIMIT 1"
            ).fetchone()
            
            if row:
                return {
                    "table": table,
                    "id": row["id"],
                    "content": row["content"],
                    "created_at": row["created_at"] if "created_at" in row.keys() else None,
                }
        except Exception as e:
            print(f"[ReflectionEngine] Error getting random start: {e}")
        
        return None
    
    def _explore_timeline(self, start: Dict[str, Any], max_questions: int = 5) -> Dict[str, Any]:
        """
        时间线探索 - 沿时间线追问
        
        Args:
            start: 起点记忆
            max_questions: 最多追问次数
        
        Returns:
            探索结果
        """
        findings = []
        questions_asked = 0
        
        while questions_asked < max_questions:
            # LLM 决定下一个问题
            question = self._next_question(start, findings)
            
            if question is None:
                break
            
            # 查询记忆库回答问题
            answer = self._answer_question(question, start)
            
            findings.append({
                "question": question,
                "answer": answer,
            })
            
            questions_asked += 1
        
        return {
            "start": start,
            "findings": findings,
            "questions_asked": questions_asked,
        }
    
    def _next_question(self, start: Dict[str, Any], findings: List[Dict]) -> Optional[str]:
        """LLM 决定下一个问题"""
        findings_text = json.dumps(findings, ensure_ascii=False) if findings else "无"
        
        prompt = f"""你正在探索一段记忆。请决定下一个问题。

当前记忆：{start.get('content', '')[:200]}
已发现：{findings_text[:300]}

可选问题类型：
1. "这个之后发生了什么？"（向前探索）
2. "这个之前是什么？"（向后探索）
3. "这个任务完成了吗？"（状态检查）
4. None（不需要再问了）

只输出问题类型或 None。"""

        try:
            response = self.llm.completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=100,
            )
            
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            
            if "None" in content or "none" in content.lower():
                return None
            
            # 提取问题类型
            if "之后" in content:
                return "这个之后发生了什么？"
            elif "之前" in content:
                return "这个之前是什么？"
            elif "完成" in content:
                return "这个任务完成了吗？"
            
            return None
        except Exception as e:
            print(f"[ReflectionEngine] Error getting next question: {e}")
            return None
    
    def _answer_question(self, question: str, start: Dict[str, Any]) -> List[Dict[str, Any]]:
        """查询记忆库回答问题"""
        conn = self.memory._get_conn()
        content = start.get("content", "")
        
        try:
            if "之后" in question:
                # 查询时间在 start 之后的记忆
                rows = conn.execute(
                    "SELECT * FROM conversations WHERE created_at > ? ORDER BY created_at LIMIT 3",
                    (start.get("created_at"),)
                ).fetchall()
            elif "之前" in question:
                # 查询时间在 start 之前的记忆
                rows = conn.execute(
                    "SELECT * FROM conversations WHERE created_at < ? ORDER BY created_at DESC LIMIT 3",
                    (start.get("created_at"),)
                ).fetchall()
            elif "完成" in question:
                # 搜索任务状态
                rows = conn.execute(
                    "SELECT * FROM key_facts WHERE content LIKE ? LIMIT 3",
                    (f"%{content[:20]}%",)
                ).fetchall()
            else:
                # 通用搜索
                rows = conn.execute(
                    "SELECT * FROM key_facts WHERE content LIKE ? LIMIT 3",
                    (f"%{content[:20]}%",)
                ).fetchall()
            
            return [
                {
                    "content": row["content"],
                    "created_at": row["created_at"] if "created_at" in row.keys() else None,
                }
                for row in rows
            ]
        except Exception as e:
            print(f"[ReflectionEngine] Error answering question: {e}")
            return []
    
    def _judge_extensibility(self, exploration: Dict[str, Any]) -> Dict[str, Any]:
        """LLM 判断推展性"""
        findings_text = json.dumps(exploration.get("findings", []), ensure_ascii=False)
        
        prompt = f"""请分析这段探索结果，判断是否有"推展性"。

起点：{exploration.get('start', {}).get('content', '')[:200]}
探索发现：{findings_text[:500]}

判断标准：
1. 有未完成的任务/待办 → 需要行动
2. 有可以深入的知识点 → 需要学习
3. 有重复/矛盾的信息 → 需要整理
4. 没什么值得做的 → 什么都不做

输出 JSON：
{{"action": "nothing/learn/organize/act", "reason": "原因", "details": "具体要做什么"}}"""

        try:
            response = self.llm.completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300,
            )
            
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            
            # 提取 JSON
            import re
            match = re.search(r'\{[\s\S]*\}', content)
            if match:
                return json.loads(match.group())
            
            return {"action": "nothing", "reason": "parse_error"}
        except Exception as e:
            print(f"[ReflectionEngine] Error judging extensibility: {e}")
            return {"action": "nothing", "reason": str(e)}
    
    def _execute_action(self, judgment: Dict[str, Any]) -> Dict[str, Any]:
        """执行决定的行动"""
        action = judgment.get("action", "nothing")
        details = judgment.get("details", "")
        
        print(f"[ReflectionEngine] Executing action: {action}")
        
        if action == "learn":
            return self._learn(details)
        
        elif action == "organize":
            return self._organize(details)
        
        elif action == "act":
            return self._propose_to_user(details)
        
        return {"action": "nothing", "reason": "unknown_action"}
    
    def _learn(self, topic: str) -> Dict[str, Any]:
        """学习补充"""
        print(f"[ReflectionEngine] Learning about: {topic[:50]}...")
        
        # 使用 LLM 获取信息
        prompt = f"""请搜索关于 "{topic}" 的最新信息，并总结关键要点。
只输出 3-5 个关键事实，不要废话。"""
        
        try:
            response = self.llm.completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500,
            )
            
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            
            # 写入记忆
            self.memory.add_episode(
                content=f"[AutoLearn] {topic}: {content}",
                metadata={"source": "reflection_learn", "topic": topic}
            )
            
            return {"action": "learn", "topic": topic, "valuable": True}
        except Exception as e:
            print(f"[ReflectionEngine] Learn error: {e}")
            return {"action": "learn", "error": str(e), "valuable": False}
    
    def _organize(self, targets: str) -> Dict[str, Any]:
        """整理记忆"""
        print(f"[ReflectionEngine] Organizing: {targets[:50]}...")
        
        conn = self.memory._get_conn()
        
        try:
            # 查找重复的 key_facts
            duplicates = conn.execute("""
                SELECT content, COUNT(*) as cnt, GROUP_CONCAT(id) as ids
                FROM key_facts
                GROUP BY content
                HAVING cnt > 1
            """).fetchall()
            
            deleted = 0
            for dup in duplicates:
                ids = dup["ids"].split(",")
                if len(ids) > 1:
                    # 保留第一个，删除其他的
                    conn.execute(
                        f"DELETE FROM key_facts WHERE id IN ({','.join(['?'] * (len(ids) - 1))})",
                        ids[1:]
                    )
                    deleted += len(ids) - 1
            
            conn.commit()
            
            if deleted > 0:
                print(f"[ReflectionEngine] Organized: deleted {deleted} duplicates")
            
            return {"action": "organize", "deleted": deleted, "valuable": deleted > 0}
        except Exception as e:
            print(f"[ReflectionEngine] Organize error: {e}")
            return {"action": "organize", "error": str(e), "valuable": False}
    
    def _propose_to_user(self, proposal: str) -> Dict[str, Any]:
        """提议给用户（通过 Hub）"""
        print(f"[ReflectionEngine] Proposing to user: {proposal[:50]}...")
        
        if self.hub:
            try:
                from ..gateway.communication_hub import MessageSender, MessageType
                
                self.hub.send(
                    msg_type=MessageType.AUTONOMOUS_STATUS,
                    content=f"[Autonomous 反思发现]\n\n{proposal}\n\n是否需要我处理？",
                    sender=MessageSender.AUTONOMOUS,
                    recipient=MessageSender.MASTER_AGENT,
                    metadata={
                        "needs_approval": True,
                        "proposal": proposal,
                    }
                )
                
                return {"action": "proposed", "proposal": proposal, "valuable": True}
            except Exception as e:
                print(f"[ReflectionEngine] Propose error: {e}")
                return {"action": "propose_error", "error": str(e), "valuable": False}
        
        return {"action": "no_hub", "valuable": False}
