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

## 内置 nanobot（架构升级 v0.2.6）
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

