"""
SkillPool - 能力固化池 (v2.0)

从 Autonomous Engine 执行经验中生成和优化 Skills，
使主动思考的成果可以被 InferenceLoop 复用。
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from loguru import logger


@dataclass
class Skill:
    """技能定义"""
    skill_id: str
    name: str
    description: str
    category: str  # code, research, analysis, data, document, etc.
    prompt_template: str
    required_tools: List[str]
    usage_count: int = 0
    success_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_used_at: Optional[float] = None
    source_bundle: Optional[str] = None  # 从哪个 Bundle 生成


@dataclass
class SkillUsageStats:
    """Skill 使用统计"""
    skill_id: str
    total_uses: int
    success_rate: float
    avg_execution_time: float
    last_used_at: float
    trend: str  # "increasing", "stable", "decreasing"


@dataclass
class ExecutionTraceAnalysis:
    """执行轨迹分析结果"""
    key_decisions: List[Dict[str, Any]]
    common_patterns: List[str]
    success_factors: List[str]
    failure_risks: List[str]
    reusability_score: float  # 0.0 - 1.0
    generalization_level: str  # "specific", "moderate", "general"
    recommended_category: str
    confidence: float


class SkillRegistry:
    """
    Skill 注册表

    管理所有可用的 Skills，支持按角色、领域、任务检索
    """

    def __init__(self, skills_dir: Optional[Path] = None):
        self.skills_dir = skills_dir or Path.home() / ".swarmbot" / "skills"
        self.skills_dir.mkdir(parents=True, exist_ok=True)

        # 内置 Skills
        self._builtin_skills: Dict[str, Skill] = self._init_builtin_skills()

        # 从文件加载 Skills
        self._custom_skills: Dict[str, Skill] = {}
        self._load_skills()

    def _init_builtin_skills(self) -> Dict[str, Skill]:
        """初始化内置 Skills"""
        return {
            "web_search": Skill(
                skill_id="web_search",
                name="网络搜索",
                description="使用搜索引擎查找最新信息",
                category="research",
                prompt_template="搜索关键词：{query}\n返回最相关的 {num_results} 条结果",
                required_tools=["web_search"],
            ),
            "code_review": Skill(
                skill_id="code_review",
                name="代码审查",
                description="审查代码质量和潜在问题",
                category="code",
                prompt_template="审查以下代码:\n{code}\n关注：正确性、性能、安全性、可读性",
                required_tools=["file_read"],
            ),
            "data_analysis": Skill(
                skill_id="data_analysis",
                name="数据分析",
                description="使用 Python 进行数据分析",
                category="data",
                prompt_template="分析以下数据:\n{data}\n使用 Python 进行统计分析并生成可视化",
                required_tools=["python_exec", "file_read"],
            ),
            "document_summary": Skill(
                skill_id="document_summary",
                name="文档摘要",
                description="生成长文档的简洁摘要",
                category="document",
                prompt_template="为以下文档生成摘要:\n{document}\n要求：简洁、包含关键点、{max_length}字以内",
                required_tools=["file_read"],
            ),
        }

    def _load_skills(self):
        """从文件加载自定义 Skills"""
        for skill_file in self.skills_dir.glob("SKILL-*.md"):
            try:
                skill = self._parse_skill_file(skill_file)
                if skill:
                    self._custom_skills[skill.skill_id] = skill
            except Exception as e:
                logger.error(f"Failed to load skill from {skill_file}: {e}")

    def _parse_skill_file(self, path: Path) -> Optional[Skill]:
        """解析 Skill 文件"""
        content = path.read_text(encoding="utf-8")

        # 简单的 YAML-like 解析
        skill_id = path.stem.replace("SKILL-", "").lower()
        name = self._extract_field(content, "name") or skill_id
        description = self._extract_field(content, "description") or ""
        category = self._extract_field(content, "category") or "general"
        prompt_template = self._extract_field(content, "prompt_template") or content
        tools_str = self._extract_field(content, "required_tools") or ""
        required_tools = [t.strip() for t in tools_str.split(",") if t.strip()]

        return Skill(
            skill_id=skill_id,
            name=name,
            description=description,
            category=category,
            prompt_template=prompt_template,
            required_tools=required_tools,
        )

    def _extract_field(self, content: str, field_name: str) -> Optional[str]:
        """从 Markdown 内容中提取字段"""
        pattern = rf"{field_name}:\s*(.+?)(?:\n|$)"
        match = re.search(pattern, content, re.IGNORECASE)
        return match.group(1).strip() if match else None

    def get_all_skills(self) -> Dict[str, Skill]:
        """获取所有 Skills"""
        return {**self._builtin_skills, **self._custom_skills}

    def get_skills_by_category(self, category: str) -> List[Skill]:
        """按类别获取 Skills"""
        return [
            s for s in self.get_all_skills().values()
            if s.category.lower() == category.lower()
        ]

    def get_skills_for_task(
        self,
        role: str,
        task_desc: str = "",
        required_skills: Optional[List[str]] = None
    ) -> Dict[str, bool]:
        """为任务获取相关 Skills"""
        # 这是与现有 SkillRegistry 兼容的方法
        # 实际实现应该查询 skill_pool.py 中的 SkillPool
        from .skill_pool import SkillPool
        pool = SkillPool.get_instance()
        return pool.get_skills_for_task(role, task_desc, required_skills)

    def register_skill(self, skill: Skill):
        """注册新 Skill"""
        # 保存到文件
        skill_file = self.skills_dir / f"SKILL-{skill.skill_id}.md"
        content = f"""---
name: {skill.name}
description: {skill.description}
category: {skill.category}
required_tools: {", ".join(skill.required_tools)}
---

# {skill.name}

{skill.description}

## Prompt Template

{skill.prompt_template}

## Usage

此技能于 {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(skill.created_at))} 创建。
"""
        skill_file.write_text(content, encoding="utf-8")
        self._custom_skills[skill.skill_id] = skill
        logger.info(f"Registered skill: {skill.skill_id}")

    def update_usage(self, skill_id: str, success: bool):
        """更新 Skill 使用统计"""
        all_skills = self.get_all_skills()
        if skill_id in all_skills:
            skill = all_skills[skill_id]
            skill.usage_count += 1
            if success:
                skill.success_count += 1
            skill.last_used_at = time.time()


class SkillGenerator:
    """
    Skill 生成器

    从 Autonomous Engine 执行经验中生成新 Skills
    """

    # 仅从高质量执行生成 Skills
    MIN_GRADE = "B"
    MIN_SCORE = 0.7
    MIN_REUSABILITY_SCORE = 0.6  # 最低可复用性评分

    def __init__(self, skill_registry: Optional[SkillRegistry] = None):
        self.registry = skill_registry or SkillRegistry()

    def generate_from_execution(self, execution_result: Dict[str, Any]) -> Optional[Skill]:
        """
        从 Bundle 执行结果中提取可复用的技能模式

        触发条件:
        - Grade >= B 或 Score >= 0.7
        - 执行结果包含可提取的模式
        - 可复用性评分 >= 0.6
        """
        eval_data = execution_result.get("eval", {})
        grade = eval_data.get("grade", "C")
        score = eval_data.get("score", 0.5)

        # 只从高质量执行生成
        if grade < self.MIN_GRADE and score < self.MIN_SCORE:
            logger.info(f"Skip skill generation: grade={grade}, score={score}")
            return None

        # 分析执行轨迹
        execution_history = execution_result.get("execution_history", [])
        if not execution_history:
            return None

        # 深度分析执行轨迹
        trace_analysis = self.analyze_execution_trace(execution_history, eval_data)

        # 检查可复用性评分
        if trace_analysis.reusability_score < self.MIN_REUSABILITY_SCORE:
            logger.info(f"Skip skill generation: reusability_score={trace_analysis.reusability_score:.2f} (too low)")
            return None

        # 生成 Skill
        skill = self._create_skill_from_analysis(trace_analysis, execution_result)
        return skill

    def analyze_execution_trace(
        self,
        execution_history: List[Dict[str, Any]],
        eval_data: Dict[str, Any]
    ) -> ExecutionTraceAnalysis:
        """
        深度分析执行轨迹

        分析内容:
        1. 识别关键决策点
        2. 提取通用模式 vs 特定情况
        3. 识别成功/失败的关键因素
        4. 评估可复用性评分
        """
        key_decisions = []
        tool_sequences = []
        success_factors = []
        failure_risks = []

        # 分析执行步骤
        for record in execution_history:
            if not isinstance(record, dict):
                continue

            # 提取决策点
            if "decision" in record:
                key_decisions.append(record["decision"])

            # 提取工具使用序列
            if "tool" in record:
                tool_sequences.append(record["tool"])

            # 提取结果和状态
            if "result" in record:
                result = record["result"]
                if isinstance(result, dict):
                    if result.get("success"):
                        success_factors.append(f"工具 {record.get('tool', 'unknown')} 执行成功")
                    elif result.get("error"):
                        failure_risks.append(f"工具 {record.get('tool', 'unknown')} 错误：{result.get('error')}")

        # 分析成功因素
        eval_success_factors = eval_data.get("success_factors", [])
        if eval_success_factors:
            success_factors.extend(eval_success_factors)

        # 计算可复用性评分
        reusability_score = self._compute_reusability_score(
            key_decisions=key_decisions,
            tool_sequences=tool_sequences,
            execution_length=len(execution_history),
            success_factors=success_factors
        )

        # 确定泛化程度
        generalization_level = self._determine_generalization_level(reusability_score)

        # 推断推荐类别
        recommended_category = self._infer_category_from_tools(tool_sequences)

        # 计算置信度
        confidence = self._compute_confidence(execution_history, eval_data)

        # 提取常见模式
        common_patterns = self._extract_common_patterns(tool_sequences, key_decisions)

        return ExecutionTraceAnalysis(
            key_decisions=key_decisions,
            common_patterns=common_patterns,
            success_factors=success_factors,
            failure_risks=failure_risks,
            reusability_score=reusability_score,
            generalization_level=generalization_level,
            recommended_category=recommended_category,
            confidence=confidence
        )

    def _extract_success_pattern(
        self,
        execution_history: List[Dict[str, Any]],
        eval_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """从执行历史中提取成功模式"""
        if not execution_history:
            return None

        # 分析执行步骤
        steps = []
        tools_used = set()
        key_decisions = []

        for record in execution_history:
            if isinstance(record, dict):
                if "step" in record:
                    steps.append(record["step"])
                if "tool" in record:
                    tools_used.add(record["tool"])
                if "decision" in record:
                    key_decisions.append(record["decision"])

        # 必须有可识别的模式
        if not steps and not key_decisions:
            return None

        return {
            "steps": steps,
            "tools_used": list(tools_used),
            "key_decisions": key_decisions,
            "success_factors": eval_data.get("success_factors", []),
        }

    def _create_skill(
        self,
        pattern: Dict[str, Any],
        execution_result: Dict[str, Any]
    ) -> Skill:
        """创建 Skill 对象"""
        bundle_id = execution_result.get("bundle_id", "unknown")
        timestamp = int(time.time())

        # 生成 Skill ID
        skill_id = f"{bundle_id}_{timestamp}"

        # 生成 Prompt Template
        prompt_template = self._generate_prompt_template(pattern)

        # 确定类别
        category = self._infer_category(pattern)

        return Skill(
            skill_id=skill_id,
            name=f"从 {bundle_id} 学到的技能",
            description=f"从 Bundle {bundle_id} 的成功执行中提取",
            category=category,
            prompt_template=prompt_template,
            required_tools=pattern.get("tools_used", []),
            source_bundle=bundle_id,
        )

    def _generate_prompt_template(self, pattern: Dict[str, Any]) -> str:
        """生成 Prompt Template"""
        steps = pattern.get("steps", [])
        key_decisions = pattern.get("key_decisions", [])

        template_parts = ["执行以下步骤：\n"]

        for i, step in enumerate(steps, 1):
            template_parts.append(f"{i}. {step}")

        if key_decisions:
            template_parts.append("\n关键决策点：")
            for decision in key_decisions:
                template_parts.append(f"- {decision}")

        return "\n".join(template_parts)

    def _infer_category(self, pattern: Dict[str, Any]) -> str:
        """推断技能类别"""
        tools = pattern.get("tools_used", [])

        if "python_exec" in tools or "file_read" in tools:
            return "data"
        if "web_search" in tools or "browser_read" in tools:
            return "research"
        if "file_write" in tools or "shell_exec" in tools:
            return "code"

        return "general"

    def _compute_reusability_score(
        self,
        key_decisions: List[Any],
        tool_sequences: List[str],
        execution_length: int,
        success_factors: List[str]
    ) -> float:
        """
        计算可复用性评分 (0.0 - 1.0)

        考虑因素:
        - 决策点数量 (适中的决策点表示有思考过程)
        - 工具多样性 (使用多种工具表示通用性)
        - 执行长度 (太长可能太具体，太短可能太简单)
        - 成功因素数量
        """
        score = 0.5  # 基础分

        # 决策点评分 (0-0.2)
        num_decisions = len(key_decisions)
        if 2 <= num_decisions <= 8:
            score += 0.2  # 适中的决策点
        elif 1 <= num_decisions <= 10:
            score += 0.1
        elif num_decisions > 0:
            score += 0.05

        # 工具多样性评分 (0-0.2)
        unique_tools = len(set(tool_sequences))
        if unique_tools >= 3:
            score += 0.2
        elif unique_tools >= 2:
            score += 0.15
        elif unique_tools >= 1:
            score += 0.1

        # 执行长度评分 (0-0.2)
        if 3 <= execution_length <= 15:
            score += 0.2  # 适中长度
        elif 2 <= execution_length <= 20:
            score += 0.1
        elif execution_length > 0:
            score += 0.05

        # 成功因素评分 (0-0.2)
        num_factors = len(success_factors)
        if num_factors >= 3:
            score += 0.2
        elif num_factors >= 2:
            score += 0.15
        elif num_factors >= 1:
            score += 0.1

        return min(1.0, max(0.0, score))

    def _determine_generalization_level(self, reusability_score: float) -> str:
        """确定泛化程度"""
        if reusability_score >= 0.8:
            return "general"  # 高度通用
        elif reusability_score >= 0.6:
            return "moderate"  # 中等通用
        else:
            return "specific"  # 特定情况

    def _infer_category_from_tools(self, tool_sequences: List[str]) -> str:
        """从工具序列推断推荐类别"""
        unique_tools = set(tool_sequences)

        if "python_exec" in unique_tools or "file_read" in unique_tools:
            return "data"
        if "web_search" in unique_tools or "browser_read" in unique_tools:
            return "research"
        if "file_write" in unique_tools or "shell_exec" in unique_tools:
            return "code"
        if "browser_open" in unique_tools:
            return "research"

        return "general"

    def _compute_confidence(
        self,
        execution_history: List[Dict[str, Any]],
        eval_data: Dict[str, Any]
    ) -> float:
        """
        计算分析置信度

        基于:
        - 执行记录完整性
        - 评估数据质量
        - 执行一致性
        """
        confidence = 0.5  # 基础置信度

        # 执行记录完整性 (0-0.3)
        if len(execution_history) >= 5:
            confidence += 0.3
        elif len(execution_history) >= 3:
            confidence += 0.2
        elif len(execution_history) >= 1:
            confidence += 0.1

        # 评估数据质量 (0-0.4)
        if eval_data.get("grade") == "A":
            confidence += 0.2
        elif eval_data.get("grade") == "B":
            confidence += 0.15

        score = eval_data.get("score", 0.5)
        if score >= 0.9:
            confidence += 0.2
        elif score >= 0.7:
            confidence += 0.1

        return min(1.0, max(0.0, confidence))

    def _extract_common_patterns(
        self,
        tool_sequences: List[str],
        key_decisions: List[Any]
    ) -> List[str]:
        """提取常见模式"""
        patterns = []

        # 工具使用模式
        if len(tool_sequences) >= 2:
            # 检测工具序列模式
            tool_pattern = " -> ".join(tool_sequences[:5])  # 取前 5 个
            patterns.append(f"工具序列：{tool_pattern}")

        # 决策模式
        if key_decisions:
            patterns.append(f"关键决策数：{len(key_decisions)}")

        return patterns

    def _create_skill_from_analysis(
        self,
        analysis: ExecutionTraceAnalysis,
        execution_result: Dict[str, Any]
    ) -> Skill:
        """基于分析结果创建 Skill"""
        bundle_id = execution_result.get("bundle_id", "unknown")
        timestamp = int(time.time())

        # 生成 Skill ID
        skill_id = f"{bundle_id}_{timestamp}"

        # 生成更智能的 Prompt Template
        prompt_template = self._generate_smart_prompt_template(analysis)

        # 生成更好的名称和描述
        name = self._generate_skill_name(analysis, bundle_id)
        description = self._generate_skill_description(analysis, bundle_id)

        # 提取使用的工具
        tools_used = list(set(
            tool for tool in execution_result.get("tools_used", [])
            if tool
        ))

        return Skill(
            skill_id=skill_id,
            name=name,
            description=description,
            category=analysis.recommended_category,
            prompt_template=prompt_template,
            required_tools=tools_used,
            source_bundle=bundle_id,
            # 新增字段用于追踪质量
            usage_count=0,
            success_count=0,
            created_at=timestamp,
            last_used_at=None,
        )

    def _generate_smart_prompt_template(self, analysis: ExecutionTraceAnalysis) -> str:
        """生成智能 Prompt Template"""
        parts = ["# 执行指南\n"]

        # 添加常见模式
        if analysis.common_patterns:
            parts.append("## 模式识别")
            for pattern in analysis.common_patterns:
                parts.append(f"- {pattern}")
            parts.append("")

        # 添加关键决策点
        if analysis.key_decisions:
            parts.append("## 关键决策点")
            for i, decision in enumerate(analysis.key_decisions[:5], 1):  # 限制 5 个
                parts.append(f"{i}. {decision}")
            parts.append("")

        # 添加成功因素
        if analysis.success_factors:
            parts.append("## 成功因素")
            for factor in analysis.success_factors[:5]:  # 限制 5 个
                parts.append(f"- {factor}")
            parts.append("")

        # 添加风险提示
        if analysis.failure_risks:
            parts.append("## 注意事项")
            for risk in analysis.failure_risks[:3]:  # 限制 3 个
                parts.append(f"⚠ {risk}")
            parts.append("")

        parts.append("## 执行步骤")
        parts.append("根据上述模式和决策点执行任务，注意避免已识别的风险。")

        return "\n".join(parts)

    def _generate_skill_name(self, analysis: ExecutionTraceAnalysis, bundle_id: str) -> str:
        """生成技能名称"""
        category_prefix = {
            "data": "数据分析",
            "research": "信息搜集",
            "code": "代码处理",
            "general": "通用"
        }
        prefix = category_prefix.get(analysis.recommended_category, "通用")

        level = {
            "general": "高级",
            "moderate": "中级",
            "specific": "专用"
        }
        level_str = level.get(analysis.generalization_level, "")

        return f"{level_str}{prefix}技能 ({bundle_id})"

    def _generate_skill_description(
        self,
        analysis: ExecutionTraceAnalysis,
        bundle_id: str
    ) -> str:
        """生成技能描述"""
        return (
            f"从 Bundle {bundle_id} 提取的{analysis.generalization_level}技能。"
            f"类别：{analysis.recommended_category}。"
            f"可复用性评分：{analysis.reusability_score:.2f}。"
            f"包含{len(analysis.success_factors)}个成功因素，{len(analysis.failure_risks)}个风险提示。"
        )


class SkillOptimizer:
    """
    Skill 优化器

    基于使用频率和成功率优化 Skills
    """

    def __init__(self, skill_registry: Optional[SkillRegistry] = None):
        self.registry = skill_registry or SkillRegistry()

    def analyze_usage(self) -> Dict[str, SkillUsageStats]:
        """分析所有 Skill 的使用情况"""
        all_skills = self.registry.get_all_skills()
        stats = {}

        for skill_id, skill in all_skills.items():
            if skill.usage_count == 0:
                trend = "stable"  # 新技能
            else:
                success_rate = skill.success_count / skill.usage_count
                if success_rate > 0.8:
                    trend = "increasing"
                elif success_rate < 0.5:
                    trend = "decreasing"
                else:
                    trend = "stable"

            stats[skill_id] = SkillUsageStats(
                skill_id=skill_id,
                total_uses=skill.usage_count,
                success_rate=skill.success_count / max(1, skill.usage_count),
                avg_execution_time=0.0,  # TODO: 记录执行时间
                last_used_at=skill.last_used_at or 0,
                trend=trend,
            )

        return stats

    def optimize(self, usage_stats: Dict[str, SkillUsageStats]) -> List[Dict[str, Any]]:
        """
        基于使用统计优化 Skills

        优化策略:
        - 高频低成功率：需要改进提示词
        - 低频高成功率：需要推广使用
        - 低频低成功率：考虑废弃
        """
        optimization_plan = []

        for skill_id, stat in usage_stats.items():
            if stat.total_uses == 0:
                continue

            recommendation = self._analyze_skill(stat)
            if recommendation:
                optimization_plan.append({
                    "skill_id": skill_id,
                    "recommendation": recommendation,
                    "priority": self._calculate_priority(stat),
                })

        # 按优先级排序
        optimization_plan.sort(key=lambda x: x["priority"], reverse=True)
        return optimization_plan

    def _analyze_skill(self, stat: SkillUsageStats) -> Optional[str]:
        """分析单个 Skill 并给出建议"""
        if stat.success_rate < 0.5 and stat.total_uses >= 3:
            return "低成功率 - 建议改进提示词或增加示例"
        if stat.success_rate > 0.8 and stat.total_uses < 5:
            return "高成功率但低频 - 建议推广使用"
        if stat.success_rate < 0.5 and stat.total_uses >= 10:
            return "持续低表现 - 考虑废弃或重构"
        if stat.trend == "decreasing":
            return "使用趋势下降 - 检查是否有更好的替代方案"

        return None

    def _calculate_priority(self, stat: SkillUsageStats) -> float:
        """计算优化优先级"""
        base = 0

        # 低成功率优先
        if stat.success_rate < 0.5:
            base += 3
        elif stat.success_rate < 0.7:
            base += 1

        # 高频使用优先
        if stat.total_uses >= 10:
            base += 2
        elif stat.total_uses >= 5:
            base += 1

        # 下降趋势优先
        if stat.trend == "decreasing":
            base += 2

        return base

    def execute_optimization(self, optimization_plan: List[Dict[str, Any]]):
        """执行优化计划"""
        for item in optimization_plan:
            skill_id = item["skill_id"]
            recommendation = item["recommendation"]

            logger.info(f"Optimizing skill {skill_id}: {recommendation}")

            # TODO: 实际执行优化操作
            # 1. 改进提示词
            # 2. 添加示例
            # 3. 标记废弃
            # 4. 从注册表移除


@dataclass
class UsagePattern:
    """技能使用模式"""
    skill_id: str
    common_scenarios: List[str]
    avg_success_rate: float
    peak_usage_time: Optional[str]
    related_tasks: List[str]
    effectiveness_score: float


class SkillRecommender:
    """
    Skill 推荐器

    功能:
    1. 根据任务描述推荐技能
    2. 分析技能使用模式
    3. 识别技能在什么场景下最有效
    """

    def __init__(self, skill_registry: Optional[SkillRegistry] = None):
        self.registry = skill_registry or SkillRegistry()
        self._usage_history: List[Dict[str, Any]] = []  # 记录使用情况

    def recommend_for_task(
        self,
        task_desc: str,
        role: str = "",
        top_k: int = 5
    ) -> List[Skill]:
        """
        根据任务描述推荐技能

        Args:
            task_desc: 任务描述
            role: 角色类型 (planner, coder, analyst 等)
            top_k: 返回 Top-N 个推荐

        Returns:
            推荐技能列表
        """
        all_skills = self.registry.get_all_skills()
        if not all_skills:
            return []

        # 计算每个技能的相关性评分
        scored_skills = []

        for skill_id, skill in all_skills.items():
            score = self._compute_skill_relevance(skill, task_desc, role)
            if score > 0.2:  # 阈值过滤
                scored_skills.append((skill, score))

        # 按评分排序
        scored_skills.sort(key=lambda x: x[1], reverse=True)

        # 返回 Top-K
        return [skill for skill, score in scored_skills[:top_k]]

    def _compute_skill_relevance(
        self,
        skill: Skill,
        task_desc: str,
        role: str
    ) -> float:
        """
        计算技能相关性评分

        考虑因素:
        1. 角色匹配度 (40%)
        2. 任务描述关键词匹配 (30%)
        3. 历史成功率 (20%)
        4. 使用频率 (10%)
        """
        score = 0.0

        # 1. 角色匹配度 (40%)
        role_match = self._compute_role_match(skill, role)
        score += role_match * 0.4

        # 2. 任务描述关键词匹配 (30%)
        task_match = self._compute_task_match(skill, task_desc)
        score += task_match * 0.3

        # 3. 历史成功率 (20%)
        if skill.usage_count > 0:
            success_rate = skill.success_count / skill.usage_count
            score += success_rate * 0.2
        else:
            score += 0.1  # 新技能给基础分

        # 4. 使用频率 (10%) - 归一化
        frequency_score = min(1.0, skill.usage_count / 10)
        score += frequency_score * 0.1

        return score

    def _compute_role_match(self, skill: Skill, role: str) -> float:
        """计算角色匹配度"""
        if not role:
            return 0.5  # 无角色时给中等分数

        role_lower = role.lower()

        # 角色 - 技能映射
        role_skill_keywords = {
            "planner": ["plan", "search", "analyze", "规划", "计划"],
            "analyst": ["analyze", "search", "data", "分析", "调研"],
            "collector": ["collect", "search", "browser", "搜集", "采集"],
            "evaluator": ["evaluate", "check", "review", "评估", "审查"],
            "reviewer": ["review", "check", "analyze", "审查", "检查"],
            "critic": ["critic", "review", "analyze", "批判", "评估"],
            "summarizer": ["summary", "document", "summarize", "总结", "摘要"],
            "master": ["master", "general", "overview", "总控", "通用"],
            "coder": ["code", "write", "file", "shell", "代码", "文件"],
            "researcher": ["search", "browser", "research", "搜索", "研究"],
        }

        for r, keywords in role_skill_keywords.items():
            if r in role_lower:
                # 检查技能描述是否包含相关关键词
                skill_text = f"{skill.description} {skill.prompt_template}".lower()
                match_count = sum(1 for kw in keywords if kw.lower() in skill_text)
                if match_count > 0:
                    return min(1.0, match_count / len(keywords))

        return 0.3  # 默认较低分数

    def _compute_task_match(self, skill: Skill, task_desc: str) -> float:
        """计算任务描述匹配度"""
        if not task_desc:
            return 0.5

        task_lower = task_desc.lower()
        skill_text = f"{skill.description} {skill.prompt_template}".lower()

        # 提取任务关键词
        task_keywords = self._extract_keywords(task_lower)

        if not task_keywords:
            return 0.3

        # 计算关键词匹配
        match_count = sum(1 for kw in task_keywords if kw in skill_text)
        return min(1.0, match_count / len(task_keywords))

    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        import re
        stopwords = {"的", "了", "在", "是", "我", "有", "和", "就", "不", "与", "等", "及", "一个", "一些", "请", "帮我", "需要", "想要"}

        # 提取中英文词
        words = re.findall(r'[a-zA-Z0-9\u4e00-\u9fff]+', text)
        return [w for w in words if w.lower() not in stopwords and len(w) > 1]

    def get_skill_usage_pattern(self, skill_id: str) -> Optional[UsagePattern]:
        """
        分析技能使用模式

        识别技能在什么场景下最有效
        """
        all_skills = self.registry.get_all_skills()
        if skill_id not in all_skills:
            return None

        skill = all_skills[skill_id]

        # 从使用历史中分析模式
        skill_usage = [u for u in self._usage_history if u.get("skill_id") == skill_id]

        common_scenarios = []
        related_tasks = []

        if skill_usage:
            # 提取常见场景
            scenarios = set()
            tasks = set()
            for usage in skill_usage:
                if "scenario" in usage:
                    scenarios.add(usage["scenario"])
                if "task_desc" in usage:
                    tasks.add(usage["task_desc"][:50])

            common_scenarios = list(scenarios)[:5]
            related_tasks = list(tasks)[:5]

        # 计算有效性评分
        effectiveness = 0.5
        if skill.usage_count > 0:
            success_rate = skill.success_count / skill.usage_count
            effectiveness = 0.5 + success_rate * 0.5

        return UsagePattern(
            skill_id=skill_id,
            common_scenarios=common_scenarios,
            avg_success_rate=skill.success_count / max(1, skill.usage_count),
            peak_usage_time=None,  # TODO: 实现时间分析
            related_tasks=related_tasks,
            effectiveness_score=effectiveness,
        )

    def record_usage(
        self,
        skill_id: str,
        task_desc: str,
        role: str,
        success: bool,
        scenario: str = ""
    ):
        """记录技能使用情况"""
        self._usage_history.append({
            "skill_id": skill_id,
            "task_desc": task_desc,
            "role": role,
            "success": success,
            "scenario": scenario,
            "timestamp": time.time(),
        })

        # 更新技能统计
        all_skills = self.registry.get_all_skills()
        if skill_id in all_skills:
            skill = all_skills[skill_id]
            skill.usage_count += 1
            if success:
                skill.success_count += 1
            skill.last_used_at = time.time()

    def get_recommendation_explanation(self, skill: Skill, task_desc: str) -> str:
        """获取推荐解释"""
        reasons = []

        # 成功率
        if skill.usage_count > 0:
            rate = skill.success_count / skill.usage_count
            if rate > 0.8:
                reasons.append(f"历史成功率 {rate:.0%}")
            elif rate < 0.5:
                reasons.append(f"成功率较低 {rate:.0%}")

        # 使用频率
        if skill.usage_count >= 10:
            reasons.append(f"已使用 {skill.usage_count} 次")
        elif skill.usage_count == 0:
            reasons.append("新技能")

        # 类别匹配
        if task_desc:
            task_lower = task_desc.lower()
            if skill.category == "data" and any(kw in task_lower for kw in ["data", "分析", "统计"]):
                reasons.append("适合数据分析任务")
            elif skill.category == "research" and any(kw in task_lower for kw in ["搜索", "研究", "查找"]):
                reasons.append("适合信息搜集任务")
            elif skill.category == "code" and any(kw in task_lower for kw in ["代码", "文件", "程序"]):
                reasons.append("适合代码处理任务")

        return "; ".join(reasons) if reasons else "通用推荐"


class SkillPool:
    """
    SkillPool - 能力固化池

    统一管理 Skills 的生成、存储、检索和优化
    """

    _instance: Optional["SkillPool"] = None

    @classmethod
    def get_instance(cls, skills_dir: Optional[Path] = None) -> "SkillPool":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls(skills_dir)
        return cls._instance

    def __init__(self, skills_dir: Optional[Path] = None):
        self.skills_dir = skills_dir or Path.home() / ".swarmbot" / "skills"
        self.registry = SkillRegistry(self.skills_dir)
        self.generator = SkillGenerator(self.registry)
        self.optimizer = SkillOptimizer(self.registry)
        self.recommender = SkillRecommender(self.registry)

    def generate_skill_from_execution(self, execution_result: Dict[str, Any]) -> Optional[Skill]:
        """从执行结果生成 Skill"""
        skill = self.generator.generate_from_execution(execution_result)
        if skill:
            self.registry.register_skill(skill)
        return skill

    def get_skills_for_task(
        self,
        role: str,
        task_desc: str = "",
        required_skills: Optional[List[str]] = None
    ) -> Dict[str, bool]:
        """为任务获取相关 Skills"""
        # 兼容现有 InferenceLoop 的接口
        VALID_SKILLS = {
            "whiteboard_update",
            "hot_memory_update",
            "web_search",
            "browser_open",
            "browser_read",
            "file_read",
            "file_write",
            "python_exec",
            "shell_exec",
        }

        out = {"whiteboard_update": True, "hot_memory_update": True}

        # 按角色获取
        role_lower = (role or "").strip().lower()
        role_skill_map = {
            "planner": ["web_search", "python_exec"],
            "analyst": ["web_search", "browser_read", "python_exec"],
            "collector": ["web_search", "browser_open", "browser_read", "file_read"],
            "evaluator": ["file_read", "python_exec"],
            "reviewer": ["file_read", "python_exec"],
            "critic": ["web_search", "python_exec"],
            "summarizer": ["file_read", "python_exec"],
            "master": ["file_read", "web_search"],
            "coder": ["file_write", "shell_exec", "file_read", "python_exec"],
            "researcher": ["web_search", "browser_open", "browser_read"],
        }

        for r, skills in role_skill_map.items():
            if r in role_lower:
                for s in skills:
                    if s in VALID_SKILLS:
                        out[s] = True

        # 按任务描述获取
        desc_lower = (task_desc or "").lower()
        domain_map = {
            "code": ["file_read", "file_write", "python_exec"],
            "research": ["web_search", "browser_open", "browser_read"],
            "data": ["python_exec", "file_read", "file_write"],
            "analysis": ["python_exec", "web_search"],
        }

        for domain, skills in domain_map.items():
            if domain in desc_lower:
                for s in skills:
                    if s in VALID_SKILLS:
                        out[s] = True

        # 显式要求的技能
        for s in (required_skills or []):
            if isinstance(s, str) and s in VALID_SKILLS:
                out[s] = True

        return out

    def get_all_skills(self) -> Dict[str, Skill]:
        """获取所有 Skills"""
        return self.registry.get_all_skills()

    def run_optimization_cycle(self):
        """执行一轮优化"""
        usage_stats = self.optimizer.analyze_usage()
        optimization_plan = self.optimizer.optimize(usage_stats)
        self.optimizer.execute_optimization(optimization_plan)
        return optimization_plan

    # SkillRecommender 代理方法

    def recommend_skills(
        self,
        task_desc: str,
        role: str = "",
        top_k: int = 5
    ) -> List[Skill]:
        """推荐技能"""
        return self.recommender.recommend_for_task(task_desc, role, top_k)

    def get_skill_usage_pattern(self, skill_id: str) -> Optional[UsagePattern]:
        """获取技能使用模式"""
        return self.recommender.get_skill_usage_pattern(skill_id)

    def record_skill_usage(
        self,
        skill_id: str,
        task_desc: str,
        role: str,
        success: bool,
        scenario: str = ""
    ):
        """记录技能使用"""
        self.recommender.record_usage(skill_id, task_desc, role, success, scenario)

    def get_recommendation_explanation(self, skill: Skill, task_desc: str) -> str:
        """获取推荐解释"""
        return self.recommender.get_recommendation_explanation(skill, task_desc)
