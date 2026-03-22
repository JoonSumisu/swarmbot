# Swarmbot

[中文](README.md) | [English](README_EN.md)

**Swarmbot (v1.1.0)** 是一个基于 **[swarms](https://github.com/kyegomez/swarms)** 和 **nanobot** 架构的多 Agent 集群智能系统，专为本地部署和私有 LLM 接口设计。

它集成了 **QMD 四层记忆系统**（白板、热记忆、温记忆、冷记忆）与 **三环自进化架构**（推理、反思、行动），支持通过 **Feishu (飞书/Lark)** 等 IM 通道进行交互。

> **核心理念**: "All-in-One" —— 将网关、记忆、工具链和多智能体编排融合在一个轻量级进程中。

---

## 📁 目录分层

- 开发/实验目录说明见 [WORKSPACE_LAYOUT.md](WORKSPACE_LAYOUT.md)

## 🌟 版本 v1.1.0 更新亮点

*   **3-Loop Architecture**: 
    *   **Inference Loop**: 8 步标准推理（分析-搜集-规划-执行-评估-转译-整理）。
    *   **Overthinking Loop**: 后台只读压缩，将短期记忆转化为长期知识 (QMD)。
    *   **Overaction Loop**: 主动进化，基于知识库进行联网补充、自我优化与记忆清理。
*   **4-Layer Memory**:
    *   L1 **Whiteboard**: 会话级临时白板。
    *   L2 **Hot Memory**: 1-7天短期记忆与待办 (Todo)。
    *   L3 **Warm Memory**: 时序性每日日志。
    *   L4 **Cold Memory**: 语义向量数据库 (QMD)。
*   **Native Feishu Integration**: 深度优化的飞书通道支持。

---

## 🧠 v0.6 Logic Enhanced (逻辑增强)

为了解决传统 Agent 容易陷入"效率陷阱"（如"50米走路比开车快，所以走路去洗车"）的逻辑漏洞，v0.6 引入了多重逻辑框架进行约束：

1.  **模态逻辑 (Modal Logic)**:
    *   区分 **必要性 (Necessary, □)** 与 **可能性 (Possible, ◇)**。
    *   强制检查前置条件（如：洗车必须带车）。
2.  **规范逻辑 (Deontic Logic)**:
    *   分析 **义务 (Obligation)**、**禁止 (Prohibition)** 与 **许可 (Permission)**。
3.  **认知逻辑 (Epistemic Logic)**:
    *   区分 **知识 (Knowledge)** 与 **信念 (Belief)**，减少幻觉。
4.  **控制论 (Cybernetics)**:
    *   引入反馈回路 (Feedback Loop) 进行自我纠错与系统优化。

这些逻辑约束被深度集成到 System Prompts 中，确保 Swarmbot 在推理时不仅考虑"怎么做最快"，更优先考虑"这样做是否符合物理/逻辑规律"。

---

## 🆕 v1.1 推理编排增强

- 引入 `framework_doc` 严格校验与落地，PLANNING 输出不再是松散 tasks。
- 执行链拆分为 Skill Discovery 与 Tool Decision 双通道，明确 `skill` 与 `tool` 边界。
- 新增 Supervisor 控制动作幂等与阶段锁机制，支持提前收敛评分触发输出。
- Whiteboard 升级为“关键信息 + 外部内容”平衡模型，减少噪声并保留关键上下文。

推荐本地模型测试名：

```bash
unsloth/qwen3-coder-next
```

---

## 🚀 快速开始

### 1. 安装

Swarmbot 支持 Python 3.10+。

如果你在 macOS（尤其是 Homebrew Python）上执行 `pip install .` 遇到：

```
This environment is externally managed
```

这是 Python 对“系统级 Python 环境”的保护机制（常见于 Homebrew / OS 发行版），为了避免把依赖装进系统 Python 导致环境损坏。解决方式是：**永远安装到虚拟环境（venv）**。

本项目内置了跨平台安装脚本，默认会优先做“**直接安装**”（无需手动激活 venv），并在安装后自动检查：

- `swarmbot` 核心模块可导入
- `gateway` 依赖可导入
- `Feishu(Lark)` 依赖 `lark-oapi` 可导入

- 优先使用 `pipx` 安装为全局可执行命令 `swarmbot`
- 若无 `pipx`，尝试 `pip --user` 安装
- 若都失败，再回退到 `.venv/` 安装
- 如需一键安装回归评测依赖，可追加 `--with-eval-deps`

**推荐（跨平台）**

```bash
git clone https://github.com/JoonSumisu/swarmbot.git
cd swarmbot
python3 scripts/bootstrap.py
```

你也可以明确指定安装模式：

```bash
# 直接安装（推荐，命令可直接用）
python3 scripts/bootstrap.py --mode pipx

# 用户目录安装（不进 venv）
python3 scripts/bootstrap.py --mode user

# 传统 venv 安装
python3 scripts/bootstrap.py --mode venv

# 开发调试（editable，代码改动即时生效）
python3 scripts/bootstrap.py --editable

# 安装并附带回归评测依赖（datasets）
python3 scripts/bootstrap.py --mode venv --with-eval-deps

# 跳过安装后检查（不推荐）
python3 scripts/bootstrap.py --skip-check
```

**macOS / Linux（可选）**

```bash
bash scripts/bootstrap.sh
```

**Windows PowerShell（可选）**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
```

安装完成后，优先直接使用：

```bash
swarmbot --help
```

若你选择了 `venv` 模式，再使用：

```bash
./.venv/bin/swarmbot --help
source ./.venv/bin/activate
```

### 2. 首次启动（Onboarding）

首次运行建议直接执行：

```bash
./.venv/bin/swarmbot daemon start
```

该命令会自动完成初始化并生成：

- 配置文件：`~/.swarmbot/config.json`
- 工作目录：`~/.swarmbot/workspace/`
- Boot 配置：`~/.swarmbot/boot/*.md`

如果你只想初始化但不启动守护进程：

```bash
./.venv/bin/swarmbot onboard
```

### 3. 配置模型（必须）

你可以手动编辑 `~/.swarmbot/config.json`，或使用 CLI：

```bash
# 设置主模型 (支持 OpenAI 兼容接口，如 vLLM, Ollama, DeepSeek 等)
./.venv/bin/swarmbot provider add \
  --base-url "http://127.0.0.1:8000/v1" \
  --api-key "sk-xxxx" \
  --model "qwen3-coder-next" \
  --max-tokens 8192
```

### 4. 配置通道（可选：Feishu / 飞书）

```bash
./.venv/bin/swarmbot channels add feishu \
  app_id=cli_xxx \
  app_secret=xxx \
  encrypt_key=xxx \
  verification_token=xxx
```

提示：如果不想把密钥写进 shell history，可以直接运行 `./.venv/bin/swarmbot channels add feishu`，按提示交互输入。

### 5. 启动 Gateway（接入 Feishu）

启动网关以接入 IM 通道（如 Feishu）并开启 API 服务：

```bash
# 前台启动
./.venv/bin/swarmbot gateway
```

快速可用性检查（推荐）：

```bash
# 仅验证网关可启动（20秒烟测）
timeout 20 ./.venv/bin/swarmbot gateway
```

### 6. 本地调试对话（不走 IM）

```bash
./.venv/bin/swarmbot run
```

### 7. 常用 CLI 命令速查

```bash
./.venv/bin/swarmbot status
./.venv/bin/swarmbot provider add --help
./.venv/bin/swarmbot channels list
./.venv/bin/swarmbot heartbeat status
./.venv/bin/swarmbot overthinking setup --enabled true --interval 30 --steps 20
./.venv/bin/swarmbot daemon shutdown
```

---

## 🧯 故障排查

- **pip 报错 This environment is externally managed**：不要 system-wide 安装；用 `python3 scripts/bootstrap.py` 创建 `.venv/`。
- **模型调用 Timeout**：降低 `--max-tokens` / 并发 worker 数，或提升推理服务并发与超时设置。
- **飞书无法收消息**：确认 `channels feishu` 已启用且 `app_id/app_secret` 正确，网关在运行（`swarmbot gateway`）。

---

## ✅ 实时链路验证（Gateway + Loops）

建议每次升级后按以下清单做一次健康检查：

1. **启动守护进程并确认子进程**
```bash
./.venv/bin/swarmbot daemon start
pgrep -af "swarmbot.daemon|swarmbot.cli gateway|swarmbot.cli overthinking"
```

2. **检查网关日志四段链路**
- 收到消息：`[Feishu] Received message ...`
- 推理执行：`[InferenceLoop] Start: ...`
- 出站发布：`publish_outbound` 后续日志
- 飞书发送：`Feishu message sent ...` 或 fallback 文本发送日志

3. **检查 Inference Tool Call**
- 观察 `[CoT] ... calls tool: ...` 日志，确认 `whiteboard_update` / `context_policy_update` / `skill_summary` / `skill_load` 可调用。

4. **检查 EvoMap / Whiteboard（MemoryMap）**
- 本项目中的 EvoMap 对应 `MemoryMap/Whiteboard`。
- 通过工具调用写入并验证键值（如 `evomap_status=ready`）可确认可用。

5. **检查后台双环**
- Overthinking 周期日志：`[Overthinking] Cycle ... Added N entries to Cold Memory.`
- Overaction 周期日志：`[Overaction] Cycle ...` 与 Warm Memory 清理日志。

6. **关键日志路径**
```bash
tail -n 200 ~/.swarmbot/logs/daemon_gateway.log
tail -n 200 ~/.swarmbot/logs/gateway.log
cat ~/.swarmbot/daemon_state.json
```

---

## 🧪 回归测试（本地模型）

建议在核心逻辑改动后至少执行一轮回归：

```bash
# 逻辑陷阱回归（推荐 qwen3-coder-next）
./.venv/bin/python scripts/eval_logic_traps.py --model qwen3-coder-next --tag reg_$(date +%Y%m%d_%H%M)

# 本地问答样例回归
./.venv/bin/python scripts/eval_local_agent.py --tag reg_local_$(date +%Y%m%d_%H%M) --limit 4
```

默认输出到 `artifacts/`，可用于前后版本对比。

---

## 🔬 实验脚本

### Bundle 自优化实验

验证 Autonomous Engine 的 Bundle 自优化闭环能力：

```bash
# 完整实验流程
./.venv/bin/python tests/experiment_bundle_optimization.py --phase all

# 单独运行某个阶段
./.venv/bin/python tests/experiment_bundle_optimization.py --phase create   # 创建 Bundle
./.venv/bin/python tests/experiment_bundle_optimization.py --phase monitor  # 监控执行
./.venv/bin/python tests/experiment_bundle_optimization.py --phase inject   # 注入低分
./.venv/bin/python tests/experiment_bundle_optimization.py --phase analyze  # 分析效果

# 自定义参数
./.venv/bin/python tests/experiment_bundle_optimization.py --phase all \
  --prompt "请创建一个监控系统状态的 Bundle" \
  --min-executions 5 \
  --eval-score 0.4
```

实验报告输出：`artifacts/bundle_optimization_report_*.json`

详细实验设计参考：[docs/EXPERIMENT_BUNDLE_SELF_OPTIMIZATION.md](docs/EXPERIMENT_BUNDLE_SELF_OPTIMIZATION.md)

### 全流程冒烟测试

验证从安装配置到自主运行的完整用户旅程：

```bash
# 完整测试
./.venv/bin/python tests/smoke_test_full_e2e.py

# 快速测试（跳过部分阶段）
./.venv/bin/python tests/smoke_test_full_e2e.py --quick

# 仅测试特定阶段
./.venv/bin/python tests/smoke_test_full_e2e.py --phase 1,2,3
```

测试报告输出：`artifacts/smoke_test_full_report.json`

详细测试报告参考：[docs/SMOKE_TEST_REPORT_2026-03-22.md](docs/SMOKE_TEST_REPORT_2026-03-22.md)

---

## 🧩 关键设计细节（Docs 摘要）

### 1) Loop Profile 与 Worker 自动分配

Inference Loop 固定 8 个 phase，但不同 profile 会自动调整 worker 数、上下文窗口和重试次数：

| Profile | analysis_workers | collection_workers | evaluation_workers | max_eval_loops | context_limit |
|:--|--:|--:|--:|--:|--:|
| `lean` | 1 | 1 | 2 | 2 | 3500 |
| `balanced` (默认推荐) | 2 | 2 | 3 | 3 | 6000 |
| `swarm_max` | 3 | 3 | 3 | 3 | 9000 |

在 `auto` 模式下，系统会先做分析，再通过 3 次无工具投票多数决选择 profile，避免单次抖动误判。

### 2) 多 Worker 并行策略

- Analysis / Collection / Evaluation 使用并行 worker。
- Inference Step 会对 plan 中的多 task 并行执行（不是串行逐个执行）。
- 当单次 LLM 返回多个 `tool_calls` 时，会按调用数量并发执行工具。
- Tool Gate / Profile Gate 的多次投票请求为并行发起。

这意味着：只要某个 phase 分配了 N 个 worker，就会并发发起 N 路请求（受运行时资源与服务端限流影响）。

### 3) Overthinking / Overaction 自动运行机制

- `swarmbot gateway` 启动时，如果 `overthinking.enabled=true`，会自动拉起：
  - Overthinking Loop（默认 30 分钟周期）
  - Overaction Loop（默认 60 分钟周期）
- `swarmbot daemon start` 在默认配置下会托管并自愈：
  - Gateway 进程
  - Overthinking 进程

建议线上采用 daemon 模式，以获得自动重启和状态托管能力。

### 4) Runtime Guards（推理链路保护）

- 每条入站消息使用隔离的 `InferenceLoop` 实例，避免会话间白板污染。
- 出站消息异步分发，并对瞬时失败进行重试路径处理。
- 推理异常时会输出 fallback 回复，避免“吞消息”。

### 5) 推荐模型配置（本地 OpenAI 兼容）

```bash
./.venv/bin/swarmbot provider add \
  --base-url "http://127.0.0.1:8000/v1" \
  --api-key "local-key" \
  --model "qwen3-coder-next" \
  --max-tokens 64000
```

---

## 📖 文档

*   **[架构详解 (Architecture)](docs/ARCHITECTURE.md)**: 深入了解 Swarmbot 的核心循环、三层记忆系统和多 Agent 编排机制。
*   **[Loop 优化方案](docs/LOOP_PROFILE_PLAN.md)**: 分析优先、工具门控、Skill 门控和 profile 切换策略。
*   **[记忆与循环机制详解](docs/memory_and_loop_architecture.md)**: 历史设计脉络、记忆读写和工具编排机制。

---

## 📄 License

MIT License

---

## 👥 Contributors

- [JoonSumisu](https://github.com/JoonSumisu) - Original Author
- [opencode](https://opencode.ai) - v2.0.2 Architecture Enhancement
