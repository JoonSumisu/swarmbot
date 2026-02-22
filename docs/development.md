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

## 内置 nanobot（配置桥接）
Swarmbot 内置 nanobot 实现用于复用网关/通道能力，并在运行时将 SwarmbotConfig 映射为 nanobot 的 Config。
该映射逻辑位于 [loader.py](file:///root/swarmbot/swarmbot/nanobot/config/loader.py)。

## 测试
运行全部单测：
```bash
python -m unittest discover -s tests -p "test*.py" -v
```

