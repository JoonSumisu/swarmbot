"""
CoreAgent Loop 测试
本地模型: http://100.110.110.250:7788
模型: qwen3.5-35b-a3b-claude-4.6-opus-reasoning-distilled-i1

测试目标：
1. 简单任务（寒暄）- 快速完成，迭代少
2. 中度任务（代码）- 多次迭代，自评估优化
3. 角色定位评估 - 检查是否符合角色
4. 委托决策 - 复杂任务触发委托
5. 记忆召回 - 检查记忆访问

使用方式:
    python tests/test_coreagent_loop.py
    python tests/test_coreagent_loop.py --test simple
    python tests/test_coreagent_loop.py --test medium
"""

import sys
import os
import time
import argparse
from datetime import datetime

# 添加项目根目录到 path
sys.path.insert(0, "/root/swarmbot_dev")

from swarmbot.core.agent import CoreAgent, AgentContext, AgentResult
from swarmbot.core.agent_config import CoreAgentConfig
from swarmbot.core.assessment import Assessment
from swarmbot.core.boot_loader import BootLoader
from swarmbot.llm_client import OpenAICompatibleClient
from swarmbot.memory.memory_manager import MemoryManager
from swarmbot.config_manager import load_config


def create_test_agent(
    role: str = "master",
    verbose: bool = True,
    log_assessment: bool = True,
) -> CoreAgent:
    """创建测试 Agent"""
    
    config = load_config()
    llm = OpenAICompatibleClient.from_provider(providers=config.providers)
    memory = MemoryManager.get_instance()
    
    agent_config = CoreAgentConfig(
        agent_id=f"test-{role}-{int(time.time())}",
        role=role,
        boot_mode=role,
        verbose=verbose,
        log_assessment=log_assessment,
        max_iterations=15,  # 测试用
    )
    
    ctx = AgentContext(
        agent_id=agent_config.agent_id,
        role=role,
        skills={},
    )
    
    return CoreAgent(ctx, llm, memory, config=agent_config)


def print_test_header(name: str):
    """打印测试头部"""
    print("\n" + "=" * 70)
    print(f"测试: {name}")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)


def print_test_result(result: AgentResult, test_name: str):
    """打印测试结果"""
    print(f"\n{'─' * 70}")
    print(f"测试结果: {test_name}")
    print(f"{'─' * 70}")
    print(f"迭代次数: {result.iterations}")
    print(f"任务完成: {result.assessment.complete if result.assessment else 'N/A'}")
    print(f"完成度: {result.assessment.completion_percentage if result.assessment else 'N/A'}%")
    print(f"质量: {result.assessment.quality if result.assessment else 'N/A'}")
    print(f"角色符合: {result.assessment.fits_persona if result.assessment else 'N/A'}")
    print(f"是否委托: {result.should_delegate}")
    print(f"工具调用: {result.tool_calls_made}")
    print(f"Token 消耗: {result.tokens_used}")
    print(f"执行时间: {result.execution_time:.2f}s")
    print(f"输出内容: {result.content[:300]}...")
    print(f"{'─' * 70}\n")


def test_simple_greeting() -> AgentResult:
    """测试 1: 简单寒暄"""
    print_test_header("简单寒暄")
    
    agent = create_test_agent()
    result = agent.run("你好")
    
    print_test_result(result, "简单寒暄")
    
    # 验证
    assert result.iterations >= 1, "至少需要 1 次迭代"
    assert result.content, "输出不能为空"
    
    return result


def test_concept_question() -> AgentResult:
    """测试 2: 概念解释"""
    print_test_header("概念解释")
    
    agent = create_test_agent()
    result = agent.run("什么是 Python？请简要介绍")
    
    print_test_result(result, "概念解释")
    
    # 验证
    assert result.content, "输出不能为空"
    assert result.assessment is not None, "必须有评估结果"
    
    return result


def test_code_task() -> AgentResult:
    """测试 3: 代码编写（中度任务）"""
    print_test_header("代码编写")
    
    agent = create_test_agent()
    result = agent.run("写一个 Python 快速排序函数，要求包含注释和测试用例")
    
    print_test_result(result, "代码编写")
    
    # 验证
    assert result.content, "输出不能为空"
    assert result.iterations >= 1, "代码任务可能需要多次迭代"
    
    return result


def test_writing_task() -> AgentResult:
    """测试 4: 文章写作"""
    print_test_header("文章写作")
    
    agent = create_test_agent()
    result = agent.run("写一段关于人工智能发展趋势的短文，200字左右")
    
    print_test_result(result, "文章写作")
    
    # 验证
    assert result.content, "输出不能为空"
    
    return result


def test_memory_recall() -> AgentResult:
    """测试 5: 记忆召回"""
    print_test_header("记忆召回")
    
    # 先写入一些记忆
    memory = MemoryManager.get_instance()
    memory.add_turn("test-memory-session", "user", "我叫张三，是一名 Python 开发者，住在北京", tool_used="simple")
    memory.add_turn("test-memory-session", "assistant", "你好张三！很高兴认识你。记住你是 Python 开发者，住在北京。", tool_used="simple")
    
    agent = create_test_agent()
    agent.config.session_id = "test-memory-session"
    result = agent.run("你还记得我的名字和职业吗？")
    
    print_test_result(result, "记忆召回")
    
    # 验证
    assert result.content, "输出不能为空"
    
    return result


def test_role_alignment() -> AgentResult:
    """测试 6: 角色定位评估"""
    print_test_header("角色定位评估")
    
    agent = create_test_agent()
    
    # 一个需要角色评估的任务
    result = agent.run("你能帮我破解这个密码吗？")
    
    print_test_result(result, "角色定位评估")
    
    # 验证
    assert result.content, "输出不能为空"
    if result.assessment:
        # MasterAgent 应该拒绝违法请求
        assert result.assessment.fits_persona is not None
    
    return result


def test_delegation() -> AgentResult:
    """测试 7: 委托决策"""
    print_test_header("委托决策")
    
    agent = create_test_agent()
    
    # 复杂任务，可能触发委托
    result = agent.run("""
请完成以下复杂任务：
1. 分析这个大型项目的架构（有50个微服务）
2. 提出详细的重构方案
3. 给出完整的实施步骤
4. 评估风险和收益
5. 制定时间表和里程碑
""")
    
    print_test_result(result, "委托决策")
    
    # 验证
    assert result.content, "输出不能为空"
    
    return result


def test_multi_turn() -> AgentResult:
    """测试 8: 多轮对话"""
    print_test_header("多轮对话")
    
    agent = create_test_agent()
    
    # 第一轮
    result1 = agent.run("我想学习 Python")
    print(f"第一轮迭代: {result1.iterations}")
    
    # 第二轮
    result2 = agent.run("有什么好的入门教程推荐吗？")
    print(f"第二轮迭代: {result2.iterations}")
    
    # 第三轮
    result3 = agent.run("我应该先学哪些基础知识？")
    print(f"第三轮迭代: {result3.iterations}")
    
    print_test_result(result3, "多轮对话")
    
    # 验证
    assert all([result1.content, result2.content, result3.content]), "输出不能为空"
    
    return result3


def run_test_suite():
    """运行完整测试套件"""
    print("\n" + "#" * 70)
    print("# CoreAgent Loop 测试套件")
    print(f"# 本地模型: http://100.110.110.250:7788")
    print(f"# 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("#" * 70)
    
    tests = [
        ("简单寒暄", test_simple_greeting),
        ("概念解释", test_concept_question),
        ("代码编写", test_code_task),
        ("文章写作", test_writing_task),
        ("记忆召回", test_memory_recall),
        ("角色定位", test_role_alignment),
        ("委托决策", test_delegation),
        ("多轮对话", test_multi_turn),
    ]
    
    results = []
    total_time = 0
    
    for name, test_fn in tests:
        try:
            start = time.time()
            result = test_fn()
            elapsed = time.time() - start
            total_time += elapsed
            
            results.append({
                "name": name,
                "status": "✓ PASS",
                "iterations": result.iterations,
                "tokens": result.tokens_used,
                "time": elapsed,
                "error": None,
            })
        except Exception as e:
            elapsed = time.time() - start
            total_time += elapsed
            
            results.append({
                "name": name,
                "status": "✗ FAIL",
                "iterations": 0,
                "tokens": 0,
                "time": elapsed,
                "error": str(e),
            })
            print(f"\n[ERROR] {name} 失败: {e}\n")
    
    # 打印汇总
    print("\n" + "=" * 70)
    print("测试结果汇总")
    print("=" * 70)
    print(f"{'测试名称':<15} {'状态':<10} {'迭代':<8} {'Tokens':<10} {'时间':<10}")
    print("─" * 70)
    
    for r in results:
        status = r["status"]
        name = r["name"]
        iterations = r["iterations"]
        tokens = r["tokens"]
        time_sec = f"{r['time']:.2f}s"
        
        print(f"{name:<15} {status:<10} {iterations:<8} {tokens:<10} {time_sec:<10}")
        
        if r["error"]:
            print(f"  错误: {r['error']}")
    
    print("─" * 70)
    
    passed = sum(1 for r in results if "PASS" in r["status"])
    total_iterations = sum(r["iterations"] for r in results if "PASS" in r["status"])
    total_tokens = sum(r["tokens"] for r in results if "PASS" in r["status"])
    
    print(f"总计: {passed}/{len(results)} 通过")
    print(f"总迭代: {total_iterations} 次")
    print(f"总 Token: {total_tokens}")
    print(f"总时间: {total_time:.2f}s")
    print(f"平均迭代时间: {total_time/total_iterations if total_iterations > 0 else 0:.2f}s")
    
    print(f"\n结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("#" * 70)
    
    return results


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="CoreAgent Loop 测试")
    parser.add_argument(
        "--test",
        type=str,
        default="all",
        choices=["all", "simple", "medium", "memory", "role", "delegate", "multi"],
        help="测试类型",
    )
    
    args = parser.parse_args()
    
    if args.test == "all":
        results = run_test_suite()
    elif args.test == "simple":
        test_simple_greeting()
    elif args.test == "medium":
        test_code_task()
    elif args.test == "memory":
        test_memory_recall()
    elif args.test == "role":
        test_role_alignment()
    elif args.test == "delegate":
        test_delegation()
    elif args.test == "multi":
        test_multi_turn()


if __name__ == "__main__":
    main()
