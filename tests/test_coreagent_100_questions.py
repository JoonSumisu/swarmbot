"""
CoreAgent 100 题测试
本地模型: http://100.110.110.250:7788

使用 100 道常规问题测试 CoreAgent 的：
1. 循环行为 - 简单/中度任务的迭代次数
2. 自评估准确性 - 完成度、角色符合度、质量
3. 性能指标 - Token 消耗、执行时间

使用方式:
    python tests/test_coreagent_100_questions.py
    python tests/test_coreagent_100_questions.py --limit 20
    python tests/test_coreagent_100_questions.py --timeout 600
"""

import sys
import os
import time
import json
import argparse
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

# 添加项目根目录到 path
sys.path.insert(0, "/root/swarmbot_dev")


@dataclass
class TestCase:
    question: str
    expected_route: str  # 仅供参考，CoreAgent 会自主决策
    category: str
    complexity: str = "medium"


def get_test_cases() -> List[TestCase]:
    """获取 100 道测试题"""
    return [
        # ===== 简单问候 (15) =====
        TestCase("你好！", "simple_direct", "问候", "simple"),
        TestCase("你好", "simple_direct", "问候", "simple"),
        TestCase("您好", "simple_direct", "问候", "simple"),
        TestCase("hi", "simple_direct", "问候", "simple"),
        TestCase("hello", "simple_direct", "问候", "simple"),
        TestCase("嗨", "simple_direct", "问候", "simple"),
        TestCase("早啊", "simple_direct", "问候", "simple"),
        TestCase("晚上好", "simple_direct", "问候", "simple"),
        TestCase("再见！", "simple_direct", "寒暄", "simple"),
        TestCase("bye", "simple_direct", "寒暄", "simple"),
        TestCase("明天见", "simple_direct", "寒暄", "simple"),
        TestCase("谢谢", "simple_direct", "感谢", "simple"),
        TestCase("thanks", "simple_direct", "感谢", "simple"),
        TestCase("好的", "simple_direct", "确认", "simple"),
        TestCase("没问题", "simple_direct", "确认", "simple"),
        
        # ===== 简单概念定义 (20) =====
        TestCase("什么是Python？", "simple_direct", "概念", "simple"),
        TestCase("什么是机器学习？", "simple_direct", "概念", "simple"),
        TestCase("人工智能是什么？", "simple_direct", "概念", "simple"),
        TestCase("什么是API？", "simple_direct", "概念", "simple"),
        TestCase("Docker是什么？", "simple_direct", "概念", "simple"),
        TestCase("Git是什么？", "simple_direct", "概念", "simple"),
        TestCase("什么是区块链？", "simple_direct", "概念", "simple"),
        TestCase("HTTP是什么？", "simple_direct", "概念", "simple"),
        TestCase("数据库是什么？", "simple_direct", "概念", "simple"),
        TestCase("云计算是什么？", "simple_direct", "概念", "simple"),
        TestCase("什么是深度学习？", "simple_direct", "概念", "simple"),
        TestCase("大数据是什么？", "simple_direct", "概念", "simple"),
        TestCase("物联网是什么？", "simple_direct", "概念", "simple"),
        TestCase("5G是什么？", "simple_direct", "概念", "simple"),
        TestCase("什么是DevOps？", "simple_direct", "概念", "simple"),
        TestCase("CI/CD是什么？", "simple_direct", "概念", "simple"),
        TestCase("微服务是什么？", "simple_direct", "概念", "simple"),
        TestCase("什么是容器化？", "simple_direct", "概念", "simple"),
        TestCase("Serverless是什么？", "simple_direct", "概念", "simple"),
        TestCase("边缘计算是什么？", "simple_direct", "概念", "simple"),
        
        # ===== 代码生成 (20) =====
        TestCase("帮我写一个快速排序算法", "standard", "代码生成", "medium"),
        TestCase("写一个Python函数计算斐波那契数列", "standard", "代码生成", "medium"),
        TestCase("生成一个Flask应用结构", "standard", "项目创建", "medium"),
        TestCase("帮我写爬虫抓取网页数据", "standard", "代码+工具", "medium"),
        TestCase("写一个Python脚本自动备份文件", "standard", "代码任务", "medium"),
        TestCase("生成一个RESTful API示例", "standard", "代码生成", "medium"),
        TestCase("帮我写单元测试代码", "standard", "代码生成", "medium"),
        TestCase("创建一个人脸识别Python脚本", "standard", "代码任务", "medium"),
        TestCase("写一个数据分析的Python脚本", "standard", "代码+分析", "medium"),
        TestCase("生成一个贪吃蛇游戏代码", "standard", "代码生成", "medium"),
        TestCase("帮我写一个二分查找算法", "standard", "代码生成", "medium"),
        TestCase("生成一个Django项目结构", "standard", "项目创建", "medium"),
        TestCase("写一个Python脚本发送邮件", "standard", "代码任务", "medium"),
        TestCase("帮我写一个归并排序", "standard", "代码生成", "medium"),
        TestCase("生成一个JWT认证示例", "standard", "代码生成", "medium"),
        TestCase("写一个Redis缓存封装类", "standard", "代码生成", "medium"),
        TestCase("帮我写一个状态机实现", "standard", "代码生成", "medium"),
        TestCase("生成一个WebSocket聊天示例", "standard", "代码+实时", "medium"),
        TestCase("写一个Python装饰器实现重试", "standard", "代码生成", "medium"),
        TestCase("帮我创建一个CLI工具框架", "standard", "项目创建", "medium"),
        
        # ===== 调研分析 (20) =====
        TestCase("帮我调查2024年AI发展趋势", "standard", "调研", "medium"),
        TestCase("分析React vs Vue优缺点", "standard", "对比分析", "medium"),
        TestCase("最新的人工智能新闻有哪些？", "standard", "调研", "medium"),
        TestCase("帮我分析一下这个技术方案", "standard", "技术分析", "medium"),
        TestCase("调研一下目前最流行的前端框架", "standard", "调研", "medium"),
        TestCase("对比MySQL和PostgreSQL的优劣", "standard", "对比分析", "medium"),
        TestCase("帮我分析代码性能瓶颈", "standard", "代码分析", "medium"),
        TestCase("研究Kubernetes的核心特性", "standard", "技术调研", "medium"),
        TestCase("分析微服务架构的优缺点", "standard", "架构分析", "medium"),
        TestCase("对比云计算三大平台AWS/Azure/GCP", "standard", "对比分析", "medium"),
        TestCase("帮我调研最新的大模型技术", "standard", "调研", "medium"),
        TestCase("分析TypeScript vs JavaScript", "standard", "对比分析", "medium"),
        TestCase("研究一下向量数据库的应用", "standard", "技术调研", "medium"),
        TestCase("对比GraphQL和REST API", "standard", "对比分析", "medium"),
        TestCase("帮我分析日志系统的选型", "standard", "技术分析", "medium"),
        TestCase("调研Serverless的适用场景", "standard", "调研", "medium"),
        TestCase("分析Redis和Memcached区别", "standard", "对比分析", "medium"),
        TestCase("帮我研究自动驾驶技术现状", "standard", "调研", "medium"),
        TestCase("对比GitFlow和TrunkBased开发", "standard", "对比分析", "medium"),
        TestCase("分析区块链在供应链的应用", "standard", "技术分析", "medium"),
        
        # ===== 评估报告 (10) =====
        TestCase("评估微服务架构重构方案", "standard", "评估任务", "medium"),
        TestCase("帮我创建一个数据分析报告", "standard", "报告生成", "medium"),
        TestCase("评估这个技术选型的可行性", "standard", "评估任务", "medium"),
        TestCase("生成一份项目进度报告", "standard", "报告生成", "medium"),
        TestCase("帮我评估系统安全性", "standard", "安全评估", "medium"),
        TestCase("评估这个数据库设计", "standard", "评估任务", "medium"),
        TestCase("帮我写一份技术方案评审", "standard", "报告生成", "medium"),
        TestCase("评估API接口的性能", "standard", "性能评估", "medium"),
        TestCase("生成一份代码质量报告", "standard", "报告生成", "medium"),
        TestCase("帮我评估迁移到云平台的风险", "standard", "风险评估", "medium"),
        
        # ===== 需要确认 (10) =====
        TestCase("请确认是否删除所有临时文件", "supervised", "需确认", "medium"),
        TestCase("是否批准这个代码合并请求？", "supervised", "审批", "medium"),
        TestCase("帮我删除测试环境中的所有数据", "supervised", "危险操作", "medium"),
        TestCase("确认执行数据库迁移脚本", "supervised", "需确认", "medium"),
        TestCase("批准这个产品发布吗？", "supervised", "审批", "medium"),
        TestCase("帮我清空生产环境缓存", "supervised", "危险操作", "medium"),
        TestCase("确认关闭这个服务实例", "supervised", "需确认", "medium"),
        TestCase("批准用户权限变更请求", "supervised", "审批", "medium"),
        TestCase("帮我删除过期的日志文件", "supervised", "需确认", "medium"),
        TestCase("确认回滚这次部署", "supervised", "需确认", "medium"),
        
        # ===== 多角色 (5) =====
        TestCase("帮我组织一场产品评审会议", "swarms", "多角色", "complex"),
        TestCase("模拟一场技术方案评审讨论", "swarms", "多角色", "complex"),
        TestCase("组织一个代码审查会议", "swarms", "多角色", "complex"),
        TestCase("模拟产品经理和开发者的对话", "swarms", "多角色", "complex"),
        TestCase("帮我组织一场头脑风暴", "swarms", "多角色", "complex"),
    ]


def create_agent():
    """创建 CoreAgent 实例"""
    from swarmbot.core.agent import CoreAgent, AgentContext
    from swarmbot.core.agent_config import CoreAgentConfig
    from swarmbot.llm_client import OpenAICompatibleClient
    from swarmbot.memory.memory_manager import MemoryManager
    from swarmbot.config_manager import load_config
    
    config = load_config()
    llm = OpenAICompatibleClient.from_provider(providers=config.providers)
    memory = MemoryManager.get_instance()
    
    agent_config = CoreAgentConfig(
        agent_id=f"test-100q-{int(time.time())}",
        role="master",
        boot_mode="master",
        verbose=False,  # 减少日志
        log_assessment=False,
        max_iterations=30,  # 足够大的上限
    )
    
    ctx = AgentContext(
        agent_id=agent_config.agent_id,
        role="master",
        skills={},
    )
    
    return CoreAgent(ctx, llm, memory, config=agent_config)


def run_single_test(agent, test: TestCase, timeout_per_question: int = 600) -> Dict:
    """运行单个测试题"""
    print(f"\n[{test.category}] {test.question[:40]}...")
    
    start = time.time()
    
    try:
        result = agent.run(test.question)
        elapsed = time.time() - start
        
        # 检查超时
        if elapsed > timeout_per_question:
            print(f"  ✗ TIMEOUT ({elapsed:.1f}s > {timeout_per_question}s)")
            return {
                "question": test.question,
                "category": test.category,
                "complexity": test.complexity,
                "expected_route": test.expected_route,
                "iterations": 0,
                "complete": False,
                "completion_percentage": 0,
                "quality": "timeout",
                "fits_persona": None,
                "tokens": 0,
                "time": elapsed,
                "status": "timeout",
                "decision": "timeout",
                "content": "",
                "error": "timeout",
            }
        
        assessment = result.assessment
        
        return {
            "question": test.question,
            "category": test.category,
            "complexity": test.complexity,
            "expected_route": test.expected_route,
            "iterations": result.iterations,
            "complete": assessment.complete if assessment else False,
            "completion_percentage": assessment.completion_percentage if assessment else 0,
            "quality": assessment.quality if assessment else "unknown",
            "fits_persona": assessment.fits_persona if assessment else None,
            "tokens": result.tokens_used,
            "time": elapsed,
            "status": "pass" if (assessment and assessment.complete) else "fail",
            "decision": assessment.decision if assessment else "unknown",
            "content": result.content[:200] if result.content else "",
            "error": None,
        }
        
    except Exception as e:
        elapsed = time.time() - start
        print(f"  ✗ ERROR: {e}")
        return {
            "question": test.question,
            "category": test.category,
            "complexity": test.complexity,
            "expected_route": test.expected_route,
            "iterations": 0,
            "complete": False,
            "completion_percentage": 0,
            "quality": "error",
            "fits_persona": None,
            "tokens": 0,
            "time": elapsed,
            "status": "error",
            "decision": "error",
            "content": "",
            "error": str(e),
        }


def print_detailed_results(results: List[Dict]):
    """打印详细结果"""
    print("\n" + "=" * 80)
    print("详细测试结果")
    print("=" * 80)
    
    for i, r in enumerate(results, 1):
        status_icon = "✓" if r["status"] == "pass" else "✗" if r["status"] == "fail" else "⚠"
        print(f"{i:3}. {status_icon} [{r['category']}] {r['question'][:40]}")
        print(f"     迭代: {r['iterations']} | 完成度: {r['completion_percentage']:.0f}% | "
              f"质量: {r['quality']} | 时间: {r['time']:.1f}s | Token: {r['tokens']}")
        if r["error"]:
            print(f"     错误: {r['error']}")


def print_summary_report(results: List[Dict]):
    """打印汇总报告"""
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    errors = sum(1 for r in results if r["status"] == "error")
    timeouts = sum(1 for r in results if r["status"] == "timeout")
    
    total_time = sum(r["time"] for r in results)
    total_tokens = sum(r["tokens"] for r in results)
    avg_iterations = sum(r["iterations"] for r in results) / total if total > 0 else 0
    
    # 迭代次数分布
    iteration_distribution = {}
    for r in results:
        iters = r["iterations"]
        iteration_distribution[iters] = iteration_distribution.get(iters, 0) + 1
    
    # 按类别统计
    by_category = {}
    for r in results:
        cat = r["category"]
        if cat not in by_category:
            by_category[cat] = {"total": 0, "passed": 0, "iterations": []}
        by_category[cat]["total"] += 1
        if r["status"] == "pass":
            by_category[cat]["passed"] += 1
        by_category[cat]["iterations"].append(r["iterations"])
    
    # 按复杂度统计
    by_complexity = {}
    for r in results:
        comp = r["complexity"]
        if comp not in by_complexity:
            by_complexity[comp] = {"total": 0, "passed": 0}
        by_complexity[comp]["total"] += 1
        if r["status"] == "pass":
            by_complexity[comp]["passed"] += 1
    
    print("\n" + "=" * 80)
    print("CoreAgent 100 题测试汇总报告")
    print("=" * 80)
    
    print(f"\n📊 总体统计")
    print(f"  总题数:     {total}")
    print(f"  通过:       {passed} ({passed/total*100:.1f}%)")
    print(f"  失败:       {failed} ({failed/total*100:.1f}%)")
    print(f"  错误:       {errors}")
    print(f"  超时:       {timeouts}")
    print(f"  总时间:     {total_time:.1f}s ({total_time/60:.1f}min)")
    print(f"  总 Token:   {total_tokens:,}")
    print(f"  平均迭代:   {avg_iterations:.2f} 次")
    print(f"  平均时间:   {total_time/total:.1f}s/题")
    
    print(f"\n📈 迭代次数分布")
    for iters in sorted(iteration_distribution.keys()):
        count = iteration_distribution[iters]
        bar = "█" * count + "░" * (30 - count)
        print(f"  {iters:2} 次: {bar} {count} 题 ({count/total*100:.0f}%)")
    
    print(f"\n📋 按类别统计")
    for cat in sorted(by_category.keys()):
        stats = by_category[cat]
        pct = stats["passed"] / stats["total"] * 100 if stats["total"] > 0 else 0
        avg_it = sum(stats["iterations"]) / len(stats["iterations"]) if stats["iterations"] else 0
        print(f"  {cat:12} {stats['passed']:3}/{stats['total']:3} ({pct:5.1f}%) | 平均迭代: {avg_it:.1f}")
    
    print(f"\n📋 按复杂度统计")
    for comp in ["simple", "medium", "complex"]:
        if comp in by_complexity:
            stats = by_complexity[comp]
            pct = stats["passed"] / stats["total"] * 100 if stats["total"] > 0 else 0
            print(f"  {comp:8} {stats['passed']:3}/{stats['total']:3} ({pct:5.1f}%)")
    
    print(f"\n🎯 结论")
    if passed >= total * 0.9:
        print(f"  ✅ 优秀! 通过率 {passed/total*100:.1f}%")
    elif passed >= total * 0.7:
        print(f"  👍 良好! 通过率 {passed/total*100:.1f}%")
    elif passed >= total * 0.5:
        print(f"  ⚠️  一般! 通过率 {passed/total*100:.1f}%")
    else:
        print(f"  ❌ 需要改进! 通过率 {passed/total*100:.1f}%")
    
    print("=" * 80)


def save_results(results: List[Dict], output_file: str):
    """保存结果到 JSON 文件"""
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total": len(results),
            "passed": sum(1 for r in results if r["status"] == "pass"),
            "results": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存到: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="CoreAgent 100 题测试")
    parser.add_argument("--limit", type=int, default=0, help="限制测试题数 (0=全部)")
    parser.add_argument("--timeout", type=int, default=600, help="每题超时时间 (秒)")
    parser.add_argument("--output", type=str, default="", help="输出文件路径")
    args = parser.parse_args()
    
    print("\n" + "#" * 80)
    print("# CoreAgent 100 题测试")
    print(f"# 本地模型: http://100.110.110.250:7788")
    print(f"# 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if args.limit:
        print(f"# 测试题数: {args.limit} 题")
    else:
        print(f"# 测试题数: 全部 100 题")
    print(f"# 超时时间: {args.timeout}s/题")
    print("#" * 80)
    
    # 加载测试题
    tests = get_test_cases()
    if args.limit > 0:
        tests = tests[:args.limit]
    
    print(f"\n共 {len(tests)} 道测试题")
    
    # 创建 Agent
    agent = create_agent()
    print(f"Agent 创建成功: {agent.config.agent_id}")
    
    # 运行测试
    start_time = time.time()
    results = []
    
    for i, test in enumerate(tests, 1):
        print(f"\n--- 测试 {i}/{len(tests)} ---")
        result = run_single_test(agent, test, timeout_per_question=args.timeout)
        results.append(result)
        
        # 每 10 题打印中间进度
        if i % 10 == 0:
            passed_so_far = sum(1 for r in results if r["status"] == "pass")
            elapsed = time.time() - start_time
            print(f"\n[进度] {i}/{len(tests)} 题完成 | 通过: {passed_so_far} | 耗时: {elapsed:.1f}s")
    
    total_time = time.time() - start_time
    
    # 打印详细结果
    print_detailed_results(results)
    
    # 打印汇总报告
    print_summary_report(results)
    
    # 保存结果
    if args.output:
        output_file = args.output
    else:
        output_file = f"/root/swarmbot_dev/tests/results_coreagent_100q_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    save_results(results, output_file)
    
    print(f"\n结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"总耗时: {total_time:.1f}s ({total_time/60:.1f}min)")
    print("#" * 80)


if __name__ == "__main__":
    main()
