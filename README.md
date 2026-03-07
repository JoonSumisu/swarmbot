# Swarmbot

[中文](README.md) | [English](README_EN.md)

**Swarmbot (v0.5.5)** 是一个基于 **[swarms](https://github.com/kyegomez/swarms)** 和 **nanobot** 架构的多 Agent 集群智能系统，专为本地部署和私有 LLM 接口设计。

它集成了 **QMD 四层记忆系统**（白板、热记忆、温记忆、冷记忆）与 **三环自进化架构**（推理、反思、行动），支持通过 **Feishu (飞书/Lark)** 等 IM 通道进行交互。

> **核心理念**: "All-in-One" —— 将网关、记忆、工具链和多智能体编排融合在一个轻量级进程中。

---

## 📁 目录分层

- 开发/实验目录说明见 [WORKSPACE_LAYOUT.md](WORKSPACE_LAYOUT.md)

## 🌟 版本 v0.5.5 更新亮点

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

## 🚀 快速开始

### 1. 安装

Swarmbot 支持 Python 3.10+。

如果你在 macOS（尤其是 Homebrew Python）上执行 `pip install .` 遇到：

```
This environment is externally managed
```

这是 Python 对“系统级 Python 环境”的保护机制（常见于 Homebrew / OS 发行版），为了避免把依赖装进系统 Python 导致环境损坏。解决方式是：**永远安装到虚拟环境（venv）**。

本项目内置了跨平台安装脚本，默认会优先做“**直接安装**”（无需手动激活 venv）：

- 优先使用 `pipx` 安装为全局可执行命令 `swarmbot`
- 若无 `pipx`，尝试 `pip --user` 安装
- 若都失败，再回退到 `.venv/` 安装

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
  --model "qwen3-coder-30b-instruct" \
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

## 📖 文档

*   **[架构详解 (Architecture)](docs/ARCHITECTURE.md)**: 深入了解 Swarmbot 的核心循环、三层记忆系统和多 Agent 编排机制。

---

## 📄 License

MIT License

All code power by trae & tomoko
