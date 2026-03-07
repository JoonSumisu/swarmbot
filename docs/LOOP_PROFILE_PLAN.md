# Loop 优化方案（8-phase 保持不变）

## 目标

- 保持 Step7（master 对外转译）和 Step8（记忆整理）设计意图不变
- 其余 phase 通过可切换策略优化：
  - 优先分析，再决定是否调用 tool/skill
  - 利用 loop 弥补小模型逻辑短板
  - 降低无效工具调用与上下文开销

## 已实现改造

1. 工具调用门控（Analysis First）
   - Step3 改为“先无工具收集，再按需工具补充（Step3b）”
   - Step5 按 task 的 `tool` 字段精确放行工具
   - Step7 默认无工具，仅在实时/联网类问题启用
   - 门控决策采用 3 次无工具投票，多数决避免单次抖动

2. Skill 调用门控
   - 非显式技能请求时，自动屏蔽 `skill_*` 工具
   - 只有用户明确提及技能（如 `skill_summary` / `skill_load`）才允许调用

3. Loop Profile（可切换）
   - 通过 `SWARMBOT_LOOP_PROFILE` 切换：
     - `auto`: 先做 Step2 分析，再由 LLM 选择 profile
     - `lean`: 更低开销
     - `balanced`: 平衡精度与成本
     - `swarm_max`: 更高冗余与鲁棒性

## Profile 参数

- `auto`
  - 由初步分析结果驱动选择 lean / balanced / swarm_max
  - 采用 3 次无工具投票多数决，降低单次误判
  - 若解析失败回退 `balanced`

- `lean`
  - analysis_workers=1
  - collection_workers=1
  - evaluation_workers=2
  - max_eval_loops=2
  - context_limit=3500

- `balanced`
  - analysis_workers=2
  - collection_workers=2
  - evaluation_workers=3
  - max_eval_loops=3
  - context_limit=6000

- `swarm_max`
  - analysis_workers=3
  - collection_workers=3
  - evaluation_workers=3
  - max_eval_loops=3
  - context_limit=9000

## 本地测试结论（agentcpm-explore）

- 评估脚本：`scripts/eval_loop_profiles.py`
- 样例集：逻辑陷阱 3 题（洗车/快递/打印）
- 结果：`artifacts/loop_profiles_profile_v1.json`

核心结论：
- 三个 profile 在该测试集准确率均为 1.0
- `balanced` 在准确率不降的前提下，综合开销更优（推荐默认）
- 工具调用和 skill 调用均受控，非必要场景下为 0
- 在 `auto` 模式下，profile 由 Step2 分析后的 LLM 决策，不再依赖硬编码关键词

## 你的验收建议

1. 先用 `balanced` 做主线回归
2. 高并发或轻量场景改用 `lean`
3. 高风险推理场景改用 `swarm_max`

## 运行命令

```bash
python scripts/eval_loop_profiles.py --model agentcpm-explore --tag profile_v1
python scripts/eval_logic_traps.py --model agentcpm-explore --tag final_check
```
