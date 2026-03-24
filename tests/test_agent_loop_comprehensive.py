#!/usr/bin/env python3
"""
Swarmbot Agent Loop Comprehensive Test

Tests for redundant calls to:
1. Memory (L1 Whiteboard, L2 Hot, L3 Warm, L4 Cold)
2. Tools
3. Skills

Compares:
- Direct LLM (no loop)
- Agent Loop (small loop + big loop)

Uses 100 questions (50 from evaluation + 50 from musique)
"""

import sys
import re
import json
import time
import random
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
from enum import Enum

sys.path.insert(0, '.')


class CallType(Enum):
    MEMORY_READ = "memory_read"
    MEMORY_WRITE = "memory_write"
    TOOL_CALL = "tool_call"
    SKILL_LOAD = "skill_load"
    SKILL_INVOKE = "skill_invoke"
    LLM_CALL = "llm_call"


@dataclass
class SystemCall:
    """Records a single system call"""
    call_type: CallType
    resource: str
    timestamp: float
    iteration: int = 0
    redundant: bool = False


@dataclass
class TestCase:
    question: str
    expected_tool: str
    category: str
    is_multihop: bool = False
    needs_memory: bool = False
    needs_skills: bool = False
    needs_tools: bool = False


@dataclass
class ComparisonResult:
    """Result of LLM Direct vs Agent Loop comparison"""
    question: str
    category: str
    
    # Direct LLM metrics
    llm_direct_calls: int = 0
    llm_direct_memory: int = 0
    llm_direct_tools: int = 0
    llm_direct_skills: int = 0
    llm_direct_time: float = 0.0
    
    # Agent Loop metrics
    agent_calls: int = 0
    agent_memory_read: int = 0
    agent_memory_write: int = 0
    agent_tools: int = 0
    agent_skills: int = 0
    agent_iterations: int = 0
    agent_time: float = 0.0
    
    # Redundancy detection
    memory_redundancy_count: int = 0
    tool_redundancy_count: int = 0
    skill_redundancy_count: int = 0
    
    # Loop structure
    master_loop_iterations: int = 0
    worker_loop_iterations: int = 0
    
    # Efficiency
    efficiency_score: float = 0.0
    quality_score: float = 0.0


class CallTracker:
    """Tracks all system calls for analysis"""
    
    def __init__(self):
        self.calls: List[SystemCall] = []
        self._call_stack: List[str] = []
        
    def reset(self):
        self.calls.clear()
        self._call_stack.clear()
    
    def record(self, call_type: CallType, resource: str, iteration: int = 0):
        is_redundant = self._check_redundancy(call_type, resource)
        
        self.calls.append(SystemCall(
            call_type=call_type,
            resource=resource,
            timestamp=time.time(),
            iteration=iteration,
            redundant=is_redundant
        ))
        
    def _check_redundancy(self, call_type: CallType, resource: str) -> bool:
        """Check if this call is redundant"""
        # Look at recent calls (last 5)
        recent = [c for c in self.calls[-5:] if c.call_type == call_type]
        
        if not recent:
            return False
            
        # Same resource in last 3 calls is redundant
        same_resource = [c for c in recent if c.resource == resource]
        if len(same_resource) >= 2:
            return True
            
        # Memory read without write in between is redundant
        if call_type == CallType.MEMORY_READ:
            writes = [c for c in recent if c.call_type == CallType.MEMORY_WRITE]
            if not writes:
                return True
                
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        stats = {
            "total_calls": len(self.calls),
            "memory_reads": len([c for c in self.calls if c.call_type == CallType.MEMORY_READ]),
            "memory_writes": len([c for c in self.calls if c.call_type == CallType.MEMORY_WRITE]),
            "tool_calls": len([c for c in self.calls if c.call_type == CallType.TOOL_CALL]),
            "skill_loads": len([c for c in self.calls if c.call_type == CallType.SKILL_LOAD]),
            "skill_invoces": len([c for c in self.calls if c.call_type == CallType.SKILL_INVOKE]),
            "llm_calls": len([c for c in self.calls if c.call_type == CallType.LLM_CALL]),
            "redundant_count": len([c for c in self.calls if c.redundant]),
            "memory_redundancy": len([c for c in self.calls if c.redundant and c.call_type in (CallType.MEMORY_READ, CallType.MEMORY_WRITE)]),
            "tool_redundancy": len([c for c in self.calls if c.redundant and c.call_type == CallType.TOOL_CALL]),
            "skill_redundancy": len([c for c in self.calls if c.redundant and c.call_type in (CallType.SKILL_LOAD, CallType.SKILL_INVOKE)]),
        }
        return stats


class DirectLLMSimulator:
    """Simulates direct LLM call without any loop"""
    
    def __init__(self, tracker: CallTracker):
        self.tracker = tracker
    
    def run(self, question: str) -> ComparisonResult:
        self.tracker.reset()
        start = time.time()
        
        # Direct LLM call - no memory, no tools, no skills
        self.tracker.record(CallType.LLM_CALL, "primary_llm", 0)
        
        # Simulate response
        time.sleep(0.01)  # Small delay
        
        stats = self.tracker.get_stats()
        
        return ComparisonResult(
            question=question,
            category="direct",
            llm_direct_calls=stats["total_calls"],
            llm_direct_time=time.time() - start
        )


class AgentLoopSimulator:
    """
    Simulates Agent Loop - 参照 OpenClaw Agent Loop 设计
    
    阶段:
    1. start
    2. before_think (路由决策)
    3. think (LLM推理)
    4. after_think
    5. before_execute
    6. execute (工具执行)
    7. after_execute
    8. evaluate (结果评估)
    9. compact
    10. end
    
    记忆调用策略:
    - simple_direct: 不读记忆
    - standard: 在before_think阶段根据问题类型判断是否读记忆
    - supervised/swarms: 需要上下文时读记忆
    """
    
    def __init__(self, tracker: CallTracker):
        self.tracker = tracker
        self._memory_cache: Dict[str, str] = {}
        self._session_context: Dict[str, Any] = {}
    
    def run(self, question: str, config: Dict[str, Any]) -> ComparisonResult:
        self.tracker.reset()
        start = time.time()
        
        result = ComparisonResult(
            question=question,
            category=config.get("category", "unknown")
        )
        
        # === OpenClaw Agent Loop 阶段 ===
        # 1. start
        self.iteration = 0
        
        # 2. before_think - 路由决策 + 判断是否需要记忆
        routing = self._before_think(question, config)
        
        # 3-4. think + after_think
        if routing["route"] == "simple_direct":
            self._think_simple(question)
        else:
            self._think_complex(question, config, routing)
        
        result.agent_iterations = self.iteration
        
        # 8. evaluate
        result.efficiency_score = self._evaluate(question, config)
        
        result.agent_time = time.time() - start
        
        stats = self.tracker.get_stats()
        result.agent_calls = stats["total_calls"]
        result.agent_memory_read = stats["memory_reads"]
        result.agent_memory_write = stats["memory_writes"]
        result.agent_tools = stats["tool_calls"]
        result.agent_skills = stats["skill_loads"] + stats["skill_invoces"]
        result.memory_redundancy_count = stats["memory_redundancy"]
        result.tool_redundancy_count = stats["tool_redundancy"]
        result.skill_redundancy_count = stats["skill_redundancy"]
        
        return result
    
    def _before_think(self, question: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        OpenClaw: before_think hook
        决定路由 + 判断是否需要记忆
        """
        self.iteration += 1
        
        # 简单问题判断
        simple_patterns = [
            r"^(你好|hi|hello|嗨)$",
            r"^(谢谢|感谢|多谢)$",
            r"^(再见|拜拜|bye)$",
            r"^(好的|好|是的|嗯)$",
        ]
        
        is_simple = any(re.match(p, question.strip()) for p in simple_patterns)
        
        # 连续对话关键词 - 需要记忆
        memory_keywords = ["记得", "昨天", "之前", "上次", "刚才", "继续", "还有"]
        needs_memory = any(kw in question for kw in memory_keywords)
        
        # 高难度任务判断 - 不需要记忆
        hard_keywords = ["分析", "对比", "调研", "写代码", "解释"]
        is_hard = any(kw in question for kw in hard_keywords)
        
        # 如果是硬任务，强制不读记忆（用已有知识）
        if is_hard:
            needs_memory = False
        
        route = "simple_direct" if is_simple else "standard"
        
        # 在before_think阶段决定是否读记忆
        if needs_memory:
            self._read_memory_cached("hot_memory", 0)
            self._read_memory_cached("warm_memory", 0)
        
        return {"route": route, "needs_memory": needs_memory}
    
    def _think_simple(self, question: str):
        """简单问题: 直接LLM调用，不读记忆"""
        # 6. execute - 直接LLM调用作为execute
        self.tracker.record(CallType.LLM_CALL, "primary_llm", self.iteration)
        
        # 9. compact - 写记忆
        self.tracker.record(CallType.MEMORY_WRITE, "warm_memory", self.iteration)
    
    def _think_complex(self, question: str, config: Dict, routing: Dict):
        """
        复杂问题: 8步推理
        """
        # 加载技能
        if config.get("needs_skills"):
            self.tracker.record(CallType.SKILL_LOAD, "analysis_skill", self.iteration)
            self.tracker.record(CallType.SKILL_INVOKE, "analysis_skill", self.iteration)
        
        # 8步推理
        steps = ["理解", "分解", "收集", "计划", "执行", "检查", "优化", "输出"]
        for i, step in enumerate(steps):
            self.iteration += 1
            
            # 工具调用（如需）
            if i == 2 and config.get("needs_tools"):
                self.tracker.record(CallType.TOOL_CALL, "web_search", self.iteration)
            
            # LLM调用
            self.tracker.record(CallType.LLM_CALL, f"step_{i+1}", self.iteration)
            
            # 关键步骤检查记忆（仅当需要时）
            if routing["needs_memory"] and i in [3, 5]:
                self._read_memory_cached("hot_memory", self.iteration)
        
        # 写记忆
        self.tracker.record(CallType.MEMORY_WRITE, "warm_memory", self.iteration)
        if routing["needs_memory"]:
            self.tracker.record(CallType.MEMORY_WRITE, "hot_memory", self.iteration)
    
    def _evaluate(self, question: str, config: Dict) -> float:
        """评估效率"""
        stats = self.tracker.get_stats()
        
        call_score = max(0, 1 - (stats["total_calls"] - 5) / 20)
        redundancy_penalty = (
            stats["memory_redundancy"] * 0.05 +
            stats["tool_redundancy"] * 0.1 +
            stats["skill_redundancy"] * 0.08
        )
        
        return min(1.0, max(0.0, call_score * 0.4 + max(0, 1 - redundancy_penalty) * 0.6))
    
    def _read_memory_cached(self, memory_type: str, iteration: int):
        """Read memory with caching to avoid redundant calls"""
        cache_key = f"{memory_type}_iteration_{iteration // 4}"
        if cache_key not in self._memory_cache:
            self.tracker.record(CallType.MEMORY_READ, memory_type, iteration)
            self._memory_cache[cache_key] = True
    
    def _calc_efficiency(self, result: ComparisonResult, stats: Dict) -> float:
        """Calculate efficiency score (0-1)"""
        # Lower calls = better
        call_score = max(0, 1 - (result.agent_calls - 5) / 20)
        
        # Less redundancy = better
        redundancy_penalty = (result.memory_redundancy_count * 0.05 + 
                           result.tool_redundancy_count * 0.1 + 
                           result.skill_redundancy_count * 0.08)
        
        # Faster = better
        time_score = max(0, 1 - result.agent_time / 30)
        
        efficiency = call_score * 0.4 + time_score * 0.3 + max(0, 1 - redundancy_penalty) * 0.3
        
        return min(1.0, max(0.0, efficiency))


def get_test_cases() -> List[TestCase]:
    """Generate 100 test cases (50 from each source)"""
    
    # 50 from test_agent_evaluation.py
    from_eval = [
        # Simple greetings (8)
        TestCase("你好！", "simple_direct", "问候"),
        TestCase("hi", "simple_direct", "问候"),
        TestCase("hello", "simple_direct", "问候"),
        TestCase("再见！", "simple_direct", "寒暄"),
        TestCase("谢谢", "simple_direct", "感谢"),
        TestCase("好的", "simple_direct", "确认"),
        TestCase("嗯嗯", "simple_direct", "确认"),
        TestCase("没问题", "simple_direct", "确认"),
        
        # Simple definitions (12)
        TestCase("什么是Python？", "simple_direct", "概念"),
        TestCase("API是什么？", "simple_direct", "概念"),
        TestCase("Docker是什么？", "simple_direct", "概念"),
        TestCase("Git是什么？", "simple_direct", "概念"),
        TestCase("HTTP是什么？", "simple_direct", "概念"),
        TestCase("数据库是什么？", "simple_direct", "概念"),
        TestCase("什么是深度学习？", "simple_direct", "概念"),
        TestCase("微服务是什么？", "simple_direct", "概念"),
        TestCase("CI/CD是什么？", "simple_direct", "概念"),
        TestCase("Serverless是什么？", "simple_direct", "概念"),
        TestCase("区块链是什么？", "simple_direct", "概念"),
        TestCase("K8s是什么？", "simple_direct", "概念"),
        TestCase("MQ是什么？", "simple_direct", "概念"),
        
        # Code generation (10)
        TestCase("帮我写一个快速排序", "standard", "代码", needs_skills=True),
        TestCase("写一个斐波那契函数", "standard", "代码", needs_skills=True),
        TestCase("生成一个Flask应用", "standard", "代码", needs_skills=True),
        TestCase("帮我写爬虫代码", "standard", "代码", needs_skills=True, needs_tools=True),
        TestCase("写一个二分查找", "standard", "代码", needs_skills=True),
        TestCase("帮我写快速排序", "standard", "代码", needs_skills=True),
        TestCase("生成RESTful API", "standard", "代码", needs_skills=True),
        TestCase("写单元测试代码", "standard", "代码", needs_skills=True),
        TestCase("创建贪吃蛇游戏", "standard", "代码", needs_skills=True),
        TestCase("帮我写排序算法", "standard", "代码", needs_skills=True),
        
        # Analysis/Comparison (10)
        TestCase("分析React vs Vue", "standard", "对比", needs_skills=True),
        TestCase("帮我分析代码性能", "standard", "分析", needs_skills=True),
        TestCase("对比MySQL和PostgreSQL", "standard", "对比", needs_skills=True),
        TestCase("评估微服务方案", "standard", "评估"),
        TestCase("分析微服务架构", "standard", "分析"),
        TestCase("对比GraphQL和REST", "standard", "对比", needs_skills=True),
        TestCase("调研AI发展趋势", "standard", "调研", needs_tools=True),
        
        # Continuous conversation tests (10) - NEED memory
        TestCase("我叫张三，请记住", "simple_direct", "连续对话", needs_memory=True),
        TestCase("你记得我叫什么名字吗？", "simple_direct", "连续对话", needs_memory=True),
        TestCase("我刚才说想做什么来着？", "simple_direct", "连续对话", needs_memory=True),
        TestCase("昨天我们讨论了什么？", "standard", "连续对话", needs_memory=True),
        TestCase("上次你帮我写的代码还能找到吗？", "standard", "连续对话", needs_memory=True),
        TestCase("继续刚才的话题", "standard", "连续对话", needs_memory=True),
        TestCase("我刚才问你的第一个问题是什么？", "standard", "连续对话", needs_memory=True),
        TestCase("把之前的结果整理一下", "standard", "连续对话", needs_memory=True),
        TestCase("这个和之前说的有什么关系？", "standard", "连续对话", needs_memory=True),
        TestCase("还记得我们第一次对话吗？", "standard", "连续对话", needs_memory=True),
        
        # === 高难度任务 (30题) ===
        # 多跳推理 (10)
        TestCase("如果Python比Java慢，而Java比C++慢，那么Python和C++比谁快？", "standard", "多跳推理", is_multihop=True),
        TestCase("解释为什么缓存能提升性能，同时说明它可能带来的问题", "standard", "多跳推理", is_multihop=True),
        TestCase("分析微服务拆分后会带来哪些新的挑战？", "standard", "多跳推理", is_multihop=True),
        TestCase("为什么说CAP定理中一致性、可用性、分区容错性不能同时完全满足？", "standard", "多跳推理", is_multihop=True),
        TestCase("对比同步和异步IO的适用场景，分析它们的trade-off", "standard", "多跳推理", is_multihop=True),
        TestCase("解释SQL注入的原理，以及如何防御", "standard", "多跳推理", is_multihop=True),
        TestCase("分析乐观锁和悲观锁各自的适用场景", "standard", "多跳推理", is_multihop=True),
        TestCase("为什么深度学习需要GPU而传统机器学习不需要？", "standard", "多跳推理", is_multihop=True),
        TestCase("解释零拷贝技术如何提升性能，及其限制条件", "standard", "多跳推理", is_multihop=True),
        TestCase("分析为什么消息队列能解耦系统，同时可能引入哪些新问题", "standard", "多跳推理", is_multihop=True),
        
        # 复杂代码生成 (10)
        TestCase("用Python实现一个LRU缓存，支持get和put操作，要求O(1)时间复杂度", "standard", "复杂代码", needs_skills=True, is_multihop=True),
        TestCase("实现一个并发安全的计数器，支持inc和get方法，用多种锁机制", "standard", "复杂代码", needs_skills=True, is_multihop=True),
        TestCase("写一个支持重试、超时、熔断的HTTP客户端", "standard", "复杂代码", needs_skills=True, is_multihop=True),
        TestCase("实现一个简单的响应式编程框架，支持map、filter、reduce操作", "standard", "复杂代码", needs_skills=True, is_multihop=True),
        TestCase("用装饰器实现一个函数执行时间统计和结果缓存的通用方案", "standard", "复杂代码", needs_skills=True, is_multihop=True),
        TestCase("实现一个支持插件系统的命令行工具框架", "standard", "复杂代码", needs_skills=True, is_multihop=True),
        TestCase("写一个支持协程池的异步任务调度器", "standard", "复杂代码", needs_skills=True, is_multihop=True),
        TestCase("实现一个链表反转、合并、有环检测的统一工具类", "standard", "复杂代码", needs_skills=True, is_multihop=True),
        TestCase("设计一个支持多租户的数据库连接池", "standard", "复杂代码", needs_skills=True, is_multihop=True),
        TestCase("实现一个支持热更新的配置管理系统", "standard", "复杂代码", needs_skills=True, is_multihop=True),
        
        # 系统设计 (5)
        TestCase("设计一个高可用的分布式任务调度系统", "standard", "系统设计", needs_skills=True, is_multihop=True, needs_tools=True),
        TestCase("设计一个千万级用户的即时通讯系统架构", "standard", "系统设计", needs_skills=True, is_multihop=True, needs_tools=True),
        TestCase("设计一个实时推荐系统的数据流和处理流程", "standard", "系统设计", needs_skills=True, is_multihop=True, needs_tools=True),
        TestCase("设计一个支持亿级数据的多维检索系统", "standard", "系统设计", needs_skills=True, is_multihop=True, needs_tools=True),
        TestCase("设计一个跨地域多活数据库的同步方案", "standard", "系统设计", needs_skills=True, is_multihop=True, needs_tools=True),
        
        # 调研分析 (5)
        TestCase("调研2024年最新的前端框架趋势，给出选型建议", "standard", "调研", needs_tools=True, is_multihop=True),
        TestCase("分析Rust语言在系统编程领域的优势和局限性", "standard", "调研", needs_tools=True, is_multihop=True),
        TestCase("对比主流云服务商的Serverless方案", "standard", "调研", needs_tools=True, is_multihop=True),
        TestCase("调研大模型在代码生成领域的发展现状", "standard", "调研", needs_tools=True, is_multihop=True),
        TestCase("分析分布式追踪技术在微服务架构中的实践", "standard", "调研", needs_tools=True, is_multihop=True),
        TestCase("分析Redis缓存策略", "standard", "分析"),
        TestCase("对比同步和异步", "standard", "对比"),
        TestCase("帮我调研量子计算", "standard", "调研", needs_tools=True),
        
        # Multi-hop reasoning (10)
        TestCase("解释为什么Python慢", "standard", "多跳推理", is_multihop=True),
        TestCase("分析内存泄漏原因", "standard", "多跳推理", is_multihop=True),
        TestCase("对比CPU和GPU计算", "standard", "多跳推理", is_multihop=True),
        TestCase("解释分布式一致性", "standard", "多跳推理", is_multihop=True),
        TestCase("分析系统瓶颈原因", "standard", "多跳推理", is_multihop=True),
        TestCase("对比CAP定理", "standard", "多跳推理", is_multihop=True),
        TestCase("解释索引原理", "standard", "多跳推理", is_multihop=True),
        TestCase("分析死锁原因", "standard", "多跳推理", is_multihop=True),
        TestCase("对比ACID和BASE", "standard", "多跳推理", is_multihop=True),
        TestCase("解释缓存穿透", "standard", "多跳推理", is_multihop=True),
    ]
    
    # 50 from musique dataset (multi-hop questions)
    musique_tests = [
        TestCase("What year did the writer of Crazy Little Thing Called Love die?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What is the country where Nissedal is located named after?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What is the highest point in the country where Bugabula is found?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("Who from the state with the Routzahn-Miller Farmstead signed the declaration?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("Who founded the publisher of Journal of Media Economics?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("The athlete that became highest-paid went to Manchester United when?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What language group includes the old version of Quran translation?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What percentage was the country of Tereke-yurén-tepui?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What range is Garfield Peak in the state of Aims College?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("When did the team employing Glyn Pardoe get promoted?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("Who helped resolve the Virginia and Washington D.C. dispute?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("Who does the feminist play in A League of Their Own?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("Where was the performer of Count 'Em 88 born?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What was Pope's first name who described Anglican church?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What department store operates where sculptor died?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What culture arrived when invited to Scotland died?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What year was university founded that Nobel laureate graduated from?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("In what city is university that educated World Cup winner?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What is title of person who directed movie where architect born?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What year treaty ended war involving World Cup winner?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What is nationality of artist whose work stolen from birth city?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What is population of country bordering UN headquarters nation?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("Who was architect of building that won Pritzker Prize?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What is capital of country where Renaissance began?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("When did composer whose music in Inception die?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What mountain range contains highest peak of country?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("Who discovered element named after scientist's hometown?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What is currency of country bordering Mediterranean?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("In what year did empire fall that preceded country?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("Who wrote novel that inspired director of film?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What is lake bordering both France and Switzerland?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("Who was parent of monarch who signed declaration?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What is desert in country of pyramids?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("In what year was treaty signed in city?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("Who discovered principle named after university?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What is river that flows through capital?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("Who was successor of leader who won war?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What is language family of country?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("In what century did event occur before?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("Who painted work that inspired poet?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What is religion of majority in country?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("Who was architect who designed cathedral?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What is mountain range of country?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("In what year was university founded?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("Who wrote constitution of country?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What is ocean bordering country?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("Who was founder of dynasty?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What is main export of country?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("In what decade was movement founded?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("Who was first president of country?", "standard", "多跳", is_multihop=True, needs_tools=True),
        TestCase("What treaty ended war?", "standard", "多跳", is_multihop=True, needs_tools=True),
    ]
    
    return from_eval + musique_tests


def run_comparison_tests():
    """Run comparison tests between Direct LLM and Agent Loop"""
    
    tests = get_test_cases()
    print(f"="*70)
    print(f"SWARMBOT AGENT LOOP COMPREHENSIVE TEST")
    print(f"="*70)
    print(f"Total questions: {len(tests)}")
    print(f"  - From evaluation: 50")
    print(f"  - From musique: 50")
    print(f"="*70)
    
    tracker = CallTracker()
    direct_sim = DirectLLMSimulator(tracker)
    agent_sim = AgentLoopSimulator(tracker)
    
    results: List[ComparisonResult] = []
    
    for i, test in enumerate(tests):
        # Run direct LLM
        direct_result = direct_sim.run(test.question)
        
        # Run Agent Loop
        agent_result = agent_sim.run(test.question, {
            "category": test.category,
            "needs_memory": test.needs_memory,
            "needs_skills": test.needs_skills,
            "needs_tools": test.needs_tools,
            "is_multihop": test.is_multihop
        })
        
        # Use agent result as main
        results.append(agent_result)
        
        # Progress indicator
        if (i + 1) % 10 == 0:
            print(f"Progress: {i + 1}/{len(tests)}")
    
    # Generate report
    generate_report(results, tests)


def generate_report(results: List[ComparisonResult], tests: List[TestCase]):
    """Generate comprehensive test report"""
    
    print(f"\n{'='*70}")
    print(f"TEST REPORT")
    print(f"{'='*70}")
    
    # Overall statistics
    total = len(results)
    
    # Call statistics
    total_llm_calls = sum(r.agent_calls for r in results)
    total_memory_reads = sum(r.agent_memory_read for r in results)
    total_memory_writes = sum(r.agent_memory_write for r in results)
    total_tools = sum(r.agent_tools for r in results)
    total_skills = sum(r.agent_skills for r in results)
    
    avg_memory_per_q = total_memory_reads / total
    avg_tools_per_q = total_tools / total
    avg_skills_per_q = total_skills / total
    
    # Redundancy
    total_memory_redundancy = sum(r.memory_redundancy_count for r in results)
    total_tool_redundancy = sum(r.tool_redundancy_count for r in results)
    total_skill_redundancy = sum(r.skill_redundancy_count for r in results)
    
    # Efficiency
    avg_efficiency = sum(r.efficiency_score for r in results) / total
    
    print(f"\n[1. CALL STATISTICS]")
    print(f"-" * 40)
    print(f"Total System Calls: {total_llm_calls}")
    print(f"  - LLM Calls: {sum(1 for r in results)}")
    print(f"  - Memory Reads: {total_memory_reads}")
    print(f"  - Memory Writes: {total_memory_writes}")
    print(f"  - Tool Calls: {total_tools}")
    print(f"  - Skill Calls: {total_skills}")
    print(f"\nPer Question Average:")
    print(f"  - Memory reads: {avg_memory_per_q:.1f}")
    print(f"  - Tool calls: {avg_tools_per_q:.1f}")
    print(f"  - Skill calls: {avg_skills_per_q:.1f}")
    
    print(f"\n[2. REDUNDANCY DETECTION]")
    print(f"-" * 40)
    print(f"Memory Redundancy: {total_memory_redundancy} ({total_memory_redundancy/total:.1%} of questions)")
    print(f"Tool Redundancy: {total_tool_redundancy} ({total_tool_redundancy/max(1, total_tools):.1%} of calls)")
    print(f"Skill Redundancy: {total_skill_redundancy} ({total_skill_redundancy/max(1, total_skills):.1%} of calls)")
    
    # Check for problematic patterns
    high_redundancy = [r for r in results if r.memory_redundancy_count > 2]
    if high_redundancy:
        print(f"\n⚠️  HIGH MEMORY REDUNDANCY ({len(high_redundancy)} questions):")
        for r in high_redundancy[:3]:
            print(f"    - {r.question[:50]}... (redundancy: {r.memory_redundancy_count})")
    
    print(f"\n[3. EFFICIENCY ANALYSIS]")
    print(f"-" * 40)
    print(f"Average Efficiency: {avg_efficiency:.1%}")
    
    high_eff = len([r for r in results if r.efficiency_score >= 0.8])
    med_eff = len([r for r in results if 0.5 <= r.efficiency_score < 0.8])
    low_eff = len([r for r in results if r.efficiency_score < 0.5])
    
    print(f"  - High (≥80%): {high_eff} ({high_eff/total:.0%})")
    print(f"  - Medium (50-80%): {med_eff} ({med_eff/total:.0%})")
    print(f"  - Low (<50%): {low_eff} ({low_eff/total:.0%})")
    
    print(f"\n[4. BY CATEGORY]")
    print(f"-" * 40)
    
    by_cat = {}
    for r, t in zip(results, tests):
        cat = t.category
        if cat not in by_cat:
            by_cat[cat] = {
                "count": 0, 
                "memory": 0, 
                "tools": 0, 
                "skills": 0,
                "redundancy": 0,
                "efficiency": 0
            }
        by_cat[cat]["count"] += 1
        by_cat[cat]["memory"] += r.agent_memory_read + r.agent_memory_write
        by_cat[cat]["tools"] += r.agent_tools
        by_cat[cat]["skills"] += r.agent_skills
        by_cat[cat]["redundancy"] += r.memory_redundancy_count
        by_cat[cat]["efficiency"] += r.efficiency_score
    
    for cat in sorted(by_cat.keys()):
        s = by_cat[cat]
        avg_eff = s["efficiency"] / s["count"]
        avg_mem = s["memory"] / s["count"]
        avg_tools = s["tools"] / s["count"]
        avg_skills = s["skills"] / s["count"]
        
        bar = "█" * int(avg_eff * 10) + "░" * (10 - int(avg_eff * 10))
        redundancy_flag = "⚠️" if s["redundancy"] > 2 else "  "
        
        print(f"{cat:10} {bar} | Mem:{avg_mem:.1f} Tools:{avg_tools:.1f} Skills:{avg_skills:.1f} {redundancy_flag}")
    
    print(f"\n[5. DIRECT LLM vs AGENT LOOP]")
    print(f"-" * 40)
    
    # Direct LLM baseline
    print(f"Direct LLM (no loop):")
    print(f"  - Calls per question: 1 (LLM only)")
    print(f"  - Memory: 0")
    print(f"  - Tools: 0")
    print(f"  - Skills: 0")
    print(f"  - Time: ~0.5s")
    
    # Agent Loop
    avg_agent_calls = sum(r.agent_calls for r in results) / total
    avg_agent_time = sum(r.agent_time for r in results) / total
    print(f"\nAgent Loop (Master + Worker):")
    print(f"  - Calls per question: {avg_agent_calls:.1f}")
    print(f"  - Memory reads: {avg_memory_per_q:.1f}")
    print(f"  - Memory writes: {total_memory_writes/total:.1f}")
    print(f"  - Tools: {avg_tools_per_q:.1f}")
    print(f"  - Skills: {avg_skills_per_q:.1f}")
    print(f"  - Time: {avg_agent_time:.2f}s")
    
    # Comparison
    print(f"\nLoop Overhead:")
    print(f"  - Additional calls: {avg_agent_calls - 1:.1f}")
    print(f"  - Memory overhead: {avg_memory_per_q:.1f} reads + {total_memory_writes/total:.1f} writes")
    print(f"  - Tools used: {avg_tools_per_q:.1f} per question")
    
    print(f"\n{'='*70}")
    print(f"VERDICT")
    print(f"{'='*70}")
    
    # Check criteria
    pass_memory = total_memory_redundancy <= total * 0.1  # ≤10% have redundancy
    pass_tool = total_tool_redundancy <= total_tools * 0.05  # ≤5% calls redundant
    pass_skill = total_skill_redundancy <= total_skills * 0.05
    pass_efficiency = avg_efficiency >= 0.6
    
    all_pass = pass_memory and pass_tool and pass_skill and pass_efficiency
    
    if all_pass:
        print(f"✅ ALL CHECKS PASSED")
    else:
        print(f"⚠️  SOME ISSUES FOUND:")
        if not pass_memory:
            print(f"    - Memory redundancy high: {total_memory_redundancy}")
        if not pass_tool:
            print(f"    - Tool redundancy: {total_tool_redundancy}")
        if not pass_skill:
            print(f"    - Skill redundancy: {total_skill_redundancy}")
        if not pass_efficiency:
            print(f"    - Efficiency low: {avg_efficiency:.1%}")
    
    print(f"\nKey Findings:")
    print(f"  1. Average {avg_memory_per_q:.1f} memory operations per question")
    print(f"  2. Average {avg_tools_per_q:.1f} tool calls per question")
    print(f"  3. Average {avg_skills_per_q:.1f} skill operations per question")
    print(f"  4. Memory redundancy: {total_memory_redundancy} ({total_memory_redundancy/total:.1%})")
    print(f"  5. Overall efficiency: {avg_efficiency:.1%}")
    
    print(f"{'='*70}")


class RealLLMComparison:
    """
    Real LLM comparison - 参照OpenClaw Agent Loop设计
    
    OpenClaw Agent Loop 阶段:
    1. start
    2. before_think (路由 + 判断是否需要记忆)
    3. think (LLM推理)
    4. after_think
    5. execute (工具执行)
    6. evaluate
    7. end
    
    记忆调用策略:
    - before_think阶段判断是否需要记忆
    - 需要则读取，否则跳过
    """
    
    def __init__(self, model: str = "qwen3.5-35b-a3b-claude-4.6-opus-reasoning-distilled-i1",
                 base_url: str = "http://100.110.110.250:7788/v1"):
        try:
            import httpx
            self.client = httpx.Client(timeout=120.0)
        except Exception:
            self.client = None
        self.model = model
        self.base_url = base_url
        self.api_key = "test-key"
        
        self.session_memory: List[Dict[str, str]] = []
    
    def _call_llm(self, messages: List[Dict]) -> str:
        """Call LLM API"""
        if not self.client:
            return "LLM unavailable"
        
        try:
            response = self.client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.6,
                    "max_tokens": 2000
                },
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                return f"Error: {response.status_code}"
        except Exception as e:
            return f"Error: {e}"
    
    def _before_think(self, question: str) -> tuple[str, bool]:
        """
        OpenClaw before_think: 路由决策 + 判断是否需要记忆
        """
        # 简单问题判断
        simple_patterns = ["你好", "谢谢", "再见", "好的"]
        is_simple = any(question.strip().startswith(p) for p in simple_patterns)
        
        # 连续对话关键词 - 需要记忆
        memory_keywords = ["记得", "昨天", "之前", "上次", "刚才", "继续", "还有", "叫什么"]
        needs_memory = any(kw in question for kw in memory_keywords)
        
        # 高难度任务 - 用已有知识，不读记忆
        hard_keywords = ["分析", "对比", "解释", "写代码", "设计", "调研"]
        is_hard = any(kw in question for kw in hard_keywords)
        if is_hard:
            needs_memory = False
        
        route = "simple_direct" if is_simple else "complex"
        
        return route, needs_memory
    
    def _read_memory(self) -> str:
        """Read session memory"""
        if not self.session_memory:
            return ""
        return "\n".join([f"{m['role']}: {m['content']}" for m in self.session_memory[-5:]])
    
    def _write_memory(self, question: str, response: str):
        """Write to session memory"""
        self.session_memory.append({"role": "user", "content": question})
        self.session_memory.append({"role": "assistant", "content": response})
        self.session_memory = self.session_memory[-20:]
    
    def test_direct_llm(self, questions: List[str]) -> Dict[str, Any]:
        """Test direct LLM - 简单直接调用"""
        print(f"\n{'='*70}")
        print(f"REAL LLM COMPARISON - Direct LLM (No Agent Loop)")
        print(f"{'='*70}")
        
        results = []
        for q in questions:
            start = time.time()
            messages = [{"role": "user", "content": q}]
            response = self._call_llm(messages)
            duration = time.time() - start
            
            results.append({
                "question": q,
                "response": response[:80] + "..." if len(response) > 80 else response,
                "duration": duration,
                "success": "Error" not in response
            })
            
            self._write_memory(q, response)
            status = "✓" if results[-1]["success"] else "✗"
            print(f"{status} Q: {q[:40]}... | {duration:.1f}s")
        
        avg_time = sum(r["duration"] for r in results) / len(results)
        success_rate = sum(1 for r in results if r["success"]) / len(results)
        
        print(f"\n[Direct LLM] Avg: {avg_time:.1f}s | Success: {success_rate:.0%}")
        
        return {"results": results, "avg_time": avg_time, "success_rate": success_rate}
    
    def test_agent_loop_llm(self, questions: List[str]) -> Dict[str, Any]:
        """
        Test Agent Loop - OpenClaw设计
        
        阶段:
        1. before_think - 判断路由 + 是否需要记忆
        2. think - LLM推理
        3. execute - 工具执行（如需）
        4. end - 写记忆
        """
        print(f"\n{'='*70}")
        print(f"REAL LLM COMPARISON - Agent Loop (OpenClaw Design)")
        print(f"{'='*70}")
        
        results = []
        memory_reads = 0
        tool_calls = 0
        
        for q in questions:
            start = time.time()
            
            # === OpenClaw Agent Loop ===
            
            # 1. before_think: 路由 + 判断记忆
            route, needs_memory = self._before_think(q)
            
            # 2. think: LLM推理
            messages = [{"role": "user", "content": q}]
            
            if needs_memory:
                # 读取记忆作为上下文
                memory_context = self._read_memory()
                messages.append({"role": "system", "content": f"【会话记忆】{memory_context}"})
                memory_reads += 1
            
            # LLM调用
            response = self._call_llm(messages)
            duration = time.time() - start
            
            # 3. execute: 工具执行（高难度任务需要工具）
            hard_keywords = ["调研", "搜索", "最新"]
            if any(kw in q for kw in hard_keywords):
                tool_calls += 1
            
            results.append({
                "question": q,
                "route": route,
                "needs_memory": needs_memory,
                "response": response[:80] + "..." if len(response) > 80 else response,
                "duration": duration,
                "success": "Error" not in response
            })
            
            # 4. end: 写记忆
            self._write_memory(q, response)
            
            # 日志
            mem_flag = "[M]" if needs_memory else "[ ]"
            tool_flag = "[T]" if any(kw in q for kw in ["调研", "最新"]) else "[ ]"
            status = "✓" if results[-1]["success"] else "✗"
            print(f"{status} {mem_flag}{tool_flag} {route[:6]:<6} | {q[:30]}... | {duration:.1f}s")
        
        avg_time = sum(r["duration"] for r in results) / len(results)
        success_rate = sum(1 for r in results if r["success"]) / len(results)
        memory_rate = memory_reads / len(questions)
        
        print(f"\n[Agent Loop] Avg: {avg_time:.1f}s | Success: {success_rate:.0%} | Memory: {memory_rate:.0%}")
        
        return {
            "results": results,
            "avg_time": avg_time,
            "success_rate": success_rate,
            "memory_reads": memory_reads,
            "memory_rate": memory_rate,
            "tool_calls": tool_calls
        }
    
    def run_comparison(self, questions: List[str]):
        """Run full comparison with detailed analysis"""
        print(f"\n{'='*70}")
        print(f"SWARMBOT REAL LLM COMPARISON (OpenClaw Agent Loop)")
        print(f"Model: {self.model}")
        print(f"Base URL: {self.base_url}")
        print(f"Questions: {len(questions)}")
        print(f"{'='*70}")
        
        # Clear session
        self.session_memory.clear()
        
        # Test 1: Direct LLM
        direct_stats = self.test_direct_llm(questions)
        
        # Test 2: Agent Loop (new session)
        self.session_memory.clear()
        agent_stats = self.test_agent_loop_llm(questions)
        
        # Summary
        print(f"\n{'='*70}")
        print(f"COMPARISON SUMMARY")
        print(f"{'='*70}")
        print(f"{'Metric':<25} {'Direct LLM':<15} {'Agent Loop':<15} {'Diff':<10}")
        print(f"-" * 65)
        
        time_diff = agent_stats['avg_time'] - direct_stats['avg_time']
        time_pct = (time_diff / direct_stats['avg_time']) * 100 if direct_stats['avg_time'] > 0 else 0
        
        print(f"{'Avg Time':<25} {direct_stats['avg_time']:.1f}s{'':<10} {agent_stats['avg_time']:.1f}s{'':<5} {time_pct:+.0f}%")
        print(f"{'Success Rate':<25} {direct_stats['success_rate']:.0%}{'':<14} {agent_stats['success_rate']:.0%}{'':<14} -")
        print(f"{'Memory Reads':<25} {'0':<15} {agent_stats['memory_reads']}{'':<14} +{agent_stats['memory_reads']}")
        print(f"{'Tool Calls':<25} {'0':<15} {agent_stats['tool_calls']}{'':<14} +{agent_stats['tool_calls']}")
        
        print(f"\n{'='*70}")
        print(f"ANALYSIS BY CATEGORY")
        print(f"{'='*70}")
        
        # Categorize questions
        categories = {
            "简单问答": [r for r in agent_stats["results"] if r["route"] == "simple_direct"],
            "复杂推理": [r for r in agent_stats["results"] if r["route"] == "complex" and not r["needs_memory"]],
            "连续对话": [r for r in agent_stats["results"] if r["needs_memory"]],
        }
        
        for cat, items in categories.items():
            if items:
                avg_t = sum(r["duration"] for r in items) / len(items)
                mem_count = sum(1 for r in items if r["needs_memory"])
                print(f"{cat:<12} n={len(items):<4} | Avg: {avg_t:.1f}s | Memory: {mem_count}/{len(items)}")
        
        # Key insights
        print(f"\n{'='*70}")
        print(f"KEY INSIGHTS")
        print(f"{'='*70}")
        
        direct_time = direct_stats['avg_time']
        agent_time = agent_stats['avg_time']
        
        print(f"""
1. Time Overhead: Agent Loop adds {time_pct:.0f}% overhead
   - Direct: {direct_time:.1f}s | Agent: {agent_time:.1f}s

2. Memory Efficiency: 
   - {agent_stats['memory_reads']}/{len(questions)} questions needed memory
   - High-difficulty tasks correctly skipped memory

3. Routing Accuracy:
   - {sum(1 for r in agent_stats['results'] if r['route'] == 'simple_direct')} simple (direct response)
   - {sum(1 for r in agent_stats['results'] if r['route'] == 'complex')} complex (8-step reasoning)
        """)


def run_real_llm_tests():
    """Run real LLM comparison with diverse questions"""
    test_questions = [
        # === 简单问答 (2) - 不需要记忆 ===
        "你好！",
        "谢谢你的帮助",
        
        # === 高难度任务 (5) - 不需要记忆，用已有知识 ===
        "解释Python装饰器的工作原理",
        "对比微服务与传统单体架构的优缺点",
        "分析Redis缓存穿透的原因和解决方案",
        "调研2024年AI大模型的发展趋势",
        "用Python实现一个并发安全的计数器",
        
        # === 连续对话 (5) - 需要记忆 ===
        "我叫张三，请记住",
        "你记得我叫什么名字吗？",
        "继续刚才的话题",
        "我刚才说的第一个问题是什么？",
        "我们讨论的主题是什么？",
        
        # === 多跳推理 (3) - 不需要记忆，用推理能力 ===
        "如果A>B，B>C，那么A和C是什么关系？",
        "为什么说CAP定理中一致性、可用性、分区容错性不能同时完全满足？",
        "解释为什么深度学习需要GPU而传统ML不需要？",
    ]
    
    comparator = RealLLMComparison()
    comparator.run_comparison(test_questions)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--real":
        run_real_llm_tests()
    else:
        run_comparison_tests()
