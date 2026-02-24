from swarmbot.config_manager import load_config, save_config, ProviderConfig, ChannelConfig

print("Loading config...")
cfg = load_config()

# Update primary provider
print("Updating provider settings...")
if not cfg.providers:
    cfg.providers = [ProviderConfig(name="primary")]

primary = cfg.providers[0]
primary.name = "primary"
primary.base_url = "http://100.110.110.250:8888/v1"
primary.api_key = "dummy-key" 
primary.model = "qwen3-coder-30b-a3b-instruct"
primary.max_tokens = 4096

# Ensure Swarm settings
print("Updating swarm settings...")
cfg.swarm.max_agents = 4
cfg.swarm.roles = [] 
cfg.swarm.auto_builder = True

# Ensure Feishu channel entry exists (mock if missing)
if "feishu" not in cfg.channels:
    print("Adding mock feishu channel config...")
    cfg.channels["feishu"] = ChannelConfig(
        enabled=True, 
        app_id="test_id", 
        app_secret="test_secret",
        verification_token="test_token",
        encrypt_key="test_key"
    )
else:
    print("Feishu channel config exists, keeping it.")

save_config(cfg)
print("Config updated successfully.")
