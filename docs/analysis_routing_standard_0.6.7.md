# Analysis 路由标准（v0.6.7）

## 三档路由

1. `simple_direct_master`  
   - 目标：普通问答、轻沟通、简短建议。  
   - 执行：Analysis 后直接 Master 回复，不进入 swarm 推理链。  
   - 输出要求：先人话再结构，不出现执行体术语。  

2. `reasoning_swarm`  
   - 目标：需要分析/哲学心理分析/简单代码与参数调整。  
   - 执行：Analysis → Collection → Planning → Swarm(2-5 workers) → Master。  
   - 说明：不进入多轮评估重试，以降低时延。  

3. `engineering_complex`  
   - 目标：工程复杂问题（多文件、线上故障、架构改造、高风险变更）。  
   - 执行：完整 swarm + loop（包含评估与必要重规划）。  

## 决策规则

- 首选 Analysis 结果 + 用户输入语义做 3 次多数决。  
- 当模型决策失败时，使用启发式回退规则。  
- `reasoning_swarm` worker 数限制在 2-5。  

## 与原框架兼容性

- 不改动 Step Translation 的 Master 收口职责。  
- `engineering_complex` 路径保持原有完整链路。  
- 仅新增前置路由，不破坏现有 Tool Gate、校准与组织阶段。  

## 验收指标

1. 普通问题平均耗时显著低于完整链路。  
2. 普通问题输出中“命令化术语”占比下降。  
3. 工程复杂问题仍能走完整评估链，准确率不回退。  
