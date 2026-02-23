# 开发文档

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

### 启动网关（飞书/Slack/Telegram 等）
```bash
swarmbot gateway
tail -f ~/.swarmbot/logs/gateway.log
```

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

### Cron 定时任务

Swarmbot 直接集成了 nanobot 的 `CronService`，并提供统一 CLI：

```bash
# 列出所有定时任务
swarmbot cron list

# 添加一个每 60 分钟执行一次的任务
swarmbot cron add \
  --name "heartbeat-every-60m" \
  --message "请执行一次 HEARTBEAT，并根据 HEARTBEAT.md 更新必要记录，然后回复 HEARTBEAT_OK 或简要总结。" \
  --every-minutes 60

# 禁用/删除任务
swarmbot cron disable --id <job_id>
swarmbot cron remove --id <job_id>
```

### Heartbeat 循环

Heartbeat 服务基于 `~/.swarmbot/workspace/HEARTBEAT.md` 文件工作，推荐模板见 README 中的「推荐运行模板」章节。

开发过程中常用命令：

```bash
# 查看 HEARTBEAT 状态（文件是否存在、是否有待办）
swarmbot heartbeat status

# 手动触发一次 HEARTBEAT（会创建临时 AgentLoop 执行）
swarmbot heartbeat trigger
```

## 内置 nanobot（架构升级 v0.2.8）
Swarmbot 现已彻底集成 nanobot 源码（vendored），不再依赖外部 pip 包。

### Gateway 架构
1.  **Wrapper**: `gateway_wrapper.py` 作为入口，负责 Monkeypatch `AgentLoop` 和 `ChannelManager`。
2.  **Config Sync**: `swarmbot.nanobot.config.loader` 负责实时将 `SwarmbotConfig` 映射为内存中的 nanobot 配置，不再生成临时文件。
3.  **Hook 机制**:
    *   **External Patch**: 在 Gateway 启动前拦截 `AgentLoop._process_message`。
    *   **Native Hook**: 在 `nanobot/agent/loop.py` 内部硬编码检查 `SWARM_MANAGER`，作为兜底防线。
    *   **Message Fix**: 修复了 `InboundMessage` 缺失 `message_id` 的问题，确保消息回执可靠。

该设计确保了 Swarmbot 拥有对消息流的完全控制权，同时复用了成熟的通道适配器。

## 测试
运行全部单测：
```bash
python -m unittest discover -s tests -p "test*.py" -v
```
