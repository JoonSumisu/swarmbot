# 开发文档（适配 Swarmbot v0.3.1）

## 目标
Swarmbot 的长期目标：
* 只存在一个配置文件：`~/.swarmbot/config.json`
* 网关/通道能力内置（不再依赖 pip 安装 nanobot）

## 依赖安装
```bash
chmod +x scripts/install_deps.sh
./scripts/install_deps.sh
```

## 运行方式
### 本地交互运行
```bash
swarmbot run
```

### 启动网关（当前版本已禁用）

当前版本已移除对 nanobot Gateway 的运行时依赖，CLI 中的 `swarmbot gateway` 命令会直接提示“功能已禁用”。如果需要 IM 通道接入生产环境，推荐通过企业内部现有网关或反向代理实现，只保留 Swarmbot 作为“任务大脑”。

## 配置说明
唯一配置文件：`~/.swarmbot/config.json`

### Provider（模型）
通过 CLI 写入：
```bash
swarmbot provider add --base-url "http://127.0.0.1:8000/v1" --api-key "YOUR_API_KEY" --model "your-model-name" --max-tokens 8192
```

也可以手动编辑 `config.json`：
```json
{
  "provider": {
    "name": "custom",
    "base_url": "http://127.0.0.1:8000/v1",
    "api_key": "YOUR_API_KEY",
    "model": "your-model-name",
    "max_tokens": 8192,
    "temperature": 0.6
  }
}
```

### Channels（通道）
通道配置位于 `channels` 字段下（示例以飞书为例）：
```json
{
  "channels": {
    "feishu": {
      "enabled": true,
      "appId": "YOUR_APP_ID",
      "appSecret": "YOUR_APP_SECRET",
      "allowFrom": []
    }
  }
}
```

## 守护进程与定时任务

### Swarmbot Daemon（守护进程）

Swarmbot 提供一个内置守护进程，用于统一管理：

- gateway 子进程（含飞书等通道）
- Overthinking 循环（可选）
- 配置与 Boot 的变更备份
- LLM 与 Channel 的健康检查

相关配置位于 `~/.swarmbot/config.json` 的 `daemon` 段，例如：

```jsonc
"daemon": {
  "backup_interval_seconds": 60,
  "health_check_interval_seconds": 3600,
  "manage_gateway": true,
  "manage_overthinking": false
}
```

启动与关闭：

```bash
swarmbot daemon start
swarmbot daemon shutdown
```

守护进程会将状态写入 `~/.swarmbot/daemon_state.json`，开发时可以通过 `file_read` 工具或直接打开该文件查看。

### 定时任务（系统级 cron 推荐）

当前版本中，Swarmbot 内置的 `swarmbot cron` 管理接口已禁用，仅保留配置结构用于兼容旧版本。开发与生产环境中推荐使用 **系统级 cron / 统一任务平台** 来调度以下命令：

```bash
# 每 60 分钟执行一次 HEARTBEAT（轻量自检）
swarmbot heartbeat trigger

# 每 60 分钟执行一次 Feishu 连通性检测（可选）
cd /root/swarmbot && python test_feishu_send.py
```

上述模板与 README 中保持一致：Heartbeat 负责内部自检，Feishu Connectivity Test 用于通道联通性探测，建议最多每小时一次。

### Heartbeat 循环

Heartbeat 服务基于 `~/.swarmbot/workspace/HEARTBEAT.md` 文件工作，推荐模板见 README 中的「推荐运行模板」章节。

开发过程中常用命令：

```bash
# 查看 HEARTBEAT 状态（文件是否存在、是否有待办）
swarmbot heartbeat status

# 手动触发一次 HEARTBEAT（会创建临时 AgentLoop 执行）
swarmbot heartbeat trigger
```

## 记忆与上下文优化（v0.3 系列）

当前版本的 Swarmbot 在三层记忆（LocalMD / Whiteboard / QMD）之上，增加了更精细的上下文控制能力，用于解决“大模型易超长 / 无关历史过多”的问题：

- **Whiteboard 摘要生成**：`QMDMemoryStore` 会根据当前问题自动构建任务白板摘要，只保留任务规格、执行计划、近期子任务与关键中间结果。
- **QMD 相关性检索**：长程记忆检索结果会按关键词匹配度排序，只注入与当前问题高度相关的少量文档片段。
- **本地历史裁剪**：仅保留最近若干条会话作为上下文，长文本按配置进行截断。
- **context_policy 动态控制**：Whiteboard 支持 `context_policy` 字段，LLM 可以通过 `context_policy_update` 工具在推理前动态设置：
  - `max_whiteboard_chars`
  - `max_history_items`
  - `max_history_chars_per_item`
  - `max_qmd_chars`
  - `max_qmd_docs`

推荐实践：
 
- 复杂运维问诊 / 代码审查场景：适当提高 `max_whiteboard_chars`、`max_history_items`，保证诊断信息足够完整；
- 简单问答 / 小任务：降低上述参数，把更多 token 留给当前问题的推理与输出。
 
## 外部技能市场集成（EvoMap）
 
v0.3.1 在工具层面增加了对外部技能市场的原生支持，方便在运行时按需发现和缓存新能力：
 
- **EvoMap**  
  - 通过 `skill_fetch` 工具从类似 `https://evomap.ai/skill.md` 的地址抓取远程 `SKILL.md`；  
  - 抓取结果会写入 `~/.swarmbot/workspace/skills/<name>/SKILL.md`，后续同样使用 `skill_summary` / `skill_load` 访问；  
  - 若抓取失败（无外网等），上层 Agent 应优雅退化为仅做规划或使用本地备份。
 
这些工具均由 `tools/adapter.py` 暴露为 OpenAI Tool，Swarm 内部的 Planner / Researcher / Coder 可以在需要时主动调用，无需人工干预。
 
## Overthinking 记忆分类（Facts / Experiences / Theories）
 
Overthinking 循环在 v0.3.1 中对记忆写入方式作了结构化约束，便于后续检索与复用：
 
- 短期日志整理：`_step_consolidate_short_term` 会将当日 LocalMD 中的聊天片段总结为三个部分：  
  - Facts：客观事实与配置信息；  
  - Experiences：具体行动及其结果；  
  - Theories：从经验中抽象出的原则与假设。  
  汇总内容写入 `qmd/core_memory/`，作为长期事实与经验库。  
- 反思与拓展：`_step_expand_thoughts` 使用同样的三分法生成 `Reflection` 文档，写入 `qmd/thoughts/`，更偏向理论与规划层。  
- 与 QMD 检索联动：在线推理时，QMD 检索可以针对 Facts / Experiences / Theories 选择性注入，避免将过于主观的反思混入事实上下文。
 
## 测试
运行全部单测：
```bash
python -m unittest discover -s tests -p "test*.py" -v
```

## 常见问题：Litellm 400 - Failed to process regex

- **问题现象**  
  返回 `400`，错误内容包含 `{'error': 'Failed to process regex'}`，多出现在输入或上下文中包含大量 `(`、`)`、反引号、反斜杠等特殊字符时。

- **系统内置处理**  
  Swarmbot 在调用 Litellm 失败且错误信息包含 `failed to process regex` 时，会自动对请求消息做一次清洗：  
  - 递归遍历 `messages`；  
  - 对所有字符串字段执行正则替换，去掉 `(`、`)`、`` ` ``、`\` 等字符；  
  - 使用清洗后的 `messages` 立即重试一次调用。  
  这一逻辑内置在 `swarmbot/llm_client.py` 中，通常可以消除大部分由正则解析器引起的 400 错误。

- **推荐人工排错流程**（当仍持续出现类似错误时）  
  1. **统一输入格式**：尽量使用纯自然语言或标准 JSON，避免在同一条消息中混用大量正则符号。  
  2. **预处理清洗**：在上游业务里对原始输入做一次清洗，例如：  
     ```python
     cleaned = re.sub(r'[()\\/`]', '', raw_text)
     ```  
  3. **拆分长句**：将一长串复合指令拆成若干条清晰的 action item，分别交给 Swarm。  
  4. **写入 Whiteboard 供 Planner 使用**：  
     - 写入预处理后的问题：  
       ```json
       {"key": "prepared_input", "value": "好，找出问题，给我一个问题的优化方法"}
       ```  
     - 写入行动计划：  
       ```json
       {
         "key": "action_items",
         "value": ["使用纯文本/标准 JSON", "拆分长句", "转义特殊符号"]
       }
       ```  
     - 之后以 `prepared_input` 为主问题重新跑 Planner，使后续 Agent 可以直接复用 Whiteboard 中的结构化信息。
