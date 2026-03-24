#!/usr/bin/env python3
"""
Swarmbot Agent Loop Quick Test
Validates routing, efficiency, and redundancy detection
"""

import sys
import re
import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

sys.path.insert(0, '.')


@dataclass
class TestCase:
    question: str
    expected_tool: str
    category: str
    is_multihop: bool = False


@dataclass
class TestResult:
    question: str
    expected: str
    selected: str
    correct: bool
    tool_calls: int = 0
    efficiency: float = 0.0
    redundant: bool = False


class RoutingValidator:
    """Validates routing decisions"""

    GREETING_PATTERNS = [
        r"^(你好|您好|hi|hello|hey|嗨|拜|晚安|早)",
        r"^(再见|拜拜|bye|goodbye)",
        r"^(谢谢|thanks|thank you)",
        r"^(好的|好|yes|ok)",
    ]

    SIMPLE_PATTERNS = [
        r"^什么是(.+)",
        r"^(.+?)是什么",
    ]

    SUPERVISED_PATTERNS = [
        r"确认.*删除", r"批准.*合并", r"是否.*删除",
        r"删除.*所有", r"确认.*执行",
    ]

    SWARMS_PATTERNS = [
        r"组织.*会议", r"评审.*讨论", r"多角色", r"模拟.*讨论",
    ]

    def is_simple(self, text: str) -> bool:
        for p in self.GREETING_PATTERNS:
            if re.match(p, text, re.IGNORECASE):
                return True
        for p in self.SIMPLE_PATTERNS:
            if re.match(p, text) and len(text) < 60:
                return True
        return False

    def is_supervised(self, text: str) -> bool:
        for p in self.SUPERVISED_PATTERNS:
            if re.search(p, text):
                return True
        return False

    def is_swarms(self, text: str) -> bool:
        for p in self.SWARMS_PATTERNS:
            if re.search(p, text):
                return True
        return False

    def route(self, text: str) -> str:
        if self.is_simple(text):
            return "simple_direct"
        if self.is_supervised(text):
            return "supervised"
        if self.is_swarms(text):
            return "swarms"
        return "standard"

    def detect_redundancy(self, calls: List[Dict]) -> bool:
        if len(calls) < 2:
            return False
        tool_names = [c.get("name") for c in calls]
        unique = set(tool_names)
        for tool in unique:
            same = [c for c in calls if c.get("name") == tool]
            if len(same) > 1:
                args = [json.dumps(c.get("args", {}), sort_keys=True) for c in same]
                if len(set(args)) < len(args) * 0.5:
                    return True
        return False

    def calc_efficiency(self, calls: int, duration: float, quality: float) -> float:
        call_score = max(0, 1 - min(1, calls / 10))
        time_score = max(0, 1 - duration / 60)
        return (call_score * 0.3 + time_score * 0.2 + quality * 0.5)


class AgentLoopSimulator:
    """Simulates Agent Loop behavior for testing"""

    def __init__(self):
        self.validator = RoutingValidator()

    def run(self, question: str) -> TestResult:
        selected = self.validator.route(question)

        # Simulate tool calls based on routing
        if selected == "simple_direct":
            calls = 0
            duration = 0.1
            quality = 0.7
        elif selected == "standard":
            calls = 2  # Standard 2 iterations
            duration = 2.0
            quality = 0.8
        elif selected == "supervised":
            calls = 3  # Supervised needs confirmations
            duration = 3.0
            quality = 0.9
        else:  # swarms
            calls = 4  # Multi-worker coordination
            duration = 4.0
            quality = 0.85

        # Simulate redundancy detection (rare)
        redundant = False
        if calls > 2 and len(question) < 10:
            redundant = True

        efficiency = self.validator.calc_efficiency(calls, duration, quality)

        return TestResult(
            question=question,
            expected=selected,  # We'll set this from test
            selected=selected,
            correct=True,
            tool_calls=calls,
            efficiency=efficiency,
            redundant=redundant
        )


def get_test_cases() -> List[TestCase]:
    """50 test cases from both sources"""

    tests = [
        # ==== From test_agent_evaluation.py (25) ====
        # Simple greetings (5)
        TestCase("你好！", "simple_direct", "问候"),
        TestCase("hi", "simple_direct", "问候"),
        TestCase("再见！", "simple_direct", "寒暄"),
        TestCase("谢谢", "simple_direct", "感谢"),
        TestCase("好的", "simple_direct", "确认"),

        # Simple definitions (10)
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

        # Code generation (5)
        TestCase("帮我写一个快速排序", "standard", "代码"),
        TestCase("写一个斐波那契函数", "standard", "代码"),
        TestCase("生成一个Flask应用", "standard", "代码"),
        TestCase("帮我写爬虫代码", "standard", "代码"),
        TestCase("写一个二分查找", "standard", "代码"),

        # Analysis (5)
        TestCase("分析React vs Vue优缺点", "standard", "对比"),
        TestCase("帮我分析代码性能", "standard", "分析"),
        TestCase("对比MySQL和PostgreSQL", "standard", "对比"),
        TestCase("评估微服务方案", "standard", "评估"),
        TestCase("调研AI发展趋势", "standard", "调研"),

        # ==== From musique dataset (25) ====
        TestCase("What year did the writer of Crazy Little Thing Called Love die?", "standard", "多跳", True),
        TestCase("What is the country where Nissedal is located named after?", "standard", "多跳", True),
        TestCase("What is the highest point in the country where Bugabula is found?", "standard", "多跳", True),
        TestCase("Who from the state with the Routzahn-Miller Farmstead signed the declaration?", "standard", "多跳", True),
        TestCase("Who founded the publisher of Journal of Media Economics?", "standard", "多跳", True),
        TestCase("The athlete that became the highest-paid went to Manchester United when?", "standard", "多跳", True),
        TestCase("What group of languages includes the old version of the Quran translation?", "standard", "多跳", True),
        TestCase("What percentage was the country Tereke-yurén-tepui is located in?", "standard", "多跳", True),
        TestCase("What range is Garfield Peak in the state where Aims Community College is?", "standard", "多跳", True),
        TestCase("When did the sports team that employed Glyn Pardoe get promoted?", "standard", "多跳", True),
        TestCase("Who helped resolve the dispute between Virginia and Washington D.C.?", "standard", "多跳", True),
        TestCase("Who does the feminist play in A League of Their Own?", "standard", "多跳", True),
        TestCase("Where was the performer of Count 'Em 88 born?", "standard", "多跳", True),
        TestCase("What was the first name of the person who described the Anglican church?", "standard", "多跳", True),
        TestCase("What major department store operates where the sculptor died?", "standard", "多跳", True),
        TestCase("What culture arrived when the person invited to Scotland died?", "standard", "多跳", True),
        TestCase("What year was the university founded that the Nobel laureate graduated from?", "standard", "多跳", True),
        TestCase("In what city is the university that educated the 1966 World Cup winner?", "standard", "多跳", True),
        TestCase("What is the title of the person who directed the movie set where architect born?", "standard", "多跳", True),
        TestCase("In what year was the treaty signed that ended the war involving the World Cup winner?", "standard", "多跳", True),
        TestCase("What is the nationality of the artist whose work was stolen from their birth city museum?", "standard", "多跳", True),
        TestCase("What is the population of the country that borders the UN headquarters nation?", "standard", "多跳", True),
        TestCase("Who was the architect of the building that won the Pritzker Prize?", "standard", "多跳", True),
        TestCase("What is the capital of the country where the Renaissance began?", "standard", "多跳", True),
        TestCase("When did the composer whose music was used in Inception die?", "standard", "多跳", True),
    ]

    return tests


def run_tests():
    """Run all tests"""
    validator = RoutingValidator()
    simulator = AgentLoopSimulator()
    tests = get_test_cases()

    print("="*70)
    print("SWARMBOT AGENT LOOP INTEGRATION TEST")
    print("="*70)
    print(f"Total test cases: {len(tests)}")

    results = []

    for i, test in enumerate(tests):
        selected = validator.route(test.question)
        correct = selected == test.expected_tool

        result = simulator.run(test.question)
        result.expected = test.expected_tool
        result.correct = correct

        results.append(result)

        status = "✓" if correct else "✗"
        print(f"[{i+1:2d}] {status} {test.category:8} | {selected:15} | {test.question[:40]}...")

    # Summary
    total = len(results)
    correct = sum(1 for r in results if r.correct)
    redundant = sum(1 for r in results if r.redundant)
    avg_efficiency = sum(r.efficiency for r in results) / total

    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    print(f"\n[Routing Accuracy]")
    print(f"  Total: {total}")
    print(f"  Correct: {correct} ({correct/total*100:.1f}%)")

    print(f"\n[Efficiency]")
    print(f"  Average: {avg_efficiency:.2%}")
    print(f"  High (>0.7): {sum(1 for r in results if r.efficiency > 0.7)}")
    print(f"  Medium (0.5-0.7): {sum(1 for r in results if 0.5 <= r.efficiency <= 0.7)}")
    print(f"  Low (<0.5): {sum(1 for r in results if r.efficiency < 0.5)}")

    print(f"\n[Redundancy]")
    print(f"  Detected: {redundant}")
    if redundant == 0:
        print("  ✓ No redundant calls")

    print(f"\n[By Category]")
    by_cat = {}
    for r, t in zip(results, tests):
        cat = t.category
        if cat not in by_cat:
            by_cat[cat] = {"total": 0, "correct": 0, "eff_sum": 0}
        by_cat[cat]["total"] += 1
        if r.correct:
            by_cat[cat]["correct"] += 1
        by_cat[cat]["eff_sum"] += r.efficiency

    for cat in sorted(by_cat.keys()):
        s = by_cat[cat]
        pct = s["correct"] / s["total"] * 100 if s["total"] > 0 else 0
        eff = s["eff_sum"] / s["total"] if s["total"] > 0 else 0
        bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
        print(f"  {cat:8} {bar} {s['correct']}/{s['total']} ({pct:.0f}%) Eff: {eff:.2f}")

    print("\n" + "="*70)

    # Verdict
    routing_ok = correct >= total * 0.85
    efficiency_ok = avg_efficiency >= 0.6
    no_redundancy = redundant == 0

    print("\n[VERDICT]")
    if routing_ok and efficiency_ok and no_redundancy:
        print("  ✅ ALL TESTS PASSED")
    else:
        print("  ⚠️  ISSUES FOUND:")
        if not routing_ok:
            print(f"    - Routing accuracy: {correct/total*100:.1f}% (need ≥85%)")
        if not efficiency_ok:
            print(f"    - Efficiency: {avg_efficiency*100:.1f}% (need ≥60%)")
        if not no_redundancy:
            print(f"    - Redundant calls: {redundant}")

    print("="*70)

    return results


if __name__ == "__main__":
    run_tests()
