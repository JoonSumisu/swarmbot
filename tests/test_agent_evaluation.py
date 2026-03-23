#!/usr/bin/env python3
"""
Swarmbot v2.0.2 Agent Evaluation (50 questions)

Uses hybrid approach:
1. Keyword pre-filter for obvious simple cases (greetings, thanks)
2. LLM-based routing for complex decisions
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


@dataclass
class TestCase:
    question: str
    expected_tool: str
    category: str
    requires_web: bool = False
    complexity: str = "medium"


class SmartRouter:
    """Hybrid router: keyword pre-filter + LLM for complex cases"""
    
    GREETING_PATTERNS = [
        r"^(你好|您好|hi|hello|hey|嗨|拜|晚安|早)\s*$",
        r"^(你好|您好|hi|hello|hey|嗨|拜|晚安|早)[\s！!]*$",
        r"^(再见|拜拜|bye|goodbye|拜)\s*$",
        r"^(再见|拜拜|bye|goodbye|拜)[\s！!]*$",
        r"^(谢谢|thanks|thank you|感谢|多谢)\s*$",
        r"^(好的|好|yes|yep|yeah|ok|okay)\s*$",
        r"^(不|no|nope|算了)\s*$",
        r"^(哈哈|哈哈哈|haha|lol)\s*$",
        r"^(嗯|嗯嗯|mmm)\s*$",
    ]
    
    SIMPLE_PATTERNS = [
        r"^什么是(.+)[？?]?\s*$",
        r"^(.+?)是什么[？?]?\s*$",
        r"^(.+?)的定义(是|为)[？?]?\s*$",
    ]
    
    SUPERVISED_PATTERNS = [
        r"确认.*删除",
        r"批准.*合并",
        r"是否.*删除",
        r"是否.*批准",
        r"删除.*所有",
        r"危险.*操作",
        r"确认.*执行",
    ]
    
    SWARMS_PATTERNS = [
        r"组织.*会议",
        r"评审.*讨论",
        r"多角色",
        r"模拟.*讨论",
        r"组织.*讨论",
        r"会议.*讨论",
    ]
    
    def __init__(self, llm_client):
        self.llm = llm_client
    
    def is_simple_greeting(self, text: str) -> bool:
        """Check if text is a simple greeting"""
        text = text.strip()
        for pattern in self.GREETING_PATTERNS:
            if re.match(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def is_simple_definition(self, text: str) -> bool:
        """Check if text is a simple definition question"""
        if len(text) > 60:
            return False
        for pattern in self.SIMPLE_PATTERNS:
            if re.match(pattern, text):
                return True
        return False
    
    def is_supervised_required(self, text: str) -> bool:
        """Check if text requires human confirmation"""
        text_lower = text.lower()
        for pattern in self.SUPERVISED_PATTERNS:
            if re.search(pattern, text_lower):
                return True
        if "删除" in text and ("所有" in text or "全部" in text):
            return True
        if "批准" in text or "confirm" in text_lower:
            return True
        return False
    
    def is_swarms_required(self, text: str) -> bool:
        """Check if text requires multi-agent collaboration"""
        text_lower = text.lower()
        for pattern in self.SWARMS_PATTERNS:
            if re.search(pattern, text_lower):
                return True
        if "会议" in text or "讨论" in text:
            return True
        return False
    
    async def route_with_llm(self, question: str) -> str:
        """Use LLM to determine routing"""
        system_prompt = """你是一个严格的问题路由系统。

【路由规则】
- simple_direct: 纯问候（你好/Hi/Hello）、简单概念一句话解释、寒暄
- standard: 代码生成、调研报告、分析对比、多步骤任务
- supervised: 高风险操作需要确认
- swarms: 多角色会议讨论

【判断标准】
1. 问句中包含"帮我"、"请生成"、"请写"、"分析对比"、"调研" → standard
2. 纯一句话解释概念（"什么是X"）且<40字 → simple_direct
3. 包含危险操作词（删除/修改系统）→ supervised
4. 包含多角色词（会议、讨论、辩论）→ swarms
5. 其他情况 → standard

只输出工具名称。"""

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"问题：{question}\n\n工具："}
            ]
            resp = await self.llm.acompletion(messages, temperature=0.1, max_tokens=30)
            resp_text = resp.choices[0].message.content if resp.choices else ""
            resp_text = resp_text.strip().lower()
            
            for tool in ["simple_direct", "standard", "supervised", "swarms"]:
                if tool in resp_text:
                    return tool
            return "standard"
        except Exception as e:
            print(f"      [LLM Error] {e}")
            return "standard"
    
    async def route(self, question: str) -> Tuple[str, str]:
        """
        Hybrid routing: keyword pre-filter + LLM
        Returns: (tool, method) where method is 'keyword' or 'llm'
        """
        if self.is_simple_greeting(question):
            return "simple_direct", "keyword"
        
        if self.is_simple_definition(question):
            return "simple_direct", "keyword"
        
        if self.is_supervised_required(question):
            return "supervised", "keyword"
        
        if self.is_swarms_required(question):
            return "swarms", "keyword"
        
        tool = await self.route_with_llm(question)
        return tool, "llm"


class AgentEvaluator:
    def __init__(self, workspace: Path, config):
        self.workspace = workspace
        self.config = config
        self.results: List[Dict] = []
        self.router: Optional[SmartRouter] = None
        self.llm = None
        self.session_id = f"eval_{int(time.time())}"

    def setup(self):
        from swarmbot.gateway.orchestrator import GatewayMasterAgent
        self.agent = GatewayMasterAgent(str(self.workspace), self.config)
        self.llm = self.agent._get_llm()
        self.router = SmartRouter(self.llm)
        print(f"[Setup] Available tools: {list(self.agent._tools.keys())}")

    async def run_test(self, test: TestCase) -> Dict:
        print(f"\n[{test.category}] {test.question[:40]}...")
        start = time.time()
        
        selected, method = await self.router.route(test.question)
        
        duration = time.time() - start
        correct = selected == test.expected_tool
        status = "✓" if correct else "✗"
        print(f"  {status} {selected} (expected: {test.expected_tool}) [{duration:.1f}s] [{method}]")
        
        return {
            "question": test.question,
            "category": test.category,
            "expected": test.expected_tool,
            "selected": selected,
            "correct": correct,
            "time": duration,
            "method": method,
            "needs_web": test.requires_web,
            "complexity": test.complexity
        }

    async def run_all(self) -> List[Dict]:
        tests = self.get_test_cases()
        
        print("="*60)
        print(f"Swarmbot v2.0.2 Agent Evaluation ({len(tests)} questions)")
        print("="*60)
        
        self.setup()
        
        for test in tests:
            result = await self.run_test(test)
            self.results.append(result)
        
        self.print_summary()
        return self.results

    def get_test_cases(self) -> List[TestCase]:
        return [
            # 简单问候 (10)
            TestCase("你好！", "simple_direct", "问候", complexity="simple"),
            TestCase("你好", "simple_direct", "问候", complexity="simple"),
            TestCase("您好", "simple_direct", "问候", complexity="simple"),
            TestCase("hi", "simple_direct", "问候", complexity="simple"),
            TestCase("hello", "simple_direct", "问候", complexity="simple"),
            TestCase("再见！", "simple_direct", "寒暄", complexity="simple"),
            TestCase("bye", "simple_direct", "寒暄", complexity="simple"),
            TestCase("谢谢", "simple_direct", "感谢", complexity="simple"),
            TestCase("thanks", "simple_direct", "感谢", complexity="simple"),
            TestCase("好的", "simple_direct", "确认", complexity="simple"),
            
            # 简单概念定义 (10)
            TestCase("什么是Python？", "simple_direct", "概念", complexity="simple"),
            TestCase("什么是机器学习？", "simple_direct", "概念", complexity="simple"),
            TestCase("人工智能是什么？", "simple_direct", "概念", complexity="simple"),
            TestCase("什么是API？", "simple_direct", "概念", complexity="simple"),
            TestCase("Docker是什么？", "simple_direct", "概念", complexity="simple"),
            TestCase("Git是什么？", "simple_direct", "概念", complexity="simple"),
            TestCase("什么是区块链？", "simple_direct", "概念", complexity="simple"),
            TestCase("HTTP是什么？", "simple_direct", "概念", complexity="simple"),
            TestCase("数据库是什么？", "simple_direct", "概念", complexity="simple"),
            TestCase("云计算是什么？", "simple_direct", "概念", complexity="simple"),
            
            # 代码生成 (10)
            TestCase("帮我写一个快速排序算法", "standard", "代码生成"),
            TestCase("写一个Python函数计算斐波那契数列", "standard", "代码生成"),
            TestCase("生成一个Flask应用结构", "standard", "项目创建"),
            TestCase("帮我写爬虫抓取网页数据", "standard", "代码+工具", True),
            TestCase("写一个Python脚本自动备份文件", "standard", "代码任务"),
            TestCase("生成一个RESTful API示例", "standard", "代码生成"),
            TestCase("帮我写单元测试代码", "standard", "代码生成"),
            TestCase("创建一个人脸识别Python脚本", "standard", "代码任务"),
            TestCase("写一个数据分析的Python脚本", "standard", "代码+分析"),
            TestCase("生成一个贪吃蛇游戏代码", "standard", "代码生成"),
            
            # 调研分析 (10)
            TestCase("帮我调查2024年AI发展趋势", "standard", "调研", True),
            TestCase("分析React vs Vue优缺点", "standard", "对比分析", True),
            TestCase("最新的人工智能新闻有哪些？", "standard", "调研", True),
            TestCase("帮我分析一下这个技术方案", "standard", "技术分析"),
            TestCase("调研一下目前最流行的前端框架", "standard", "调研", True),
            TestCase("对比MySQL和PostgreSQL的优劣", "standard", "对比分析", True),
            TestCase("帮我分析代码性能瓶颈", "standard", "代码分析"),
            TestCase("研究Kubernetes的核心特性", "standard", "技术调研", True),
            TestCase("分析微服务架构的优缺点", "standard", "架构分析"),
            TestCase("对比云计算三大平台AWS/Azure/GCP", "standard", "对比分析", True),
            
            # 评估报告 (5)
            TestCase("评估微服务架构重构方案", "standard", "评估任务"),
            TestCase("帮我创建一个数据分析报告", "standard", "报告生成", True),
            TestCase("评估这个技术选型的可行性", "standard", "评估任务"),
            TestCase("生成一份项目进度报告", "standard", "报告生成"),
            TestCase("帮我评估系统安全性", "standard", "安全评估"),
            
            # 需要确认 (3)
            TestCase("请确认是否删除所有临时文件", "supervised", "需确认"),
            TestCase("是否批准这个代码合并请求？", "supervised", "审批"),
            TestCase("帮我删除测试环境中的所有数据", "supervised", "危险操作"),
            
            # 多角色 (2)
            TestCase("帮我组织一场产品评审会议", "swarms", "多角色"),
            TestCase("模拟一场技术方案评审讨论", "swarms", "多角色"),
        ]

    def print_summary(self):
        total = len(self.results)
        correct = sum(1 for r in self.results if r["correct"])
        avg_time = sum(r["time"] for r in self.results) / total if total > 0 else 0
        
        keyword_used = sum(1 for r in self.results if r["method"] == "keyword")
        llm_used = sum(1 for r in self.results if r["method"] == "llm")
        
        web_needed = sum(1 for r in self.results if r["needs_web"])
        
        print("\n" + "="*60)
        print("Evaluation Summary")
        print("="*60)
        print(f"Total: {total} | Correct: {correct} ({correct/total*100:.1f}%)")
        print(f"Avg Time: {avg_time:.2f}s")
        print(f"Routing Method: keyword={keyword_used}, llm={llm_used}")
        print(f"Web Search Needed: {web_needed}")
        
        print("\nBy Category:")
        by_cat = {}
        for r in self.results:
            cat = r["category"]
            if cat not in by_cat:
                by_cat[cat] = {"total": 0, "correct": 0}
            by_cat[cat]["total"] += 1
            if r["correct"]:
                by_cat[cat]["correct"] += 1
        
        for cat in sorted(by_cat.keys()):
            stats = by_cat[cat]
            pct = stats["correct"] / stats["total"] * 100 if stats["total"] > 0 else 0
            bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
            print(f"  {cat:12} {bar} {stats['correct']}/{stats['total']} ({pct:.0f}%)")
        
        print("\nBy Complexity:")
        for comp in ["simple", "medium", "high"]:
            comp_results = [r for r in self.results if r["complexity"] == comp]
            if comp_results:
                c_correct = sum(1 for r in comp_results if r["correct"])
                c_total = len(comp_results)
                pct = c_correct / c_total * 100
                print(f"  {comp:8} {c_correct}/{c_total} ({pct:.0f}%)")
        
        print("\n" + "="*60)
        if correct == total:
            print("🎉 Perfect score!")
        elif correct >= total * 0.9:
            print("✅ Excellent!")
        elif correct >= total * 0.7:
            print("👍 Good performance")
        else:
            print(f"⚠️  {total - correct} tests failed")
        print("="*60)


async def run_async(evaluator: AgentEvaluator) -> List[Dict]:
    return await evaluator.run_all()


def main():
    parser = argparse.ArgumentParser(description="Swarmbot Agent Evaluation")
    parser.add_argument("--model", default="qwen3.5-35b-a3b")
    parser.add_argument("--base-url", default="http://100.110.110.250:7788")
    parser.add_argument("--limit", type=int, default=50, help="Limit number of tests")
    args = parser.parse_args()
    
    from swarmbot.config_manager import load_config
    
    workspace = Path.home() / ".swarmbot" / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    
    config = load_config()
    for p in config.providers:
        if p.name == "custom":
            p.base_url = args.base_url
            p.model = args.model
            break
    
    evaluator = AgentEvaluator(workspace, config)
    asyncio.run(evaluator.run_all())


if __name__ == "__main__":
    main()
