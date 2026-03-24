# Changelog

All notable changes to this project will be documented in this file.

## [2.0.3] - 2026-03-24

### Added

#### Agent Loop Architecture
- **New `swarmbot/agents/` directory** with complete agent architecture:
  - `base/`: BaseAgent, AgentContext, EventBus, AgentLoop
  - `master/`: MasterAgent, MasterLoop (max 2 iterations)
  - `workers/`: BaseWorkerAgent, WorkerLoop
  - `autonomous/`: AutonomousEngine, AutonomousLoop (max 5 iterations)
  - `research/`: AutoresearchMixin, MetricsEvaluator

- **Test suite** for agent loop:
  - `tests/test_agents/`: 42 unit tests
  - `tests/test_agent_loop_quick.py`: 50-question quick test
  - `tests/test_agent_loop_full.py`: 200-question comprehensive test (100 CN + 100 EN musique)

- **Data source**: `data/musique_full.json` with 4834 English multi-hop questions

#### Routing with Context
- **Before**: LLM classified questions without context
- **After**: MasterAgent reads session context before routing decision

### Changed

#### GatewayMasterAgent._think_then_decide()
- Now accepts `session_id` parameter
- Reads session history from `self._sessions` before routing
- Passes context to LLM for better classification
- Key improvement: Continuity questions now correctly route based on context

#### Routing Logic
- **Before**: Direct LLM classification based on text only
- **After**: 
  1. Read session context (before_think)
  2. LLM decides based on [context + question]
  3. Continuity questions with context → `standard`
  4. Greetings/concepts without context → `simple_direct`

### Fixed

- **Concept questions routing**: 0% → 100%
- **Greeting questions routing**: 43% → 71%
- **Overall routing accuracy**: 84% → 95%

### Performance

| Metric | Before | After |
|--------|--------|-------|
| Routing Accuracy | 84% | 95% |
| Concept Questions | 0% | 100% |
| Greeting Questions | 43% | 71% |
| Skill Conflicts | 0 | 0 |
| Memory Conflicts | 0 | 0 |

## [2.0.2] - 2026-03-24

### Added
- Agent Loop Architecture based on OpenClaw patterns
- AutoresearchMixin for self-optimization
- Bundle anti-over-optimization parameters

### Changed
- Restructured boot files by component
- Improved inference tool direct execution

## [2.0.1] - 2026-03-24

### Added
- 100-question evaluation with report generation
- 50-question agent evaluation with hybrid routing

## [2.0.0] - 2026-03-23

### Added
- GatewayMasterAgent with routing
- CommunicationHub for message queuing
- Standard/Supervised/Swarms inference tools
- Memory system (Whiteboard/Hot/Warm/Cold)
- SkillPool for capability consolidation
