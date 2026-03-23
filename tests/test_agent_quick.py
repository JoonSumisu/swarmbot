#!/usr/bin/env python3
"""
Swarmbot v2.0.2 Quick Agent Evaluation (10 questions)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


@dataclass
class TestCase:
    question: str
    expected_tool: str
    category: str
    requires_web: bool = False


class QuickEvaluator:
    def __init__(self, workspace: Path, config):
        self.workspace = workspace
        self.config = config
        self.results: List[Dict] = []
        self.agent = None
        self.session_id = f"eval_{int(time.time())}"

    def setup(self):
        from swarmbot.gateway.orchestrator import GatewayMasterAgent
        self.agent = GatewayMasterAgent(str(self.workspace), self.config)
        print(f"[Setup] Available tools: {list(self.agent._tools.keys())}")

    def evaluate_tool(self, question: str) -> str:
        """Determine which tool should be used using LLM-based routing"""
        system_prompt = """你是一个严格的问题路由系统。

【工具定义】
- simple_direct: 问候语（你好/Hi/Hello等）、纯概念定义问题（"什么是X"只需一句话解释）、寒暄
- standard: 代码生成、调研报告、分析对比、多步骤任务、需要收集信息的任务
- supervised: 高风险操作（删除/修改系统）、需要用户明确批准的任务
- swarms: 多角色讨论、会议、辩论

【判断标准】
- 纯文本回答，一句话能解释清楚 → simple_direct
- 需要代码/例子/多段解释 → standard
- 明确要求"帮我做"、"请生成"、"分析对比" → standard
- 问句带"为什么"、"如何实现"、"怎么做" → standard

请只输出工具名称。"""

        user_prompt = f"问题：{question}\n\n工具："
        
        try:
            llm = self.agent._get_llm()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            resp = asyncio.run(llm.acompletion(messages, temperature=0.1, max_tokens=30))
            resp_text = resp.choices[0].message.content if resp.choices else ""
            resp_text = resp_text.strip().lower()
            
            for t in ["simple_direct", "standard", "supervised", "swarms"]:
                if t in resp_text:
                    return t
            return "standard"
        except Exception as e:
            print(f"    [Error] {e}")
            return "error"

    def run_test(self, test: TestCase) -> Dict:
        print(f"\n[{test.category}] {test.question[:40]}...")
        start = time.time()
        
        selected = self.evaluate_tool(test.question)
        
        duration = time.time() - start
        
        correct = selected == test.expected_tool
        print(f"  → {selected} (expected: {test.expected_tool}) [{duration:.1f}s]")
        
        return {
            "question": test.question,
            "category": test.category,
            "expected": test.expected_tool,
            "selected": selected,
            "correct": correct,
            "time": duration,
            "needs_web": test.requires_web
        }

    def run_all(self) -> List[Dict]:
        tests = [
            TestCase("你好！", "simple_direct", "问候"),
            TestCase("再见！", "simple_direct", "寒暄"),
            TestCase("谢谢你的帮助", "simple_direct", "感谢"),
            TestCase("帮我写一个快速排序算法", "standard", "代码生成"),
            TestCase("帮我调查2024年AI发展趋势", "standard", "调研", True),
            TestCase("生成一个Flask应用结构", "standard", "项目创建"),
            TestCase("分析React vs Vue优缺点", "standard", "对比分析", True),
            TestCase("帮我写爬虫抓取网页数据", "standard", "代码+工具", True),
            TestCase("评估微服务架构重构方案", "standard", "评估任务"),
            TestCase("请确认是否删除所有临时文件", "supervised", "需确认"),
            TestCase("帮我组织一场产品评审会议讨论", "swarms", "多角色"),
            TestCase("最新的人工智能新闻有哪些？", "standard", "调研", True),
            TestCase("解释一下HTTP协议的工作原理", "standard", "技术解释"),
            TestCase("帮我创建一个数据分析报告", "standard", "报告生成", True),
            TestCase("你好，今天天气怎么样？", "simple_direct", "简单对话"),
        ]
        
        self.setup()
        
        for t in tests:
            self.results.append(self.run_test(t))
        
        self.print_summary()
        return self.results

    def print_summary(self):
        total = len(self.results)
        correct = sum(1 for r in self.results if r["correct"])
        avg_time = sum(r["time"] for r in self.results) / total
        
        web_needed = sum(1 for r in self.results if r["needs_web"])
        
        print("\n" + "="*60)
        print("Summary")
        print("="*60)
        print(f"Total: {total} | Correct: {correct} ({correct/total*100:.0f}%)")
        print(f"Avg Time: {avg_time:.1f}s")
        print(f"Web Search Needed: {web_needed}")
        
        by_cat = {}
        for r in self.results:
            cat = r["category"]
            if cat not in by_cat:
                by_cat[cat] = {"total": 0, "correct": 0}
            by_cat[cat]["total"] += 1
            if r["correct"]:
                by_cat[cat]["correct"] += 1
        
        print("\nBy Category:")
        for cat, stats in by_cat.items():
            pct = stats["correct"] / stats["total"] * 100
            print(f"  {cat}: {stats['correct']}/{stats['total']} ({pct:.0f}%)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3.5-35b-a3b")
    parser.add_argument("--base-url", default="http://100.110.110.250:7788")
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
    
    evaluator = QuickEvaluator(workspace, config)
    evaluator.run_all()


if __name__ == "__main__":
    main()
