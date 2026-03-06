# Logic Trap Evaluation (agentcpm-explore)

## Scope

- Model: `agentcpm-explore`
- Pipeline: Swarmbot 8-phase inference loop
- Focus:
  - Logical trap handling for prerequisite constraints
  - Role assignment and evaluation loop behavior
  - Tool/skill call observability

## Test Set

1. 洗车店 50 米：应避免“人到场但车不到场”错误
2. 快递点近但包裹在家：应先拿包裹
3. 打印店近但 U 盘在办公室：应先取依赖再执行

## Baseline (before calibration fix)

- Report: `artifacts/logic_traps_baseline.json`
- Result:
  - Direct QA: `0.333`
  - Swarm loop: `0.333`
- Typical failure:
  - 小模型把“距离近”当作唯一优化目标，忽略“前置条件必须先满足”。

## After Fix (local source)

- Report: `artifacts/logic_traps_round12_localsrc.json`
- Module under test:
  - `/root/swarmbot_dev/swarmbot/loops/inference.py`
- Result:
  - Direct QA: `0.333`
  - Swarm loop: `1.000`

## What Changed

- Added domain-neutral constraints in definitions:
  - memory filtering for unrelated entities
  - stronger domain grounding rules
- Added final-response calibration in inference loop:
  - derive hard constraints from input
  - detect prerequisite violations
  - deterministic fallback for prerequisite-location traps

## Observability Checks

- Roles observed in loop logs:
  - analyst / collector / planner / reasoner / evaluator / master
- Evaluation loop:
  - evaluation step and re-planning are traceable (`Step 6`, `Step 4b`)
- Tool/skill:
  - tool calls are logged and countable
  - skill calls remain optional and scenario-dependent

## Daemon/Gateway Regression Check

- `swarmbot daemon start` verified to auto-manage gateway:
  - `daemon_state.json` contains non-empty `services.gateway.pid`
